//go:build treesitter

package main

import (
	"bytes"
	"fmt"
	"path/filepath"
	"slices"

	ts "github.com/tree-sitter/go-tree-sitter"
	goGrammar "github.com/tree-sitter/tree-sitter-go/bindings/go"
	htmlGrammar "github.com/tree-sitter/tree-sitter-html/bindings/go"
	jsGrammar "github.com/tree-sitter/tree-sitter-javascript/bindings/go"
	phpGrammar "github.com/tree-sitter/tree-sitter-php/bindings/go"
	pythonGrammar "github.com/tree-sitter/tree-sitter-python/bindings/go"
	rustGrammar "github.com/tree-sitter/tree-sitter-rust/bindings/go"
	typescriptGrammar "github.com/tree-sitter/tree-sitter-typescript/bindings/go"
)

type grammarSpec struct {
	extensions []string
	language   *ts.Language
	kinds      []string
}

func grammars() []grammarSpec {
	return []grammarSpec{
		{[]string{".py", ".pyi"}, ts.NewLanguage(pythonGrammar.Language()), []string{"string", "concatenated_string"}},
		{[]string{".php"}, ts.NewLanguage(phpGrammar.LanguagePHP()), []string{"string", "encapsed_string", "heredoc", "nowdoc"}},
		{[]string{".go"}, ts.NewLanguage(goGrammar.Language()), []string{"interpreted_string_literal", "raw_string_literal"}},
		{[]string{".rs"}, ts.NewLanguage(rustGrammar.Language()), []string{"string_literal", "raw_string_literal"}},
		{[]string{".js", ".mjs", ".cjs", ".jsx"}, ts.NewLanguage(jsGrammar.Language()), []string{"string", "template_string"}},
		{[]string{".ts"}, ts.NewLanguage(typescriptGrammar.LanguageTypescript()), []string{"string", "template_string"}},
		{[]string{".tsx"}, ts.NewLanguage(typescriptGrammar.LanguageTSX()), []string{"string", "template_string"}},
		{[]string{".html", ".htm"}, ts.NewLanguage(htmlGrammar.Language()), []string{"quoted_attribute_value", "attribute_value"}},
	}
}

func collectStrings(tree *ts.Tree, kinds []string) []span {
	var candidates []span
	pending := []*ts.Node{tree.RootNode()}
	for len(pending) > 0 {
		node := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		if slices.Contains(kinds, node.Kind()) {
			candidates = append(candidates, span{int(node.StartByte()), int(node.EndByte())})
		}
		for i := uint(0); i < node.ChildCount(); i++ {
			pending = append(pending, node.Child(i))
		}
	}
	return candidates
}

func parseCorpus(root string) ([][]span, error) {
	parser := ts.NewParser()
	defer parser.Close()
	byExtension := map[string]grammarSpec{}
	for _, grammar := range grammars() {
		// Verify every required binding up front rather than silently skipping it.
		if err := parser.SetLanguage(grammar.language); err != nil {
			return nil, fmt.Errorf("%w: %v", errBindingUnavailable, err)
		}
		for _, extension := range grammar.extensions {
			byExtension[extension] = grammar
		}
	}
	paths, err := gitOutput(root, "ls-tree", "-r", "--name-only", "-z", baseCommit)
	if err != nil {
		return nil, err
	}
	var batches [][]span
	for _, rawPath := range bytes.Split(paths, []byte{0}) {
		if len(rawPath) == 0 {
			continue
		}
		path := string(rawPath)
		grammar, supported := byExtension[filepath.Ext(path)]
		if !supported {
			continue
		}
		source, err := gitOutput(root, "show", baseCommit+":"+path)
		if err != nil {
			return nil, err
		}
		if err := parser.SetLanguage(grammar.language); err != nil {
			return nil, fmt.Errorf("%w: %v", errBindingUnavailable, err)
		}
		tree := parser.Parse(source, nil)
		if tree == nil {
			return nil, fmt.Errorf("tree-sitter returned no tree for %s", path)
		}
		// Include recovery trees and files with no string nodes; do not discard them.
		candidates := collectStrings(tree, grammar.kinds)
		tree.Close()
		batches = append(batches, prepare(candidates))
	}
	if len(batches) == 0 {
		return nil, fmt.Errorf("no supported tracked files at %s", baseCommit)
	}
	return batches, nil
}

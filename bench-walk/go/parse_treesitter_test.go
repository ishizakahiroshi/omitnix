//go:build treesitter

package main

import (
	"strings"
	"testing"
)

func TestFixedCorpus(t *testing.T) {
	root, err := gitOutput(".", "rev-parse", "--show-toplevel")
	if err != nil {
		t.Fatal(err)
	}
	batches, err := parseCorpus(strings.TrimSpace(string(root)))
	if err != nil {
		t.Fatal(err)
	}
	total := counts{}
	candidates := 0
	for _, batch := range batches {
		candidates += len(batch)
		result := walk(batch)
		total.comparisons += result.comparisons
		total.remaining += result.remaining
	}
	if len(batches) != 110 || candidates != 4104 || total != (counts{334231, 3881}) {
		t.Fatalf("unexpected corpus: files=%d, candidates=%d, counters=%+v", len(batches), candidates, total)
	}
}

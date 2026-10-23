//go:build !treesitter

// Report unavailable native bindings for the standalone Go benchmark.
package main

func parseCorpus(_ string) ([][]span, error) {
	return nil, errBindingUnavailable
}

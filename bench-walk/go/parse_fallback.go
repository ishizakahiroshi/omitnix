//go:build !treesitter

package main

func parseCorpus(_ string) ([][]span, error) {
	return nil, errBindingUnavailable
}

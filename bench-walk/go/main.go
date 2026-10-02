// Standalone containment-loop benchmark. No omitnix product code is invoked.
package main

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"sort"
	"strings"
	"time"
)

const baseCommit = "374e5bb337ec0f7e0f4a47d97c70083a306eb1ed"

var errBindingUnavailable = errors.New("tree-sitter binding unavailable")

type span struct{ start, end int }
type counts struct{ comparisons, remaining int }

func walk(candidates []span) counts {
	accepted := make([]span, 0)
	comparisons := 0
	for _, candidate := range candidates {
		contained := false
		for _, outer := range accepted {
			comparisons++
			if outer.start <= candidate.start && candidate.end <= outer.end {
				contained = true
				break
			}
		}
		if !contained {
			accepted = append(accepted, candidate)
		}
	}
	return counts{comparisons, len(accepted)}
}

func prepare(candidates []span) []span {
	sort.Slice(candidates, func(i, j int) bool {
		if candidates[i].start != candidates[j].start {
			return candidates[i].start < candidates[j].start
		}
		return candidates[i].end > candidates[j].end
	})
	return candidates
}

func requireCounts(actual, expected counts) {
	if actual != expected {
		panic(fmt.Sprintf("counter mismatch: got %+v, want %+v", actual, expected))
	}
}

func measure(batches [][]span, expected *counts) (counts, time.Duration) {
	warm := counts{}
	for _, candidates := range batches {
		result := walk(candidates)
		warm.comparisons += result.comparisons
		warm.remaining += result.remaining
	}
	if expected != nil {
		requireCounts(warm, *expected)
	}
	var minimum time.Duration
	for run := 0; run < 5; run++ {
		total := counts{}
		var elapsed time.Duration
		for _, candidates := range batches {
			started := time.Now()
			result := walk(candidates)
			elapsed += time.Since(started)
			total.comparisons += result.comparisons
			total.remaining += result.remaining
		}
		requireCounts(total, warm)
		if run == 0 || elapsed < minimum {
			minimum = elapsed
		}
	}
	return warm, minimum
}

type syntheticCase struct {
	label          string
	candidates     []span
	candidateCount int
	expected       counts
}

func syntheticCases() []syntheticCase {
	var small, nested, medium []span
	for i := 0; i < 825; i++ {
		small = append(small, span{i, i + 1})
	}
	for i := 0; i < 200; i++ {
		nested = append(nested, span{i * 1000, i*1000 + 500})
		for j := 0; j < 20; j++ {
			nested = append(nested, span{i*1000 + 1 + j, i*1000 + 2 + j})
		}
	}
	for i := 0; i < 4000; i++ {
		medium = append(medium, span{i, i + 1})
	}
	return []syntheticCase{
		{"S", prepare(small), 825, counts{339900, 825}},
		{"N", prepare(nested), 4200, counts{421900, 200}},
		{"M", prepare(medium), 4000, counts{7998000, 4000}},
	}
}

func gitOutput(root string, arguments ...string) ([]byte, error) {
	command := exec.Command("git", arguments...)
	command.Dir = root
	command.Stderr = os.Stderr
	return command.Output()
}

func main() {
	for _, dataset := range syntheticCases() {
		if len(dataset.candidates) != dataset.candidateCount {
			panic("synthetic candidate count mismatch")
		}
		result, elapsed := measure([][]span{dataset.candidates}, &dataset.expected)
		fmt.Printf("walk go %s %d %d %d %.1f\n", dataset.label, len(dataset.candidates),
			result.comparisons, result.remaining, float64(elapsed)/float64(time.Millisecond))
	}
	rootBytes, err := gitOutput(".", "rev-parse", "--show-toplevel")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	batches, err := parseCorpus(strings.TrimSpace(string(rootBytes)))
	if errors.Is(err, errBindingUnavailable) {
		fmt.Fprintln(os.Stderr, err)
		fmt.Println("parse go BINDING_FAILED")
		return
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	candidateCount := 0
	for _, batch := range batches {
		candidateCount += len(batch)
	}
	result, elapsed := measure(batches, nil)
	fmt.Printf("parse go ok %d %d %d %d %.1f\n", len(batches), candidateCount,
		result.comparisons, result.remaining, float64(elapsed)/float64(time.Millisecond))
}

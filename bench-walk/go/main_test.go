// Check the standalone Go range-walk counters and measurement contract.
package main

import (
	"reflect"
	"testing"
)

func TestSyntheticCounters(t *testing.T) {
	for _, dataset := range syntheticCases() {
		t.Run(dataset.label, func(t *testing.T) {
			if len(dataset.candidates) != dataset.candidateCount {
				t.Fatalf("candidate count: %d", len(dataset.candidates))
			}
			if actual := walk(dataset.candidates); actual != dataset.expected {
				t.Fatalf("got %+v, want %+v", actual, dataset.expected)
			}
		})
	}
}

func TestFrontFirstAndEarlyBreak(t *testing.T) {
	// The final candidate is contained in the FIRST accepted range, requiring
	// one comparison; scanning from the back would incorrectly total six.
	actual := walk([]span{{0, 10}, {20, 30}, {40, 50}, {1, 2}})
	if actual != (counts{4, 3}) {
		t.Fatalf("front-first counters: %+v", actual)
	}
}

func TestSortOrder(t *testing.T) {
	actual := prepare([]span{{3, 4}, {1, 2}, {1, 8}})
	expected := []span{{1, 8}, {1, 2}, {3, 4}}
	if !reflect.DeepEqual(actual, expected) {
		t.Fatalf("got %+v, want %+v", actual, expected)
	}
}

func TestEmpty(t *testing.T) {
	if actual := walk(nil); actual != (counts{}) {
		t.Fatalf("empty counters: %+v", actual)
	}
}

func TestEqualBounds(t *testing.T) {
	if actual := walk([]span{{0, 1}, {0, 1}}); actual != (counts{1, 1}) {
		t.Fatalf("equality counters: %+v", actual)
	}
}

func TestPerFileStateIsolation(t *testing.T) {
	expected := counts{0, 2}
	actual, elapsed := measure([][]span{{{0, 1}}, {{0, 1}}}, &expected)
	if actual != expected || elapsed < 0 {
		t.Fatalf("got %+v, elapsed %s", actual, elapsed)
	}
}

func TestCounterAssertion(t *testing.T) {
	defer func() {
		if recover() == nil {
			t.Fatal("expected counter mismatch to panic")
		}
	}()
	expected := counts{1, 1}
	measure([][]span{{{0, 1}}}, &expected)
}

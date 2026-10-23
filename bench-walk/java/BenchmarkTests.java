import java.util.AbstractList;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

/** Standard-library-only checks; no product report generation. */
public final class BenchmarkTests {
    private static final class CountingList extends AbstractList<Benchmark.Span> {
        int iterations;
        @Override public Benchmark.Span get(int index) {
            if (index != 0) throw new IndexOutOfBoundsException(index);
            return new Benchmark.Span(0, 1);
        }
        @Override public int size() { return 1; }
        @Override public Iterator<Benchmark.Span> iterator() {
            iterations++;
            return super.iterator();
        }
    }

    public static void main(String[] args) {
        for (Benchmark.Dataset dataset : Benchmark.datasets()) {
            Benchmark.require(dataset.candidates().size() == dataset.size(), "dataset size");
            Benchmark.require(Benchmark.walk(dataset.candidates()).equals(dataset.expected()), "dataset counters");
        }
        Benchmark.require(Benchmark.walk(List.of(new Benchmark.Span(0, 10), new Benchmark.Span(20, 30),
                new Benchmark.Span(40, 50), new Benchmark.Span(1, 2)))
                .equals(new Benchmark.Counts(4, 3)), "front-first early break");
        Benchmark.require(Benchmark.prepare(new ArrayList<>(List.of(new Benchmark.Span(3, 4),
                new Benchmark.Span(1, 2), new Benchmark.Span(1, 8)))).equals(List.of(
                new Benchmark.Span(1, 8), new Benchmark.Span(1, 2), new Benchmark.Span(3, 4))), "sort order");
        Benchmark.require(Benchmark.walk(List.of()).equals(new Benchmark.Counts(0, 0)), "empty input");
        Benchmark.require(Benchmark.walk(List.of(new Benchmark.Span(0, 1), new Benchmark.Span(0, 1)))
                .equals(new Benchmark.Counts(1, 1)), "equal bounds");
        CountingList counting = new CountingList();
        Benchmark.measure(List.of(counting), new Benchmark.Counts(0, 1));
        Benchmark.require(counting.iterations == 6, "one warm-up plus five measured runs");
        Benchmark.measure(List.of(List.of(new Benchmark.Span(0, 1)), List.of(new Benchmark.Span(0, 1))),
                new Benchmark.Counts(0, 2));
        boolean rejected = false;
        try {
            Benchmark.measure(List.of(List.of(new Benchmark.Span(0, 1))), new Benchmark.Counts(1, 1));
        } catch (AssertionError expected) {
            rejected = true;
        }
        Benchmark.require(rejected, "wrong counters must fail");
        System.err.println("10 standalone checks passed; native parsing is checked separately by the benchmark.");
    }
}

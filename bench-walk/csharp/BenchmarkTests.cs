using System;
using System.Collections;
using System.Collections.Generic;
using System.Runtime.InteropServices;

internal static class BenchmarkTests
{
    private sealed class CountingInput : IReadOnlyList<Interval>
    {
        public int Reads { get; private set; }
        public int Count => 1;
        public Interval this[int index]
        {
            get { Reads++; return new Interval(0, 1); }
        }
        public IEnumerator<Interval> GetEnumerator() { yield return this[0]; }
        IEnumerator IEnumerable.GetEnumerator() => GetEnumerator();
    }

    internal static void Run()
    {
        int checks = 0;
        foreach (string name in new[] { "S", "N", "M" })
        {
            Benchmark.Require(Benchmark.Walk(Benchmark.Generate(name)), Benchmark.Expected(name));
            checks++;
        }
        // The third range is contained by the first accepted item: front-first must use one comparison.
        Benchmark.Require(Benchmark.Walk(new[] { new Interval(0, 10), new Interval(20, 30),
            new Interval(1, 2) }), new Counts(3, 2, 2));
        checks++;
        var sorted = new List<Interval> { new(1, 2), new(0, 2), new(0, 10) };
        Benchmark.Sort(sorted);
        if (sorted[0] != new Interval(0, 10) || sorted[1] != new Interval(0, 2))
            throw new InvalidOperationException("Sort order");
        checks++;
        Benchmark.Require(Benchmark.Walk(Array.Empty<Interval>()), new Counts(0, 0, 0));
        checks++;
        Benchmark.Require(Benchmark.Walk(new[] { new Interval(0, 1), new Interval(0, 1) }),
            new Counts(2, 1, 1));
        checks++;
        var perFile = new List<IReadOnlyList<Interval>> {
            new[] { new Interval(0, 10) }, new[] { new Interval(1, 2) }
        };
        Benchmark.Require(Benchmark.Aggregate(perFile, false).Counts, new Counts(2, 0, 2));
        checks++;
        var observed = new CountingInput();
        Benchmark.Measure(new List<IReadOnlyList<Interval>> { observed }, new Counts(1, 0, 1));
        if (observed.Reads != 6)
            throw new InvalidOperationException("Expected one warm-up and five measured walks");
        checks++;
        bool rejected = false;
        try { Benchmark.Require(new Counts(1, 2, 3), new Counts(4, 5, 6)); }
        catch (InvalidOperationException) { rejected = true; }
        if (!rejected) throw new InvalidOperationException("Counter assertion did not fail");
        checks++;
        if (Marshal.SizeOf<TreeSitterInputs.Node>() != 16 + 2 * IntPtr.Size)
            throw new InvalidOperationException("TSNode ABI layout mismatch");
        checks++;
        Console.Error.WriteLine($"{checks} standalone checks passed");
    }
}

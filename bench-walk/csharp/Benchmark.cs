using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;

internal readonly record struct Interval(int Start, int End);
internal readonly record struct Counts(long Candidates, long Comparisons, long Remaining);
internal readonly record struct Measurement(Counts Counts, double Milliseconds);

internal static class Benchmark
{
    internal const string BaseCommit = "374e5bb337ec0f7e0f4a47d97c70083a306eb1ed";

    internal static Counts Walk(IReadOnlyList<Interval> ranges)
    {
        var accepted = new List<Interval>();
        long comparisons = 0;
        for (int i = 0; i < ranges.Count; i++)
        {
            Interval current = ranges[i];
            bool contained = false;
            // Insertion order, from the FRONT; count one whole predicate.
            foreach (Interval outer in accepted)
            {
                comparisons++;
                if (outer.Start <= current.Start && current.End <= outer.End)
                {
                    contained = true;
                    break;
                }
            }
            if (!contained)
                accepted.Add(current);
        }
        return new Counts(ranges.Count, comparisons, accepted.Count);
    }

    internal static void Sort(List<Interval> ranges) => ranges.Sort((a, b) =>
    {
        int byStart = a.Start.CompareTo(b.Start);
        return byStart != 0 ? byStart : b.End.CompareTo(a.End);
    });

    internal static List<Interval> Generate(string name)
    {
        var ranges = new List<Interval>();
        if (name == "S" || name == "M")
        {
            int size = name == "S" ? 825 : 4000;
            for (int i = 0; i < size; i++)
                ranges.Add(new Interval(i, i + 1));
        }
        else if (name == "N")
        {
            for (int i = 0; i < 200; i++)
            {
                ranges.Add(new Interval(i * 1000, i * 1000 + 500));
                for (int j = 0; j < 20; j++)
                    ranges.Add(new Interval(i * 1000 + 1 + j, i * 1000 + 2 + j));
            }
        }
        else
            throw new ArgumentException("Unknown synthetic input", nameof(name));
        Sort(ranges);
        return ranges;
    }

    internal static Counts Expected(string name) => name switch
    {
        "S" => new Counts(825, 339900, 825),
        "N" => new Counts(4200, 421900, 200),
        "M" => new Counts(4000, 7998000, 4000),
        _ => throw new ArgumentException("Unknown synthetic input", nameof(name))
    };

    internal static void Require(Counts actual, Counts expected)
    {
        if (actual != expected)
            throw new InvalidOperationException($"Counter mismatch: {actual} != {expected}");
    }

    internal static Measurement Aggregate(IReadOnlyList<IReadOnlyList<Interval>> files, bool timed)
    {
        long candidates = 0, comparisons = 0, remaining = 0, elapsed = 0;
        foreach (IReadOnlyList<Interval> ranges in files)
        {
            long start = timed ? Stopwatch.GetTimestamp() : 0;
            Counts counts = Walk(ranges);
            if (timed)
                elapsed += Stopwatch.GetTimestamp() - start;
            candidates += counts.Candidates;
            comparisons += counts.Comparisons;
            remaining += counts.Remaining;
        }
        return new Measurement(new Counts(candidates, comparisons, remaining),
            elapsed * 1000.0 / Stopwatch.Frequency);
    }

    internal static Measurement Measure(IReadOnlyList<IReadOnlyList<Interval>> files, Counts? expected)
    {
        Counts warm = Aggregate(files, false).Counts; // Exactly one warm-up.
        Require(warm, expected ?? warm);
        double minimum = double.PositiveInfinity;
        for (int run = 0; run < 5; run++)
        {
            Measurement measured = Aggregate(files, true);
            Require(measured.Counts, warm); // Outside the timed walk.
            minimum = Math.Min(minimum, measured.Milliseconds);
        }
        return new Measurement(warm, minimum);
    }

    internal static string Format(Measurement measured) =>
        $"{measured.Counts.Candidates} {measured.Counts.Comparisons} {measured.Counts.Remaining} " +
        measured.Milliseconds.ToString("F1", CultureInfo.InvariantCulture);

    private static int Main(string[] args)
    {
        try
        {
            if (args.Length == 1 && args[0] == "--test")
            {
                BenchmarkTests.Run();
                return 0;
            }
            if (args.Length != 0)
                throw new ArgumentException("Usage: Benchmark [--test]");
            foreach (string name in new[] { "S", "N", "M" })
            {
                List<Interval> ranges = Generate(name); // Generation and sort outside timing.
                var files = new List<IReadOnlyList<Interval>> { ranges };
                Console.WriteLine($"walk csharp {name} {Format(Measure(files, Expected(name)))}");
            }

            List<IReadOnlyList<Interval>> parsed;
            try
            {
                parsed = TreeSitterInputs.Prepare(); // Git, parse, traversal, sort outside timing.
            }
            catch (Exception error) when (error is DllNotFoundException or EntryPointNotFoundException
                or BadImageFormatException or BindingUnavailableException)
            {
                Console.Error.WriteLine($"Tree-sitter binding preparation failed: {error.Message}");
                Console.WriteLine("parse csharp BINDING_FAILED");
                return 0;
            }
            Console.WriteLine($"parse csharp ok {parsed.Count} {Format(Measure(parsed, null))}");
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error);
            return 1;
        }
    }
}

import java.io.IOException;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

/** Standalone benchmark; never imports or invokes omitnix. */
public final class Benchmark {
    static final String BASE = "374e5bb337ec0f7e0f4a47d97c70083a306eb1ed";
    record Span(int start, int end) {}
    record Counts(long comparisons, int remaining) {}
    record Measurement(Counts counts, double milliseconds) {}
    record Dataset(String name, List<Span> candidates, int size, Counts expected) {}

    static Counts walk(List<Span> candidates) {
        List<Span> accepted = new ArrayList<>();
        long comparisons = 0;
        for (Span candidate : candidates) {
            boolean contained = false;
            for (Span outer : accepted) {
                comparisons++;
                if (outer.start <= candidate.start && candidate.end <= outer.end) {
                    contained = true;
                    break;
                }
            }
            if (!contained) accepted.add(candidate);
        }
        return new Counts(comparisons, accepted.size());
    }

    static List<Span> prepare(List<Span> candidates) {
        candidates.sort(Comparator.comparingInt(Span::start)
                .thenComparing(Comparator.comparingInt(Span::end).reversed()));
        return candidates;
    }

    static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    static Measurement measure(List<List<Span>> batches, Counts expected) {
        long warmComparisons = 0;
        int warmRemaining = 0;
        for (List<Span> candidates : batches) {
            Counts result = walk(candidates);
            warmComparisons += result.comparisons;
            warmRemaining += result.remaining;
        }
        Counts warm = new Counts(warmComparisons, warmRemaining);
        require(expected == null || warm.equals(expected), "warm-up counters");
        long minimum = Long.MAX_VALUE;
        for (int run = 0; run < 5; run++) {
            long elapsed = 0, comparisons = 0;
            int remaining = 0;
            for (List<Span> candidates : batches) {
                long started = System.nanoTime();
                Counts result = walk(candidates);
                elapsed += System.nanoTime() - started;
                comparisons += result.comparisons;
                remaining += result.remaining;
            }
            require(new Counts(comparisons, remaining).equals(warm), "measured counters");
            minimum = Math.min(minimum, elapsed);
        }
        return new Measurement(warm, minimum / 1_000_000.0);
    }

    static List<Dataset> datasets() {
        List<Span> small = new ArrayList<>(), nested = new ArrayList<>(), medium = new ArrayList<>();
        for (int i = 0; i < 825; i++) small.add(new Span(i, i + 1));
        for (int i = 0; i < 200; i++) {
            nested.add(new Span(i * 1000, i * 1000 + 500));
            for (int j = 0; j < 20; j++) {
                nested.add(new Span(i * 1000 + 1 + j, i * 1000 + 2 + j));
            }
        }
        for (int i = 0; i < 4000; i++) medium.add(new Span(i, i + 1));
        return List.of(
                new Dataset("S", prepare(small), 825, new Counts(339900, 825)),
                new Dataset("N", prepare(nested), 4200, new Counts(421900, 200)),
                new Dataset("M", prepare(medium), 4000, new Counts(7998000, 4000)));
    }

    static String git(Path root, String... arguments) throws IOException, InterruptedException {
        List<String> command = new ArrayList<>(List.of("git"));
        command.addAll(Arrays.asList(arguments));
        Process process = new ProcessBuilder(command).directory(root.toFile())
                .redirectError(ProcessBuilder.Redirect.INHERIT).start();
        byte[] output = process.getInputStream().readAllBytes();
        if (process.waitFor() != 0) throw new IOException("Git source read failed");
        return new String(output, StandardCharsets.UTF_8);
    }

    static List<List<Span>> parseCorpus(Path root) throws Exception {
        // Reflection allows a real missing-binding result without replacing the parser.
        Class<?> parserType = Class.forName("org.treesitter.TSParser");
        Class<?> languageType = Class.forName("org.treesitter.TSLanguage");
        Class<?> treeType = Class.forName("org.treesitter.TSTree");
        Class<?> nodeType = Class.forName("org.treesitter.TSNode");
        Object language = Class.forName("org.treesitter.TreeSitterPython").getConstructor().newInstance();
        Object parser = parserType.getConstructor().newInstance();
        Method parse = parserType.getMethod("parseString", treeType, String.class);
        Method rootNode = treeType.getMethod("getRootNode");
        Method type = nodeType.getMethod("getType");
        Method start = nodeType.getMethod("getStartByte");
        Method end = nodeType.getMethod("getEndByte");
        Method childCount = nodeType.getMethod("getChildCount");
        Method child = nodeType.getMethod("getChild", int.class);
        List<List<Span>> batches = new ArrayList<>();
        try {
            boolean loaded = (Boolean) parserType.getMethod("setLanguage", languageType)
                    .invoke(parser, language);
            if (!loaded) throw new ReflectiveOperationException("tree-sitter grammar ABI mismatch");
            for (String path : git(root, "ls-tree", "-r", "--name-only", "-z", BASE).split("\0")) {
                if (!path.endsWith(".py") && !path.endsWith(".pyi")) continue;
                Object tree = parse.invoke(parser, null, git(root, "show", BASE + ":" + path));
                List<Span> candidates = new ArrayList<>();
                try {
                    ArrayDeque<Object> pending = new ArrayDeque<>();
                    pending.push(rootNode.invoke(tree));
                    while (!pending.isEmpty()) {
                        Object node = pending.pop();
                        String kind = (String) type.invoke(node);
                        if (kind.equals("string") || kind.equals("concatenated_string")) {
                            candidates.add(new Span((Integer) start.invoke(node), (Integer) end.invoke(node)));
                        }
                        for (int i = 0; i < (Integer) childCount.invoke(node); i++) {
                            pending.push(child.invoke(node, i));
                        }
                    }
                } finally {
                    treeType.getMethod("close").invoke(tree);
                }
                batches.add(prepare(candidates));
            }
        } finally {
            parserType.getMethod("close").invoke(parser);
        }
        require(!batches.isEmpty(), "no supported base-commit files");
        return batches;
    }

    public static void main(String[] args) throws Exception {
        for (Dataset dataset : datasets()) {
            require(dataset.candidates.size() == dataset.size, "synthetic candidate count");
            Measurement result = measure(List.of(dataset.candidates), dataset.expected);
            System.out.printf(Locale.ROOT, "walk java %s %d %d %d %.1f%n", dataset.name,
                    dataset.size, result.counts.comparisons, result.counts.remaining, result.milliseconds);
        }
        List<List<Span>> batches;
        try {
            Path root = Path.of(git(Path.of("."), "rev-parse", "--show-toplevel").strip());
            batches = parseCorpus(root);
        } catch (ReflectiveOperationException | LinkageError | ClassCastException exception) {
            System.err.println("tree-sitter binding preparation failed: " + exception);
            System.out.println("parse java BINDING_FAILED");
            return;
        }
        Measurement result = measure(batches, null);
        int candidates = batches.stream().mapToInt(List::size).sum();
        System.out.printf(Locale.ROOT, "parse java ok %d %d %d %d %.1f%n", batches.size(),
                candidates, result.counts.comparisons, result.counts.remaining, result.milliseconds);
    }
}

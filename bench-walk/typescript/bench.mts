import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const BASE = '374e5bb337ec0f7e0f4a47d97c70083a306eb1ed';
const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
type Range = { start: number; end: number };
type Stats = { candidates: number; comparisons: number; remaining: number };
let observable = 0;

export function sortRanges(ranges: Range[]): Range[] {
  return ranges.sort((a, b) => a.start - b.start || b.end - a.end);
}

export function walk(ranges: readonly Range[]): Stats {
  const accepted: Range[] = [];
  let comparisons = 0;
  for (const candidate of ranges) {
    let contained = false;
    // Deliberately scan from the FRONT in insertion order.
    for (const outer of accepted) {
      comparisons += 1; // One comparison for the complete containment predicate.
      if (outer.start <= candidate.start && candidate.end <= outer.end) {
        contained = true;
        break;
      }
    }
    if (!contained) accepted.push(candidate);
  }
  return { candidates: ranges.length, comparisons, remaining: accepted.length };
}

export function walkFiles(files: readonly Range[][]): Stats {
  const total: Stats = { candidates: 0, comparisons: 0, remaining: 0 };
  for (const ranges of files) {
    const result = walk(ranges);
    total.candidates += result.candidates;
    total.comparisons += result.comparisons;
    total.remaining += result.remaining;
  }
  return total;
}

export function measure(operation: () => Stats, expected?: Stats): [Stats, number] {
  const warm = operation(); // Exactly one untimed warm-up.
  if (expected) assert.deepEqual(warm, expected);
  let minimum = Number.POSITIVE_INFINITY;
  for (let i = 0; i < 5; i += 1) {
    const start = process.hrtime.bigint();
    const result = operation();
    const elapsed = Number(process.hrtime.bigint() - start) / 1_000_000;
    // Consume and validate outside timing; every call creates a fresh accepted.
    observable += result.comparisons + result.remaining;
    assert.deepEqual(result, warm);
    minimum = Math.min(minimum, elapsed);
  }
  return [warm, minimum];
}

export function disjoint(count: number): Range[] {
  return Array.from({ length: count }, (_, i) => ({ start: i, end: i + 1 }));
}

export function nested(): Range[] {
  const result: Range[] = [];
  for (let i = 0; i < 200; i += 1) {
    const start = i * 1000;
    result.push({ start, end: start + 500 });
    for (let j = 0; j < 20; j += 1) {
      result.push({ start: start + 1 + j, end: start + 2 + j });
    }
  }
  return result;
}

function git(args: string[]): Buffer {
  return execFileSync('git', args, { cwd: ROOT, maxBuffer: 32 * 1024 * 1024 });
}

function extractStrings(tree: any, source: string): Range[] {
  const ranges: Range[] = [];
  const stack = [tree.rootNode];
  while (stack.length) {
    const node = stack.pop();
    if (node.type === 'string' || node.type === 'concatenated_string') {
      // Node's native binding uses JavaScript string indexes. Convert explicitly
      // to UTF-8 byte offsets before timing; verify that assumption on every node.
      assert.equal(node.text, source.slice(node.startIndex, node.endIndex));
      ranges.push({
        start: Buffer.byteLength(source.slice(0, node.startIndex), 'utf8'),
        end: Buffer.byteLength(source.slice(0, node.endIndex), 'utf8'),
      });
    }
    // This traversal is outside timing. The containment walk is never reversed.
    for (let i = node.namedChildCount - 1; i >= 0; i -= 1) {
      stack.push(node.namedChild(i));
    }
  }
  return sortRanges(ranges);
}

function loadParser(): any | null {
  const require = process.env.BENCH_BINDING_ROOT
    ? createRequire(resolve(process.env.BENCH_BINDING_ROOT, 'package.json'))
    : createRequire(import.meta.url);
  try {
    // A real load + grammar initialization + Unicode parse, never a fake success.
    const Parser = require('tree-sitter');
    const Python = require('tree-sitter-python');
    const parser = new Parser();
    parser.setLanguage(Python);
    const probe = "value = ('é🙂' 'x')\n";
    const tree = parser.parse(probe);
    assert.ok(tree);
    assert.deepEqual(walk(extractStrings(tree, probe)), {
      candidates: 3, comparisons: 2, remaining: 1,
    });
    return parser;
  } catch (error) {
    console.error('tree-sitter binding check failed:', error instanceof Error ? error.message : String(error));
    return null;
  }
}

function parseInputs(parser: any): Range[][] {
  const paths = git(['ls-tree', '-r', '--name-only', '-z', BASE])
    .toString('utf8').split('\0').filter(Boolean);
  const supported = paths.filter(path => path.endsWith('.py') || path.endsWith('.pyi'));
  assert.ok(supported.length > 0, 'no supported files at the pinned commit');
  const files: Range[][] = [];
  for (const path of supported) {
    const source = git(['show', BASE + ':' + path]).toString('utf8');
    const tree = parser.parse(source);
    assert.ok(tree, 'tree-sitter returned no tree: ' + path);
    if (tree.rootNode.hasError) console.error('recovery AST included:', path);
    files.push(extractStrings(tree, source));
  }
  console.error('parse coverage:', supported.length, 'of', paths.length, 'tracked files; excluded:', paths.length - supported.length);
  return files;
}

function selfTest(): void {
  const expected = [
    { candidates: 825, comparisons: 339900, remaining: 825 },
    { candidates: 4200, comparisons: 421900, remaining: 200 },
    { candidates: 4000, comparisons: 7998000, remaining: 4000 },
  ];
  [disjoint(825), nested(), disjoint(4000)].forEach((ranges, i) =>
    assert.deepEqual(walk(sortRanges(ranges)), expected[i]));
  assert.deepEqual(walk([{ start: 0, end: 1 }, { start: 2, end: 10 }, { start: 3, end: 4 }]),
    { candidates: 3, comparisons: 3, remaining: 2 });
  const tied = sortRanges([{ start: 0, end: 2 }, { start: 0, end: 4 }, { start: 0, end: 4 }]);
  assert.deepEqual(tied.map(range => range.end), [4, 4, 2]);
  assert.deepEqual(walk(tied), { candidates: 3, comparisons: 2, remaining: 1 });
  assert.deepEqual(walkFiles([[{ start: 0, end: 10 }], [{ start: 0, end: 2 }]]),
    { candidates: 2, comparisons: 0, remaining: 2 });
  assert.deepEqual(walk([{ start: 0, end: 5 }, { start: 4, end: 6 }]),
    { candidates: 2, comparisons: 1, remaining: 2 });
  let calls = 0;
  measure(() => { calls += 1; return walk([]); });
  assert.equal(calls, 6);
  assert.deepEqual(walk([]), { candidates: 0, comparisons: 0, remaining: 0 });
  console.error('self-test: S/N/M, front scan, tie/duplicate handling, file isolation, overlap, 1+5 runs, empty input passed');
}

function main(): void {
  if (process.argv.includes('--self-test')) {
    selfTest();
    return;
  }
  const cases: [string, Range[], Stats][] = [
    ['S', disjoint(825), { candidates: 825, comparisons: 339900, remaining: 825 }],
    ['N', nested(), { candidates: 4200, comparisons: 421900, remaining: 200 }],
    ['M', disjoint(4000), { candidates: 4000, comparisons: 7998000, remaining: 4000 }],
  ];
  for (const [name, input, expected] of cases) {
    sortRanges(input); // Generation and sorting remain outside all timed runs.
    const [stats, milliseconds] = measure(() => walk(input), expected);
    console.log('walk typescript', name, stats.candidates, stats.comparisons, stats.remaining, milliseconds.toFixed(1));
  }
  const parser = loadParser();
  if (!parser) {
    console.log('parse typescript BINDING_FAILED');
  } else {
    const files = parseInputs(parser); // Reading, parsing, extraction, sorting excluded.
    const [stats, milliseconds] = measure(() => walkFiles(files));
    console.log('parse typescript ok', files.length, stats.candidates, stats.comparisons, stats.remaining, milliseconds.toFixed(1));
  }
  assert.ok(Number.isFinite(observable));
}

main();

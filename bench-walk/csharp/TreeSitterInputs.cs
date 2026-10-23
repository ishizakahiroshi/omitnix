using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

internal sealed class BindingUnavailableException : Exception
{
    internal BindingUnavailableException(string message) : base(message) { }
}

// Direct C# P/Invoke binding to the real tree-sitter C ABI, not a substitute parser.
internal static class TreeSitterInputs
{
    private const string Runtime = "tree-sitter";
    private const string Grammar = "tree-sitter-python";

    [StructLayout(LayoutKind.Sequential)]
    internal struct Node
    {
        public uint Context0, Context1, Context2, Context3;
        public IntPtr Id, Tree;
    }

    [DllImport(Runtime, CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr ts_parser_new();
    [DllImport(Runtime, CallingConvention = CallingConvention.Cdecl)]
    private static extern void ts_parser_delete(IntPtr parser);
    [DllImport(Runtime, CallingConvention = CallingConvention.Cdecl)]
    [return: MarshalAs(UnmanagedType.I1)]
    private static extern bool ts_parser_set_language(IntPtr parser, IntPtr language);
    [DllImport(Grammar, CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr tree_sitter_python();
    [DllImport(Runtime, CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr ts_parser_parse_string(IntPtr parser, IntPtr oldTree,
        byte[] source, uint length);
    [DllImport(Runtime, CallingConvention = CallingConvention.Cdecl)]
    private static extern void ts_tree_delete(IntPtr tree);
    [DllImport(Runtime, CallingConvention = CallingConvention.Cdecl)]
    private static extern Node ts_tree_root_node(IntPtr tree);
    [DllImport(Runtime, CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr ts_node_type(Node node);
    [DllImport(Runtime, CallingConvention = CallingConvention.Cdecl)]
    private static extern uint ts_node_start_byte(Node node);
    [DllImport(Runtime, CallingConvention = CallingConvention.Cdecl)]
    private static extern uint ts_node_end_byte(Node node);
    [DllImport(Runtime, CallingConvention = CallingConvention.Cdecl)]
    private static extern uint ts_node_child_count(Node node);
    [DllImport(Runtime, CallingConvention = CallingConvention.Cdecl)]
    private static extern Node ts_node_child(Node node, uint index);

    private static byte[] Git(params string[] args)
    {
        var info = new ProcessStartInfo("git")
        {
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false
        };
        foreach (string arg in args)
            info.ArgumentList.Add(arg);
        using var process = Process.Start(info) ?? throw new InvalidOperationException("Cannot start git");
        var error = process.StandardError.ReadToEndAsync();
        using var bytes = new MemoryStream();
        process.StandardOutput.BaseStream.CopyTo(bytes);
        process.WaitForExit();
        string diagnostic = error.GetAwaiter().GetResult();
        if (process.ExitCode != 0)
            throw new InvalidOperationException($"git failed: {diagnostic.Trim()}");
        return bytes.ToArray();
    }

    internal static List<IReadOnlyList<Interval>> Prepare()
    {
        IntPtr parser = ts_parser_new(); // A real native loading attempt precedes Git work.
        if (parser == IntPtr.Zero)
            throw new BindingUnavailableException("ts_parser_new returned NULL");
        try
        {
            if (!ts_parser_set_language(parser, tree_sitter_python()))
                throw new BindingUnavailableException("Python grammar ABI is incompatible");
            string root = Encoding.UTF8.GetString(Git("rev-parse", "--show-toplevel")).Trim();
            string[] paths = Encoding.UTF8.GetString(Git("-C", root, "ls-tree", "-r", "-z",
                "--name-only", Benchmark.BaseCommit)).Split('\0', StringSplitOptions.RemoveEmptyEntries);
            var files = new List<IReadOnlyList<Interval>>();
            foreach (string path in paths)
            {
                if (!path.EndsWith(".py", StringComparison.Ordinal) &&
                    !path.EndsWith(".pyi", StringComparison.Ordinal))
                    continue;
                byte[] source = Git("-C", root, "show", $"{Benchmark.BaseCommit}:{path}");
                IntPtr tree = ts_parser_parse_string(parser, IntPtr.Zero, source, checked((uint)source.Length));
                if (tree == IntPtr.Zero)
                    throw new InvalidOperationException($"Native parse returned NULL: {path}");
                try
                {
                    var ranges = new List<Interval>();
                    var pending = new Stack<Node>();
                    pending.Push(ts_tree_root_node(tree));
                    while (pending.Count > 0)
                    {
                        Node node = pending.Pop();
                        string? type = Marshal.PtrToStringUTF8(ts_node_type(node));
                        if (type is "string" or "concatenated_string")
                            ranges.Add(new Interval(checked((int)ts_node_start_byte(node)),
                                checked((int)ts_node_end_byte(node))));
                        uint children = ts_node_child_count(node);
                        for (uint i = children; i > 0; i--)
                            pending.Push(ts_node_child(node, i - 1));
                    }
                    Benchmark.Sort(ranges);
                    files.Add(ranges); // Include empty and error-recovery trees too.
                }
                finally { ts_tree_delete(tree); }
            }
            if (files.Count == 0)
                throw new InvalidOperationException("No Python base-commit files found");
            return files;
        }
        finally { ts_parser_delete(parser); }
    }
}

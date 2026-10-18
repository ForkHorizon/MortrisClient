using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using Daliys.Analytics.Internal.Transport;

namespace M7Transport.Tests
{
    internal static class TestSupport
    {
        internal static string Root => Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
        internal static string Fixture(string name) => Path.Combine(Root, "fixtures", name);
        internal static byte[] FixtureBytes(string name) => File.ReadAllBytes(Fixture(name));
        internal static string FixtureText(string name) => File.ReadAllText(Fixture(name));

        [ModuleInitializer]
        internal static void ResolveNativeZstd()
        {
            NativeLibrary.SetDllImportResolver(typeof(NativeZstdCompressor).Assembly, (name, assembly, path) =>
            {
                if (name != "daliys_zstd") return IntPtr.Zero;
                var dylib = Environment.GetEnvironmentVariable("DALIYS_ZSTD") ?? Path.GetFullPath(Path.Combine(Root, "../../../../../Runtime/Plugins/macOS/libdaliys_zstd.dylib"));
                return NativeLibrary.Load(dylib);
            });
        }

        /// <summary>Runs the research Python decoder over a frame; returns its stdout, or null when no interpreter is configured.</summary>
        internal static string PythonDecode(string catalogFile, string dictionaryFile, string aliasesFile, string frameFile, string expectedFile, out int exitCode)
        {
            var python = Environment.GetEnvironmentVariable("M7_PYTHON");
            exitCode = 0;
            if (string.IsNullOrEmpty(python)) return null;
            var start = new ProcessStartInfo(python) { RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false };
            start.Environment["PYTHONDONTWRITEBYTECODE"] = "1";
            start.Environment["M7_SCRIPTS"] = Path.GetFullPath(Path.Combine(Root, "../../../../../Theory~/transport-v7/comparison/scripts"));
            foreach (var argument in new[] { Path.Combine(Root, "tools", "py_decode.py"), catalogFile, dictionaryFile, aliasesFile, frameFile, expectedFile }) start.ArgumentList.Add(argument);
            using (var process = Process.Start(start))
            {
                var output = process.StandardOutput.ReadToEnd() + process.StandardError.ReadToEnd();
                process.WaitForExit();
                exitCode = process.ExitCode;
                return output;
            }
        }
    }
}

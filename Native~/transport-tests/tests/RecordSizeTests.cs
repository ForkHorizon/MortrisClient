// Diagnostic: size of the stored binary record per event for a JSONL corpus.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Daliys.Analytics.Internal.Transport;
using Xunit;

namespace M7Transport.Tests
{
    /// <summary>Diagnostic: size of the binary record the SDK stores per event for a JSONL corpus ({"name","props"}). Prints RECSIZE lines; skipped without M8_CORPUS_DIR (a directory of .jsonl files).</summary>
    public class RecordSizeTests
    {
        [Fact]
        public void ZRecordSizesOfCorpora()
        {
            var dir = Environment.GetEnvironmentVariable("M8_CORPUS_DIR");
            if (string.IsNullOrEmpty(dir)) return;
            var context = EventContext.Build(60, "1.1.14", "214", "android", "Android 15", "Pixel 8", "en-US");
            foreach (var file in Directory.GetFiles(dir, "*.jsonl").OrderBy(f => f))
            {
                var writer = new EventRecordWriter { TypedNumbers = true };
                var sizes = new List<int>();
                foreach (var line in File.ReadLines(file).Take(3000))
                {
                    using (var doc = System.Text.Json.JsonDocument.Parse(line))
                    {
                        var props = new Dictionary<string, object>();
                        foreach (var kv in doc.RootElement.GetProperty("props").EnumerateObject())
                            props[kv.Name] = kv.Value.ValueKind == System.Text.Json.JsonValueKind.String ? kv.Value.GetString()
                                : kv.Value.ValueKind == System.Text.Json.JsonValueKind.True ? true : kv.Value.ValueKind == System.Text.Json.JsonValueKind.False ? false
                                : kv.Value.TryGetInt64(out var l) ? (object)l : kv.Value.GetDouble();
                        if (props.Count > 32) continue; // the SDK rejects these
                        writer.Begin(new EventHeader(Guid.NewGuid(), Guid.NewGuid(), 1700000000000, 1000, context), doc.RootElement.GetProperty("name").GetString(), props.Count);
                        foreach (var p in props) writer.AddClr(p.Key, p.Value);
                        sizes.Add(writer.Finish());
                    }
                }
                sizes.Sort();
                Console.WriteLine("RECSIZE " + Path.GetFileName(file) + " n=" + sizes.Count + " mean=" + sizes.Average().ToString("F0") + " p50=" + sizes[sizes.Count / 2] + " p99=" + sizes[(int)(sizes.Count * 0.99)] + " ctx=" + context.Length);
            }
        }
    }
}

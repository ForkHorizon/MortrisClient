using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text.Json;
using Daliys.Analytics.Internal.Transport;

internal static class Program
{
    private sealed class FrameRecord
    {
        public int batch_index { get; set; }
        public string base64 { get; set; }
    }

    private sealed class StreamRecord
    {
        public string origin { get; set; }
        public string epoch { get; set; }
        public JsonElement aliases { get; set; }
        public List<FrameRecord> frames { get; set; }
    }

    private static int Main(string[] args)
    {
        try
        {
            if (args.Length != 3) return Fail();
            NativeLibrary.SetDllImportResolver(typeof(NativeZstdCompressor).Assembly, (name, assembly, path) =>
                name == "daliys_zstd" ? NativeLibrary.Load(args[2]) : IntPtr.Zero);

            var catalog = M7Catalog.Parse(File.ReadAllBytes(args[0]));
            var dictionary = args[1] == "-" ? Array.Empty<byte>() : File.ReadAllBytes(args[1]);
            using var input = JsonDocument.Parse(Console.In.ReadToEnd());
            var root = input.RootElement;
            var batchSize = root.GetProperty("batch_size").GetInt32();
            var integerModel = root.GetProperty("integer_model").GetBoolean();
            var stringModel = root.GetProperty("string_model").GetBoolean();
            if (batchSize < 1 || batchSize > M7FrameEncoder.MaxRows) return Fail();

            long outputBytes = 0, inputBytes = 0, fallbackBytes = 0, encodedEvents = 0, fallbackEvents = 0;
            long encodeNanoseconds = 0;
            var frames = 0;
            var streams = new List<StreamRecord>();
            var rows = new List<object>();
            var failureKinds = new Dictionary<string, int>();
            foreach (var sample in root.GetProperty("samples").EnumerateArray())
            {
                long sampleOutput = 0, sampleInput = 0, sampleFallback = 0, sampleEvents = 0, sampleFallbackEvents = 0;
                var sampleFrames = 0;
                var sampleAliases = 0;
            foreach (var stream in sample.GetProperty("streams").EnumerateArray())
            {
                var origin = stream.GetProperty("origin").GetString();
                var epoch = stream.GetProperty("epoch").GetString();
                var epochBytes = Convert.FromHexString(epoch);
                var aliases = new M7Aliases(epochBytes);
                var streamFrames = new List<FrameRecord>();
                using var encoder = new M7EventEncoder(catalog, aliases, dictionary, origin,
                    new NativeZstdCompressor(dictionary), integerModel, stringModel);
                var batchIndex = 0;
                foreach (var batch in stream.GetProperty("batches").EnumerateArray())
                {
                    var events = batch.GetProperty("events");
                    var count = events.GetArrayLength();
                    if (count < 1 || count > batchSize) return Fail();
                    sampleEvents += count;
                    var forceFallback = batch.TryGetProperty("force_fallback", out var force) && force.GetBoolean();
                    M7EncodeResult encoded = null;
                    if (!forceFallback)
                    {
                        var started = Stopwatch.GetTimestamp();
                        encoded = encoder.Encode(events.GetRawText());
                        encodeNanoseconds += (long)(Stopwatch.GetElapsedTime(started).TotalMilliseconds * 1_000_000);
                    }
                    var batchInput = batch.GetProperty("input_bytes").GetInt64();
                    inputBytes += batchInput;
                    sampleInput += batchInput;
                    if (encoded != null && encoded.Ok)
                    {
                        outputBytes += encoded.Frame.Length;
                        sampleOutput += encoded.Frame.Length;
                        encodedEvents += count;
                        sampleFrames++;
                        streamFrames.Add(new FrameRecord { batch_index = batchIndex, base64 = Convert.ToBase64String(encoded.Frame) });
                        frames++;
                    }
                    else
                    {
                        var kind = FailureKind(encoded?.Failure);
                        failureKinds[kind] = failureKinds.GetValueOrDefault(kind) + count;
                        var fallback = batch.GetProperty("fallback_bytes").GetInt64();
                        if (fallback < 1) return Fail();
                        outputBytes += fallback;
                        sampleOutput += fallback;
                        fallbackBytes += fallback;
                        sampleFallback += fallback;
                        fallbackEvents += count;
                        sampleFallbackEvents += count;
                    }
                    batchIndex++;
                }

                using var records = JsonDocument.Parse(aliases.RecordsJson(0, aliases.Count));
                sampleAliases += records.RootElement.GetArrayLength();
                streams.Add(new StreamRecord { origin = origin, epoch = epoch, aliases = records.RootElement.Clone(), frames = streamFrames });
            }
                rows.Add(new
                {
                    output_bytes = sampleOutput,
                    input_bytes = sampleInput,
                    events = sampleEvents,
                    fallback_bytes = sampleFallback,
                    fallback_events = sampleFallbackEvents,
                    frames = sampleFrames,
                    alias_records = sampleAliases,
                    v1_gzip100_bytes = sample.GetProperty("v1_gzip100_bytes").GetInt64()
                });
            }

            var result = new
            {
                ok = true,
                project_matches = catalog.Project == root.GetProperty("project_id").GetString(),
                encoded_bytes = outputBytes,
                input_bytes = inputBytes,
                fallback_bytes = fallbackBytes,
                encoded_events = encodedEvents,
                fallback_events = fallbackEvents,
                frames,
                alias_records = streams.Sum(s => s.aliases.GetArrayLength()),
                encode_nanoseconds = encodeNanoseconds,
                failure_kinds = failureKinds,
                rows,
                streams
            };
            Console.Out.WriteLine(JsonSerializer.Serialize(result));
            return 0;
        }
        catch
        {
            return Fail();
        }
    }

    private static string FailureKind(string reason)
    {
        if (reason == null) return "origin_rejected";
        if (reason.Contains("unknown shape", StringComparison.Ordinal)) return "unknown_shape";
        if (reason.Contains("occurred_at_client", StringComparison.Ordinal)) return "timestamp_format";
        if (reason.Contains("sequences", StringComparison.Ordinal)) return "sequence_order";
        if (reason.Contains("does not fit a packet", StringComparison.Ordinal)) return "packet_limit";
        return "invalid_event";
    }

    private static int Fail()
    {
        Console.Error.WriteLine("V7 replay failed; details are suppressed to protect event data.");
        return 2;
    }
}

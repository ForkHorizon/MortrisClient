using System;
using System.IO;
using System.Text.Json;
using System.Diagnostics;

static class FramesMain
{
    static int Main(string[] args)
    {
        long controlBefore = GC.GetAllocatedBytesForCurrentThread();
        byte[] control = new byte[4096];
        long controlBytes = GC.GetAllocatedBytesForCurrentThread() - controlBefore;
        GC.KeepAlive(control);
        if (controlBytes < 4096) throw new Exception("allocation counter control");
        using var manifest = JsonDocument.Parse(File.ReadAllBytes(args[0]));
        var config = manifest.RootElement;
        byte[] dictionary = File.ReadAllBytes(config.GetProperty("dictionary").GetString());
        using var encoder = new FrameEncoder(Convert.FromHexString(config.GetProperty("catalog_id").GetString()), Convert.FromHexString(config.GetProperty("epoch").GetString()), dictionary,
            config.GetProperty("preserve_ids").GetBoolean(), config.GetProperty("integer_model").GetBoolean(), config.GetProperty("string_model").GetBoolean());
        int iterations = config.GetProperty("iterations").GetInt32(), warmup = config.GetProperty("warmup").GetInt32();
        if (iterations < 1 || iterations > 1000 || warmup < 1 || warmup > 200) throw new ArgumentException("measurement bounds");
        foreach (var job in config.GetProperty("jobs").EnumerateArray())
        {
            using var source = JsonDocument.Parse(File.ReadAllBytes(job.GetProperty("input").GetString()));
            Row[] rows = Program.LoadRows(source.RootElement, out int[] types);
            int capacity = job.TryGetProperty("capacity", out var cap) ? cap.GetInt32() : FrameEncoder.MaxFrame;
            if (capacity < 0 || capacity > FrameEncoder.MaxFrame) throw new ArgumentException("capacity");
            byte[] frame = new byte[capacity]; int length = 0;
            bool success = false, expected = !job.TryGetProperty("expected_success", out var expectedValue) || expectedValue.GetBoolean();
            for (int i = 0; i < warmup; i++) success = encoder.TryPack(rows, types, frame, out length);
            long before = GC.GetAllocatedBytesForCurrentThread(), start = Stopwatch.GetTimestamp();
            for (int i = 0; i < iterations; i++) success = encoder.TryPack(rows, types, frame, out length);
            long ticks = Stopwatch.GetTimestamp() - start, allocated = GC.GetAllocatedBytesForCurrentThread() - before;
            if (success != expected || allocated != 0 || (!success && length != 0)) throw new Exception("frame result/allocation");
            if (success) File.WriteAllBytes(job.GetProperty("output").GetString(), frame.AsSpan(0, length).ToArray());
            Console.WriteLine(JsonSerializer.Serialize(new { fixture = job.GetProperty("name").GetString(), events = rows.Length, success, frame_bytes = length,
                iterations, allocation_control_bytes = controlBytes, gc_bytes = allocated, mean_ms = 1000.0 * ticks / Stopwatch.Frequency / iterations,
                scope = "pretyped columns + reused zstd + M7 header/CRC; excludes ingress/catalog lookup/queue/JNI/HTTP" }));
        }
        return 0;
    }
}

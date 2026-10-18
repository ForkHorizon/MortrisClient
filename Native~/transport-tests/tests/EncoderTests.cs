using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using Daliys.Analytics.Internal.Transport;
using Xunit;

namespace M7Transport.Tests
{
    public class EncoderTests
    {
        private sealed class Setup : IDisposable
        {
            internal M7Catalog Catalog; internal M7Aliases Aliases; internal M7EventEncoder Encoder; internal byte[] Dictionary; internal string Origin, Batch, Variant, Profile;
            internal Setup(string variant, string profile, bool dictionary = true, bool numeric = true, bool strings = true)
            {
                Variant = variant; Profile = profile;
                Catalog = M7Catalog.Parse(TestSupport.FixtureBytes("catalog-" + variant + ".json"));
                Dictionary = dictionary ? TestSupport.FixtureBytes("dictionary-" + variant + ".bin") : null;
                Batch = TestSupport.FixtureText("batch-" + profile + ".json");
                Origin = (string)((Dictionary<string, object>)MiniJson.Parse(TestSupport.FixtureText("expected-" + profile + ".json")))["origin"];
                Aliases = new M7Aliases();
                Encoder = new M7EventEncoder(Catalog, Aliases, Dictionary, Origin, new NativeZstdCompressor(Dictionary), numeric, strings);
            }
            public void Dispose() => Encoder.Dispose();
        }

        public static IEnumerable<object[]> Matrix()
        {
            foreach (var variant in new[] { "plain", "logical" })
                foreach (var profile in new[] { "low", "high", "wide" })
                    yield return new object[] { variant, profile };
        }

        [Theory, MemberData(nameof(Matrix))]
        public void EncodesTheWholeBatchIntoAWellFormedPacket(string variant, string profile)
        {
            using (var s = new Setup(variant, profile))
            {
                var result = s.Encoder.Encode(s.Batch);
                Assert.True(result.Ok, result.Failure);
                Assert.Equal(100, result.Count);
                Assert.Equal(100, result.Sequences.Length);
                var f = result.Frame;
                Assert.Equal((byte)'M', f[0]); Assert.Equal((byte)'7', f[1]);
                Assert.Equal(6, f[2]);                       // integer + string models, no legacy ids
                Assert.True(f[3] <= 1);
                Assert.Equal(s.Catalog.Id, Slice(f, 4, 8));
                Assert.Equal(s.Aliases.Epoch, Slice(f, 12, 8));
                using (var sha = SHA256.Create()) Assert.Equal(Slice(sha.ComputeHash(s.Dictionary), 0, 8), Slice(f, 20, 8));
                var crc = BitConverter.ToUInt32(f, f.Length - 4);
                Assert.Equal(M7FrameEncoder.Crc(f, f.Length - 4), crc);
                Assert.True(f.Length < M7FrameEncoder.MaxFrame);
                if (profile != "wide") Assert.True(f.Length < 12000, "packet is " + f.Length + " bytes");
            }
        }

        [Theory, MemberData(nameof(Matrix))]
        public void PacketsDecodeToTheOriginalEventsWithThePythonReferenceDecoder(string variant, string profile)
        {
            foreach (var (numeric, strings) in new[] { (true, true), (true, false), (false, true), (false, false) })
                foreach (var dictionary in new[] { true, false })
                    using (var s = new Setup(variant, profile, dictionary, numeric, strings))
                    {
                        var result = s.Encoder.Encode(s.Batch);
                        Assert.True(result.Ok, result.Failure);
                        var dir = Directory.CreateTempSubdirectory("m7").FullName;
                        try
                        {
                            File.WriteAllBytes(Path.Combine(dir, "frame.bin"), result.Frame);
                            File.WriteAllText(Path.Combine(dir, "aliases.json"), "{\"epoch\":\"" + s.Aliases.EpochHex + "\",\"records\":" + s.Aliases.RecordsJson(0, s.Aliases.Count) + "}");
                            File.WriteAllBytes(Path.Combine(dir, "dictionary.bin"), s.Dictionary ?? new byte[0]);
                            var output = TestSupport.PythonDecode(TestSupport.Fixture("catalog-" + variant + ".json"), Path.Combine(dir, "dictionary.bin"), Path.Combine(dir, "aliases.json"),
                                Path.Combine(dir, "frame.bin"), TestSupport.Fixture("expected-" + profile + ".json"), out var exit);
                            if (output == null) return; // no interpreter configured: structure is still checked by the other tests
                            Assert.True(exit == 0 && output.StartsWith("OK 100"), $"{variant}/{profile} numeric={numeric} strings={strings} dict={dictionary}: {output}");
                        }
                        finally { Directory.Delete(dir, true); }
                    }
        }

        [Fact]
        public void AliasTableGrowsOnlyWithNewContextsAndSerializesToTheWireForm()
        {
            using (var s = new Setup("plain", "low"))
            {
                Assert.True(s.Encoder.Encode(s.Batch).Ok);
                var first = s.Aliases.Count;
                Assert.InRange(first, 2, 100);
                Assert.True(s.Encoder.Encode(s.Batch).Ok);
                Assert.Equal(first, s.Aliases.Count);   // same contexts: no new records
                var records = MiniJson.ParseArray(s.Aliases.RecordsJson(0, first));
                Assert.Equal(first, records.Count);
                var one = (List<object>)records[0];
                Assert.Equal(9, one.Count);
                Assert.Equal(s.Origin, one[0]);
                Assert.IsType<JsonNumber>(one[8]);       // timezone is an integer, not a string
                Assert.Equal(2, ((List<object>)MiniJson.ParseArray(s.Aliases.RecordsJson(first - 2, 2))).Count);
            }
        }

        [Fact]
        public void AnUnknownShapeIsNeverEncoded()
        {
            using (var s = new Setup("plain", "low"))
            {
                var changed = s.Batch.Replace("\"coins\"", "\"coinz\"");
                var result = s.Encoder.Encode(changed);
                Assert.False(result.Ok);
                Assert.Contains("unknown shape", result.Failure);
            }
        }

        [Theory]
        [InlineData("[]")]
        [InlineData("not json")]
        [InlineData("[1]")]
        [InlineData("[{\"sequence\":1}]")]
        public void MalformedBatchesFailWithoutThrowing(string json)
        {
            using (var s = new Setup("plain", "low")) Assert.False(s.Encoder.Encode(json).Ok);
        }

        [Fact]
        public void SequencesMustIncreaseAndStartAtOne()
        {
            using (var s = new Setup("plain", "low"))
            {
                var events = MiniJson.ParseArray(s.Batch);
                var reversed = new List<object>(events);
                reversed.Reverse();
                Assert.False(s.Encoder.Encode(TestSupport.Serialize(reversed)).Ok);
                var zero = s.Batch.Replace("\"sequence\":1}", "\"sequence\":0}");
                Assert.False(s.Encoder.Encode(zero).Ok);
            }
        }

        [Fact]
        public void IncompressibleLargeBatchesGrowTheRawBufferInsteadOfFailing()
        {
            using (var s = new Setup("plain", "wide"))
            {
                var result = s.Encoder.Encode(s.Batch);
                Assert.True(result.Ok, result.Failure);
                Assert.True(result.Frame.Length > 60000, "the wide batch must exceed the initial 64 KiB raw buffer; packet is " + result.Frame.Length);
            }
        }

        [Fact]
        public void ABatchThatCannotFitOnePacketIsRejectedForV1Fallback()
        {
            using (var s = new Setup("plain", "wide"))
            {
                // Every event carries a 900-character note and incompressible text: a 500-event batch exceeds the 256 KiB frame limit.
                var events = MiniJson.ParseArray(s.Batch);
                var many = new List<object>();
                long sequence = 1;
                var random = new Random(5);
                const string alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+/";
                for (var copy = 0; copy < 5; copy++)
                    foreach (Dictionary<string, object> e in events)
                    {
                        var clone = new Dictionary<string, object>(e) { ["sequence"] = new JsonNumber((sequence++).ToString()) };
                        var properties = new Dictionary<string, object>((Dictionary<string, object>)e["properties"]);
                        var note = new char[900];
                        for (var i = 0; i < note.Length; i++) note[i] = alphabet[random.Next(alphabet.Length)];
                        properties["note"] = new string(note);   // unique text: duplicates would compress away
                        clone["properties"] = properties;
                        many.Add(clone);
                    }
                var result = s.Encoder.Encode(TestSupport.Serialize(many));
                Assert.False(result.Ok);
            }
        }

        private static byte[] Slice(byte[] data, int offset, int count) { var r = new byte[count]; Buffer.BlockCopy(data, offset, r, 0, count); return r; }
    }
}

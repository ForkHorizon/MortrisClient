using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using Daliys.Analytics.Internal.Transport;
using Xunit;

namespace M7Transport.Tests
{
    public class RecordTests
    {
        private static readonly byte[] Context = EventContext.Build("1.4.0", "214", "android", "14", "phone", "en-US", -300);

        private static byte[] Write(string name, IReadOnlyDictionary<string, object> properties, Guid? id = null, Guid? session = null, long at = 1790000000123, long elapsed = 4567)
        {
            var writer = new EventRecordWriter();
            writer.Begin(id ?? Guid.NewGuid(), session ?? Guid.NewGuid(), at, elapsed, Context, name, properties.Count);
            foreach (var property in properties) writer.AddClr(property.Key, property.Value);
            var length = writer.Finish();
            var record = new byte[length];
            Buffer.BlockCopy(writer.Buffer, 0, record, 0, length);
            return record;
        }

        private static ParsedEvent Read(byte[] record)
        {
            var parsed = new ParsedEvent();
            new EventRecordReader().Read(record, 0, record.Length, parsed);
            return parsed;
        }

        /// <summary>What the SDK's previous JSON serializer wrote for a value: the lexeme every later stage classified.</summary>
        private static string OldLexeme(object value)
        {
            switch (value)
            {
                case float single: return single.ToString("R", CultureInfo.InvariantCulture);
                case double number: return number.ToString("R", CultureInfo.InvariantCulture);
                case IFormattable number: return number.ToString(null, CultureInfo.InvariantCulture);
                default: throw new InvalidOperationException();
            }
        }

        [Fact]
        public void EveryValueKindRoundTripsThroughTheRecord()
        {
            var id = Guid.NewGuid(); var session = Guid.NewGuid();
            var props = new Dictionary<string, object>
            {
                { "nothing", null }, { "yes", true }, { "no", false }, { "small", 7 }, { "negative", -123456789012L }, { "big", ulong.MaxValue },
                { "fraction", 4.99 }, { "text", "héllo \"quoted\" \n\u2028 " }, { "empty", "" }, { "whole_double", 3.0 },
            };
            var parsed = Read(Write("level_end", props, id, session));
            Assert.Equal(id.ToString("D"), parsed.EventIdText);
            Assert.Equal(session.ToString("D"), parsed.SessionIdText);
            Assert.Equal("level_end", parsed.Name);
            Assert.Equal(1790000000123, parsed.OccurredAtUnixMs);
            Assert.Equal(4567, parsed.SessionElapsedMs);
            Assert.Equal(("1.4.0", "214", "android", "14", "phone", "en-US", -300), (parsed.AppVersion, parsed.BuildNumber, parsed.Platform, parsed.OsVersion, parsed.DeviceClass, parsed.Locale, parsed.TimezoneOffsetMinutes));
            var byKey = Enumerable.Range(0, parsed.PropertyCount).ToDictionary(i => parsed.Properties[i].Key, i => parsed.Properties[i]);
            Assert.Equal(EventRecordFormat.TagNull, byKey["nothing"].Tag);
            Assert.Equal(EventRecordFormat.TagTrue, byKey["yes"].Tag);
            Assert.Equal(EventRecordFormat.TagFalse, byKey["no"].Tag);
            Assert.Equal(7, byKey["small"].I);
            Assert.Equal(-123456789012L, byKey["negative"].I);
            Assert.Equal(ulong.MaxValue, byKey["big"].U);
            Assert.Equal(4.99, byKey["fraction"].D);
            Assert.Equal("héllo \"quoted\" \n\u2028 ", byKey["text"].S);
            Assert.Equal("", byKey["empty"].S);
            Assert.Equal(EventRecordFormat.TagInt, byKey["whole_double"].Tag); // 3.0 serialised as "3": an integer, like the JSON path
            Assert.Equal(3, byKey["whole_double"].I);
        }

        [Fact]
        public void UuidByteOrderMatchesTheTextForm()
        {
            for (var i = 0; i < 50; i++)
            {
                var id = Guid.NewGuid();
                var record = Write("e", new Dictionary<string, object>(), id);
                Assert.Equal(id.ToString("D"), EventRecordFormat.UuidText(record, EventRecordFormat.IdOffset));
                Assert.Equal(id, EventRecordFormat.ReadUuid(record, EventRecordFormat.IdOffset));
                var bytes = new byte[16];
                Assert.True(EventRecordFormat.TryParseUuid(id.ToString("D"), bytes, 0));
                Assert.Equal(bytes, record.Skip(EventRecordFormat.IdOffset).Take(16).ToArray());
            }
        }

        public static IEnumerable<object[]> Numbers()
        {
            object[] values =
            {
                0, 1, -1, 7, int.MaxValue, int.MinValue, long.MaxValue, long.MinValue, uint.MaxValue, ulong.MaxValue, (ulong)long.MaxValue + 1, (byte)200, (sbyte)-5, (short)-300, (ushort)65535,
                0.0, -0.0, 3.0, -3.0, 0.1, 4.99, 1.5, 123456789.125, 1e-5, 1e-7, 0.000123, 999999999999999.0, 1e100, double.MaxValue, double.Epsilon,
                0.1f, 1.5f, 3.0f, 16777216f, 1e10f, 1e-7f, float.MaxValue, 123456.789f, 100000f,
                12.50m, 7m, 0.0000001m, 1234567890123.45m, -0.5m,
            };
            foreach (var value in values) yield return new[] { value };
        }

        [Theory, MemberData(nameof(Numbers))]
        public void NumbersAreClassifiedLikeTheOldJsonLexeme(object value)
        {
            var parsed = Read(Write("e", new Dictionary<string, object> { { "n", value } }));
            var viaRecord = M7Event.FromParsed(parsed, 1, true).Properties.Single().Value;

            M7Value viaLexeme;
            try { viaLexeme = M7Event.Classify(new JsonNumber(OldLexeme(value)), true); }
            catch (FormatException) { viaLexeme = default; viaLexeme.Type = -1; } // the old path could not encode it (V1 sent it as it is)
            if (viaLexeme.Type == -1)
            {
                Assert.True(viaRecord.Type == M7Catalog.TypeFloat32 || viaRecord.Type == M7Catalog.TypeFloat64); // now sent as a double instead of forcing the batch to V1
                return;
            }
            Assert.Equal(viaLexeme.Type, viaRecord.Type);
            Assert.Equal(viaLexeme.I, viaRecord.I);
            Assert.Equal(viaLexeme.U, viaRecord.U);
            Assert.Equal(viaLexeme.D, viaRecord.D);
        }

        /// <summary>
        /// Integral doubles from 1e15 up: "R" prints them with an exponent on the Unity runtime (so they were doubles) and in full on modern .NET (integers),
        /// and a decimal beyond 64 bits had no integer form at all. Either way the value must arrive intact as an integer or a double, and never fail.
        /// </summary>
        [Theory]
        [InlineData(1e15)] [InlineData(1.5e15)] [InlineData(123456789012345680.0)] [InlineData(1e21)]
        public void HugeIntegralDoublesAreKeptWhateverTheirClassification(double value)
        {
            var parsed = Read(Write("e", new Dictionary<string, object> { { "n", value } }));
            var typed = M7Event.FromParsed(parsed, 1, true).Properties.Single().Value;
            Assert.True(typed.Type == M7Catalog.TypeFloat32 || typed.Type == M7Catalog.TypeFloat64);
            Assert.Equal(value, typed.D);
        }

        [Fact]
        public void ADecimalBeyondSixtyFourBitsIsSentAsADouble()
        {
            var parsed = Read(Write("e", new Dictionary<string, object> { { "n", 79228162514264337593543950335m } }));
            var typed = M7Event.FromParsed(parsed, 1, true).Properties.Single().Value;
            Assert.True(typed.Type == M7Catalog.TypeFloat32 || typed.Type == M7Catalog.TypeFloat64);
            Assert.Equal(7.9228162514264338E+28, typed.D);
        }

        [Theory, MemberData(nameof(Numbers))]
        public void TheV1JsonNumberIsTheSameNumberAsBefore(object value)
        {
            var parsed = Read(Write("e", new Dictionary<string, object> { { "n", value } }));
            var json = new System.Text.StringBuilder();
            EventRecordJson.Append(json, parsed, parsed.EventIdText, 1);
            var emitted = (JsonNumber)((Dictionary<string, object>)((Dictionary<string, object>)MiniJson.Parse(json.ToString()))["properties"])["n"];
            var before = double.Parse(OldLexeme(value), CultureInfo.InvariantCulture);
            Assert.Equal(before, double.Parse(emitted.Lexeme, CultureInfo.InvariantCulture));
            // integers keep their exact digits (a double above 2^53 would not)
            if (value is long || value is ulong || value is int) Assert.Equal(OldLexeme(value), emitted.Lexeme);
        }

        [Fact]
        public void V1JsonCarriesEveryFieldInTheOrderOfTheOldSerializer()
        {
            var id = Guid.NewGuid(); var session = Guid.NewGuid();
            var parsed = Read(Write("level_end", new Dictionary<string, object> { { "level", 33 }, { "mode", "hard" } }, id, session, 1790000000123, 20000));
            var json = new System.Text.StringBuilder();
            EventRecordJson.Append(json, parsed, id.ToString("D"), 9);
            var when = DateTimeOffset.FromUnixTimeMilliseconds(1790000000123).ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'", CultureInfo.InvariantCulture);
            Assert.Equal("{\"event_id\":\"" + id + "\",\"session_id\":\"" + session + "\",\"name\":\"level_end\",\"occurred_at_client\":\"" + when + "\",\"session_elapsed_ms\":20000," +
                         "\"app_version\":\"1.4.0\",\"build_number\":\"214\",\"platform\":\"android\",\"os_version\":\"14\",\"device_class\":\"phone\",\"locale\":\"en-US\",\"timezone_offset_minutes\":-300," +
                         "\"properties\":{\"level\":33,\"mode\":\"hard\"},\"sequence\":9}", json.ToString());
        }

        [Fact]
        public void JsonFixturesSurviveTheRecordRoundTrip()
        {
            foreach (var profile in new[] { "low", "high", "wide" })
            {
                var text = TestSupport.FixtureText("batch-" + profile + ".json");
                var batch = QueueBatch.FromJsonArray(text);
                var back = MiniJson.ParseArray(batch.ToJsonArray(new EventRecordReader()));
                var original = MiniJson.ParseArray(text);
                Assert.Equal(original.Count, back.Count);
                for (var i = 0; i < original.Count; i++) AssertSame(original[i], back[i], "event " + i);
            }
        }

        [Fact]
        public void LegacyJsonRowsAreConvertedWhenReadFromAFrame()
        {
            var original = (Dictionary<string, object>)MiniJson.ParseArray(TestSupport.FixtureText("batch-low.json"))[0];
            var payload = System.Text.Encoding.UTF8.GetBytes(TestSupport.Serialize(original));
            var frame = new List<byte> { 0, 0, 0, 1, 0 };                               // count 1, format 0 (JSON)
            for (var shift = 56; shift >= 0; shift -= 8) frame.Add((byte)(41L >> shift)); // sequence (the queue's column wins over the payload's)
            frame.AddRange(new[] { (byte)(payload.Length >> 24), (byte)(payload.Length >> 16), (byte)(payload.Length >> 8), (byte)payload.Length });
            frame.AddRange(payload);
            var batch = QueueBatch.FromFrame(frame.ToArray());
            Assert.Equal(1, batch.Count);
            Assert.Equal(41, batch.Sequence(0));
            Assert.Equal((string)original["event_id"], batch.EventId(0));
        }

        /// <summary>The key property of the whole change: events tracked as CLR values and encoded from records give the exact packet the JSON route gave.</summary>
        [Theory]
        [InlineData("plain", "low")]
        [InlineData("plain", "wide")]
        [InlineData("logical", "high")]
        public void TrackedEventsEncodeToTheSamePacketAsTheOldJsonRoute(string variant, string profile)
        {
            var events = MiniJson.ParseArray(TestSupport.FixtureText("batch-" + profile + ".json")).Cast<Dictionary<string, object>>().ToList();
            var oldJson = new List<string>();
            var frames = new List<byte>();
            var writer = new EventRecordWriter();
            foreach (var e in events)
            {
                var properties = new Dictionary<string, object>();
                foreach (var p in (Dictionary<string, object>)e["properties"]) properties.Add(p.Key, ToClr(p.Value));
                // the old route: serialise like PersistenceEventSerializer did
                var old = new Dictionary<string, object>(e) { ["properties"] = properties.ToDictionary(p => p.Key, p => OldValue(p.Value)) };
                oldJson.Add(TestSupport.Serialize(old));
                // the new route: one record per event
                var id = Guid.NewGuid();
                var session = Guid.Parse((string)e["session_id"]);
                var time = DateTimeOffset.ParseExact((string)e["occurred_at_client"], "yyyy-MM-dd'T'HH:mm:ss.fff'Z'", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal).ToUnixTimeMilliseconds();
                var context = EventContext.Build((string)e["app_version"], (string)e["build_number"], (string)e["platform"], (string)e["os_version"], (string)e["device_class"], (string)e["locale"], int.Parse(((JsonNumber)e["timezone_offset_minutes"]).Lexeme));
                writer.Begin(id, session, time, long.Parse(((JsonNumber)e["session_elapsed_ms"]).Lexeme), context, (string)e["name"], properties.Count);
                foreach (var p in properties) writer.AddClr(p.Key, p.Value);
                var length = writer.Finish();
                frames.AddRange(new[] { (byte)(length >> 24), (byte)(length >> 16), (byte)(length >> 8), (byte)length });
                frames.AddRange(writer.Buffer.Take(length));
            }

            var queue = new FakeQueue();
            queue.EnqueueRecords(frames.ToArray(), events.Count, 10000, 1 << 30, 1 << 30);
            var oldQueue = new FakeQueue();
            oldQueue.Enqueue("[" + string.Join(",", oldJson) + "]");

            byte[] fromRecords, fromJson;
            var catalog = M7Catalog.Parse(TestSupport.FixtureBytes("catalog-" + variant + ".json"));
            var dictionary = TestSupport.FixtureBytes("dictionary-" + variant + ".bin");
            var origin = (string)((Dictionary<string, object>)MiniJson.Parse(TestSupport.FixtureText("expected-" + profile + ".json")))["origin"];
            var epoch = new byte[8];
            using (var a = new M7EventEncoder(catalog, new M7Aliases(epoch), dictionary, origin, new NativeZstdCompressor(dictionary)))
            using (var b = new M7EventEncoder(catalog, new M7Aliases(epoch), dictionary, origin, new NativeZstdCompressor(dictionary)))
            {
                var r1 = a.Encode(queue.ReadOldest(100)); var r2 = b.Encode(oldQueue.ReadOldest(100));
                Assert.True(r1.Ok, r1.Failure); Assert.True(r2.Ok, r2.Failure);
                fromRecords = r1.Frame; fromJson = r2.Frame;
            }
            Assert.Equal(fromJson, fromRecords);
        }

        private static object ToClr(object json)
        {
            switch (json)
            {
                case JsonNumber n when n.Lexeme.IndexOfAny(new[] { '.', 'e', 'E' }) < 0: return long.Parse(n.Lexeme, CultureInfo.InvariantCulture);
                case JsonNumber n: return double.Parse(n.Lexeme, CultureInfo.InvariantCulture);
                default: return json;
            }
        }

        private static object OldValue(object clr)
        {
            switch (clr)
            {
                case long _: case double _: return new JsonNumber(OldLexeme(clr));
                default: return clr;
            }
        }

        private static void AssertSame(object expected, object actual, string where)
        {
            switch (expected)
            {
                case Dictionary<string, object> map:
                    var other = Assert.IsType<Dictionary<string, object>>(actual);
                    Assert.Equal(map.Keys.OrderBy(k => k), other.Keys.OrderBy(k => k));
                    foreach (var pair in map) AssertSame(pair.Value, other[pair.Key], where + "." + pair.Key);
                    break;
                case JsonNumber number:
                    Assert.Equal(double.Parse(number.Lexeme, CultureInfo.InvariantCulture), double.Parse(Assert.IsType<JsonNumber>(actual).Lexeme, CultureInfo.InvariantCulture));
                    break;
                default:
                    Assert.True(Equals(expected, actual), where + ": " + expected + " != " + actual);
                    break;
            }
        }
    }
}

namespace M7Transport.Tests
{
    using System;
    using System.Globalization;
    using Daliys.Analytics.Internal.Transport;
    using Xunit;

    public class FloatFastPathTests
    {
        private static void Check(float f, ref long fast)
        {
            if (!EventRecordWriter.TryShortestDouble(f, out var d)) return;
            fast++;
            var expected = double.Parse(f.ToString("R", CultureInfo.InvariantCulture), NumberStyles.Float, CultureInfo.InvariantCulture);
            Assert.True(BitConverter.DoubleToInt64Bits(d) == BitConverter.DoubleToInt64Bits(expected), $"{BitConverter.SingleToInt32Bits(f):x8} {f:R}: fast {d:R} text {expected:R}");
        }

        [Fact]
        public void FastShortestMatchesTheTextRouteOnRandomAndStructuredFloats()
        {
            long fast = 0, total = 0;
            var rng = new Random(12345);
            for (var i = 0; i < 6_000_000; i++, total++) Check(BitConverter.Int32BitsToSingle(rng.Next() ^ (rng.Next(2) << 31)), ref fast);
            for (var i = 0; i < 3_000_000; i++, total++) // ranges games use: positions, speeds, fractions with few digits
            {
                Check((float)(rng.NextDouble() * 2000 - 1000), ref fast);
                Check((float)Math.Round(rng.NextDouble() * 1000, rng.Next(1, 5)), ref fast);
                Check(rng.Next(-100000, 100000) / (float)Math.Pow(10, rng.Next(1, 6)), ref fast);
            }
            for (var bits = 0x3F000000; bits < 0x3F000000 + 2_000_000; bits++, total++) Check(BitConverter.Int32BitsToSingle(bits), ref fast);
            Assert.True(fast > total / 4, $"fast path taken {fast} of {total}");
        }
    }
}

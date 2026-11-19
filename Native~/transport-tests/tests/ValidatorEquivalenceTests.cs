// Tests that the allocation-free validator reaches exactly the verdicts of the original.
using System;
using System.Collections.Generic;
using System.Text;
using Daliys.Analytics.Internal;
using Xunit;

namespace M7Transport.Tests
{
    /// <summary>The validator was rewritten to stop allocating on every Track; it must reach exactly the verdicts of the original.</summary>
    public class ValidatorEquivalenceTests
    {
        private static readonly string[] Alphabet = { "a", "z", "Q", "0", "_", " ", "\"", "\\", "\n", "<", "&", "\u00e9", "\u00df", "\u20ac", "\u2028", "\ud83d\ude00", "\ud800", "x" };

        private static string RandomText(Random random, int max)
        {
            var sb = new StringBuilder();
            for (var n = random.Next(0, max); n > 0; n--) sb.Append(Alphabet[random.Next(Alphabet.Length)]);
            return sb.ToString();
        }

        private static object RandomValue(Random random)
        {
            switch (random.Next(14))
            {
                case 0: return null;
                case 1: return RandomText(random, 40);
                case 2: return random.Next(2) == 0;
                case 3: return random.Next();
                case 4: return (long)random.Next() * random.Next();
                case 5: return random.NextDouble() * Math.Pow(10, random.Next(-10, 25));
                case 6: return (float)(random.NextDouble() * 1000);
                case 7: return (uint)random.Next();
                case 8: return ulong.MaxValue - (ulong)random.Next();
                case 9: return (short)random.Next(short.MinValue, short.MaxValue);
                case 10: return (byte)random.Next(256);
                case 11: return (sbyte)random.Next(-128, 128);
                case 12: return (decimal)random.NextDouble() * 1000m;
                default: return random.Next(3) == 0 ? (object)double.NaN : new object();
            }
        }

        [Fact]
        public void EveryVerdictMatchesTheOriginal()
        {
            var random = new Random(20261024);
            for (var round = 0; round < 6000; round++)
            {
                var props = new Dictionary<string, object>();
                for (var n = random.Next(0, 12); n > 0; n--) props[random.Next(4) == 0 ? RandomText(random, 20) : "key_" + random.Next(100)] = RandomValue(random);
                IReadOnlyDictionary<string, object> asInterface = props;
                Assert.Equal(EventValidatorOld.HasValidProperties(asInterface), EventValidator.HasValidProperties(asInterface));
                Assert.Equal(EventValidatorOld.HasValidProperties(asInterface), EventValidator.HasValidProperties(new SortedDictionary<string, object>(props)is IReadOnlyDictionary<string, object> r ? r : asInterface));
            }
        }

        [Fact]
        public void TheEightKilobyteBudgetBitesAtTheSamePlace()
        {
            // strings sized around the limit, with multi-byte and escaped characters, must be accepted or refused exactly as before
            foreach (var unit in new[] { "a", "\u00e9", "\u20ac", "\ud83d\ude00", "\n", "<" })
                for (var count = 0; count < 1100; count += 17)
                {
                    var props = new Dictionary<string, object>();
                    for (var i = 0; i < 9; i++) props["k" + i] = string.Concat(System.Linq.Enumerable.Repeat(unit, count));
                    Assert.Equal(EventValidatorOld.HasValidProperties(props), EventValidator.HasValidProperties(props));
                }
        }
    }
}

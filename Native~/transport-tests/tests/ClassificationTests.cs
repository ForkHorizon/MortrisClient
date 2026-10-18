using System.Collections.Generic;
using Daliys.Analytics.Internal.Transport;
using Xunit;

namespace M7Transport.Tests
{
    public class ClassificationTests
    {
        [Fact]
        public void EveryVectorMatchesThePythonReferenceClassifier()
        {
            var vectors = MiniJson.ParseArray(TestSupport.FixtureText("classify.json"));
            Assert.True(vectors.Count > 30);
            foreach (Dictionary<string, object> vector in vectors)
            {
                var json = (string)vector["json"];
                var expected = int.Parse(((JsonNumber)vector["type"]).Lexeme);
                var plain = M7Event.Classify(MiniJson.Parse(json), false);
                Assert.True(expected == plain.Type, "type of " + json + ": expected " + expected + " got " + plain.Type);
                // With logical strings every string is a plain string; other types are unaffected.
                var logical = M7Event.Classify(MiniJson.Parse(json), true);
                Assert.Equal(expected == M7Catalog.TypeUuid || expected == M7Catalog.TypeHex ? M7Catalog.TypeString : expected, logical.Type);
            }
        }

        [Theory]
        [InlineData("9223372036854775808", M7Catalog.TypeUInt64)]
        [InlineData("-9223372036854775808", M7Catalog.TypeInt)]
        [InlineData("0.1", M7Catalog.TypeFloat64)]
        [InlineData("0.5", M7Catalog.TypeFloat32)]
        public void CriticalCases(string json, int type) => Assert.Equal(type, M7Event.Classify(MiniJson.Parse(json), false).Type);

        [Theory]
        [InlineData("18446744073709551616")]
        [InlineData("-9223372036854775809")]
        public void IntegersOutsideTheDomainAreRejected(string json) => Assert.Throws<System.FormatException>(() => M7Event.Classify(MiniJson.Parse(json), false));
    }
}

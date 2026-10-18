using System;
using System.Collections.Generic;
using Daliys.Analytics.Internal.Transport;
using Xunit;

namespace M7Transport.Tests
{
    public class MiniJsonTests
    {
        [Fact]
        public void ParsesNestedValuesAndKeepsNumberLexemes()
        {
            var root = MiniJson.ParseObject("{\"a\":[1,-2.50,1E+3,true,false,null],\"b\":{\"c\":\"x\\u00e9\\n\\\"\"}}");
            var list = (List<object>)root["a"];
            Assert.Equal("1", ((JsonNumber)list[0]).Lexeme);
            Assert.Equal("-2.50", ((JsonNumber)list[1]).Lexeme);
            Assert.Equal("1E+3", ((JsonNumber)list[2]).Lexeme);
            Assert.True((bool)list[3]);
            Assert.False((bool)list[4]);
            Assert.Null(list[5]);
            Assert.Equal("x\u00e9\n\"", ((Dictionary<string, object>)root["b"])["c"]);
        }

        [Theory]
        [InlineData("")]
        [InlineData("{")]
        [InlineData("{\"a\":1,\"a\":2}")]
        [InlineData("[1,]")]
        [InlineData("{\"a\":1} x")]
        [InlineData("01")]
        [InlineData("1.")]
        [InlineData("1e")]
        [InlineData("\"\\q\"")]
        [InlineData("\"abc")]
        [InlineData("tru")]
        [InlineData("[\"a\u0001\"]")]
        public void RejectsMalformedJson(string json) => Assert.Throws<FormatException>(() => MiniJson.Parse(json));

        [Fact]
        public void RejectsExcessiveNesting()
        {
            var deep = new string('[', 40) + new string(']', 40);
            Assert.Throws<FormatException>(() => MiniJson.Parse(deep));
        }

        [Fact]
        public void EscapeProducesRoundTrippableStrings()
        {
            const string original = "line\nquote\" back\\ tab\t \u0001 \u00e9 \ud83d\ude42";
            Assert.Equal(original, MiniJson.Parse(MiniJson.Escape(original)));
        }
    }
}

using System;
using System.IO;
using Daliys.Analytics.Internal.Transport;
using Xunit;

namespace M7Transport.Tests
{
    public class ExportTests
    {
        /// <summary>
        /// With M7_EXPORT_DIR set, writes the C#-encoded packets (and the alias tables they need) so the server repository can
        /// decode them with its own Go decoder. Skipped otherwise.
        /// </summary>
        [Fact]
        public void ExportsPacketsForTheServerDecoderTests()
        {
            var dir = Environment.GetEnvironmentVariable("M7_EXPORT_DIR");
            if (string.IsNullOrEmpty(dir)) return;
            Directory.CreateDirectory(dir);
            foreach (var variant in new[] { "plain", "logical" })
                foreach (var profile in new[] { "low", "high", "wide" })
                {
                    var catalog = M7Catalog.Parse(TestSupport.FixtureBytes("catalog-" + variant + ".json"));
                    var dictionary = TestSupport.FixtureBytes("dictionary-" + variant + ".bin");
                    var expected = (System.Collections.Generic.Dictionary<string, object>)MiniJson.Parse(TestSupport.FixtureText("expected-" + profile + ".json"));
                    var aliases = new M7Aliases();
                    using (var encoder = new M7EventEncoder(catalog, aliases, dictionary, (string)expected["origin"], new NativeZstdCompressor(dictionary)))
                    {
                        var result = encoder.Encode(TestSupport.FixtureText("batch-" + profile + ".json"));
                        Assert.True(result.Ok, result.Failure);
                        File.WriteAllBytes(Path.Combine(dir, $"packet-{variant}-{profile}.bin"), result.Frame);
                        File.WriteAllText(Path.Combine(dir, $"aliases-{variant}-{profile}.json"), "{\"epoch\":\"" + aliases.EpochHex + "\",\"records\":" + aliases.RecordsJson(0, aliases.Count) + "}");
                    }
                }
        }
    }
}

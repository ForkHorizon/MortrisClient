// EditMode tests of the browser gzip writer: stored-block gzip must read back with any gzip reader.
using Daliys.Analytics.Internal.Web;
using NUnit.Framework;

namespace Daliys.Analytics.Internal
{
    public sealed class WebGzipTests
    {
        [TestCase(0)]
        [TestCase(1)]
        [TestCase(65535)]
        [TestCase(65536)]
        [TestCase(200000)]
        public void StoredGzipIsReadableByAnyGzipReader(int size)
        {
            var data = new byte[size];
            new System.Random(size).NextBytes(data);
            using (var input = new System.IO.Compression.GZipStream(new System.IO.MemoryStream(WebGzip.Stored(data)), System.IO.Compression.CompressionMode.Decompress))
            using (var output = new System.IO.MemoryStream())
            {
                input.CopyTo(output);
                Assert.That(output.ToArray(), Is.EqualTo(data));
            }
        }

        [Test]
        public void Crc32MatchesTheStandardCheckValue() => Assert.That(WebGzip.Crc32(System.Text.Encoding.ASCII.GetBytes("123456789")), Is.EqualTo(0xCBF43926u));
    }
}

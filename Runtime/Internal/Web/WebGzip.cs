// gzip for the browser build, where System.IO.Compression may have no zlib behind it.
using System;
using System.IO;
using System.IO.Compression;
using System.Text;

namespace Daliys.Analytics.Internal.Web
{
    /// <summary>
    /// The V1 batch endpoint takes gzip only. A WebGL player's <see cref="GZipStream"/> needs a native zlib that Unity does not document for the Web platform,
    /// so the first failure switches to <see cref="Stored"/> for the rest of the session: a valid gzip member whose deflate blocks are stored, not compressed.
    /// </summary>
    internal static class WebGzip
    {
        private static bool _streamUnavailable;

        internal static byte[] Compress(string text)
        {
            var data = new UTF8Encoding(false).GetBytes(text);
            if (!_streamUnavailable)
            {
                try
                {
                    using (var output = new MemoryStream(data.Length / 3 + 64))
                    {
                        using (var gzip = new GZipStream(output, CompressionLevel.Fastest, true)) gzip.Write(data, 0, data.Length);
                        return output.ToArray();
                    }
                }
                catch (Exception) // DllNotFoundException, EntryPointNotFoundException, NotSupportedException...: no zlib in this player
                {
                    _streamUnavailable = true;
                }
            }
            return Stored(data);
        }

        /// <summary>RFC 1952 gzip around RFC 1951 stored blocks (at most 65 535 bytes each): 18 bytes plus 5 per block over the input.</summary>
        internal static byte[] Stored(byte[] data)
        {
            const int Block = 65535;
            var blocks = Math.Max(1, (data.Length + Block - 1) / Block);
            var output = new byte[10 + data.Length + 5 * blocks + 8];
            output[0] = 0x1f; output[1] = 0x8b; output[2] = 8; output[9] = 0xff; // deflate, no flags, no mtime, unknown OS
            var position = 10;
            for (var offset = 0; blocks-- > 0; offset += Block)
            {
                var length = Math.Min(Block, data.Length - offset);
                output[position++] = (byte)(blocks == 0 ? 1 : 0); // BFINAL on the last block, BTYPE 00 (stored)
                output[position++] = (byte)length; output[position++] = (byte)(length >> 8);
                output[position++] = (byte)~length; output[position++] = (byte)(~length >> 8);
                Buffer.BlockCopy(data, offset, output, position, length);
                position += length;
            }
            WriteUInt32(output, position, Crc32(data));
            WriteUInt32(output, position + 4, (uint)data.Length);
            return output;
        }

        private static readonly uint[] Table = BuildTable();

        private static uint[] BuildTable()
        {
            var table = new uint[256];
            for (uint n = 0; n < 256; n++)
            {
                var c = n;
                for (var k = 0; k < 8; k++) c = (c & 1) != 0 ? 0xEDB88320u ^ (c >> 1) : c >> 1;
                table[n] = c;
            }
            return table;
        }

        internal static uint Crc32(byte[] data)
        {
            var crc = 0xFFFFFFFFu;
            foreach (var b in data) crc = Table[(crc ^ b) & 0xFF] ^ (crc >> 8);
            return crc ^ 0xFFFFFFFFu;
        }

        private static void WriteUInt32(byte[] buffer, int at, uint value)
        {
            buffer[at] = (byte)value; buffer[at + 1] = (byte)(value >> 8); buffer[at + 2] = (byte)(value >> 16); buffer[at + 3] = (byte)(value >> 24);
        }
    }
}

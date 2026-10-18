using System;
using System.Security.Cryptography;

namespace Daliys.Analytics.Internal.Transport
{
    /// <summary>
    /// Builds one M7 packet: "M7", flags, compression mode, catalog id, alias epoch, dictionary id, row count, raw size,
    /// body (zstd when smaller, else raw), CRC32 of everything before it. Mirrors the research FrameEncoder; the server
    /// decoder (internal/transportv7) is the authority on what is accepted.
    /// </summary>
    internal sealed class M7FrameEncoder : IDisposable
    {
        internal const int MaxRaw = 2097152, MaxFrame = 262144, MaxRows = 500;
        private const int InitialRaw = 64 * 1024;
        private static readonly uint[] CrcTable = CreateCrcTable();

        private readonly M7Columns _columns = new M7Columns();
        private readonly IM7Compressor _compressor;
        private readonly byte[] _catalogId, _aliasEpoch, _dictionaryId = new byte[8];
        private readonly bool _numeric, _strings;
        private readonly byte _flags;
        private byte[] _raw = new byte[InitialRaw];

        internal M7FrameEncoder(IM7Compressor compressor, byte[] catalogId, byte[] aliasEpoch, byte[] dictionary, bool integerModel, bool stringModel)
        {
            if (compressor == null || catalogId == null || catalogId.Length != 8 || aliasEpoch == null || aliasEpoch.Length != 8 ||
                (dictionary != null && dictionary.Length > MaxRaw))
                throw new ArgumentException("Invalid transport assets.");
            _compressor = compressor;
            _catalogId = (byte[])catalogId.Clone();
            _aliasEpoch = (byte[])aliasEpoch.Clone();
            _numeric = integerModel;
            _strings = stringModel;
            _flags = (byte)((integerModel ? 2 : 0) | (stringModel ? 4 : 0)); // flag 1 (legacy event ids) is never used
            if (dictionary != null && dictionary.Length > 0)
                using (var sha = SHA256.Create())
                    Buffer.BlockCopy(sha.ComputeHash(dictionary), 0, _dictionaryId, 0, 8);
        }

        /// <summary>Returns false when the rows cannot be packed (unsupported value, oversize); the caller falls back to V1.</summary>
        internal bool TryPack(M7Row[] rows, int[] columnTypes, out byte[] frame)
        {
            frame = null;
            int rawLength;
            while (true)
            {
                try { rawLength = _columns.Pack(rows, columnTypes, false, _raw, _numeric, _strings); break; }
                catch (M7CapacityException)
                {
                    if (_raw.Length >= MaxRaw) return false;
                    _raw = new byte[Math.Min(MaxRaw, _raw.Length * 2)];
                }
                catch (ArgumentException) { return false; }
                catch (OverflowException) { return false; }
            }

            var compressed = _compressor.Compress(_raw, rawLength);
            var useCompressed = compressed != null && compressed.Length < rawLength;
            var bodyLength = useCompressed ? compressed.Length : rawLength;
            var buffer = new byte[28 + 5 + 5 + bodyLength + 4];
            buffer[0] = (byte)'M'; buffer[1] = (byte)'7'; buffer[2] = _flags; buffer[3] = (byte)(useCompressed ? 1 : 0);
            Buffer.BlockCopy(_catalogId, 0, buffer, 4, 8);
            Buffer.BlockCopy(_aliasEpoch, 0, buffer, 12, 8);
            Buffer.BlockCopy(_dictionaryId, 0, buffer, 20, 8);
            var position = 28;
            WriteVarint(buffer, ref position, (uint)rows.Length);
            WriteVarint(buffer, ref position, (uint)rawLength);
            Buffer.BlockCopy(useCompressed ? compressed : _raw, 0, buffer, position, bodyLength);
            position += bodyLength;
            if (position + 4 > MaxFrame) return false;
            var crc = Crc(buffer, position);
            for (var i = 0; i < 4; i++) buffer[position++] = (byte)(crc >> (i * 8));
            frame = new byte[position];
            Buffer.BlockCopy(buffer, 0, frame, 0, position);
            return true;
        }

        public void Dispose() => _compressor.Dispose();

        private static void WriteVarint(byte[] target, ref int position, uint value)
        {
            while (value >= 128) { target[position++] = (byte)(value | 128); value >>= 7; }
            target[position++] = (byte)value;
        }

        internal static uint Crc(byte[] data, int length)
        {
            var crc = 0xffffffffu;
            for (var i = 0; i < length; i++) crc = CrcTable[(crc ^ data[i]) & 255] ^ (crc >> 8);
            return ~crc;
        }

        private static uint[] CreateCrcTable()
        {
            var table = new uint[256];
            for (uint i = 0; i < 256; i++)
            {
                var c = i;
                for (var j = 0; j < 8; j++) c = (c >> 1) ^ ((c & 1) != 0 ? 0xedb88320u : 0);
                table[i] = c;
            }
            return table;
        }
    }
}

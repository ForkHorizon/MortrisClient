using System;
using System.Runtime.InteropServices;
using System.Security.Cryptography;

// Research M7 sender. Catalog resolution/typed ingress and reliable delivery are outside this class.
public sealed unsafe class FrameEncoder : IDisposable
{
    public const int MaxRaw = 2097152, MaxFrame = 262144;
#if UNITY_ANDROID && !UNITY_EDITOR
    const string Zstd = "zstd";
#elif UNITY_EDITOR_OSX
    const string Zstd = "/opt/homebrew/opt/zstd/lib/libzstd.dylib";
#else
    const string Zstd = "libzstd";
#endif
    [DllImport(Zstd)] static extern IntPtr ZSTD_createCCtx();
    [DllImport(Zstd)] static extern IntPtr ZSTD_createCDict(byte* dictionary, UIntPtr size, int level);
    [DllImport(Zstd)] static extern UIntPtr ZSTD_compress_usingCDict(IntPtr ctx, byte* dst, UIntPtr capacity, byte* src, UIntPtr size, IntPtr dict);
    [DllImport(Zstd)] static extern UIntPtr ZSTD_compressCCtx(IntPtr ctx, byte* dst, UIntPtr capacity, byte* src, UIntPtr size, int level);
    [DllImport(Zstd)] static extern uint ZSTD_isError(UIntPtr code);
    [DllImport(Zstd)] static extern UIntPtr ZSTD_freeCCtx(IntPtr ctx);
    [DllImport(Zstd)] static extern UIntPtr ZSTD_freeCDict(IntPtr dict);
    readonly Columns columns = new Columns();
    readonly byte[] raw = new byte[MaxRaw], catalog, epoch, dictionaryId = new byte[8];
    readonly bool preserveIds, numeric, stringsModel;
    readonly byte flags;
    IntPtr context, dictionary;
    static readonly uint[] CrcTable = CreateCrcTable();

    public FrameEncoder(byte[] catalogId, byte[] aliasEpoch, byte[] dictionaryBytes, bool ids, bool integerModel, bool stringModel)
    {
        if (catalogId == null || catalogId.Length != 8 || aliasEpoch == null || aliasEpoch.Length != 8 || dictionaryBytes == null || dictionaryBytes.Length > MaxRaw)
            throw new ArgumentException("transport assets");
        catalog = (byte[])catalogId.Clone(); epoch = (byte[])aliasEpoch.Clone();
        preserveIds = ids; numeric = integerModel; stringsModel = stringModel;
        flags = (byte)((ids ? 1 : 0) | (integerModel ? 2 : 0) | (stringModel ? 4 : 0));
        if (dictionaryBytes.Length != 0)
        {
            using (SHA256 sha = SHA256.Create()) Buffer.BlockCopy(sha.ComputeHash(dictionaryBytes), 0, dictionaryId, 0, 8);
            fixed (byte* p = dictionaryBytes) dictionary = ZSTD_createCDict(p, (UIntPtr)dictionaryBytes.Length, 1);
            if (dictionary == IntPtr.Zero) throw new InvalidOperationException("zstd dictionary init");
        }
        context = ZSTD_createCCtx();
        if (context == IntPtr.Zero) { Dispose(); throw new InvalidOperationException("zstd context init"); }
    }
    static uint[] CreateCrcTable()
    {
        var table = new uint[256];
        for (uint i = 0; i < 256; i++) { uint c = i; for (int j = 0; j < 8; j++) c = (c >> 1) ^ ((c & 1) != 0 ? 0xedb88320u : 0); table[i] = c; }
        return table;
    }
    static uint Crc(byte[] data, int length)
    {
        uint crc = 0xffffffffu;
        for (int i = 0; i < length; i++) crc = CrcTable[(crc ^ data[i]) & 255] ^ (crc >> 8);
        return ~crc;
    }
    static void U(byte[] target, ref int p, uint value)
    {
        while (value >= 128) { target[p++] = (byte)(value | 128); value >>= 7; }
        target[p++] = (byte)value;
    }
    public bool TryPack(Row[] rows, int[] types, byte[] destination, out int length)
    {
        length = 0;
        if (context == IntPtr.Zero) throw new ObjectDisposedException(nameof(FrameEncoder));
        if (destination == null) throw new ArgumentNullException(nameof(destination));
        int limit = Math.Min(destination.Length, MaxFrame);
        if (limit < 38) return false;
        int rawLength;
        // Unsupported/oversized input returns to the caller for split/V1; no queue mutation occurs here.
        try { rawLength = columns.Pack(rows, types, preserveIds, raw, numeric, stringsModel); }
        catch (ArgumentException) { return false; }
        catch (OverflowException) { return false; }
        destination[0] = (byte)'M'; destination[1] = (byte)'7'; destination[2] = flags; destination[3] = 0;
        Buffer.BlockCopy(catalog, 0, destination, 4, 8); Buffer.BlockCopy(epoch, 0, destination, 12, 8); Buffer.BlockCopy(dictionaryId, 0, destination, 20, 8);
        int p = 28; U(destination, ref p, (uint)rows.Length); U(destination, ref p, (uint)rawLength);
        int capacity = limit - p - 4;
        if (capacity < 0) return false;
        UIntPtr compressed;
        fixed (byte* src = raw) fixed (byte* dst = destination)
            compressed = dictionary != IntPtr.Zero
                ? ZSTD_compress_usingCDict(context, dst + p, (UIntPtr)capacity, src, (UIntPtr)rawLength, dictionary)
                : ZSTD_compressCCtx(context, dst + p, (UIntPtr)capacity, src, (UIntPtr)rawLength, 1);
        if (ZSTD_isError(compressed) == 0 && compressed.ToUInt64() < (ulong)rawLength)
        {
            destination[3] = 1; p += checked((int)compressed.ToUInt64());
        }
        else
        {
            if (rawLength > capacity) return false;
            Buffer.BlockCopy(raw, 0, destination, p, rawLength); p += rawLength;
        }
        uint crc = Crc(destination, p);
        for (int i = 0; i < 4; i++) destination[p++] = (byte)(crc >> (i * 8));
        length = p; return true;
    }
    public void Dispose()
    {
        if (context != IntPtr.Zero) { ZSTD_freeCCtx(context); context = IntPtr.Zero; }
        if (dictionary != IntPtr.Zero) { ZSTD_freeCDict(dictionary); dictionary = IntPtr.Zero; }
    }
}

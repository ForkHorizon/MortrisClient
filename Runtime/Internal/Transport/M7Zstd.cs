// zstd compression of V7/V8 bodies with an optional project dictionary.
using System;
using System.Runtime.InteropServices;

namespace Daliys.Analytics.Internal.Transport
{
    /// <summary>Compresses a V7 body with an optional project dictionary.</summary>
    internal interface IM7Compressor : IDisposable
    {
        /// <summary>Compresses <paramref name="source"/>[0..length) into a new array, or returns null when it fails.</summary>
        byte[] Compress(byte[] source, int length);
    }

    /// <summary>
    /// Native zstd 1.5.7 (compression only, built from the pinned upstream source by Native~/zstd/build.sh) with a reusable
    /// context and an optional pre-digested dictionary. Level 1, like the research packets.
    /// </summary>
    internal sealed class NativeZstdCompressor : IM7Compressor
    {
        private const string Library = "daliys_zstd";
        private IntPtr _context;
        private IntPtr _dictionary;
        private const int CompressionLevelParameter = 100; // ZSTD_c_compressionLevel

        [DllImport(Library)] private static extern IntPtr ZSTD_createCCtx();
        [DllImport(Library)] private static extern IntPtr ZSTD_createCDict(byte[] dictionary, UIntPtr size, int level);
        [DllImport(Library)] private static extern UIntPtr ZSTD_CCtx_setParameter(IntPtr context, int parameter, int value);
        [DllImport(Library)] private static extern UIntPtr ZSTD_CCtx_refCDict(IntPtr context, IntPtr dictionary);
        [DllImport(Library)] private static extern UIntPtr ZSTD_compress2(IntPtr context, byte[] destination, UIntPtr capacity, byte[] source, UIntPtr size);
        [DllImport(Library)] private static extern UIntPtr ZSTD_compressBound(UIntPtr size);
        [DllImport(Library)] private static extern uint ZSTD_isError(UIntPtr code);
        [DllImport(Library)] private static extern UIntPtr ZSTD_freeCCtx(IntPtr context);
        [DllImport(Library)] private static extern UIntPtr ZSTD_freeCDict(IntPtr dictionary);

        internal NativeZstdCompressor(byte[] dictionary)
        {
            _context = ZSTD_createCCtx();
            if (_context == IntPtr.Zero) throw new InvalidOperationException("zstd context could not be created.");
            // Level and dictionary stay on the context for every ZSTD_compress2 call (the advanced API keeps both until a parameter reset).
            if (ZSTD_isError(ZSTD_CCtx_setParameter(_context, CompressionLevelParameter, 1)) != 0) Fail("zstd level could not be set.");
            if (dictionary == null || dictionary.Length == 0) return;
            _dictionary = ZSTD_createCDict(dictionary, (UIntPtr)dictionary.Length, 1);
            if (_dictionary == IntPtr.Zero || ZSTD_isError(ZSTD_CCtx_refCDict(_context, _dictionary)) != 0) Fail("zstd dictionary could not be loaded.");
        }

        private void Fail(string message)
        {
            Dispose();
            throw new InvalidOperationException(message);
        }

        public byte[] Compress(byte[] source, int length)
        {
            if (_context == IntPtr.Zero) throw new ObjectDisposedException(nameof(NativeZstdCompressor));
            var capacity = ZSTD_compressBound((UIntPtr)length);
            var buffer = new byte[checked((int)capacity.ToUInt64())];
            var written = ZSTD_compress2(_context, buffer, capacity, source, (UIntPtr)length);
            if (ZSTD_isError(written) != 0) return null;
            var result = new byte[checked((int)written.ToUInt64())];
            Buffer.BlockCopy(buffer, 0, result, 0, result.Length);
            return result;
        }

        public void Dispose()
        {
            if (_context != IntPtr.Zero) { ZSTD_freeCCtx(_context); _context = IntPtr.Zero; }
            if (_dictionary != IntPtr.Zero) { ZSTD_freeCDict(_dictionary); _dictionary = IntPtr.Zero; }
        }
    }
}

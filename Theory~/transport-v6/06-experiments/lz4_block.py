"""Research binding to installed liblz4. Caller frame carries the raw size."""
import ctypes as c
import ctypes.util

LIB = c.CDLL(ctypes.util.find_library('lz4'))
LIB.LZ4_compressBound.argtypes = [c.c_int]
LIB.LZ4_compressBound.restype = c.c_int
LIB.LZ4_compress_default.argtypes = [c.c_void_p, c.c_void_p, c.c_int, c.c_int]
LIB.LZ4_compress_default.restype = c.c_int
LIB.LZ4_decompress_safe.argtypes = [c.c_void_p, c.c_void_p, c.c_int, c.c_int]
LIB.LZ4_decompress_safe.restype = c.c_int

def compress(raw):
    dest = c.create_string_buffer(LIB.LZ4_compressBound(len(raw)))
    size = LIB.LZ4_compress_default(raw, dest, len(raw), len(dest))
    if size <= 0:
        raise ValueError('lz4 encode')
    return dest.raw[:size]

def decompress(raw, size):
    dest = c.create_string_buffer(size)
    actual = LIB.LZ4_decompress_safe(raw, dest, len(raw), size)
    if actual != size:
        raise ValueError('lz4 decode size')
    return dest.raw

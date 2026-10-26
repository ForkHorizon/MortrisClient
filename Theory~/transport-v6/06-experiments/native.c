/* Allocation-free integer column kernel; wire-identical to codec.integers.
   All buffers belong to caller. No heap, SHA, adaptive probability table. */
#include <stdint.h>
#include <stddef.h>
#include <limits.h>

static uint64_t zigzag(int64_t v) { return ((uint64_t)v << 1) ^ (uint64_t)-(v < 0); }
static size_t usize(uint64_t v) { size_t n = 1; while (v >= 128) { n++; v >>= 7; } return n; }
static int64_t value(const int64_t *x, size_t i, int delta) {
    /* Called only after overflow was excluded by the sizing pass. */
    return delta && i ? (int64_t)((__int128)x[i] - x[i-1]) : x[i];
}
static unsigned width(uint64_t x) { unsigned n = 0; while (x) { n++; x >>= 1; } return n; }
static size_t putu(uint8_t *out, uint64_t v) {
    size_t n = 0; while (v >= 128) { out[n++] = (uint8_t)(v | 128); v >>= 7; } out[n++] = (uint8_t)v; return n;
}
size_t mtb6_ints(const int64_t *x, size_t n, uint8_t *out, size_t cap) {
    if (n > 500 || (!x && n) || !out) return SIZE_MAX;
    if (!n) return 0;
    size_t best = SIZE_MAX; int chosen = -1; int64_t base = 0; unsigned bits = 0;
    for (int delta = 0; delta < 2; delta++) {
        int valid = 1; int64_t lo = INT64_MAX, hi = INT64_MIN; size_t var = 1;
        for (size_t i = 0; i < n; i++) {
            __int128 v = delta && i ? (__int128)x[i] - x[i-1] : x[i];
            if (v < INT64_MIN || v > INT64_MAX) { valid = 0; break; }
            int64_t w = (int64_t)v;
            if (w < lo) lo = w;
            if (w > hi) hi = w;
            var += usize(zigzag(w));
        }
        if (!valid) continue;
        unsigned w = width((uint64_t)hi - (uint64_t)lo);
        size_t packed = 2 + usize(zigzag(lo)) + (n*w+7)/8;
        if (var < best) { best = var; chosen = delta; }
        if (packed < best) { best = packed; chosen = delta+2; base = lo; bits = w; }
    }
    if (chosen < 0 || best > cap) return SIZE_MAX;
    size_t pos = 0; out[pos++] = (uint8_t)chosen;
    if (chosen < 2) {
        for (size_t i = 0; i < n; i++) pos += putu(out+pos, zigzag(value(x, i, chosen)));
    } else {
        pos += putu(out+pos, zigzag(base)); out[pos++] = (uint8_t)bits;
        size_t bytes = (n*bits+7)/8;
        for (size_t i = 0; i < bytes; i++) out[pos+i] = 0;
        for (size_t i = 0; i < n; i++) {
            uint64_t v = (uint64_t)value(x, i, chosen-2) - (uint64_t)base;
            unsigned left = bits; size_t offset = i*bits;
            while (left) {
                unsigned shift = (unsigned)(offset & 7), take = 8-shift;
                if (take > left) take = left;
                out[pos+(offset>>3)] |= (uint8_t)((v & ((1u<<take)-1)) << shift);
                v >>= take; left -= take; offset += take;
            }
        }
        pos += bytes;
    }
    return pos;
}

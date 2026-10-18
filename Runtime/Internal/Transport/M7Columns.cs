using System;
using System.Collections.Generic;

namespace Daliys.Analytics.Internal.Transport
{

    /// <summary>Capacity of the caller-supplied output buffer was exceeded (the caller may retry with a larger one).</summary>
    internal sealed class M7CapacityException : ArgumentException { internal M7CapacityException() : base("capacity") { } }

    // Column stage of the V7 codec, ported from the research implementation (Theory~/transport-v7/06-experiments/native/Columns.cs).
    // Typed input and all workspaces are prepared before Pack. No game names or keys: fields are catalog column numbers.
    internal struct M7Cell { public long I; public ulong U; public double D; public string S; }
    internal sealed class M7Row
    {
        public long Sequence, Time, Elapsed;
        public int Shape, Context, Session;
        public byte[] Id;
        public int[] Columns;
        public M7Cell[] Values;
    }
    internal sealed class M7Columns
    {
        readonly System.Text.UTF8Encoding utf8 = new System.Text.UTF8Encoding(false, true);
        readonly long[] work = new long[500], original = new long[500], bestValues = new long[500], integerValues = new long[500], integerIndices = new long[500];
        readonly M7Row[] owners = new M7Row[500];
        readonly Dictionary<long, int> integerUnique = new Dictionary<long, int>(500);
        bool integerModel, stringModel;
        readonly long[] prefixes = new long[500], suffixes = new long[500];
        readonly int[] textLengths = new int[500];
        readonly byte[] textTags = new byte[500], textA = new byte[8192], textB = new byte[8192];
        readonly long[] previousElapsed = new long[MaxSessions], previousTime = new long[MaxSessions];
        readonly bool[] previousSeen = new bool[MaxSessions];
        internal const int MaxSessions = 512;
        readonly M7Cell[] cells = new M7Cell[500];
        readonly int[] order = new int[16000];
        readonly bool[] seen = new bool[16000];
        readonly Dictionary<string, int> unique = new Dictionary<string, int>(500);
        readonly string[] strings = new string[500];
        byte[] output;
        int pos;
        void Byte(byte b) { if (pos == output.Length) throw new M7CapacityException(); output[pos++] = b; }
        void U(ulong v) { while (v >= 128) { Byte((byte)(v | 128)); v >>= 7; } Byte((byte)v); }
        static ulong Z(long v) => unchecked((ulong)((v << 1) ^ (v >> 63)));
        static int Cost(ulong v) { int n = 1; while (v >= 128) { v >>= 7; n++; } return n; }
        static long Value(long[] x, int i, bool delta) => delta && i > 0 ? checked(x[i] - x[i - 1]) : x[i];
        int Ints(int n, bool emit = true)
        {
            int best = int.MaxValue, mode = 0, width = 0;
            long floor = 0;
            // Same tie order as V6: direct varint, direct bits, delta varint, delta bits.
            for (int d = 0; d < 2; d++)
            {
                long min = long.MaxValue, max = long.MinValue;
                int cost = 1;
                bool valid = true;
                for (int i = 0; i < n; i++)
                {
                    if (d == 1 && i > 0 && ((work[i - 1] > 0 && work[i] < long.MinValue + work[i - 1]) || (work[i - 1] < 0 && work[i] > long.MaxValue + work[i - 1]))) { valid = false; break; }
                    long v = Value(work, i, d == 1);
                    min = Math.Min(min, v); max = Math.Max(max, v); cost += Cost(Z(v));
                }
                if (!valid) continue;
                if (cost < best) { best = cost; mode = d; }
                ulong range = unchecked((ulong)max - (ulong)min);
                int w = 0; for (ulong x = range; x != 0; x >>= 1) w++;
                cost = 2 + Cost(Z(min)) + (n * w + 7) / 8;
                if (cost < best) { best = cost; mode = d + 2; floor = min; width = w; }
            }
            if (!emit) return best;
            Byte((byte)mode);
            if (mode < 2) { for (int i = 0; i < n; i++) U(Z(Value(work, i, mode == 1))); return best; }
            U(Z(floor)); Byte((byte)width);
            int bits = 0; byte current = 0;
            for (int i = 0; i < n; i++)
            {
                ulong v = unchecked((ulong)Value(work, i, mode == 3) - (ulong)floor);
                for (int b = 0; b < width; b++)
                {
                    current |= (byte)(((v >> b) & 1) << bits);
                    if (++bits == 8) { Byte(current); bits = 0; current = 0; }
                }
            }
            if (bits != 0) Byte(current);
            return best;
        }
        void Numeric(int n)
        {
            for (int i = 0; i < n; i++) original[i] = work[i] = cells[i].I;
            int best = Ints(n, false), selected = 0;
            Array.Copy(work, bestValues, n);
            for (int mode = 1; mode <= 3; mode++)
            {
                bool valid = true;
                for (int i = 0; i < n; i++)
                {
                    long basis = mode == 1 ? owners[i].Time : mode == 2 ? owners[i].Sequence : owners[i].Elapsed;
                    if ((basis > 0 && original[i] < long.MinValue + basis) || (basis < 0 && original[i] > long.MaxValue + basis)) { valid = false; break; }
                    work[i] = original[i] - basis;
                }
                if (!valid) continue;
                int cost = Ints(n, false);
                if (cost < best) { best = cost; selected = mode; Array.Copy(work, bestValues, n); }
            }
            integerUnique.Clear(); int count = 0;
            for (int i = 0; i < n; i++)
            {
                if (!integerUnique.TryGetValue(original[i], out int ix)) { ix = count; integerUnique.Add(original[i], count); integerValues[count++] = original[i]; }
                integerIndices[i] = ix;
            }
            Array.Copy(integerValues, work, count); int tableCost = Cost((ulong)count) + Ints(count, false);
            Array.Copy(integerIndices, work, n); tableCost += Ints(n, false);
            if (tableCost < best) selected = 4;
            Byte((byte)selected);
            if (selected == 4)
            {
                U((ulong)count); Array.Copy(integerValues, work, count); Ints(count);
                Array.Copy(integerIndices, work, n); Ints(n);
            }
            else { Array.Copy(bestValues, work, n); Ints(n); }
        }
        void Bytes(byte[] data) { for (int i = 0; i < data.Length; i++) Byte(data[i]); }
        static int Hex(char c) => c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : throw new ArgumentException("hex");
        void Text(string s, int type)
        {
            if (type == 5 || type == 6)
            {
                if (type == 6) { if ((s.Length & 1) != 0) throw new ArgumentException("hex"); U((ulong)s.Length / 2); }
                int hi = -1, count = 0;
                for (int i = 0; i < s.Length; i++)
                {
                    if (type == 5 && s[i] == '-') continue;
                    int v = Hex(s[i]);
                    if (hi < 0) hi = v; else { Byte((byte)((hi << 4) | v)); hi = -1; count++; }
                }
                if (hi >= 0 || (type == 5 && count != 16)) throw new ArgumentException("uuid/hex");
                return;
            }
            // Strict UTF-8 encoder writes directly into caller-owned output.
            int length = utf8.GetByteCount(s);
            U((ulong)length);
            if (length > output.Length - pos) throw new M7CapacityException();
            pos += utf8.GetBytes(s.AsSpan(), output.AsSpan(pos));
        }
        static int BinaryTag(string s)
        {
            bool uuid = s.Length == 36;
            if (uuid)
                for (int i = 0; i < s.Length; i++)
                    if (i == 8 || i == 13 || i == 18 || i == 23) { if (s[i] != '-') { uuid = false; break; } }
                    else if (!LowerHex(s[i])) { uuid = false; break; }
            if (uuid) return 1;
            if (s.Length == 0 || (s.Length & 1) != 0) return 0;
            foreach (char c in s) if (!LowerHex(c)) return 0;
            return 2;
        }
        static bool LowerHex(char c) => (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
        void Strings(int n, int count, int type)
        {
            Array.Copy(work, integerIndices, n); int indicesCost = Ints(n, false);
            int baseCost = Cost((ulong)count) + indicesCost, prefixCost = baseCost, mixedCost = baseCost, hexCost = baseCost;
            bool allUuid = true, allHex = true;
            byte[] current = textA, previous = textB; int previousLength = 0;
            for (int i = 0; i < count; i++)
            {
                string s = strings[i]; int length = utf8.GetByteCount(s);
                if (length > (type == 1 ? 1024 : 8192)) throw new ArgumentException("text limit");
                textLengths[i] = length; utf8.GetBytes(s.AsSpan(), current.AsSpan());
                int p = 0, suffix = 0;
                while (p < Math.Min(previousLength, length) && previous[p] == current[p]) p++;
                while (suffix < Math.Min(previousLength - p, length - p) && previous[previousLength - suffix - 1] == current[length - suffix - 1]) suffix++;
                prefixes[i] = p; suffixes[i] = suffix;
                int middle = length - p - suffix;
                baseCost += Cost((ulong)length) + length;
                prefixCost += Cost((ulong)middle) + middle;
                int tag = type == 1 ? BinaryTag(s) : 0; textTags[i] = (byte)tag;
                allUuid &= tag == 1; allHex &= tag == 2;
                int binaryLength = tag == 1 ? 16 : tag == 2 ? s.Length / 2 : length;
                int valueCost = tag == 1 ? 16 : Cost((ulong)binaryLength) + binaryLength;
                mixedCost += 1 + valueCost; hexCost += valueCost;
                byte[] swap = previous; previous = current; current = swap; previousLength = length;
            }
            Array.Copy(prefixes, work, count); prefixCost += Ints(count, false);
            Array.Copy(suffixes, work, count); prefixCost += Ints(count, false);
            int best = baseCost, mode = 0;
            if (prefixCost < best) { best = prefixCost; mode = 1; }
            int uuidCost = Cost((ulong)count) + indicesCost + count * 16;
            if (allUuid && uuidCost < best) { best = uuidCost; mode = 2; }
            if (allHex && hexCost < best) { best = hexCost; mode = 3; }
            if (type == 1 && mixedCost < best) mode = 4;
            Byte((byte)mode); U((ulong)count);
            if (mode == 1)
            {
                Array.Copy(prefixes, work, count); Ints(count);
                Array.Copy(suffixes, work, count); Ints(count);
                for (int i = 0; i < count; i++)
                {
                    utf8.GetBytes(strings[i].AsSpan(), textA.AsSpan());
                    int length = textLengths[i] - (int)prefixes[i] - (int)suffixes[i]; U((ulong)length);
                    for (int j = 0; j < length; j++) Byte(textA[(int)prefixes[i] + j]);
                }
            }
            else for (int i = 0; i < count; i++)
            {
                int tag = mode == 2 ? 1 : mode == 3 ? 2 : mode == 4 ? textTags[i] : 0;
                if (mode == 4) Byte((byte)tag);
                Text(strings[i], tag == 1 ? 5 : tag == 2 ? 6 : type);
            }
            Array.Copy(integerIndices, work, n); Ints(n);
        }
        void Values(int n, int type)
        {
            if (type == 0) { if (integerModel) Numeric(n); else { for (int i = 0; i < n; i++) work[i] = cells[i].I; Ints(n); } return; }
            if (type == 10) { for (int i = 0; i < n; i++) U(cells[i].U); return; }
            if (type == 7) return;
            if (type == 2)
            {
                for (int i = 0; i < n; i += 8) { byte b = 0; for (int j = 0; j < 8 && i + j < n; j++) b |= (byte)(cells[i + j].I << j); Byte(b); }
                return;
            }
            if (type == 3 || type == 4)
            {
                // shortcut: raw exact IEEE floats only; add V6's fixed-point option if profiling justifies it.
                Byte(0);
                for (int i = 0; i < n; i++)
                {
                    if ((double.IsNaN(cells[i].D) || double.IsInfinity(cells[i].D))) throw new ArgumentException("finite");
                    ulong bits = type == 3 ? unchecked((uint)BitConverter.SingleToInt32Bits((float)cells[i].D)) : unchecked((ulong)BitConverter.DoubleToInt64Bits(cells[i].D));
                    for (int j = 0; j < (type == 3 ? 4 : 8); j++) Byte((byte)(bits >> (8 * j)));
                }
                return;
            }
            if (type != 1 && type != 5 && type != 6 && type != 11) throw new ArgumentException("type");
            unique.Clear(); int count = 0;
            for (int i = 0; i < n; i++)
            {
                string s = cells[i].S;
                if (!unique.TryGetValue(s, out int ix)) { ix = count; unique.Add(s, count); strings[count++] = s; }
                work[i] = ix;
            }
            if (stringModel && (type == 1 || type == 11)) { Strings(n, count, type); return; }
            U((ulong)count);
            for (int i = 0; i < count; i++) Text(strings[i], type);
            Ints(n);
        }
        internal int Pack(M7Row[] rows, int[] types, bool ids, byte[] destination, bool numeric = false, bool stringsModel = false)
        {
            if (rows.Length < 1 || rows.Length > 500 || types.Length > seen.Length) throw new ArgumentException("bounds");
            integerModel = numeric; stringModel = stringsModel; output = destination; pos = 0; Array.Clear(seen, 0, seen.Length); Array.Clear(previousSeen, 0, previousSeen.Length); int nc = 0;
            for (int col = 0; col < 5; col++)
            {
                for (int i = 0; i < rows.Length; i++)
                {
                    M7Row r = rows[i];
                    long value = col == 0 ? r.Sequence : col == 1 ? r.Time : col == 2 ? r.Elapsed : col == 3 ? r.Shape : r.Context;
                    if (col == 2)
                    {
                        if (r.Session < 0 || r.Session >= previousSeen.Length) throw new ArgumentException("session");
                        if (previousSeen[r.Session]) value = checked(r.Elapsed - previousElapsed[r.Session] - r.Time + previousTime[r.Session]);
                        previousSeen[r.Session] = true; previousElapsed[r.Session] = r.Elapsed; previousTime[r.Session] = r.Time;
                    }
                    work[i] = value;
                }
                Ints(rows.Length);
            }
            if (ids) foreach (M7Row r in rows) { if (r.Id.Length != 16) throw new ArgumentException("id"); Bytes(r.Id); }
            foreach (M7Row r in rows)
            {
                if (r.Columns.Length != r.Values.Length) throw new ArgumentException("fields");
                foreach (int c in r.Columns) { if (c < 0 || c >= types.Length) throw new ArgumentException("column"); if (!seen[c]) { seen[c] = true; order[nc++] = c; } }
            }
            for (int c = 0; c < nc; c++)
            {
                int n = 0;
                foreach (M7Row r in rows) for (int j = 0; j < r.Columns.Length; j++) if (r.Columns[j] == order[c]) { owners[n] = r; cells[n++] = r.Values[j]; }
                Values(n, types[order[c]]);
            }
            return pos;
        }
    }
}

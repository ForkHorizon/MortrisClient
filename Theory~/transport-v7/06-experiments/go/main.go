// Independent bounded value-column decoder for C#/Python fixture parity.
package main

/*
#cgo CFLAGS: -I/opt/homebrew/opt/zstd/include
#cgo LDFLAGS: -L/opt/homebrew/opt/zstd/lib -lzstd
#include <zstd.h>
*/
import "C"
import (
	"bytes"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"strings"
	"unicode/utf8"
	"unsafe"
)

type row struct {
	Sequence, Time, Elapsed int64
	Shape, Context, Session int
	ID                      string
	Columns                 []int
	Values                  []json.RawMessage
}
type fixture struct {
	Types        []int
	Rows         []row
	PreserveIDs  bool `json:"preserve_ids"`
	IntegerModel bool `json:"integer_model"`
	StringModel  bool `json:"string_model"`
}
type reader struct {
	b []byte
	p int
}

func (r *reader) take(n int) []byte {
	if n < 0 || n > len(r.b)-r.p {
		panic("truncated")
	}
	b := r.b[r.p : r.p+n]
	r.p += n
	return b
}
func (r *reader) u() uint64 {
	var x uint64
	for i := 0; i < 10; i++ {
		b := r.take(1)[0]
		if i == 9 && b > 1 {
			panic("varint")
		}
		x |= uint64(b&127) << uint(i*7)
		if b < 128 {
			if i > 0 && b == 0 {
				panic("noncanonical")
			}
			return x
		}
	}
	panic("varint")
}
func (r *reader) s() int64 { x := r.u(); return int64(x>>1) ^ -int64(x&1) }
func add(a, b int64) int64 {
	c := a + b
	if (b > 0 && c < a) || (b < 0 && c > a) {
		panic("integer overflow")
	}
	return c
}
func (r *reader) bits(n, width int) []uint64 {
	if n < 0 || n > 500 || width > 64 {
		panic("bits")
	}
	data := r.take((n*width + 7) / 8)
	v := make([]uint64, n)
	for i := range v {
		for j := 0; j < width; j++ {
			bit := i*width + j
			v[i] |= uint64((data[bit/8]>>uint(bit%8))&1) << uint(j)
		}
	}
	return v
}
func (r *reader) ints(n int) []int64 {
	mode := r.take(1)[0]
	out := make([]int64, n)
	if mode < 2 {
		for i := range out {
			out[i] = r.s()
		}
	} else if mode < 4 {
		lo := r.s()
		width := int(r.take(1)[0])
		for i, v := range r.bits(n, width) {
			out[i] = int64(uint64(lo) + v)
			if out[i] < lo {
				panic("packed range")
			}
		}
	} else {
		panic("mode")
	}
	if mode == 1 || mode == 3 {
		for i := 1; i < n; i++ {
			out[i] = add(out[i-1], out[i])
		}
	}
	return out
}
func (r *reader) numeric(owners []row) []any {
	n := len(owners)
	mode := r.take(1)[0]
	var values []int64
	if mode == 4 {
		count := r.u()
		if count == 0 || count > uint64(n) {
			panic("integer dictionary count")
		}
		table := r.ints(int(count))
		indices := r.ints(n)
		values = make([]int64, n)
		for i, index := range indices {
			if index < 0 || index >= int64(count) {
				panic("integer dictionary index")
			}
			values[i] = table[index]
		}
	} else if mode <= 3 {
		values = r.ints(n)
		if mode != 0 {
			for i, e := range owners {
				basis := e.Time
				if mode == 2 {
					basis = e.Sequence
				}
				if mode == 3 {
					basis = e.Elapsed
				}
				values[i] = add(values[i], basis)
			}
		}
	} else {
		panic("integer prediction mode")
	}
	out := make([]any, n)
	for i, v := range values {
		out[i] = v
	}
	return out
}
func (r *reader) blob() []byte {
	n := r.u()
	if n > 2097152 {
		panic("blob")
	}
	return r.take(int(n))
}
func (r *reader) values(n, t int) []any {
	out := make([]any, n)
	switch t {
	case 0:
		for i, v := range r.ints(n) {
			out[i] = v
		}
	case 10:
		for i := range out {
			out[i] = r.u()
		}
	case 2:
		for i, v := range r.bits(n, 1) {
			out[i] = v == 1
		}
	case 7:
	case 3, 4:
		mode := r.take(1)[0]
		if mode == 1 {
			for i, v := range r.ints(n) {
				x := float64(v) / 100
				if t == 3 {
					x = float64(float32(x))
				}
				out[i] = x
			}
		} else if mode == 0 {
			for i := range out {
				if t == 3 {
					out[i] = float64(math.Float32frombits(binary.LittleEndian.Uint32(r.take(4))))
				} else {
					out[i] = math.Float64frombits(binary.LittleEndian.Uint64(r.take(8)))
				}
			}
		} else {
			panic("float mode")
		}
	case 1, 5, 6, 11:
		count := r.u()
		if count > uint64(n) {
			panic("distinct count")
		}
		table := make([]string, count)
		for i := range table {
			if t == 5 {
				s := hex.EncodeToString(r.take(16))
				table[i] = s[:8] + "-" + s[8:12] + "-" + s[12:16] + "-" + s[16:20] + "-" + s[20:]
			} else if t == 6 {
				table[i] = hex.EncodeToString(r.blob())
			} else {
				table[i] = string(r.blob())
			}
		}
		for i, v := range r.ints(n) {
			if v < 0 || v >= int64(count) {
				panic("distinct index")
			}
			out[i] = table[v]
		}
	default:
		panic("type")
	}
	return out
}
func (r *reader) stringValues(n, t int) []any {
	if n < 1 || n > 500 || (t != 1 && t != 11) {
		panic("string bounds")
	}
	mode := r.take(1)[0]
	limit := 1024
	if t == 11 {
		limit = 8192
	}
	var out []any
	if mode == 0 {
		out = r.values(n, t)
	} else if mode == 2 || mode == 3 {
		if t != 1 {
			panic("binary string type")
		}
		kind := 5
		if mode == 3 {
			kind = 6
		}
		out = r.values(n, kind)
	} else if mode == 1 || mode == 4 {
		if mode == 4 && t != 1 {
			panic("binary string type")
		}
		count := r.u()
		if count == 0 || count > uint64(n) {
			panic("string count")
		}
		table := make([]string, int(count))
		var prefixes, suffixes []int64
		if mode == 1 {
			prefixes = r.ints(int(count))
			suffixes = r.ints(int(count))
		}
		var previous []byte
		total := 0
		for i := range table {
			var value []byte
			if mode == 1 {
				p, s := prefixes[i], suffixes[i]
				if p < 0 || s < 0 || p > int64(len(previous)) || s > int64(len(previous))-p {
					panic("string reference")
				}
				middle := r.blob()
				if int64(len(middle)) > int64(limit)-p-s {
					panic("expanded string")
				}
				value = append(value, previous[:int(p)]...)
				value = append(value, middle...)
				value = append(value, previous[len(previous)-int(s):]...)
			} else {
				switch r.take(1)[0] {
				case 0:
					value = r.blob()
				case 1:
					s := hex.EncodeToString(r.take(16))
					value = []byte(s[:8] + "-" + s[8:12] + "-" + s[12:16] + "-" + s[16:20] + "-" + s[20:])
				case 2:
					data := r.blob()
					if len(data) > 512 {
						panic("hex string limit")
					}
					value = []byte(hex.EncodeToString(data))
				default:
					panic("string tag")
				}
			}
			if len(value) > limit || !utf8.Valid(value) {
				panic("string limit/utf8")
			}
			total += len(value)
			if total > 2097152 {
				panic("expanded table")
			}
			table[i] = string(value)
			previous = value
		}
		out = make([]any, n)
		for i, v := range r.ints(n) {
			if v < 0 || v >= int64(count) {
				panic("string index")
			}
			out[i] = table[v]
		}
	} else {
		panic("string mode")
	}
	for _, v := range out {
		s := v.(string)
		if len(s) > limit || !utf8.ValidString(s) {
			panic("string limit/utf8")
		}
	}
	return out
}
func check(f fixture, raw []byte) {
	n := len(f.Rows)
	if n < 1 || n > 500 {
		panic("count")
	}
	r := reader{b: raw}
	streams := make([][]int64, 5)
	for i := range streams {
		streams[i] = r.ints(n)
	}
	prev := map[int]row{}
	for i, e := range f.Rows {
		elapsed := e.Elapsed
		if p, ok := prev[e.Session]; ok {
			elapsed = e.Elapsed - p.Elapsed - e.Time + p.Time
		}
		prev[e.Session] = e
		expected := []int64{e.Sequence, e.Time, elapsed, int64(e.Shape), int64(e.Context)}
		for j, v := range expected {
			if streams[j][i] != v {
				panic("metadata")
			}
		}
	}
	if f.PreserveIDs {
		for _, e := range f.Rows {
			id, err := hex.DecodeString(strings.ReplaceAll(e.ID, "-", ""))
			if err != nil || !bytes.Equal(id, r.take(16)) {
				panic("event id")
			}
		}
	}
	order := []int{}
	owners := map[int][]json.RawMessage{}
	rowOwners := map[int][]row{}
	for _, e := range f.Rows {
		for i, c := range e.Columns {
			if _, ok := owners[c]; !ok {
				order = append(order, c)
			}
			owners[c] = append(owners[c], e.Values[i])
			rowOwners[c] = append(rowOwners[c], e)
		}
	}
	for _, c := range order {
		if c < 0 || c >= len(f.Types) {
			panic("column")
		}
		t := f.Types[c]
		var values []any
		if f.IntegerModel && t == 0 {
			values = r.numeric(rowOwners[c])
		} else if f.StringModel && (t == 1 || t == 11) {
			values = r.stringValues(len(owners[c]), t)
		} else {
			values = r.values(len(owners[c]), t)
		}
		for i, v := range values {
			b := owners[c][i]
			var expected any
			switch t {
			case 0:
				var x int64
				if json.Unmarshal(b, &x) != nil {
					panic("expected int")
				}
				expected = x
			case 10:
				var x uint64
				if json.Unmarshal(b, &x) != nil {
					panic("expected uint")
				}
				expected = x
			case 3, 4:
				var x float64
				if json.Unmarshal(b, &x) != nil {
					panic("expected float")
				}
				if t == 3 {
					x = float64(float32(x))
				}
				if math.Float64bits(x) != math.Float64bits(v.(float64)) {
					panic("float bits")
				}
				continue
			default:
				if json.Unmarshal(b, &expected) != nil {
					panic("expected value")
				}
			}
			if v != expected {
				panic(fmt.Sprintf("value mismatch type%d got%v expected%v", t, v, expected))
			}
		}
	}
	if r.p != len(raw) {
		panic("trailing data")
	}
}
func main() {
	if len(os.Args) == 3 && os.Args[1] == "--frame-manifest" {
		runFrameManifest(os.Args[2])
		return
	}
	if len(os.Args) != 5 {
		panic("fixture dict compressed raw")
	}
	var f fixture
	input, err := os.ReadFile(os.Args[1])
	if err != nil {
		panic(err)
	}
	if json.Unmarshal(input, &f) != nil {
		panic("fixture")
	}
	d, err := os.ReadFile(os.Args[2])
	if err != nil {
		panic(err)
	}
	comp, err := os.ReadFile(os.Args[3])
	if err != nil {
		panic(err)
	}
	raw, err := os.ReadFile(os.Args[4])
	if err != nil {
		panic(err)
	}
	if len(raw) == 0 || len(raw) > 2097152 || len(comp) == 0 || len(comp) > 262144 || len(d) == 0 {
		panic("bounds")
	}
	out := make([]byte, len(raw))
	ctx := C.ZSTD_createDCtx()
	if ctx == nil {
		panic("context")
	}
	defer C.ZSTD_freeDCtx(ctx)
	size := C.ZSTD_decompress_usingDict(ctx, unsafe.Pointer(&out[0]), C.size_t(len(out)), unsafe.Pointer(&comp[0]), C.size_t(len(comp)), unsafe.Pointer(&d[0]), C.size_t(len(d)))
	if C.ZSTD_isError(size) != 0 || int(size) != len(out) || !bytes.Equal(raw, out) {
		panic("decompression")
	}
	check(f, out)
	fmt.Printf("{\"events\":%d,\"raw_bytes\":%d,\"go_column_parity\":true}\n", len(f.Rows), len(raw))
}

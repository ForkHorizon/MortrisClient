package main

/*
#define ZSTD_STATIC_LINKING_ONLY
#include <zstd.h>
static int v7_frame_header_ok(const void* src, size_t size, unsigned long long content) {
    ZSTD_FrameHeader h;
    size_t status = ZSTD_getFrameHeader(&h, src, size);
    return status == 0 && h.frameType == ZSTD_frame && h.frameContentSize == content &&
           h.windowSize <= 2097152 && ZSTD_findFrameCompressedSize(src, size) == size;
}
*/
import "C"
import (
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"hash/crc32"
	"io"
	"math"
	"math/big"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"
	"unsafe"
)

const maxM7Raw, maxM7Frame = 2097152, 262144

var contextKeys = []string{"session_id", "app_version", "build_number", "platform", "os_version", "device_class", "locale", "timezone_offset_minutes"}
var canonicalUUID = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`)
var jsonNumeric = regexp.MustCompile(`^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$`)

type schemaField struct {
	key  string
	kind int
}
type schemaShape struct {
	name   string
	fields []schemaField
}
type FrameDecoder struct {
	project                        string
	catalogID, epoch, dictionaryID [8]byte
	shapes                         []schemaShape
	records                        [][]any
	dictionary                     []byte
}
type DecodedBatch struct {
	ProjectID string           `json:"project_id"`
	Origin    string           `json:"origin_install"`
	Events    []map[string]any `json:"events"`
}

func decodeAsset(data []byte, target any) {
	if len(data) == 0 || len(data) > maxM7Raw || !utf8.Valid(data) {
		panic("asset size/UTF-8")
	}
	d := json.NewDecoder(bytes.NewReader(data))
	d.UseNumber()
	d.DisallowUnknownFields()
	if d.Decode(target) != nil {
		panic("asset JSON")
	}
	var extra any
	if d.Decode(&extra) != io.EOF {
		panic("asset trailing data")
	}
}
func validName(s string) bool {
	if len(s) < 1 || len(s) > 64 || s[0] < 'a' || s[0] > 'z' || s[len(s)-1] == '_' {
		return false
	}
	for i, c := range []byte(s) {
		if (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') {
			continue
		}
		if c != '_' || (i > 0 && s[i-1] == '_') {
			return false
		}
	}
	return true
}

// Assets come from the server's immutable project registry, never from packet-supplied authentication.
func NewFrameDecoder(catalog, aliases, dictionary []byte) (decoder *FrameDecoder, err error) {
	defer func() {
		if p := recover(); p != nil {
			decoder = nil
			err = fmt.Errorf("invalid M7 assets: %v", p)
		}
	}()
	var c struct {
		Project        string              `json:"project_id"`
		Events         map[string]int      `json:"events"`
		Keys           []string            `json:"keys"`
		Shapes         [][]json.RawMessage `json:"shapes"`
		Masks          []json.Number       `json:"masks"`
		LogicalStrings bool                `json:"logical_strings"`
	}
	decodeAsset(catalog, &c)
	if len(c.Project) < 1 || len(c.Project) > 128 || !utf8.ValidString(c.Project) || c.Events == nil || c.Keys == nil || c.Shapes == nil || c.Masks == nil || len(c.Shapes) > 16000 || len(c.Events) > 255 || len(c.Masks) != len(c.Shapes) {
		panic("catalog limits")
	}
	names := make([]string, 0, len(c.Events))
	for name := range c.Events {
		if !validName(name) {
			panic("event name")
		}
		names = append(names, name)
	}
	sort.Strings(names)
	for i, name := range names {
		if c.Events[name] != i+1 {
			panic("event enum")
		}
	}
	keys := map[string]int{}
	for i, key := range c.Keys {
		if !validName(key) || (i > 0 && c.Keys[i-1] >= key) {
			panic("catalog key order")
		}
		keys[key] = i
	}
	out := &FrameDecoder{project: c.Project, shapes: make([]schemaShape, len(c.Shapes))}
	sum := sha256.Sum256(catalog)
	copy(out.catalogID[:], sum[:8])
	seen := map[string]bool{}
	for i, raw := range c.Shapes {
		if len(raw) != 2 {
			panic("shape tuple")
		}
		var name string
		var fields [][]json.RawMessage
		if json.Unmarshal(raw[0], &name) != nil || json.Unmarshal(raw[1], &fields) != nil || fields == nil || c.Events[name] == 0 || len(fields) > 32 {
			panic("shape fields")
		}
		shape := schemaShape{name: name}
		mask := new(big.Int)
		for _, pair := range fields {
			var key string
			var kindValue *int
			if len(pair) != 2 || json.Unmarshal(pair[0], &key) != nil || json.Unmarshal(pair[1], &kindValue) != nil || kindValue == nil {
				panic("field tuple")
			}
			kind := *kindValue
			index, ok := keys[key]
			if !ok || (len(shape.fields) > 0 && shape.fields[len(shape.fields)-1].key >= key) || kind < 0 || kind > 11 || kind == 8 || kind == 9 {
				panic("field key/type")
			}
			shape.fields = append(shape.fields, schemaField{key, kind})
			mask.SetBit(mask, index, 1)
		}
		expected, ok := new(big.Int).SetString(string(c.Masks[i]), 10)
		if !ok || mask.Cmp(expected) != 0 {
			panic("shape mask")
		}
		signature := name
		for _, field := range shape.fields {
			signature += "|" + field.key + ":" + strconv.Itoa(field.kind)
		}
		if seen[signature] {
			panic("duplicate shape")
		}
		seen[signature] = true
		out.shapes[i] = shape
	}
	var a struct {
		Epoch   string  `json:"epoch"`
		Records [][]any `json:"records"`
	}
	decodeAsset(aliases, &a)
	epoch, e := hex.DecodeString(a.Epoch)
	if e != nil || len(epoch) != 8 || len(a.Records) > 65536 {
		panic("alias epoch/count")
	}
	copy(out.epoch[:], epoch)
	aliasesSeen := map[string]bool{}
	for _, record := range a.Records {
		if len(record) != len(contextKeys)+1 {
			panic("alias tuple")
		}
		for i, v := range record[:len(record)-1] {
			s, ok := v.(string)
			if !ok || !utf8.ValidString(s) || (i < 2 && !canonicalUUID.MatchString(s)) {
				panic("alias string/UUID")
			}
		}
		number, ok := record[len(record)-1].(json.Number)
		if !ok {
			panic("alias timezone type")
		}
		value, e := number.Int64()
		if e != nil || value < math.MinInt32 || value > math.MaxInt32 {
			panic("alias timezone range")
		}
		record[len(record)-1] = value
		encoded, e := json.Marshal(record)
		if e != nil || aliasesSeen[string(encoded)] {
			panic("duplicate alias")
		}
		aliasesSeen[string(encoded)] = true
	}
	out.records = a.Records
	if len(dictionary) > maxM7Raw {
		panic("dictionary budget")
	}
	out.dictionary = append([]byte(nil), dictionary...)
	if len(dictionary) > 0 {
		sum = sha256.Sum256(dictionary)
		copy(out.dictionaryID[:], sum[:8])
	}
	return out, nil
}

func subtract(a, b int64) int64 {
	if (b > 0 && a < math.MinInt64+b) || (b < 0 && a > math.MaxInt64+b) {
		panic("integer overflow")
	}
	return a - b
}
func addThree(a, b, c int64) int64 {
	// Add opposite signs first so a representable final result cannot overflow an intermediate sum.
	if (a > 0 && b > 0 && c < 0) || (a < 0 && b < 0 && c > 0) {
		return add(add(a, c), b)
	}
	return add(add(a, b), c)
}

type wireFloat float64

func (v wireFloat) MarshalJSON() ([]byte, error) {
	x := float64(v)
	if math.IsNaN(x) || math.IsInf(x, 0) {
		return nil, fmt.Errorf("nonfinite")
	}
	text := strconv.FormatFloat(x, 'g', -1, 64)
	if !strings.ContainsAny(text, ".eE") {
		text += ".0"
	}
	return []byte(text), nil
}

// Compare a decimal lexeme against the reference's finite-double bound without expanding huge exponents.
func validDecimal(text string) bool {
	if len(text) > 8192 || !jsonNumeric.MatchString(text) {
		return false
	}
	s := strings.TrimPrefix(text, "-")
	parts := strings.FieldsFunc(s, func(r rune) bool { return r == 'e' || r == 'E' })
	mantissa := parts[0]
	point := strings.IndexByte(mantissa, '.')
	if point < 0 {
		point = len(mantissa)
	}
	digits := strings.ReplaceAll(mantissa, ".", "")
	leading := len(digits) - len(strings.TrimLeft(digits, "0"))
	digits = digits[leading:]
	if len(digits) == 0 {
		return true
	}
	exponent := int64(0)
	if len(parts) == 2 {
		var e error
		exponent, e = strconv.ParseInt(parts[1], 10, 64)
		if e != nil {
			return strings.HasPrefix(parts[1], "-")
		}
	}
	bound := int64(308 - (point - leading - 1))
	if exponent != bound {
		return exponent < bound
	}
	maximum := "17976931348623157"
	n := len(digits)
	if n < len(maximum) {
		n = len(maximum)
	}
	for i := 0; i < n; i++ {
		a, b := byte('0'), byte('0')
		if i < len(digits) {
			a = digits[i]
		}
		if i < len(maximum) {
			b = maximum[i]
		}
		if a != b {
			return a < b
		}
	}
	return true
}

func (d *FrameDecoder) Decode(frame []byte, authorizedProject, authorizedOrigin string) (batch *DecodedBatch, err error) {
	defer func() {
		if p := recover(); p != nil {
			batch = nil
			err = fmt.Errorf("invalid M7 packet: %v", p)
		}
	}()
	if authorizedProject != d.project || !canonicalUUID.MatchString(authorizedOrigin) {
		panic("project/origin authorization")
	}
	if len(frame) < 36 || len(frame) > maxM7Frame || crc32.ChecksumIEEE(frame[:len(frame)-4]) != binary.LittleEndian.Uint32(frame[len(frame)-4:]) {
		panic("frame length/CRC")
	}
	r := reader{b: frame[:len(frame)-4]}
	if string(r.take(2)) != "M7" {
		panic("magic")
	}
	flags, compression := r.take(1)[0], r.take(1)[0]
	if flags&^byte(7) != 0 || compression > 1 || !bytes.Equal(r.take(8), d.catalogID[:]) || !bytes.Equal(r.take(8), d.epoch[:]) || !bytes.Equal(r.take(8), d.dictionaryID[:]) {
		panic("flags/assets")
	}
	count, size := r.u(), r.u()
	if count < 1 || count > 500 || size < 1 || size > maxM7Raw {
		panic("frame counts")
	}
	body := r.take(len(r.b) - r.p)
	raw := body
	if compression == 1 {
		if len(body) == 0 || C.v7_frame_header_ok(unsafe.Pointer(&body[0]), C.size_t(len(body)), C.ulonglong(size)) == 0 {
			panic("zstd frame size/window/trailing")
		}
		raw = make([]byte, int(size))
		ctx := C.ZSTD_createDCtx()
		if ctx == nil {
			panic("zstd context")
		}
		defer C.ZSTD_freeDCtx(ctx)
		var dictionary unsafe.Pointer
		if len(d.dictionary) > 0 {
			dictionary = unsafe.Pointer(&d.dictionary[0])
		}
		result := C.ZSTD_decompress_usingDict(ctx, unsafe.Pointer(&raw[0]), C.size_t(len(raw)), unsafe.Pointer(&body[0]), C.size_t(len(body)), dictionary, C.size_t(len(d.dictionary)))
		if C.ZSTD_isError(result) != 0 || uint64(result) != size {
			panic("zstd decode")
		}
	}
	if len(raw) != int(size) {
		panic("raw size")
	}
	return d.decodeBody(raw, int(count), flags, authorizedOrigin), nil
}

func (d *FrameDecoder) decodeBody(raw []byte, n int, flags byte, origin string) *DecodedBatch {
	r := reader{b: raw}
	streams := make([][]int64, 5)
	for i := range streams {
		streams[i] = r.ints(n)
	}
	sequences, times, elapsed, shapes, contexts := streams[0], streams[1], streams[2], streams[3], streams[4]
	ids := make([]string, n)
	if flags&1 != 0 {
		for i := range ids {
			s := hex.EncodeToString(r.take(16))
			ids[i] = s[:8] + "-" + s[8:12] + "-" + s[12:16] + "-" + s[16:20] + "-" + s[20:]
		}
	}
	result := &DecodedBatch{ProjectID: d.project, Origin: origin, Events: make([]map[string]any, n)}
	rows := make([]row, n)
	previous := map[string]row{}
	owners := map[schemaField][]int{}
	order := []schemaField{}
	for i := 0; i < n; i++ {
		if sequences[i] < 1 || (i > 0 && sequences[i] <= sequences[i-1]) || shapes[i] < 0 || shapes[i] >= int64(len(d.shapes)) || contexts[i] < 0 || contexts[i] >= int64(len(d.records)) || times[i] < -62135596800000 || times[i] > 253402300799999 {
			panic("metadata range")
		}
		record := d.records[contexts[i]]
		if record[0].(string) != origin {
			panic("alias origin authorization")
		}
		session := record[1].(string)
		value := elapsed[i]
		if old, ok := previous[session]; ok {
			value = addThree(value, old.Elapsed, subtract(times[i], old.Time))
		}
		rows[i] = row{Sequence: sequences[i], Time: times[i], Elapsed: value}
		previous[session] = rows[i]
		shape := d.shapes[shapes[i]]
		event := map[string]any{"name": shape.name, "sequence": sequences[i], "occurred_at_client": time.UnixMilli(times[i]).UTC().Format("2006-01-02T15:04:05.000Z"), "session_elapsed_ms": value, "properties": map[string]any{}}
		for j, key := range contextKeys {
			event[key] = record[j+1]
		}
		if flags&1 != 0 {
			event["event_id"] = ids[i]
		}
		result.Events[i] = event
		for _, field := range shape.fields {
			if _, ok := owners[field]; !ok {
				order = append(order, field)
			}
			owners[field] = append(owners[field], i)
		}
	}
	for _, field := range order {
		indices := owners[field]
		var values []any
		if field.kind == 0 && flags&2 != 0 {
			subset := make([]row, len(indices))
			for j, i := range indices {
				subset[j] = rows[i]
			}
			values = r.numeric(subset)
		} else if (field.kind == 1 || field.kind == 11) && flags&4 != 0 {
			values = r.stringValues(len(indices), field.kind)
		} else {
			values = r.values(len(indices), field.kind)
		}
		for j, index := range indices {
			v := values[j]
			if field.kind == 3 || field.kind == 4 {
				f := v.(float64)
				if math.IsNaN(f) || math.IsInf(f, 0) {
					panic("nonfinite float")
				}
				v = wireFloat(f)
			} else if field.kind == 11 {
				text := v.(string)
				if !validDecimal(text) {
					panic("numeric text")
				}
				v = json.Number(text)
			} else if field.kind == 1 || field.kind == 5 || field.kind == 6 {
				text := v.(string)
				if len(text) > 1024 || !utf8.ValidString(text) {
					panic("property string")
				}
			}
			result.Events[index]["properties"].(map[string]any)[field.key] = v
		}
	}
	if r.p != len(raw) {
		panic("trailing raw")
	}
	for _, event := range result.Events {
		data, err := json.Marshal(event["properties"])
		if err != nil || len(data) > 8192 {
			panic("property bytes")
		}
	}
	return result
}

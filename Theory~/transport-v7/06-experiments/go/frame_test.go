package main

import (
	"bytes"
	"encoding/binary"
	"encoding/json"
	"hash/crc32"
	"math"
	"testing"
)

func testInts(values ...int64) []byte {
	out := []byte{0}
	for _, v := range values {
		out = binary.AppendUvarint(out, uint64(v<<1)^uint64(v>>63))
	}
	return out
}
func testDecoder(t *testing.T) *FrameDecoder {
	catalog := []byte(`{"project_id":"test_project","events":{"event_a":1},"keys":[],"shapes":[["event_a",[]]],"masks":[0]}`)
	aliases := []byte(`{"epoch":"0102030405060708","records":[["00000000-0000-0000-0000-000000000001","00000000-0000-0000-0000-000000000002","1","1","test","os","device","en",0]]}`)
	d, err := NewFrameDecoder(catalog, aliases, nil)
	if err != nil {
		t.Fatal(err)
	}
	return d
}
func testRawFrame(d *FrameDecoder, n int, raw []byte) []byte {
	out := []byte{'M', '7', 0, 0}
	out = append(out, d.catalogID[:]...)
	out = append(out, d.epoch[:]...)
	out = append(out, d.dictionaryID[:]...)
	out = binary.AppendUvarint(out, uint64(n))
	out = binary.AppendUvarint(out, uint64(len(raw)))
	out = append(out, raw...)
	return binary.LittleEndian.AppendUint32(out, crc32.ChecksumIEEE(out))
}
func TestDecimalBounds(t *testing.T) {
	for _, s := range []string{"1.2300", "-0.000", "1e-99999999999999999999", "1.7976931348623157e308", "-1.7976931348623157e308", "0.000000000000000001"} {
		if !validDecimal(s) {
			t.Errorf("rejected valid decimal %q", s)
		}
	}
	for _, s := range []string{"NaN", "Inf", "1.797693134862315700001e308", "1.8e308", "1e99999999999999999999", "+1", "01", "1.", "1e", "[1]"} {
		if validDecimal(s) {
			t.Errorf("accepted invalid decimal %q", s)
		}
	}
}
func TestElapsedCancellationAtInt64Boundary(t *testing.T) {
	d := testDecoder(t)
	raw := testInts(1, 2)
	raw = append(raw, testInts(100, 0)...)
	raw = append(raw, testInts(math.MaxInt64, 100)...)
	raw = append(raw, testInts(0, 0)...)
	raw = append(raw, testInts(0, 0)...)
	batch, err := d.Decode(testRawFrame(d, 2, raw), "test_project", "00000000-0000-0000-0000-000000000001")
	if err != nil {
		t.Fatal(err)
	}
	if batch.Events[1]["session_elapsed_ms"] != int64(math.MaxInt64) {
		t.Fatal("elapsed reconstruction")
	}
}

func TestFrameRejectionAndJSONNumbers(t *testing.T) {
	d := testDecoder(t)
	origin := "00000000-0000-0000-0000-000000000001"
	raw := append(testInts(1), testInts(100)...)
	raw = append(raw, testInts(0)...)
	raw = append(raw, testInts(0)...)
	raw = append(raw, testInts(0)...)
	frame := testRawFrame(d, 1, raw)
	if _, err := d.Decode(frame, "test_project", origin); err != nil {
		t.Fatal(err)
	}
	for i := range frame {
		broken := append([]byte(nil), frame...)
		broken[i] ^= 128
		if _, err := d.Decode(broken, "test_project", origin); err == nil {
			t.Fatal("accepted corrupt byte", i)
		}
	}
	for _, body := range [][]byte{nil, testInts(-1), append(raw, 0)} {
		if _, err := d.Decode(testRawFrame(d, 1, body), "test_project", origin); err == nil {
			t.Fatal("accepted invalid raw")
		}
	}
	number, err := json.Marshal(wireFloat(math.Copysign(0, -1)))
	if err != nil || string(number) != "-0.0" {
		t.Fatal("signed zero JSON", string(number), err)
	}
	for _, n := range []float64{math.Inf(1), math.NaN()} {
		if _, err := json.Marshal(wireFloat(n)); err == nil {
			t.Fatal("accepted nonfinite")
		}
	}
	if _, err := d.Decode(frame, "other_project", origin); err == nil {
		t.Fatal("accepted foreign project")
	}
	if _, err := d.Decode(frame, "test_project", "00000000-0000-0000-0000-000000000009"); err == nil {
		t.Fatal("accepted foreign origin")
	}
	for _, catalog := range [][]byte{[]byte(`{}`), []byte(`{"project_id":"x","shapes":[[]]}`), bytes.Repeat([]byte{'x'}, maxM7Raw+1)} {
		if _, err := NewFrameDecoder(catalog, []byte(`{}`), nil); err == nil {
			t.Fatal("accepted invalid assets")
		}
	}
}

func FuzzFullFrameBoundary(f *testing.F) {
	f.Add([]byte{0, 2, 0, 0, 0, 0, 0, 0, 0, 0})
	f.Fuzz(func(t *testing.T, raw []byte) {
		if len(raw) > 8192 {
			t.Skip()
		}
		d := testDecoder(t)
		batch, err := d.Decode(testRawFrame(d, 1, raw), "test_project", "00000000-0000-0000-0000-000000000001")
		if err == nil {
			if batch == nil || len(batch.Events) != 1 {
				t.Fatal("invalid success")
			}
			if _, err := json.Marshal(batch); err != nil {
				t.Fatal("unserializable batch")
			}
		}
	})
}

func TestNullAndDuplicateCatalogShapes(t *testing.T) {
	aliases := []byte(`{"epoch":"0102030405060708","records":[]}`)
	for _, catalog := range []string{
		`{"project_id":"test_project","events":{"event_a":1},"keys":[],"shapes":[["event_a",null]],"masks":[0]}`,
		`{"project_id":"test_project","events":{"event_a":1},"keys":["counter"],"shapes":[["event_a",[["counter",null]]]],"masks":[1]}`,
		`{"project_id":"test_project","events":{"event_a":1},"keys":[],"shapes":[["event_a",[]],["event_a",[ ]]],"masks":[0,0]}`,
		`{"project_id":"test_project","events":{},"keys":null,"shapes":[],"masks":[]}`,
	} {
		if _, err := NewFrameDecoder([]byte(catalog), aliases, nil); err == nil {
			t.Fatal("accepted invalid catalog")
		}
	}
}

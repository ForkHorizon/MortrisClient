package main

import "testing"

func TestStringVectors(t *testing.T) {
	for _, raw := range [][]byte{
		{0, 1, 2, 0xc3, 0xa9, 0, 0},
		{1, 1, 0, 0, 0, 0, 2, 0xc3, 0xa9, 0, 0},
		{4, 1, 0, 2, 0xc3, 0xa9, 0, 0},
	} {
		r := reader{b: raw}
		got := r.stringValues(1, 1)
		if got[0] != "é" || r.p != len(raw) {
			t.Fatal("string vector", got, r.p)
		}
	}
}
func TestBadStringVectors(t *testing.T) {
	for _, raw := range [][]byte{
		{}, {255}, {1, 0}, {4, 0}, {4, 1, 255}, {4, 1, 0, 1, 255, 0, 0},
		{1, 1, 0, 2, 0, 0, 0, 0, 0}, {4, 1, 0, 0, 0, 2},
	} {
		func() {
			defer func() {
				if recover() == nil {
					t.Errorf("accepted invalid vector %x", raw)
				}
			}()
			r := reader{b: raw}
			r.stringValues(1, 1)
		}()
	}
}

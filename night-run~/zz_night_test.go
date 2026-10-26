package transportv7

// Night-run decode benchmark (NOT committed): decodes the packets produced by the C# bench with the server's Go decoder and reports CPU, allocations and memory.
import (
	"bufio"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"runtime"
	"sort"
	"syscall"
	"testing"
	"time"
)

func cpuNs() int64 {
	var r syscall.Rusage
	syscall.Getrusage(syscall.RUSAGE_SELF, &r)
	return r.Utime.Nano() + r.Stime.Nano()
}

func calib() float64 {
	buf := make([]int32, 1<<20)
	acc := uint64(1469598103934665603)
	t0 := cpuNs()
	for r := 0; r < 12; r++ {
		for i := 0; i < len(buf); i += 7 {
			acc = (acc ^ uint64(buf[(i*31+r)&(len(buf)-1)])) * 1099511628211
			buf[(i*17)&(len(buf)-1)] += int32(acc)
		}
	}
	if acc == 42 {
		fmt.Print("")
	}
	return float64(cpuNs()-t0) / (12.0 * float64(len(buf)/7))
}

func TestNightDecodeBench(t *testing.T) {
	dir, packets, out := os.Getenv("NIGHT_DIR"), os.Getenv("NIGHT_PACKETS"), os.Getenv("NIGHT_OUT")
	if dir == "" {
		t.Skip("night bench only")
	}
	catalog, _ := os.ReadFile(dir + "/catalog.json")
	dict, _ := os.ReadFile(dir + "/dictionary.bin")
	aliases := map[string][]byte{}
	af, _ := os.Open(packets + ".aliases.jsonl")
	sc := bufio.NewScanner(af)
	sc.Buffer(make([]byte, 64<<20), 64<<20)
	for sc.Scan() {
		var row struct {
			Origin  string          `json:"origin"`
			Aliases json.RawMessage `json:"aliases"`
		}
		if err := json.Unmarshal(sc.Bytes(), &row); err != nil {
			t.Fatal(err)
		}
		aliases[row.Origin] = []byte(row.Aliases)
	}
	f, _ := os.Open(packets)
	rd := bufio.NewReaderSize(f, 1<<20)
	decoders := map[string]*FrameDecoder{}
	var events, frames, bytesIn, failed int64
	var per []float64
	cal := calib()
	best := cal
	var m0, m1 runtime.MemStats
	runtime.GC()
	runtime.ReadMemStats(&m0)
	var cpuTotal int64
	var calibs []float64
	n := 0
	for {
		// BinaryWriter.Write(string) = 7-bit length prefix + UTF-8
		l, err := binary.ReadUvarint(rd)
		if err != nil {
			break
		}
		ob := make([]byte, l)
		io.ReadFull(rd, ob)
		var size int32
		binary.Read(rd, binary.LittleEndian, &size)
		fr := make([]byte, size)
		io.ReadFull(rd, fr)
		origin := string(ob)
		d := decoders[origin]
		if d == nil {
			d, err = NewFrameDecoder(catalog, aliases[origin], dict)
			if err != nil {
				t.Fatal(err)
			}
			decoders[origin] = d
		}
		c0 := cpuNs()
		b, derr := d.Decode(fr, "puzzle_gravity_test", origin)
		c1 := cpuNs()
		if derr != nil {
			failed++
			continue
		}
		cnt := int64(len(b.Events))
		events += cnt
		frames++
		bytesIn += int64(size)
		cpuTotal += c1 - c0
		per = append(per, float64(c1-c0)/float64(cnt))
		n++
		if n%5000 == 0 {
			c := calib()
			calibs = append(calibs, c)
			if c < best {
				best = c
			}
		}
	}
	runtime.ReadMemStats(&m1)
	var ru syscall.Rusage
	syscall.Getrusage(syscall.RUSAGE_SELF, &ru)
	sort.Float64s(per)
	p := func(q float64) float64 { return per[int(q*float64(len(per)-1))] }
	sum := 0.0
	for _, c := range calibs {
		sum += c
	}
	avgCal := best
	if len(calibs) > 0 {
		avgCal = sum / float64(len(calibs))
	}
	res := map[string]any{
		"events": events, "frames": frames, "failed_frames": failed, "bytes_in": bytesIn, "bytes_per_event": float64(bytesIn) / float64(events),
		"decode_cpu_ns_per_event": float64(cpuTotal) / float64(events), "p50_ns": p(.5), "p95_ns": p(.95), "p99_ns": p(.99),
		"alloc_bytes_per_event": float64(m1.TotalAlloc-m0.TotalAlloc) / float64(events), "mallocs_per_event": float64(m1.Mallocs-m0.Mallocs) / float64(events),
		"gc_cycles": m1.NumGC - m0.NumGC, "heap_inuse_mb": float64(m1.HeapInuse) / 1048576, "maxrss_mb": float64(ru.Maxrss) / 1048576,
		"calib_best_ns": best, "calib_mean_ns": avgCal, "decode_cpu_ns_per_event_load_corrected": float64(cpuTotal) / float64(events) * best / avgCal,
		"go": runtime.Version(), "gomaxprocs": runtime.GOMAXPROCS(0), "time": time.Now().Format(time.RFC3339),
	}
	b, _ := json.MarshalIndent(res, "", " ")
	os.WriteFile(out, b, 0o644)
	fmt.Println(string(b))
}

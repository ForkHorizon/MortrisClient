package transportv7

// Night-run V1 server-side decode baseline (NOT committed): gunzip + contracts.DecodeBatchIngestRequest on the same holdout batches.
import (
	"bufio"
	"bytes"
	"compress/gzip"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"runtime"
	"sort"
	"strings"
	"syscall"
	"testing"

	"github.com/ForkHorizon/Mortris/internal/contracts"
)

func TestNightV1DecodeBench(t *testing.T) {
	file, out := os.Getenv("NIGHT_BATCHES"), os.Getenv("NIGHT_OUT")
	if file == "" {
		t.Skip()
	}
	f, _ := os.Open(file)
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 64<<20), 64<<20)
	var events, bad, bytesIn, rejected int64
	var cpu, cpuGunzip int64
	var per []float64
	var m0, m1 runtime.MemStats
	runtime.GC()
	runtime.ReadMemStats(&m0)
	for sc.Scan() {
		line := sc.Text()
		if !strings.Contains(line[:40], `"holdout"`) {
			continue
		}
		var row struct {
			Origin string          `json:"origin"`
			Events json.RawMessage `json:"events"`
		}
		json.Unmarshal(sc.Bytes(), &row)
		var arr []json.RawMessage
		json.Unmarshal(row.Events, &arr)
		body := []byte(`{"schema_version":1,"project_id":"puzzle_gravity_test","install_id":"` + row.Origin + `","sdk":{"name":"daliys-analytics","version":"0.2.0"},"sent_at_client":"2026-10-20T00:00:00.000Z","events":` + string(row.Events) + `}`)
		var gz bytes.Buffer
		w, _ := gzip.NewWriterLevel(&gz, gzip.BestSpeed)
		w.Write(body)
		w.Close()
		bytesIn += int64(gz.Len())
		c0 := cpuNs()
		r, _ := gzip.NewReader(bytes.NewReader(gz.Bytes()))
		raw, _ := io.ReadAll(r)
		c1 := cpuNs()
		req, rej, err := contracts.DecodeBatchIngestRequest(raw)
		c2 := cpuNs()
		if err != nil {
			bad++
			continue
		}
		_ = req
		rejected += int64(len(rej))
		events += int64(len(arr))
		cpu += c2 - c0
		cpuGunzip += c1 - c0
		per = append(per, float64(c2-c0)/float64(len(arr)))
	}
	runtime.ReadMemStats(&m1)
	sort.Float64s(per)
	var ru syscall.Rusage
	syscall.Getrusage(syscall.RUSAGE_SELF, &ru)
	// TotalAlloc includes the bench's own body building; measured separately below by subtracting a build-only pass is not done: report as upper bound
	res := map[string]any{"events": events, "bad_batches": bad, "rejected_events": rejected, "gzip_bytes_per_event": float64(bytesIn) / float64(events),
		"v1_decode_cpu_ns_per_event": float64(cpu) / float64(events), "of_which_gunzip_ns_per_event": float64(cpuGunzip) / float64(events), "p50_ns": per[len(per)/2], "p99_ns": per[int(.99*float64(len(per)-1))],
		"alloc_bytes_per_event_upper_bound": float64(m1.TotalAlloc-m0.TotalAlloc) / float64(events), "maxrss_mb": float64(ru.Maxrss) / 1048576}
	b, _ := json.MarshalIndent(res, "", " ")
	os.WriteFile(out, b, 0o644)
	fmt.Println(string(b))
}

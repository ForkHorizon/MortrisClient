package main

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"time"

	"github.com/ForkHorizon/Mortris/internal/transportv7"
)

type request struct {
	Project string         `json:"project_id"`
	Catalog []byte         `json:"catalog"`
	Dictionary []byte      `json:"dictionary"`
	Streams []streamRecord `json:"streams"`
}

type streamRecord struct {
	Origin string          `json:"origin"`
	Epoch string           `json:"epoch"`
	Aliases json.RawMessage `json:"aliases"`
	Frames []frameRecord   `json:"frames"`
}

type frameRecord struct {
	BatchIndex int    `json:"batch_index"`
	Base64     string `json:"base64"`
}

type outputFrame struct {
	StreamIndex int              `json:"stream_index"`
	BatchIndex  int              `json:"batch_index"`
	Events      []map[string]any `json:"events"`
}

type output struct {
	OK                 bool          `json:"ok"`
	DecodedFrames      int           `json:"decoded_frames"`
	DecodedEvents      int           `json:"decoded_events"`
	DecodeNanoseconds  int64         `json:"decode_nanoseconds"`
	Frames             []outputFrame `json:"frames"`
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "trusted V7 decode verification failed; event details suppressed")
		os.Exit(2)
	}
}

func run() error {
	data, err := io.ReadAll(io.LimitReader(os.Stdin, 128<<20))
	if err != nil || len(data) == 0 {
		return fmt.Errorf("request")
	}
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.DisallowUnknownFields()
	var req request
	if dec.Decode(&req) != nil {
		return fmt.Errorf("request")
	}
	var extra any
	if dec.Decode(&extra) != io.EOF || req.Project == "" || len(req.Catalog) == 0 {
		return fmt.Errorf("request")
	}
	assets, err := transportv7.LoadAssets(req.Catalog, req.Dictionary)
	if err != nil || assets.Project() != req.Project {
		return fmt.Errorf("assets")
	}
	out := output{OK: true, Frames: make([]outputFrame, 0)}
	for streamIndex, stream := range req.Streams {
		aliases, err := json.Marshal(struct {
			Epoch   string          `json:"epoch"`
			Records json.RawMessage `json:"records"`
		}{Epoch: stream.Epoch, Records: stream.Aliases})
		if err != nil {
			return fmt.Errorf("aliases")
		}
		decoder, err := transportv7.NewFrameDecoder(req.Catalog, aliases, req.Dictionary)
		if err != nil {
			return fmt.Errorf("aliases")
		}
		for _, frame := range stream.Frames {
			packet, err := base64.StdEncoding.DecodeString(frame.Base64)
			if err != nil {
				return fmt.Errorf("frame")
			}
			start := time.Now()
			batch, err := decoder.Decode(packet, req.Project, stream.Origin)
			out.DecodeNanoseconds += time.Since(start).Nanoseconds()
			if err != nil || batch.ProjectID != req.Project || batch.Origin != stream.Origin {
				return fmt.Errorf("frame")
			}
			events := make([]map[string]any, 0, len(batch.Events))
			for _, event := range batch.Events {
				events = append(events, map[string]any{
					"sequence": event.Sequence, "occurred_at_client": event.OccurredAtClient,
					"session_elapsed_ms": event.SessionElapsedMs, "session_id": event.SessionID,
					"app_version": event.AppVersion, "build_number": event.BuildNumber,
					"platform": event.Platform, "os_version": event.OSVersion,
					"device_class": event.DeviceClass, "locale": event.Locale,
					"timezone_offset_minutes": event.TimezoneOffsetMinutes,
					"name": event.Name, "properties": event.Properties,
				})
			}
			out.DecodedFrames++
			out.DecodedEvents += len(events)
			out.Frames = append(out.Frames, outputFrame{StreamIndex: streamIndex, BatchIndex: frame.BatchIndex, Events: events})
		}
	}
	enc := json.NewEncoder(os.Stdout)
	enc.SetEscapeHTML(false)
	return enc.Encode(out)
}

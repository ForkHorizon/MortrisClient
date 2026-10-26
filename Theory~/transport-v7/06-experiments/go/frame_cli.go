package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

func runFrameManifest(path string) {
	var config struct {
		Groups []struct {
			Catalog, Aliases, Dictionary, Project, Origin string
			Jobs                                          []struct {
				Name, Frame, Output, Project, Origin string
				ExpectedError                        bool `json:"expected_error"`
			}
		}
	}
	read := func(path string) []byte {
		data, err := os.ReadFile(path)
		if err != nil {
			panic(err)
		}
		return data
	}
	if json.Unmarshal(read(path), &config) != nil || len(config.Groups) == 0 {
		panic("frame manifest")
	}
	total, events, rejected := 0, 0, 0
	for _, group := range config.Groups {
		decoder, err := NewFrameDecoder(read(group.Catalog), read(group.Aliases), read(group.Dictionary))
		if err != nil {
			panic(err)
		}
		for _, job := range group.Jobs {
			project, origin := group.Project, group.Origin
			if job.Project != "" {
				project = job.Project
			}
			if job.Origin != "" {
				origin = job.Origin
			}
			batch, err := decoder.Decode(read(job.Frame), project, origin)
			if job.ExpectedError {
				if err == nil {
					panic("accepted malformed frame: " + job.Name)
				}
				rejected++
				continue
			}
			if err != nil {
				panic(fmt.Sprintf("frame %s: %v", job.Name, err))
			}
			data, err := json.Marshal(batch)
			if err != nil {
				panic(err)
			}
			if os.MkdirAll(filepath.Dir(job.Output), 0700) != nil || os.WriteFile(job.Output, data, 0600) != nil {
				panic("decoded output")
			}
			total++
			events += len(batch.Events)
		}
	}
	fmt.Printf("{\"decoded_packets\":%d,\"decoded_events\":%d,\"rejected_packets\":%d}\n", total, events, rejected)
}

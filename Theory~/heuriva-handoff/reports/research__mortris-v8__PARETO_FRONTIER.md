# MORTRIS V8 Pareto evidence

No unified MORTRIS V8 frontier is established. Existing rows below have different evaluators and workloads, so they are shown as evidence points rather than ranked together.

| Evidence point | Payload bytes/event | Client CPU / allocations | Decode/server | Correctness and scope |
|---|---:|---|---|---|
| Heuriva frozen M7 replay | 16.926 vs reconstructed V1 118.824 | Encode 2.162x V1 host reference | Decode 0.729x V1 host reference | 14 measured rows passed the typed supported-field round trip; development cohort only; not a candidate-versus-M7 result. |
| Handoff V7, batch 100 | Reported 17.8 vs V1 gzip 158.0 | Host: about 7.7 µs/event, 21.6 KiB allocations/event; emulator/phone reports differ by runtime. | Separate Go decoder and PostgreSQL summaries report lower V7 decode/server CPU. | Distinct handoff workload; reported physical-phone section conflicts with the report opening; request size is not interface wire traffic. |
| Handoff V7, small batches | Reported 24.6 at batch 30; 41.9 at batch 10 | Not a paired multiobjective comparison. | Not reported for these batch points. | Test subset; workload size and cohort differ from batch-100 analysis. |

No point is independently confirmed for V8. Do not combine points across cohorts or runtimes, and do not call V1-relative results an M7 improvement. A candidate enters the frontier only after exact correctness, same-workload paired measures, and an uncontaminated installation/session-disjoint confirmation result.

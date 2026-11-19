# MORTRIS M7/V7 baseline report

Status: historical evidence summarized on 2026-10-21; no new benchmark was run.

## Heuriva frozen frame replay

`docs/TELEMETRY_REAL_EXPERIMENTS.md` records the trusted run `mortris-v7-frame-verifier-recovery-20261020`:

- Frozen C# M7 encoder plus independent Go decoder; 152 installation-disjoint development installations and 74,559 sampled events.
- 14 successful measurements; all passed the typed supported-field round-trip check. 16 candidate rows were stored, with two unmeasured proposals.
- Best reported payload was 16.926 bytes/event versus 118.824 bytes/event for reconstructed V1 gzip-1 (85.76% lower). This is a development-cohort payload result, not a candidate improvement over M7.
- Encode CPU was 2.162x the V1 reference and decode CPU 0.729x on the measured host. Framed payload bytes include M7 framing, dictionary ID and CRC. HTTP/TLS, retries and captured network traffic were not measured.
- Original Mission remains failed due to an earlier verifier defect; the fresh recovery Mission completed after the verifier correction. The repeated run used the same development cohort and is not independent confirmation.

The recovered Study records and original failure are under ignored `.local/telemetry-research/mortris-v7-frame-verifier-recovery-20261020/`. No private event or per-installation rows are reproduced here.

## Separate MORTRIS V7 handoff measurements

The local handoff's `experiments/night-run~/REPORT.md` and `research/transport-v7/11-final-conclusions.md` report different experiments and must remain separate:

- A 2026-10-20 event corpus analysis reports 17.8 request/payload bytes per event for V7 versus 158.0 for V1 gzip at batch size 100. These are report-level application/request measurements, not interface-level network captures.
- The same night-run report lists host .NET encode CPU around 7.7 microseconds/event and 21.6 KiB/event allocations; it attributes most allocation/time to JSON parsing. These are host measurements.
- Unity IL2CPP emulator runs report V7/V1 CPU near parity for the tested queue path, higher V7 GC count, and similar PSS. The report also contains a Nothing A142 physical-phone section (CPU, GC and PSS), but its opening scope contradicts that section by stating there was no physical device. Do not merge or promote those phone numbers before reconciling the run artifacts.
- Server summaries report V7 decode at 6.7 microseconds/event and 7.8 KiB/event allocations versus V1 decode at 18.5 microseconds/event; Go/PostgreSQL end-to-end runs report lower server CPU for V7 but similar PostgreSQL cost. They are separate report workloads, not the Heuriva M7 Study.
- The final V7 research report describes a 2026-10-16 corpus with 524,934 events and an exposed 63,943-event holdout. Its candidate results include an identity migration and do not establish a production-ready protocol.

## Baseline identity and limitations

The repository baseline is frozen by the 2026-10-20 Heuriva report and current evaluator code at commit `1535b9f12bee9beb4693dc01323e889e89d9dd41`. The selected source digests and local handoff input digests are held in `.local/mortris-v8/data_manifest.json`. The handoff contains multiple snapshots; its own README reports differing event line counts. The historical M7 study supports only development evidence. There is no sealed fresh confirmation set and the prior held-out role is exposed.

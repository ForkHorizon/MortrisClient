# Architecture v2 - overview

Branch `daliys/architecture-v2`. Trigger: the 2026-10-22 four-hour MORTRIS campaign (82.5 of 240 min used, 26 of 240 Luna calls, 55 of 157 measurements repeated, 61% of wall time in seed studies, 4 of 20 studies failed on model-chosen `max_steps`) and `docs/ARCHITECTURE_FIELD_REVIEW_2026-10-22.md`. Evidence labels used in every v2 document: **Proposed / Implemented / Locally tested / CI verified / Live tested / Scientifically validated / Not yet qualified** (see `IMPLEMENTATION_STATUS.md`).

## Layers (what changed)
```
operator --(digest-approved campaign authorization)--> Campaign Supervisor            [campaign_supervisor, campaign_auth]
    evaluator lock  .  one-time domain probe  .  slots (window + call ceiling)  .  typed lifecycle verdicts  .  timing breakdown
      slot -> mission ROUNDS (separate missions only because a route manifest binds one mission), all sharing:
          CAMPAIGN KNOWLEDGE STORE  (one SQLite store for every round/segment/restart)           [campaign_knowledge]
          Mission Controller (lease, hash-chained journal, admission, routine_failures mode)      [mission_continuity]
            Director (Luna, strict schema DERIVED from the typed contract)                        [research_contract -> model_route_codex]
              action `measure`  : exact configs, paired repeats, dedupe, replication              [measure_worker]
              action `explore`  : bounded search of a region (existing study path)               [research_worker, unchanged engine]
              trusted code derives costs/limits; the model never names operational knobs          [research_contract.measure_plan, research_worker.normalize_params]
```

## Principles kept
General-purpose engine with domain behaviour behind typed interfaces (the M7 axes are read from `problems.telemetry.DOMAINS`, never retyped); models decide *what to investigate*, trusted code decides *how it runs and whether it counts*; autonomy means adapting to evidence, not filling time (a campaign that finds no new admissible work ends as `research_opportunities_exhausted`).

## Decision on agent roles (WP9)
Question: should the inner study researcher become a model? **No, not now.** The demonstrated limitation was not that the inner planner lacked intelligence but that the Director could not express the experiments it wanted (exact lists, repeats) and received poor evidence. Both are fixed at the Director interface (`measure`, uncertainty-bearing knowledge). A second model role would add ~15 s and a ledgered call per decision (measured: 15.3 s mean, 26 calls = 6.6 min), more context to keep consistent, and a new place for contract drift (the exact failure of P2/P4), for no demonstrated gain. Revisit only if the `explore` path (large/open spaces) shows a limitation the Director cannot resolve by choosing regions.

## Documents
`CAPABILITY_CONTRACT.md`, `RESEARCH_MEMORY.md`, `SCIENTIFIC_EVIDENCE.md`, `MISSION_LIFECYCLE.md`, `IMPLEMENTATION_STATUS.md`, `ACCEPTANCE_REPORT.md`, `REMAINING_WORK.md`.

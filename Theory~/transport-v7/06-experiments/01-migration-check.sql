-- Local/test DB migration design ONLY. No production UPDATE is supplied or run.
-- Gate new producer schema versions and derive before facts/BI sees these fields.
-- Query whether each observed omitted hash can be reconstructed (pgcrypto optional).
SELECT count(*) FILTER (WHERE properties ? 'placed_state_hash' AND NOT properties ? 'placed_block_ids') AS non_reconstructable,
       count(*) FILTER (WHERE properties ? 'wave_attempt_id' AND properties->>'wave_attempt_id' IS DISTINCT FROM properties->>'attempt_id') AS unequal_alias
FROM events WHERE project_id = 'puzzle_gravity_test';
-- interaction_id cannot be dropped until the game atomically persists its counter
-- before enqueue AND every consumer accepts a namespaced composite identifier.
-- Deriving SHA at ingestion preserves grouping, but loses the independent client
-- checksum signal. Keep mismatches and truncated-state hashes explicit.

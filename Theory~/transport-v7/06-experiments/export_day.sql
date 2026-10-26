BEGIN READ ONLY;
SET LOCAL statement_timeout = '90s';
COPY (SELECT row_to_json(e)::text FROM events e WHERE project_id='puzzle_gravity_test' AND received_at >= '2026-10-16T00:00:00Z'::timestamptz AND received_at < '2026-10-17T00:00:00Z'::timestamptz ORDER BY install_id, sequence, received_at) TO STDOUT;
ROLLBACK;

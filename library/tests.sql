-- Run after schema.sql and sample-data.sql in a fresh disposable database.
\set ON_ERROR_STOP on
\set skill_id '01900000-0000-7000-8000-000000000c02'
\set robot_model_id '01900000-0000-7000-8000-0000000000a2'
\set version_id '01900000-0000-7000-8000-000000000d03'

BEGIN;
SET LOCAL statement_timeout = '10s';

DO $$
DECLARE
  generated uuid;
  root_comment uuid;
  sample_version uuid := '01900000-0000-7000-8000-000000000d03';
BEGIN
  FOR i IN 1..1000 LOOP
    generated := rs_uuid7();
    IF generated::text !~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN
      RAISE EXCEPTION 'invalid UUID v7: %', generated;
    END IF;
    IF abs(('x' || substr(replace(generated::text, '-', ''), 1, 12))::bit(48)::bigint
           - floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint) > 1000 THEN
      RAISE EXCEPTION 'UUID timestamp does not match current milliseconds';
    END IF;
  END LOOP;

  IF (SELECT count(*) FROM skill_version) <> 4
     OR EXISTS (SELECT 1 FROM skill_version WHERE sha256 <> digest(packet, 'sha256')) THEN
    RAISE EXCEPTION 'expected four sample packets with matching digests';
  END IF;

  BEGIN
    UPDATE skill_version SET packet = packet || '\x01'::bytea WHERE version_id = sample_version;
    RAISE EXCEPTION 'packet corruption was accepted';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;

  BEGIN
    UPDATE skill_version SET sha256 = digest('wrong hash', 'sha256') WHERE version_id = sample_version;
    RAISE EXCEPTION 'incorrect digest was accepted';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;

  BEGIN
    UPDATE skill_version SET v_major = -1 WHERE version_id = sample_version;
    RAISE EXCEPTION 'negative semantic version component was accepted';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;

  BEGIN
    UPDATE robot SET public_key = '\x00' WHERE robot_id = '01900000-0000-7000-8000-0000000000b1';
    RAISE EXCEPTION 'invalid Ed25519 key length was accepted';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;

  BEGIN
    UPDATE robot_model_capability SET count = 0
    WHERE robot_model_id = '01900000-0000-7000-8000-0000000000a2' AND capability = 'ArmMotion';
    RAISE EXCEPTION 'zero capability count was accepted';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;

  SELECT comment_id INTO STRICT root_comment FROM comment WHERE version_id = sample_version;
  BEGIN
    INSERT INTO comment (version_id, author_id, parent_comment_id, body)
    VALUES ('01900000-0000-7000-8000-000000000d04',
            '01900000-0000-7000-8000-000000000002', root_comment, 'Wrong version');
    RAISE EXCEPTION 'cross-version comment reply was accepted';
  EXCEPTION WHEN foreign_key_violation THEN
    NULL;
  END;

  BEGIN
    UPDATE comment SET parent_comment_id = comment_id WHERE comment_id = root_comment;
    RAISE EXCEPTION 'self-reply was accepted';
  EXCEPTION WHEN check_violation THEN
    NULL;
  END;

  IF NOT EXISTS (
    SELECT 1 FROM skill_version_rank
    WHERE version_id = sample_version AND robots = 2 AND active_robots_30d = 2
      AND runs = 160 AND successes = 147 AND ratings = 1 AND stars_avg = 4
      AND success_score BETWEEN 0.85 AND 0.88 AND rank_score BETWEEN 0 AND 1
  ) THEN
    RAISE EXCEPTION 'sample ranking aggregates are incorrect';
  END IF;

  IF EXISTS (SELECT 1 FROM skill_version_rank WHERE rank_score NOT BETWEEN 0 AND 1)
     OR NOT EXISTS (
       SELECT 1 FROM skill_version_rank
       WHERE version_id = '01900000-0000-7000-8000-000000000d01' AND success_score = 0
     ) THEN
    RAISE EXCEPTION 'ranking bounds or zero-run score are incorrect';
  END IF;

  UPDATE skill_version SET status = 'withdrawn' WHERE version_id = sample_version;
  IF EXISTS (SELECT 1 FROM skill_version_rank WHERE version_id = sample_version) THEN
    RAISE EXCEPTION 'withdrawn version remained ranked before statistics refresh';
  END IF;
  UPDATE skill_version SET status = 'listed' WHERE version_id = sample_version;
END;
$$;

-- A deliberately cyclic variant family must not make query 5 recurse forever.
UPDATE skill SET parent_version_id = '01900000-0000-7000-8000-000000000d04'
WHERE skill_id = :'skill_id';

-- Deep replies, interleaved dates, and a visible child of a hidden parent.
INSERT INTO comment (comment_id, version_id, author_id, parent_comment_id, body, status, created_at) VALUES
  ('01900000-0000-7000-8000-000000000e01', :'version_id', '01900000-0000-7000-8000-000000000002',
   NULL, 'Thread A', 'visible', '2026-01-01 00:00:00Z'),
  ('01900000-0000-7000-8000-000000000e02', :'version_id', '01900000-0000-7000-8000-000000000002',
   '01900000-0000-7000-8000-000000000e01', 'Reply A', 'visible', '2026-01-03 00:00:00Z'),
  ('01900000-0000-7000-8000-000000000e03', :'version_id', '01900000-0000-7000-8000-000000000002',
   '01900000-0000-7000-8000-000000000e02', 'Nested reply A', 'visible', '2026-01-04 00:00:00Z'),
  ('01900000-0000-7000-8000-000000000e04', :'version_id', '01900000-0000-7000-8000-000000000002',
   NULL, 'Thread B', 'visible', '2026-01-02 00:00:00Z'),
  ('01900000-0000-7000-8000-000000000e05', :'version_id', '01900000-0000-7000-8000-000000000002',
   NULL, 'Hidden parent', 'hidden', '2026-01-05 00:00:00Z'),
  ('01900000-0000-7000-8000-000000000e06', :'version_id', '01900000-0000-7000-8000-000000000002',
   '01900000-0000-7000-8000-000000000e05', 'Visible orphan', 'visible', '2026-01-06 00:00:00Z');

SELECT encode(sha256, 'hex') AS sha256_hex FROM skill_version WHERE version_id = :'version_id' \gset

-- Exercise the actual example queries, including recursive traversal.
-- Expected: newest bottle version 1.1.0; matching hash lookup; two ranked
-- bottle candidates; grasp-object and lever-opener for the one-arm profile;
-- two family rows despite the cycle; threads A/reply/nested, B, visible orphan,
-- then the original sample comment.
\ir queries.sql

ROLLBACK;

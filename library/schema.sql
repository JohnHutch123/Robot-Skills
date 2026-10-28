-- Robot Skills (RS) library database, draft schema v0.1
-- Target: PostgreSQL 14 or later. Notes in docs/library-database.md say how
-- to adapt it to other databases (SQLite, MySQL, Firebird, SQL Server).
--
-- Identity rules
--   skill_id    UUID, stable for one line of versions of a skill (written in the skill file as `id`)
--   version_id  UUID, one per published version (assigned by the library)
--   sha256      hash of the signed packet bytes; the true identity of the content
-- All UUIDs are version 7 (RFC 9562): globally unique and time-ordered, so new
-- rows land at the end of indexes and inserts stay fast.

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid(), digest()

-- UUID version 7 generator (PostgreSQL 18 has uuidv7() built in).
CREATE OR REPLACE FUNCTION rs_uuid7() RETURNS uuid AS $$
  SELECT encode(
    set_bit(set_bit(
      overlay(uuid_send(gen_random_uuid())
              PLACING substring(int8send(floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint) FROM 3)
              FROM 1 FOR 6),
      52, 1), 53, 1),
    'hex')::uuid;
$$ LANGUAGE sql VOLATILE;

-- ---------------------------------------------------------------- people and robots

CREATE TABLE author (
  author_id     uuid PRIMARY KEY DEFAULT rs_uuid7(),
  display_name  text        NOT NULL,
  public_key    bytea       NOT NULL UNIQUE,            -- Ed25519, 32 bytes
  created_at    timestamptz NOT NULL DEFAULT now(),
  CHECK (octet_length(public_key) = 32)
);

CREATE TABLE robot_model (
  robot_model_id uuid PRIMARY KEY DEFAULT rs_uuid7(),
  name           text NOT NULL UNIQUE,                  -- e.g. 'generic-humanoid 1.0'
  maker          text,
  profile        text NOT NULL                          -- the robot profile (.rsk text)
);

-- A single robot. Its key signs usage reports. Owners are optional and private.
CREATE TABLE robot (
  robot_id        uuid PRIMARY KEY DEFAULT rs_uuid7(),
  robot_model_id  uuid NOT NULL REFERENCES robot_model,
  owner_author_id uuid REFERENCES author,
  public_key      bytea NOT NULL UNIQUE,
  region          char(2),                              -- country code only, never an address
  registered_at   timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- vocabularies

-- Class codes form an open-ended tree: '6', '6.1', '6.1.1', ...
CREATE TABLE skill_class (
  code        text PRIMARY KEY CHECK (code ~ '^[0-9]+(\.[0-9]+)*$'),
  parent_code text REFERENCES skill_class,
  name        text NOT NULL,
  description text,
  retired_at  timestamptz                               -- codes are never reused
);
CREATE INDEX skill_class_parent_idx ON skill_class (parent_code);

CREATE TABLE tag (
  tag_id  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  facet   text NOT NULL CHECK (facet IN ('domain','object','tool','body','material','risk')),
  value   text NOT NULL,
  UNIQUE (facet, value)
);

CREATE TABLE capability (
  name        text PRIMARY KEY,                         -- e.g. 'ForceSensing'
  description text
);

-- ---------------------------------------------------------------- skills

CREATE TABLE skill (
  skill_id          uuid PRIMARY KEY,                   -- from the skill file's `id` line
  name              text NOT NULL,                      -- e.g. 'open-bottle-with-opener'
  author_id         uuid NOT NULL REFERENCES author,
  class_code        text NOT NULL REFERENCES skill_class,
  title             text NOT NULL,
  parent_version_id uuid,                               -- set for variants; FK added below
  created_at        timestamptz NOT NULL DEFAULT now(),
  search            tsvector GENERATED ALWAYS AS
                      (to_tsvector('english', name || ' ' || title)) STORED
);
-- Prefix search on class codes: "everything under RS 6.1" uses this index.
CREATE INDEX skill_class_code_idx ON skill (class_code text_pattern_ops);
CREATE INDEX skill_author_idx     ON skill (author_id);
CREATE INDEX skill_search_idx     ON skill USING gin (search);

CREATE TABLE skill_version (
  version_id       uuid PRIMARY KEY DEFAULT rs_uuid7(),
  skill_id         uuid NOT NULL REFERENCES skill,
  semver           text NOT NULL,
  v_major          integer NOT NULL,
  v_minor          integer NOT NULL,
  v_patch          integer NOT NULL,
  sha256           bytea NOT NULL UNIQUE CHECK (octet_length(sha256) = 32),
  packet           bytea NOT NULL,                      -- the signed .rsp packet, usually 2-16 KB
  licence          text NOT NULL DEFAULT 'CC-BY-4.0' CHECK (licence IN ('CC-BY-4.0','CC0-1.0')),
  origin           text NOT NULL CHECK (origin IN ('written','recorded','learned')),
  status           text NOT NULL DEFAULT 'submitted'
                     CHECK (status IN ('submitted','testing','listed','rejected','withdrawn')),
  published_at     timestamptz NOT NULL DEFAULT now(),
  library_signed_at timestamptz,
  UNIQUE (skill_id, v_major, v_minor, v_patch)
);
CREATE INDEX skill_version_listed_idx ON skill_version (skill_id, v_major DESC, v_minor DESC, v_patch DESC)
  WHERE status = 'listed';

ALTER TABLE skill
  ADD CONSTRAINT skill_parent_fk FOREIGN KEY (parent_version_id) REFERENCES skill_version;
CREATE INDEX skill_parent_idx ON skill (parent_version_id);

CREATE TABLE skill_version_tag (
  version_id uuid    NOT NULL REFERENCES skill_version ON DELETE CASCADE,
  tag_id     integer NOT NULL REFERENCES tag,
  PRIMARY KEY (version_id, tag_id)
);
CREATE INDEX skill_version_tag_tag_idx ON skill_version_tag (tag_id, version_id);

CREATE TABLE skill_version_need (
  version_id uuid NOT NULL REFERENCES skill_version ON DELETE CASCADE,
  capability text NOT NULL REFERENCES capability,
  count      smallint NOT NULL DEFAULT 1 CHECK (count > 0),
  PRIMARY KEY (version_id, capability)
);

-- Nesting: which skills a version calls with `use`.
CREATE TABLE skill_version_use (
  version_id    uuid NOT NULL REFERENCES skill_version ON DELETE CASCADE,
  uses_skill_id uuid NOT NULL REFERENCES skill,
  version_range text NOT NULL,                          -- e.g. '>=1.0'
  PRIMARY KEY (version_id, uses_skill_id)
);
CREATE INDEX skill_version_use_rev_idx ON skill_version_use (uses_skill_id);

CREATE TABLE robot_model_capability (
  robot_model_id uuid NOT NULL REFERENCES robot_model ON DELETE CASCADE,
  capability     text NOT NULL REFERENCES capability,
  count          smallint NOT NULL DEFAULT 1,
  PRIMARY KEY (robot_model_id, capability)
);

-- ---------------------------------------------------------------- testing, use, ratings, comments

CREATE TABLE test_run (
  test_run_id    uuid PRIMARY KEY DEFAULT rs_uuid7(),
  version_id     uuid NOT NULL REFERENCES skill_version ON DELETE CASCADE,
  simulator      text NOT NULL,                         -- e.g. 'mujoco 3.2'
  robot_model_id uuid NOT NULL REFERENCES robot_model,
  runs           integer NOT NULL CHECK (runs > 0),
  passed         integer NOT NULL CHECK (passed BETWEEN 0 AND runs),
  ran_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX test_run_version_idx ON test_run (version_id);

-- Usage: one row per robot that adopted a version, updated from signed usage reports.
CREATE TABLE adoption (
  version_id    uuid NOT NULL REFERENCES skill_version ON DELETE CASCADE,
  robot_id      uuid NOT NULL REFERENCES robot,
  installed_at  timestamptz NOT NULL DEFAULT now(),
  last_used_at  timestamptz,
  runs          integer NOT NULL DEFAULT 0 CHECK (runs >= 0),
  successes     integer NOT NULL DEFAULT 0 CHECK (successes BETWEEN 0 AND runs),
  PRIMARY KEY (version_id, robot_id)
);
CREATE INDEX adoption_robot_idx ON adoption (robot_id);

-- One rating per author per version. The library only accepts a rating from an
-- author who owns a robot that has adopted the version (checked by the trigger below).
CREATE TABLE rating (
  version_id uuid     NOT NULL REFERENCES skill_version ON DELETE CASCADE,
  author_id  uuid     NOT NULL REFERENCES author,
  stars      smallint NOT NULL CHECK (stars BETWEEN 1 AND 5),
  rated_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (version_id, author_id)
);

CREATE OR REPLACE FUNCTION rs_rating_requires_adoption() RETURNS trigger AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM adoption a JOIN robot r ON r.robot_id = a.robot_id
    WHERE a.version_id = NEW.version_id AND r.owner_author_id = NEW.author_id
  ) THEN
    RAISE EXCEPTION 'rating rejected: author % has no robot that adopted version %',
      NEW.author_id, NEW.version_id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER rating_requires_adoption
  BEFORE INSERT OR UPDATE ON rating
  FOR EACH ROW EXECUTE FUNCTION rs_rating_requires_adoption();

CREATE TABLE comment (
  comment_id        uuid PRIMARY KEY DEFAULT rs_uuid7(),
  version_id        uuid NOT NULL REFERENCES skill_version ON DELETE CASCADE,
  author_id         uuid NOT NULL REFERENCES author,
  parent_comment_id uuid REFERENCES comment,            -- replies form threads
  body              text NOT NULL CHECK (length(body) BETWEEN 1 AND 10000),
  status            text NOT NULL DEFAULT 'visible' CHECK (status IN ('visible','hidden','deleted')),
  created_at        timestamptz NOT NULL DEFAULT now(),
  edited_at         timestamptz
);
CREATE INDEX comment_version_idx ON comment (version_id, created_at);

-- ---------------------------------------------------------------- fast summary for search and ranking

-- Refreshed periodically (for example every few minutes) so searches never
-- have to count millions of adoption or rating rows.
CREATE MATERIALIZED VIEW skill_version_stats AS
WITH a AS (
  SELECT version_id,
         count(*)                                                        AS robots,
         count(*) FILTER (WHERE last_used_at > now() - interval '30 days') AS active_robots_30d,
         coalesce(sum(runs), 0)                                          AS runs,
         coalesce(sum(successes), 0)                                     AS successes
  FROM adoption GROUP BY version_id
), r AS (
  SELECT version_id, count(*) AS ratings, avg(stars)::numeric(3,2) AS stars_avg, sum(stars) AS stars_sum
  FROM rating GROUP BY version_id
), c AS (
  SELECT version_id, count(*) AS comments FROM comment WHERE status = 'visible' GROUP BY version_id
)
SELECT v.version_id,
       coalesce(a.robots, 0)            AS robots,
       coalesce(a.active_robots_30d, 0) AS active_robots_30d,
       coalesce(a.runs, 0)              AS runs,
       coalesce(a.successes, 0)         AS successes,
       coalesce(r.ratings, 0)           AS ratings,
       r.stars_avg,
       coalesce(c.comments, 0)          AS comments,
       -- Success rate, cautious: Wilson lower bound (95%). Few runs => low score.
       CASE WHEN coalesce(a.runs, 0) = 0 THEN 0 ELSE
         ((a.successes::float8 / a.runs) + 1.9208 / a.runs
          - 1.96 * sqrt((a.successes::float8 / a.runs) * (1 - a.successes::float8 / a.runs) / a.runs
                        + 0.9604 / (a.runs::float8 * a.runs)))
         / (1 + 3.8416 / a.runs)
       END                               AS success_score,
       -- Rating, cautious: Bayesian average that pulls toward 3 stars until about 10 ratings exist.
       (coalesce(r.stars_sum, 0) + 3.0 * 10) / (coalesce(r.ratings, 0) + 10) AS rating_score
FROM skill_version v
LEFT JOIN a USING (version_id)
LEFT JOIN r USING (version_id)
LEFT JOIN c USING (version_id)
WHERE v.status = 'listed';

CREATE UNIQUE INDEX skill_version_stats_pk ON skill_version_stats (version_id);
-- Refresh with: REFRESH MATERIALIZED VIEW CONCURRENTLY skill_version_stats;

-- Overall ranking: success counts most, then breadth of adoption, then ratings.
CREATE VIEW skill_version_rank AS
SELECT s.*,
       0.5 * s.success_score
     + 0.3 * least(1.0, ln(1 + s.active_robots_30d) / ln(1001))   -- 1000 active robots = full marks
     + 0.2 * (s.rating_score - 1) / 4                              -- stars mapped to 0..1
       AS rank_score
FROM skill_version_stats s;

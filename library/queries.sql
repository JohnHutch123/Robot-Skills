-- Typical library queries for library/schema.sql. Each one is served by an index.
-- Parameters are written as :name (psql variables).

-- 1. Fetch a skill by its global ID, with its newest listed version.
SELECT s.skill_id, s.name, s.title, v.version_id, v.semver, v.sha256, v.packet
FROM skill s
JOIN LATERAL (
  SELECT * FROM skill_version v
  WHERE v.skill_id = s.skill_id AND v.status = 'listed'
  ORDER BY v_major DESC, v_minor DESC, v_patch DESC
  LIMIT 1
) v ON true
WHERE s.skill_id = :'skill_id';

-- 2. Fetch exactly the bytes a robot asked for, by content hash.
SELECT version_id, packet FROM skill_version WHERE sha256 = decode(:'sha256_hex', 'hex');

-- 3. Search: everything under a class (here RS 2), with a tag, ranked best first.
SELECT s.name, v.semver, r.robots, r.active_robots_30d, r.stars_avg,
       round(r.success_score::numeric, 3) AS success_score,
       round(r.rank_score::numeric, 3)    AS rank_score
FROM skill s
JOIN skill_version v        ON v.skill_id = s.skill_id AND v.status = 'listed'
JOIN skill_version_rank r   ON r.version_id = v.version_id
WHERE (s.class_code = '2' OR s.class_code LIKE '2.%')
  AND EXISTS (SELECT 1 FROM skill_version_tag vt JOIN tag t USING (tag_id)
              WHERE vt.version_id = v.version_id AND t.facet = 'object' AND t.value = 'bottle')
ORDER BY r.rank_score DESC
LIMIT 20;

-- 4. Listed versions a given robot model can run: every need is met by its capabilities.
SELECT s.name, v.semver
FROM skill_version v JOIN skill s USING (skill_id)
WHERE v.status = 'listed'
  AND NOT EXISTS (
    SELECT 1 FROM skill_version_need n
    LEFT JOIN robot_model_capability c
      ON c.capability = n.capability AND c.robot_model_id = :'robot_model_id'
    WHERE n.version_id = v.version_id AND (c.capability IS NULL OR c.count < n.count)
  )
ORDER BY s.name, v.v_major, v.v_minor, v.v_patch;

-- 5. Family tree: every variant descended from a skill, at any depth.
WITH RECURSIVE family AS (
  SELECT s.skill_id, s.name, s.parent_version_id, 0 AS depth
  FROM skill s WHERE s.skill_id = :'skill_id'
  UNION ALL
  SELECT c.skill_id, c.name, c.parent_version_id, f.depth + 1
  FROM family f
  JOIN skill_version pv ON pv.skill_id = f.skill_id
  JOIN skill c          ON c.parent_version_id = pv.version_id
)
SELECT depth, name, skill_id FROM family ORDER BY depth, name;

-- 6. Comments on a version, oldest first, with replies under their parent.
SELECT c.comment_id, c.parent_comment_id, a.display_name, c.created_at, c.body
FROM comment c JOIN author a USING (author_id)
WHERE c.version_id = :'version_id' AND c.status = 'visible'
ORDER BY coalesce(c.parent_comment_id, c.comment_id), c.created_at;

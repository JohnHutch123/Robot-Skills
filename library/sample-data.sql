-- Small sample data set for trying out library/schema.sql and library/queries.sql.
-- Keys and packets are dummy bytes.

INSERT INTO skill_class (code, parent_code, name) VALUES
  ('2', NULL, 'Changing quantity'), ('2.1', '2', 'Divide'), ('2.1.2', '2.1', 'Detach a part'),
  ('4', NULL, 'Securing'), ('4.1', '4', 'Hold'), ('4.1.1', '4.1', 'Grasp an object'),
  ('6', NULL, 'Processing'), ('6.1', '6', 'Press and smooth'), ('6.1.1', '6.1', 'Iron a garment');

INSERT INTO tag (facet, value) VALUES
  ('domain','kitchen'), ('domain','laundry'), ('object','bottle'), ('object','shirt'),
  ('tool','bottle-opener'), ('tool','iron'), ('body','two-hands'), ('risk','heat');

INSERT INTO capability (name) VALUES
  ('ArmMotion'), ('GripperMotion'), ('Grasping'), ('ForceSensing'), ('Camera'), ('Walking');

INSERT INTO author (author_id, display_name, public_key) VALUES
  ('01900000-0000-7000-8000-000000000001', 'A. Contributor', decode(repeat('01', 32), 'hex')),
  ('01900000-0000-7000-8000-000000000002', 'B. Tester',      decode(repeat('02', 32), 'hex'));

INSERT INTO robot_model (robot_model_id, name, profile) VALUES
  ('01900000-0000-7000-8000-0000000000a1', 'generic-humanoid 1.0', 'rs 0.1 ...'),
  ('01900000-0000-7000-8000-0000000000a2', 'one-arm-helper 1.0',   'rs 0.1 ...');

INSERT INTO robot_model_capability (robot_model_id, capability, count) VALUES
  ('01900000-0000-7000-8000-0000000000a1', 'ArmMotion', 2), ('01900000-0000-7000-8000-0000000000a1', 'GripperMotion', 2),
  ('01900000-0000-7000-8000-0000000000a1', 'Grasping', 1),  ('01900000-0000-7000-8000-0000000000a1', 'ForceSensing', 1),
  ('01900000-0000-7000-8000-0000000000a1', 'Camera', 1),    ('01900000-0000-7000-8000-0000000000a1', 'Walking', 1),
  ('01900000-0000-7000-8000-0000000000a2', 'ArmMotion', 1), ('01900000-0000-7000-8000-0000000000a2', 'GripperMotion', 1),
  ('01900000-0000-7000-8000-0000000000a2', 'Grasping', 1),  ('01900000-0000-7000-8000-0000000000a2', 'Camera', 1);

INSERT INTO robot (robot_id, robot_model_id, owner_author_id, public_key, region) VALUES
  ('01900000-0000-7000-8000-0000000000b1', '01900000-0000-7000-8000-0000000000a1', '01900000-0000-7000-8000-000000000002', decode(repeat('b1', 32), 'hex'), 'GB'),
  ('01900000-0000-7000-8000-0000000000b2', '01900000-0000-7000-8000-0000000000a1', NULL,                                   decode(repeat('b2', 32), 'hex'), 'DE');

-- Skills: grasp-object, open-bottle-with-opener, and a variant of the bottle skill.
INSERT INTO skill (skill_id, name, author_id, class_code, title) VALUES
  ('01900000-0000-7000-8000-000000000c01', 'grasp-object',            '01900000-0000-7000-8000-000000000001', '4.1.1', 'Grasp an object'),
  ('01900000-0000-7000-8000-000000000c02', 'open-bottle-with-opener', '01900000-0000-7000-8000-000000000001', '2.1.2', 'Open a capped bottle with a bottle opener');

INSERT INTO skill_version (version_id, skill_id, semver, v_major, v_minor, v_patch, sha256, packet, origin, status, library_signed_at) VALUES
  ('01900000-0000-7000-8000-000000000d01', '01900000-0000-7000-8000-000000000c01', '1.0.0', 1, 0, 0, digest('grasp 1.0.0', 'sha256'), '\x00', 'written', 'listed', now()),
  ('01900000-0000-7000-8000-000000000d02', '01900000-0000-7000-8000-000000000c02', '1.0.0', 1, 0, 0, digest('bottle 1.0.0', 'sha256'), '\x00', 'recorded', 'listed', now()),
  ('01900000-0000-7000-8000-000000000d03', '01900000-0000-7000-8000-000000000c02', '1.1.0', 1, 1, 0, digest('bottle 1.1.0', 'sha256'), '\x00', 'recorded', 'listed', now());

-- A variant made by B. Tester for a lever-style opener, derived from bottle 1.1.0.
INSERT INTO skill (skill_id, name, author_id, class_code, title, parent_version_id) VALUES
  ('01900000-0000-7000-8000-000000000c03', 'open-bottle-with-lever-opener', '01900000-0000-7000-8000-000000000002', '2.1.2',
   'Open a capped bottle with a lever-style opener', '01900000-0000-7000-8000-000000000d03');
INSERT INTO skill_version (version_id, skill_id, semver, v_major, v_minor, v_patch, sha256, packet, origin, status, library_signed_at) VALUES
  ('01900000-0000-7000-8000-000000000d04', '01900000-0000-7000-8000-000000000c03', '1.0.0', 1, 0, 0, digest('lever 1.0.0', 'sha256'), '\x00', 'learned', 'listed', now());

INSERT INTO skill_version_tag (version_id, tag_id)
SELECT v, t.tag_id FROM (VALUES
  ('01900000-0000-7000-8000-000000000d03'::uuid, 'domain', 'kitchen'), ('01900000-0000-7000-8000-000000000d03', 'object', 'bottle'),
  ('01900000-0000-7000-8000-000000000d03', 'tool', 'bottle-opener'),    ('01900000-0000-7000-8000-000000000d03', 'body', 'two-hands'),
  ('01900000-0000-7000-8000-000000000d04', 'domain', 'kitchen'),        ('01900000-0000-7000-8000-000000000d04', 'object', 'bottle')
) x(v, f, val) JOIN tag t ON t.facet = x.f AND t.value = x.val;

INSERT INTO skill_version_need (version_id, capability, count) VALUES
  ('01900000-0000-7000-8000-000000000d02', 'ArmMotion', 2), ('01900000-0000-7000-8000-000000000d02', 'Grasping', 1),
  ('01900000-0000-7000-8000-000000000d01', 'ArmMotion', 1), ('01900000-0000-7000-8000-000000000d01', 'Grasping', 1),
  ('01900000-0000-7000-8000-000000000d03', 'ArmMotion', 2), ('01900000-0000-7000-8000-000000000d03', 'GripperMotion', 2),
  ('01900000-0000-7000-8000-000000000d03', 'Grasping', 1),  ('01900000-0000-7000-8000-000000000d03', 'ForceSensing', 1),
  ('01900000-0000-7000-8000-000000000d04', 'ArmMotion', 1), ('01900000-0000-7000-8000-000000000d04', 'Grasping', 1);

INSERT INTO skill_version_use (version_id, uses_skill_id, version_range) VALUES
  ('01900000-0000-7000-8000-000000000d03', '01900000-0000-7000-8000-000000000c01', '>=1.0');

INSERT INTO test_run (version_id, simulator, robot_model_id, runs, passed) VALUES
  ('01900000-0000-7000-8000-000000000d03', 'mujoco 3.2', '01900000-0000-7000-8000-0000000000a1', 50, 47);

INSERT INTO adoption (version_id, robot_id, last_used_at, runs, successes) VALUES
  ('01900000-0000-7000-8000-000000000d03', '01900000-0000-7000-8000-0000000000b1', now(), 120, 111),
  ('01900000-0000-7000-8000-000000000d03', '01900000-0000-7000-8000-0000000000b2', now(),  40,  36),
  ('01900000-0000-7000-8000-000000000d04', '01900000-0000-7000-8000-0000000000b1', now(),   6,   6);

INSERT INTO rating (version_id, author_id, stars) VALUES
  ('01900000-0000-7000-8000-000000000d03', '01900000-0000-7000-8000-000000000002', 4);

INSERT INTO comment (version_id, author_id, body) VALUES
  ('01900000-0000-7000-8000-000000000d03', '01900000-0000-7000-8000-000000000002',
   'Works well with steel openers; slips with plastic ones, so I made a lever-opener variant.');

REFRESH MATERIALIZED VIEW skill_version_stats;

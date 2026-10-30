import base64
import copy
import json
import math
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import date

from robot_skills import (
    DocumentError,
    read_document,
    validate_document,
    validate_file,
    validate_text,
    write_document,
)
from robot_skills.validator import MAX_BYTES, PROFILE

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "position-cup.yaml"


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.document = read_document(FIXTURE.read_text(encoding="utf-8"))

    def assertError(self, code, document=None):
        result = validate_document(self.document if document is None else document)
        self.assertFalse(result.valid, result.to_dict())
        self.assertTrue(any(item.code == code for item in result.diagnostics), result.to_dict())
        return result

    def test_valid_fixture_without_warnings(self):
        self.assertEqual(validate_file(FIXTURE).to_dict(), {
            "profile": PROFILE, "valid": True, "diagnostics": [],
        })

    def test_read_write_roundtrip_both_formats(self):
        original = copy.deepcopy(self.document)
        for format in ("yaml", "json"):
            with self.subTest(format=format):
                text = write_document(self.document, format)
                self.assertEqual(read_document(text, format), original)
                self.assertTrue(validate_text(text, format).valid)
        self.assertEqual(self.document, original)

    def test_unquoted_dates_and_yaml_boolean_words_stay_strings(self):
        self.assertIsInstance(self.document["provenance"]["created"], str)
        self.assertEqual(read_document("a: on\nb: yes\nc: false"), {"a": "on", "b": "yes", "c": False})

    def test_writer_uses_the_same_scalar_rules_as_the_reader(self):
        self.document["title"] = "1e10"
        self.document["ext"] = {"vendor": {"strings": [
            "1e3", "1E+6", "true", "false", "null", "~", "12", "1.2",
            "2026-10-31", "on", "yes",
        ], "numbers": [1e-30, 1e30, 1.5, 1], "booleans": [True, False]}}
        written = write_document(self.document)
        self.assertEqual(read_document(written), self.document)
        self.assertTrue(validate_text(written).valid)

    def test_malformed_yaml_with_line_and_column(self):
        result = validate_text("plan: [")
        self.assertFalse(result.valid)
        self.assertEqual(result.diagnostics[0].code, "input.syntax")
        self.assertIsNotNone(result.diagnostics[0].line)

    def test_duplicate_mapping_keys_rejected(self):
        for text, format in (
            ("rs: '0.1'\nrs: '0.2'", "yaml"),
            ('{"rs":"0.1","rs":"0.2"}', "json"),
            ("plan: {wait: 1 s, wait: 2 s}", "yaml"),
        ):
            with self.subTest(text=text):
                self.assertEqual(validate_text(text, format).diagnostics[0].code, "input.syntax")

    def test_aliases_merge_keys_custom_tags_and_nonstring_keys_rejected(self):
        for text in (
            "a: &a [*a]", "a: &a 1\nb: *a", "a: {<<: {b: 1}}",
            "a: !unknown 1", "1: a", "[a, b]: c", "a: !!binary aGVsbG8=",
            "a: !!bool invalid", "a: !!timestamp invalid", "!!map {a: 1}",
        ):
            with self.subTest(text=text):
                self.assertFalse(validate_text(text).valid)

    def test_multiple_yaml_documents_rejected(self):
        self.assertFalse(validate_text("a: 1\n---\na: 2").valid)

    def test_unsupported_format_and_unknown_rs_version_rejected(self):
        self.assertEqual(validate_text("rs 0.1", "rsk").diagnostics[0].code, "input.format")
        self.document["rs"] = "0.2"
        self.assertError("schema.const")

    def test_invalid_root_values_rejected(self):
        for value in (None, [], "", 1):
            with self.subTest(value=value):
                self.assertFalse(validate_document(value).valid)

    def test_missing_fields_and_unknown_keywords_rejected(self):
        del self.document["success"]
        self.assertError("schema.required")
        self.document = read_document(FIXTURE.read_text(encoding="utf-8"))
        self.document["sucess"] = {}
        self.assertError("schema.additionalProperties")

    def test_uuid_version_and_variant_bits(self):
        for value in ("not-a-uuid", "0192f3a4-7c1e-4b2a-9d4e-5a1f6c3b8e21",
                      "0192f3a4-7c1e-7b2a-7d4e-5a1f6c3b8e21"):
            with self.subTest(value=value):
                self.document["id"] = value
                self.assertError("schema.pattern")

    def test_semver(self):
        for version in ("1.0.0", "0.2.0-alpha.1+build.2", "1.0.0-0"):
            with self.subTest(version=version):
                self.document["version"] = version
                self.assertTrue(validate_document(self.document).valid)
        for version in ("01.0.0", "1.0", "1.0.0-01", "1.0.0+", "v1.0.0"):
            with self.subTest(version=version):
                self.document["version"] = version
                self.assertError("schema.pattern")

    def test_title_single_line_and_nonempty(self):
        for title in ("", "hello\nworld", "hello\n"):
            self.document["title"] = title
            self.assertFalse(validate_document(self.document).valid)

    def test_unknown_capability_and_duplicate_counts(self):
        self.document["needs"] = ["Teleportation"]
        self.assertError("capability.unknown")
        self.document["needs"] = ["ArmMotion", "ArmMotion x2"]
        self.assertError("capability.duplicate")
        self.document["needs"] = ["ArmMotion x0"]
        self.assertError("schema.pattern")

    def test_recursive_object_parts_are_explicit(self):
        self.document["objects"]["cup"]["parts"]["lid"] = {"type": "Lid", "parts": {"rim": "Edge"}}
        self.document["plan"] = {"inspect": {"what": "cup.lid.rim"}}
        self.assertTrue(validate_document(self.document).valid)
        self.document["plan"]["inspect"]["what"] = "cup.handle"
        self.assertError("reference.object")

    def test_unknown_motion_and_data_references(self):
        self.document["plan"] = {"position": {"what": "cup", "motion": "missing"}}
        self.assertError("reference.motion")
        self.document["motions"]["approach"]["weights"] = "@missing"
        self.assertError("reference.data")

    def test_unknown_frame_reference(self):
        self.document["motions"]["approach"]["frame"] = "shelf.corner"
        self.assertError("reference.object")

    def test_units_and_positive_durations(self):
        for value, code in (("2 N", "quantity.unit"), ("0 s", "quantity.value"),
                            ("-1 ms", "quantity.value"), ("2", "quantity.unit")):
            with self.subTest(value=value):
                self.document["success"]["within"] = value
                self.assertError(code)

    def test_limit_units_and_comparators(self):
        self.document["limits"] = {"payload": ">= 1 kg", "reach": ">= 400 mm", "grip_force": ">= 40 N"}
        self.assertTrue(validate_document(self.document).valid)
        for value in ("<= 2 kg", ">= 2 m", ">= -1 kg"):
            with self.subTest(value=value):
                self.document["limits"]["payload"] = value
                self.assertFalse(validate_document(self.document).valid)

    def test_action_units_and_hand(self):
        self.document["plan"] = {"rotate": {"what": "cup", "about": "cup.rim", "by": "-25 deg"}}
        self.assertTrue(validate_document(self.document).valid)
        self.document["plan"]["rotate"]["by"] = "25 mm"
        self.assertError("quantity.unit")
        self.document["plan"] = {"hold": {"what": "cup", "with": "middle"}}
        self.assertError("schema.enum")

    def test_each_control_node_is_traversed(self):
        bad = {"inspect": {"what": "missing"}}
        nodes = [
            {"sequence": [bad]}, {"parallel": [bad]}, {"fallback": [bad]},
            {"retry": {"times": 3, "do": [bad]}},
            {"repeat": {"times": 2, "do": [bad]}},
            {"select": {"branches": [{"when": "upright(cup)", "do": bad}]}},
            {"select": {"branches": [{"when": "upright(cup)", "do": {"wait": "1 s"}}], "else": bad}},
        ]
        for node in nodes:
            with self.subTest(node=node):
                self.document["plan"] = node
                self.assertError("reference.object")

    def test_control_node_shapes(self):
        for node in ({"sequence": []}, {"retry": {"times": 0, "do": [{"wait": "1 s"}]}},
                     {"wait": "1 s", "say": "hello"}, {"unknown": {}},
                     {"select": {"branches": []}}):
            with self.subTest(node=node):
                self.document["plan"] = node
                self.assertFalse(validate_document(self.document).valid)

    def test_wait_and_say(self):
        self.document["plan"] = {"sequence": [{"wait": "100 ms"}, {"say": "Ready"}]}
        self.assertTrue(validate_document(self.document).valid)
        self.document["plan"]["sequence"][0]["wait"] = "5 kg"
        self.assertError("quantity.unit")

    def test_condition_operators_grouping_and_arguments(self):
        self.document["success"]["when"] = (
            "not (closed(cup) or capped(cup)) and is(cup, Cup) "
            "and holding(cup, left) and on(cup, shelf) and in(cup, shelf)"
        )
        self.document["abort"] = "torque > 2 Nm or force >= 40 N"
        self.assertTrue(validate_document(self.document).valid)

    def test_malformed_and_unknown_conditions(self):
        for text in ("unknown(cup)", "upright(cup) and", "upright()", "upright(cup, shelf)",
                     "upright(cup) junk", "is(cup, lower)", "holding(cup, middle)",
                     "force > 80 kg", "force 80 N", "(upright(cup)", "", "upright(cup);"):
            with self.subTest(text=text):
                self.document["success"]["when"] = text
                self.assertFalse(validate_document(self.document).valid)

    def test_conditions_check_object_references(self):
        self.document["pre"] = ["upright(missing)"]
        result = self.assertError("reference.object")
        self.assertEqual(result.diagnostics[0].path, "/pre/0")

    def test_data_count_and_dmp_shape(self):
        self.document["data"]["weights"]["values"] = [0]
        self.assertError("data.count")
        self.document["data"]["weights"] = {"type": "f16", "count": 1, "values": [0]}
        self.assertError("motion.shape")

    def test_numeric_type_range_and_integrality(self):
        for kind, number in (("f16", 70000), ("f32", 1e40), ("i16", 32768),
                             ("i16", -32769), ("i16", 1.5)):
            with self.subTest(kind=kind, number=number):
                self.document["data"]["weights"] = {"type": kind, "count": 6, "values": [number] * 6}
                self.assertError("data.number")
        for kind in ("f16", "f32", "i16"):
            self.document["data"]["weights"] = {"type": kind, "count": 6, "values": [0] * 6}
            self.assertTrue(validate_document(self.document).valid)

    def test_strict_base64_and_exact_byte_count(self):
        block = self.document["data"]["weights"]
        del block["values"]
        block["b64"] = base64.b64encode(struct.pack("<6e", *range(6))).decode("ascii")
        self.assertTrue(validate_document(self.document).valid)
        for value, code in (("...", "data.encoding"), ("AAAA\n", "data.encoding"), ("AA==", "data.count")):
            with self.subTest(value=value):
                block["b64"] = value
                self.assertError(code)

    def test_base64_nonfinite_numbers_rejected(self):
        for kind, format in (("f16", "e"), ("f32", "f")):
            for value in (math.inf, math.nan):
                with self.subTest(kind=kind, value=value):
                    self.document["data"]["weights"] = {
                        "type": kind, "count": 6,
                        "b64": base64.b64encode(struct.pack("<6" + format, *([value] * 6))).decode("ascii"),
                    }
                    self.assertError("data.number")

    def test_data_representations_are_exclusive(self):
        self.document["data"]["weights"]["b64"] = "AAAA"
        self.assertError("schema.oneOf")

    def test_unimplemented_motion_kinds_rejected(self):
        for kind in ("promp", "spline", "force"):
            self.document["motions"]["approach"]["kind"] = kind
            self.assertError("schema.const")

    def test_provenance_key_dates_and_test_counts(self):
        self.document["provenance"]["author"]["key"] = "ed25519:..."
        self.assertError("schema.pattern")
        self.document["provenance"]["author"]["key"] = "ed25519:" + "01" * 32
        self.document["provenance"]["modified"] = "2026-02-30"
        self.assertError("schema.format")
        self.document["provenance"]["modified"] = "2026-10-01"
        self.assertError("provenance.dates")
        self.document["provenance"]["modified"] = "2026-10-31"
        self.document["provenance"]["tested"] = {"simulator": "mujoco", "robots": ["reference"], "runs": 1, "passed": 2}
        self.assertError("provenance.tests")

    def test_parent_identity(self):
        self.document["provenance"]["parent"] = {
            "id": self.document["id"], "version": "1.0.0", "sha256": "01" * 32,
        }
        self.assertError("provenance.parent")

    def test_dependencies_warn_and_ranges_are_bounded(self):
        self.document["plan"] = {"use": {"skill": "grasp-object", "version": ">=1.0 <2.0", "target": "cup", "hand": "left"}}
        result = validate_document(self.document)
        self.assertTrue(result.valid)
        self.assertEqual(result.diagnostics[0].code, "dependency.unresolved")
        self.document["plan"]["use"]["version"] = ""
        self.assertError("schema.minLength")
        for version in ("^1", "latest", ">=1.0 || <2.0", ">=01.0"):
            with self.subTest(version=version):
                self.document["plan"]["use"]["version"] = version
                self.assertError("dependency.range")

    def test_optional_extension_is_preserved_and_warned(self):
        self.document["ext"] = {"vendor": {"anything": {"values": [1, 2, 3]}}}
        result = validate_document(self.document)
        self.assertTrue(result.valid)
        self.assertEqual(result.diagnostics[0].code, "extension.unchecked")
        self.assertEqual(read_document(write_document(self.document)), self.document)

    def test_missing_abort_warns(self):
        del self.document["abort"]
        result = validate_document(self.document)
        self.assertTrue(result.valid)
        self.assertEqual(result.diagnostics[0].code, "contract.abort")

    def test_non_json_types_nonfinite_and_cycles_rejected(self):
        for value in (math.inf, math.nan, b"bytes", date(2026, 10, 31)):
            with self.subTest(value=value):
                self.assertFalse(validate_document({"ext": value}).valid)
        cycle = []
        cycle.append(cycle)
        self.assertEqual(validate_document(cycle).diagnostics[0].code, "input.limit")
        for text in ('{"x": NaN}', '{"x": Infinity}', '{"x": 1e9999}'):
            self.assertFalse(validate_text(text, "json").valid)

    def test_input_size_and_nesting_limits(self):
        self.assertEqual(validate_text(" " * (MAX_BYTES + 1)).diagnostics[0].code, "input.limit")
        nested = {}
        for _ in range(70):
            nested = {"a": nested}
        self.assertEqual(validate_document(nested).diagnostics[0].code, "input.limit")
        self.assertFalse(validate_text("[" * 2000 + "]" * 2000).valid)

    def test_existing_placeholder_example_is_not_valid(self):
        result = validate_file(ROOT / "examples" / "skills" / "open-bottle-with-opener.yaml")
        self.assertFalse(result.valid)

    def test_file_errors_and_utf8_bom(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "skill.yaml"
            self.assertEqual(validate_file(path).diagnostics[0].code, "input.read")
            path.write_bytes(b"\xff")
            self.assertEqual(validate_file(path).diagnostics[0].code, "input.read")
            path.write_bytes(b"\xef\xbb\xbf" + FIXTURE.read_bytes())
            self.assertTrue(validate_file(path).valid)
            path.write_bytes(b" " * (MAX_BYTES + 1))
            self.assertEqual(validate_file(path).diagnostics[0].code, "input.limit")
            self.assertEqual(validate_file(path.with_suffix(".rsk")).diagnostics[0].code, "input.format")

    def test_invalid_documents_cannot_be_written(self):
        self.document["plan"] = {"inspect": {"what": "missing"}}
        with self.assertRaises(DocumentError):
            write_document(self.document)
        with self.assertRaises(DocumentError):
            write_document(self.document, "rsk")

    def test_json_pointer_escapes_vendor_names(self):
        self.document["data"]["bad/name"] = {"type": "f16", "count": "bad", "values": [0]}
        result = self.assertError("schema.pattern")
        self.assertTrue(any(item.path == "/data/bad~1name/count" for item in result.diagnostics))

    def test_many_shallow_condition_groups_are_not_a_nesting_error(self):
        self.document["success"]["when"] = " and ".join("(upright(cup))" for _ in range(100))
        self.assertTrue(validate_document(self.document).valid)
        self.document["success"]["when"] = "(" * 65 + "upright(cup)" + ")" * 65
        self.assertError("condition.syntax")

    def test_oversized_quantity_exponent_reports_an_error(self):
        self.document["success"]["within"] = "1e999999999999999999999999 s"
        self.assertError("quantity.value")

    def test_trailing_newlines_do_not_bypass_schema_patterns(self):
        for field in ("skill", "version", "id", "class"):
            document = copy.deepcopy(self.document)
            document[field] += "\n"
            self.assertError("schema.pattern", document)

    def test_json_syntax_positions_and_invalid_unicode(self):
        result = validate_text('{\n  "bad": ]}', "json")
        self.assertEqual(result.diagnostics[0].line, 2)
        self.assertEqual(validate_text('{"title": "\\ud800"}', "json").diagnostics[0].code, "input.encoding")
        self.assertEqual(validate_text('{"\\ud800": 1}', "json").diagnostics[0].code, "input.encoding")


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "robot_skills", *map(str, args)],
            text=True, capture_output=True, check=False,
        )

    def test_valid_json_output(self):
        process = self.run_cli("--json", FIXTURE)
        self.assertEqual(process.returncode, 0, process.stderr)
        output = json.loads(process.stdout)
        self.assertEqual(output["api_version"], 1)
        self.assertTrue(output["passed"])
        self.assertEqual(output["results"][0]["diagnostics"], [])

    def test_invalid_and_missing_input_output(self):
        process = self.run_cli("--json", FIXTURE, FIXTURE.with_name("missing.json"))
        self.assertEqual(process.returncode, 1, process.stderr)
        output = json.loads(process.stdout)
        self.assertFalse(output["passed"])
        self.assertEqual(len(output["results"]), 2)
        self.assertEqual(output["results"][1]["diagnostics"][0]["code"], "input.read")

    def test_usage_error_is_exit_two(self):
        self.assertEqual(self.run_cli().returncode, 2)

    def test_warnings_as_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "skill.yaml"
            document = read_document(FIXTURE.read_text(encoding="utf-8"))
            del document["abort"]
            path.write_text(write_document(document), encoding="utf-8")
            self.assertEqual(self.run_cli(path).returncode, 0)
            process = self.run_cli("--json", "--warnings-as-errors", path)
            self.assertEqual(process.returncode, 1)
            output = json.loads(process.stdout)
            self.assertFalse(output["passed"])
            self.assertTrue(output["results"][0]["valid"])

    def test_human_diagnostics(self):
        process = self.run_cli(ROOT / "examples" / "skills" / "open-bottle-with-opener.yaml")
        self.assertEqual(process.returncode, 1)
        self.assertIn("INVALID", process.stdout)
        self.assertIn("/provenance/author/key", process.stdout)


if __name__ == "__main__":
    unittest.main()

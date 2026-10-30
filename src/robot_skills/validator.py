"""Strict source loading and static checks for the RS authoring profile."""

from __future__ import annotations

import base64
import binascii
import json
import math
import re
import struct
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Literal

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from yaml.constructor import ConstructorError
from yaml.events import AliasEvent

PROFILE = "rs-0.1-authoring-v1"
MAX_BYTES = 1_048_576
MAX_DEPTH = 64
MAX_NODES = 50_000
NUMBER = r"[+-]?(?:[0-9]+(?:\.[0-9]+)?)(?:[eE][+-]?[0-9]+)?"
QUANTITY = re.compile(rf"({NUMBER})\s+(m|mm|deg|rad|s|ms|N|Nm|kg)")
REFERENCE = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?:\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*)*"
RANGE = re.compile(
    r"(?:>=|<=|>|<|=)?(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:\.(?:0|[1-9][0-9]*))?"
)
CAPABILITIES = {
    "BaseMotion", "Walking", "ArmMotion", "GripperMotion", "FingerMotion",
    "Grasping", "Bimanual", "ForceSensing", "TactileSensing", "Camera",
    "DepthCamera", "Microphone", "Speaker",
}


@dataclass(frozen=True)
class Diagnostic:
    severity: Literal["error", "warning"]
    code: str
    path: str
    message: str
    line: int | None = None
    column: int | None = None


@dataclass(frozen=True)
class ValidationResult:
    diagnostics: tuple[Diagnostic, ...]

    @property
    def valid(self) -> bool:
        return not any(item.severity == "error" for item in self.diagnostics)

    def to_dict(self) -> dict:
        return {
            "profile": PROFILE,
            "valid": self.valid,
            "diagnostics": [asdict(item) for item in self.diagnostics],
        }


class DocumentError(ValueError):
    """Source cannot be read or written without losing the profile's contract."""

    def __init__(self, diagnostic: Diagnostic):
        self.diagnostic = diagnostic
        super().__init__(diagnostic.message)


class _Loader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        event = self.peek_event()
        if isinstance(event, AliasEvent):
            raise ConstructorError(
                None, None, "YAML aliases are not supported", event.start_mark
            )
        if event.tag is not None:
            raise ConstructorError(
                None, None, "Explicit YAML tags are not supported", event.start_mark
            )
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise ConstructorError(
                    None, None, "mapping keys must be strings", key_node.start_mark
                )
            if key in result:
                raise ConstructorError(
                    None, None, f"duplicate mapping key: {key}", key_node.start_mark
                )
            result[key] = self.construct_object(value_node, deep=deep)
        return result


# Keep dates as strings and avoid YAML 1.1 surprises such as "on" becoming True.
_Loader.yaml_implicit_resolvers = {
    key: [
        (tag, pattern) for tag, pattern in resolvers
        if tag not in {
            "tag:yaml.org,2002:timestamp", "tag:yaml.org,2002:bool",
            "tag:yaml.org,2002:int", "tag:yaml.org,2002:float",
        }
    ]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$"), list("tf")
)
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:int", re.compile(r"^-?(?:0|[1-9][0-9]*)$"), list("-0123456789")
)
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+(?:[eE][+-]?[0-9]+)?|[eE][+-]?[0-9]+)$"),
    list("-0123456789"),
)


class _Dumper(yaml.SafeDumper):
    pass


_Dumper.yaml_implicit_resolvers = _Loader.yaml_implicit_resolvers


def _pointer(parts) -> str:
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def _input_error(code: str, message: str) -> DocumentError:
    return DocumentError(Diagnostic("error", code, "", message))


def _check_tree(document: object) -> None:
    stack = [(document, 0)]
    count = 0
    while stack:
        value, depth = stack.pop()
        count += 1
        if depth > MAX_DEPTH or count > MAX_NODES:
            raise _input_error("input.limit", "Document exceeds the depth or node limit.")
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise _input_error("input.type", "Mapping keys must be strings.")
            for key in value:
                try:
                    key.encode("utf-8")
                except UnicodeEncodeError as error:
                    raise _input_error("input.encoding", "Mapping keys must contain valid Unicode scalar values.") from error
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            stack.extend((item, depth + 1) for item in value)
        elif isinstance(value, float):
            if not math.isfinite(value):
                raise _input_error("input.number", "Non-finite numbers are not supported.")
        elif isinstance(value, str):
            try:
                value.encode("utf-8")
            except UnicodeEncodeError as error:
                raise _input_error("input.encoding", "Strings must contain valid Unicode scalar values.") from error
        elif value is not None and type(value) not in (str, int, bool):
            raise _input_error("input.type", "Only JSON-compatible values are supported.")


def _json_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate mapping key: {key}")
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError(f"Non-finite number: {value}")


def read_document(text: str, format: Literal["yaml", "json"] = "yaml") -> object:
    """Read JSON-compatible data without semantic validation; raises DocumentError."""
    if format not in ("yaml", "json"):
        raise _input_error("input.format", "Supported source formats are yaml and json, not .rsk or .rsp.")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError as error:
        raise _input_error("input.encoding", str(error)) from error
    if size > MAX_BYTES:
        raise _input_error("input.limit", f"Source exceeds {MAX_BYTES} bytes.")
    try:
        if format == "json":
            document = json.loads(text, object_pairs_hook=_json_pairs, parse_constant=_nonfinite)
        else:
            document = yaml.load(text, Loader=_Loader)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        raise DocumentError(Diagnostic(
            "error", "input.syntax", "", str(error),
            mark.line + 1 if mark else None, mark.column + 1 if mark else None,
        )) from error
    except json.JSONDecodeError as error:
        raise DocumentError(Diagnostic(
            "error", "input.syntax", "", error.msg, error.lineno, error.colno,
        )) from error
    except (ValueError, RecursionError) as error:
        raise _input_error("input.syntax", str(error)) from error
    _check_tree(document)
    return document


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    schema = json.loads(files("robot_skills").joinpath("skill.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


class _Checks:
    def __init__(self, document: dict):
        self.document = document
        self.diagnostics: list[Diagnostic] = []
        self.references: set[str] = set()
        self._objects(document["objects"])

    def add(self, code: str, path: str, message: str, severity="error"):
        self.diagnostics.append(Diagnostic(severity, code, path, message))

    def _objects(self, objects: dict, prefix=""):
        for name, value in objects.items():
            ref = f"{prefix}.{name}" if prefix else name
            self.references.add(ref)
            if isinstance(value, dict):
                self._objects(value.get("parts", {}), ref)

    def ref(self, value: str, path: str):
        if value not in self.references:
            self.add("reference.object", path, f"Undeclared object or part: {value}")

    def quantity(self, text: str, units: set[str], path: str, *, comparator="", positive=True):
        match = re.fullmatch(re.escape(comparator) + r"\s*" + QUANTITY.pattern, text.strip())
        if not match or match[2] not in units:
            self.add("quantity.unit", path, f"Expected {comparator + ' ' if comparator else ''}a quantity in {', '.join(sorted(units))}.")
        else:
            try:
                number = Decimal(match[1])
            except InvalidOperation:
                self.add("quantity.value", path, "Quantity exponent is outside the supported numeric range.")
                return
            if positive and number <= 0:
                self.add("quantity.value", path, "Quantity must be greater than zero.")

    def condition(self, text: str, path: str):
        try:
            _Condition(text, self, path).parse()
        except ValueError as error:
            self.add("condition.syntax", path, str(error))

    def node(self, node: dict, path: str):
        kind, value = next(iter(node.items()))
        path += "/" + kind
        if kind in ("sequence", "fallback", "parallel"):
            for index, child in enumerate(value):
                self.node(child, f"{path}/{index}")
        elif kind in ("retry", "repeat"):
            for index, child in enumerate(value["do"]):
                self.node(child, f"{path}/do/{index}")
        elif kind == "select":
            for index, branch in enumerate(value["branches"]):
                self.condition(branch["when"], f"{path}/branches/{index}/when")
                self.node(branch["do"], f"{path}/branches/{index}/do")
            if "else" in value:
                self.node(value["else"], path + "/else")
        elif kind == "check":
            self.condition(value, path)
        elif kind == "wait":
            self.quantity(value, {"s", "ms"}, path)
        elif kind == "say":
            return
        elif kind == "use":
            if not all(RANGE.fullmatch(term) for term in value["version"].split()) or not value["version"].strip():
                self.add("dependency.range", path + "/version", "Expected space-separated comparisons such as >=1.0 <2.0.")
            if "target" in value:
                self.ref(value["target"], path + "/target")
            self.add("dependency.unresolved", path, "Dependency is not resolved or validated by this local validator.", "warning")
        else:
            for field in ("what", "to", "about", "in"):
                if field in value:
                    self.ref(value[field], path + "/" + field)
            if "motion" in value and value["motion"] not in self.document.get("motions", {}):
                self.add("reference.motion", path + "/motion", f"Unknown motion: {value['motion']}")
            if "by" in value:
                units = {"deg", "rad"} if kind in ("rotate", "orient") else {"m", "mm"}
                self.quantity(value["by"], units, path + "/by", positive=False)
            if "force" in value:
                self.quantity(value["force"], {"N"}, path + "/force", comparator="<=")

    def data(self):
        for name, block in self.document.get("data", {}).items():
            path = "/data/" + name
            kind = block["type"]
            format, size = {"f16": ("e", 2), "f32": ("f", 4), "i16": ("h", 2)}[kind]
            if "b64" in block:
                try:
                    raw = base64.b64decode(block["b64"], validate=True)
                except (ValueError, binascii.Error):
                    self.add("data.encoding", path + "/b64", "Expected strict base64, not placeholder weights.")
                    continue
                if len(raw) != block["count"] * size:
                    self.add("data.count", path + "/b64", "Decoded byte length does not match count and numeric type.")
                    continue
                if kind != "i16" and any(not math.isfinite(item[0]) for item in struct.iter_unpack("<" + format, raw)):
                    self.add("data.number", path + "/b64", "Decoded floating-point values must be finite.")
            else:
                if len(block["values"]) != block["count"]:
                    self.add("data.count", path + "/values", "Number of values does not match count.")
                for index, number in enumerate(block["values"]):
                    try:
                        if kind == "i16":
                            if int(number) != number:
                                raise ValueError("i16 requires an integer")
                            number = int(number)
                        struct.pack("<" + format, number)
                    except (OverflowError, struct.error, ValueError):
                        self.add("data.number", f"{path}/values/{index}", f"Value is not representable as {kind}.")

    def run(self) -> list[Diagnostic]:
        needs = set()
        for index, need in enumerate(self.document["needs"]):
            capability = need.split()[0]
            if capability in needs:
                self.add("capability.duplicate", f"/needs/{index}", f"Capability declared more than once: {capability}")
            if capability not in CAPABILITIES:
                self.add("capability.unknown", f"/needs/{index}", f"Unknown starter capability: {capability}")
            needs.add(capability)
        for field in ("pre", "effect"):
            for index, value in enumerate(self.document[field]):
                self.condition(value, f"/{field}/{index}")
        self.condition(self.document["success"]["when"], "/success/when")
        self.quantity(self.document["success"]["within"], {"s", "ms"}, "/success/within")
        if "abort" in self.document:
            self.condition(self.document["abort"], "/abort")
        else:
            self.add("contract.abort", "/abort", "No abort condition is declared.", "warning")
        for name, text in self.document.get("limits", {}).items():
            self.quantity(text, {"payload": {"kg"}, "reach": {"m", "mm"}, "grip_force": {"N"}}[name],
                          "/limits/" + name, comparator=">=")
        self.node(self.document["plan"], "/plan")
        self.data()
        for name, motion in self.document.get("motions", {}).items():
            path = "/motions/" + name
            self.ref(motion["frame"], path + "/frame")
            self.quantity(motion["duration"], {"s", "ms"}, path + "/duration")
            block = self.document.get("data", {}).get(motion["weights"][1:])
            if block is None:
                self.add("reference.data", path + "/weights", f"Unknown data block: {motion['weights']}")
            elif block["count"] != motion["dims"] * motion["basis"]:
                self.add("motion.shape", path + "/weights", "DMP count must equal dims multiplied by basis.")
        provenance = self.document["provenance"]
        if date.fromisoformat(provenance["modified"]) < date.fromisoformat(provenance["created"]):
            self.add("provenance.dates", "/provenance/modified", "Modified date precedes created date.")
        tested = provenance.get("tested")
        if tested and tested["passed"] > tested["runs"]:
            self.add("provenance.tests", "/provenance/tested/passed", "Passed tests cannot exceed runs.")
        parent = provenance.get("parent")
        if parent and parent["id"] == self.document["id"]:
            self.add("provenance.parent", "/provenance/parent/id", "A variant must have a different ID from its parent.")
        for vendor in self.document.get("ext", {}):
            self.add("extension.unchecked", "/ext/" + vendor, "Extension content is preserved but not semantically validated.", "warning")
        return self.diagnostics


class _Condition:
    """Small predicate/measurement parser; no evaluation or inferred truth."""

    token = re.compile(
        rf"\s*(>=|<=|==|>|<|!=|{NUMBER}|[A-Za-z][A-Za-z0-9.-]*|[(),])"
    )
    predicates = {
        "is": ("ref", "type"), "upright": ("ref",), "capped": ("ref",),
        "reachable": ("ref",), "open": ("ref",), "closed": ("ref",),
        "holding": ("ref", "hand"), "on": ("ref", "ref"), "in": ("ref", "ref"),
    }

    def __init__(self, text: str, checks: _Checks, path: str):
        self.checks, self.path = checks, path
        self.tokens = []
        self.index = 0
        self.depth = 0
        offset = 0
        while offset < len(text.rstrip()):
            match = self.token.match(text, offset)
            if not match:
                raise ValueError(f"Invalid condition token near character {offset + 1}.")
            self.tokens.append(match[1])
            offset = match.end()

    def peek(self):
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def take(self, expected=None):
        value = self.peek()
        if value is None or expected is not None and value != expected:
            raise ValueError(f"Expected {expected or 'a token'}, found {value!r}.")
        self.index += 1
        return value

    def parse(self):
        self.expression("or")
        if self.peek() is not None:
            raise ValueError(f"Unexpected token: {self.peek()}")

    def expression(self, operator):
        def child():
            self.expression("and") if operator == "or" else self.atom()
        child()
        while self.peek() == operator:
            self.take()
            child()

    def atom(self):
        # Iterative "not" avoids recursion proportional to untrusted input.
        while self.peek() == "not":
            self.take()
        if self.peek() == "(":
            self.take()
            self.depth += 1
            if self.depth > MAX_DEPTH:
                raise ValueError("Condition nesting exceeds the profile limit.")
            self.expression("or")
            self.take(")")
            self.depth -= 1
            return
        name = self.take()
        if name in ("force", "torque"):
            comparator, number, unit = self.take(), self.take(), self.take()
            if comparator not in (">", ">=", "<", "<=", "==", "!=") or not re.fullmatch(NUMBER, number):
                raise ValueError("Expected a numeric force or torque comparison.")
            expected_unit = "N" if name == "force" else "Nm"
            if unit != expected_unit:
                raise ValueError(f"{name} requires {expected_unit}.")
            return
        if name not in self.predicates:
            raise ValueError(f"Unsupported predicate: {name}")
        self.take("(")
        for index, kind in enumerate(self.predicates[name]):
            if index:
                self.take(",")
            value = self.take()
            if kind == "ref":
                if not re.fullmatch(REFERENCE, value):
                    raise ValueError(f"Expected an object reference, found {value!r}.")
                self.checks.ref(value, self.path)
            elif kind == "hand" and value not in ("left", "right"):
                raise ValueError("holding() requires left or right as its second argument.")
            elif kind == "type" and not re.fullmatch(r"[A-Z][A-Za-z0-9]*", value):
                raise ValueError("is() requires a CamelCase type as its second argument.")
        self.take(")")


def validate_document(document: object) -> ValidationResult:
    """Validate a JSON-compatible data tree without mutating or executing it."""
    try:
        _check_tree(document)
    except DocumentError as error:
        return ValidationResult((error.diagnostic,))
    errors = sorted(
        _schema_validator().iter_errors(document),
        key=lambda error: (_pointer(error.absolute_path), error.message),
    )
    if errors:
        return ValidationResult(tuple(
            Diagnostic("error", "schema." + str(error.validator), _pointer(error.absolute_path), error.message)
            for error in errors
        ))
    return ValidationResult(tuple(_Checks(document).run()))


def validate_text(text: str, format: Literal["yaml", "json"] = "yaml") -> ValidationResult:
    try:
        document = read_document(text, format)
    except DocumentError as error:
        return ValidationResult((error.diagnostic,))
    return validate_document(document)


def validate_file(path: str | Path) -> ValidationResult:
    path = Path(path)
    format = {".yaml": "yaml", ".yml": "yaml", ".json": "json"}.get(path.suffix.lower())
    if format is None:
        return ValidationResult((Diagnostic("error", "input.format", "", "Expected a .yaml, .yml or .json file; .rsk/.rsp are not implemented."),))
    try:
        with path.open("rb") as source:
            raw = source.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise _input_error("input.limit", f"Source exceeds {MAX_BYTES} bytes.")
        text = raw.decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        return ValidationResult((Diagnostic("error", "input.read", "", str(error)),))
    except DocumentError as error:
        return ValidationResult((error.diagnostic,))
    return validate_text(text, format)


def write_document(document: object, format: Literal["yaml", "json"] = "yaml") -> str:
    """Validate then serialize source data; does not preserve comments or signatures."""
    if format not in ("yaml", "json"):
        raise _input_error("input.format", "Supported output formats are yaml and json.")
    result = validate_document(document)
    if not result.valid:
        raise DocumentError(next(item for item in result.diagnostics if item.severity == "error"))
    if format == "json":
        text = json.dumps(document, indent=2, ensure_ascii=True, allow_nan=False) + "\n"
    else:
        text = yaml.dump(document, Dumper=_Dumper, sort_keys=False, allow_unicode=False)
    # Serialized output must satisfy the same input size and type constraints.
    read_document(text, format)
    return text

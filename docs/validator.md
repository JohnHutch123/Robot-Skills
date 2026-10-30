# RS authoring validator

The Python package validates YAML and JSON source against **`rs-0.1-authoring-v1`**.
This is an explicitly limited authoring profile for progressing toward v0.2, not
a ratified v0.2 specification or permission to run a robot. It does not execute
plans, resolve dependencies, verify signatures or certify motion accuracy.

Robot safety remains the robot manufacturer's responsibility, as defined in the
specification's [safety scope](../spec/rs-spec-v0.1.md#safety-scope-and-manufacturer-responsibility).
Validator success does not replace manufacturer safety controls or authorize
execution.

## Install and run

Use Python 3.11 or later. From the repository root, in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe -m robot_skills tests\fixtures\position-cup.yaml
.\.venv\Scripts\python.exe -m robot_skills --json --warnings-as-errors tests\fixtures\position-cup.yaml
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Installing also provides `rs-validate` in the environment's `Scripts` directory.
The package has two runtime dependencies: PyYAML and jsonschema. Reinstall after
source changes, or use `pip install -e .` for development.

The CLI accepts one or more `.yaml`, `.yml` or `.json` files. Exit codes are `0`
for a successful check, `1` for invalid/unreadable input (or warnings with
`--warnings-as-errors`), and `2` for invalid CLI usage. Invalid files do not
prevent the remaining files from being checked.

The fixture uses synthetic zero weights and a public test key. It demonstrates
format validity only; it is not a recorded trajectory or a signed skill. The
older bottle example deliberately retains placeholder keys and weights and
**fails** validation. Its `bottle.cap.rim` also needs an explicit part declaration
in this profile. `.rsk`, `.rsp`, robot profiles and learning records are rejected,
not silently parsed as YAML.

## What is checked

The packaged [JSON Schema](../src/robot_skills/skill.schema.json) uses Draft
2020-12. It checks required fields, field types, unknown fields, UUID v7 syntax,
SemVer syntax, class/tag syntax, provenance, source tree shapes and the action
vocabulary. Structural failures are reported before semantic checks.

Semantic checks cover:

- Explicit object/part paths in actions, conditions and motion frames; named
  motion and data references; duplicate or unknown starter capabilities.
- Positive durations, minimum physical limits with compatible units, angular
  versus linear `by` quantities, and force caps.
- Condition syntax and argument counts, declared object references, date
  ordering, parent identity and simulator pass counts.
- Strict base64, numeric storage ranges, finite numeric values, declared data
  counts and DMP `dims * basis` weight counts.

The validator does not infer a type's parts or capabilities. Declare a nested
part as `{type: CrownCap, parts: {rim: Edge}}`; a leaf part can simply be `Edge`.
Unknown fields outside `ext` are errors. Optional `ext: {vendor: {...}}` content
is preserved with an `extension.unchecked` warning, not treated as understood.
There is no required-extension mechanism yet: behavior that depends on a vendor
extension must not rely on this validator's success.

An omitted `abort` produces a warning. Every `use` produces a
`dependency.unresolved` warning even if it supplies an ID; there is no catalogue
resolver or check of a callee's requirements. Use `--warnings-as-errors` when
unchecked dependencies or extensions must prevent a successful CLI result.

### Deliberately bounded syntax

This profile makes the following source conventions explicit without claiming
to settle the eventual execution or binary standards:

| Area | Supported form |
| --- | --- |
| Source version | `rs: "0.1"` only; not `0.2` |
| Conditions | `not`, `and`, `or`, grouping; precedence is `not`, then `and`, then `or` |
| Predicates | `upright`, `capped`, `reachable`, `open`, `closed` take one object reference; `on` and `in` take two; `is(object, Type)`; `holding(object, left/right)` |
| Measurements | `force <comparison> number N` and `torque <comparison> number Nm`; comparisons are `<`, `<=`, `>`, `>=`, `==`, `!=` |
| Controls | `sequence`, `fallback`, `parallel`: nonempty node lists; `retry`, `repeat`: `{times: positive integer, do: [nodes]}` |
| Selection | `select: {branches: [{when: condition, do: node}], else: node}`; `else` is optional |
| Actions | One verb per node; object actions use `{what: object, ...}`; `say` takes a string, `wait` takes a duration |
| Action options | `to`, `about`, `in`: object references; `with`: `left/right`; `motion`: name; `force`: `<= quantity N`; `by`: `deg/rad` for `rotate/orient`, otherwise `m/mm` |
| Calls | `use: {skill: name, version: range, id: optional UUID, target: optional object, hand: optional left/right}` |
| Ranges | Space-separated comparisons, e.g. `>=1.0 <2.0`; unsigned `major.minor` or `major.minor.patch`, no leading zeros; no caret, OR, wildcard or prerelease ranges |
| Motions | DMP declarations only, with `frame`, `dims` (6 or 7), `basis`, `duration`, `weights` |
| Data | `type: f16/f32/i16`, positive `count`, exactly one of `values: [numbers]` or `b64: string` |
| Binary numeric source blocks | IEEE binary16/binary32 or signed int16, little-endian for this authoring profile only |
| Provenance | ISO date strings, `origin: written/recorded/learned`, hexadecimal 32-byte `ed25519:` public key, licence; optional `parent`, `robot`, `region`, `tested` |

Other action-specific contracts (for example whether `position` requires `to`)
remain unspecified. Accepted action shapes do not establish that the action
is meaningful or implementable. `is` checks argument syntax, not membership
in an agreed object ontology. Unknown predicates, ProMPs, splines, force-motion
layouts, models and detailed recording-origin blocks are rejected rather than
given incomplete success-shaped validation.

Input is a single UTF-8 document (files may have a BOM), limited to 1 MiB,
64 container levels and 50,000 values. YAML aliases, merge keys, explicit tags,
duplicate keys, non-string mapping keys and non-JSON values are rejected.
Implicit YAML dates remain strings; only lowercase `true`/`false` and
JSON-style numbers are implicitly typed. JSON also rejects duplicate keys
and non-finite numbers. Numeric type compatibility is checked, but f16/f32
rounding is not a proof of trajectory accuracy.

## Python read/write API

The validation library is independent of the CLI. Its data model is ordinary
JSON-compatible dictionaries, lists and scalar values:

```python
from pathlib import Path
from robot_skills import read_document, validate_document, write_document

source = Path("tests") / "fixtures" / "position-cup.yaml"
document = read_document(source.read_text(encoding="utf-8"), "yaml")
result = validate_document(document)
if not result.valid:
    raise ValueError(result.to_dict())
json_source = write_document(document, "json")
```

`read_document` checks source syntax and resource limits, not skill semantics.
`validate_document`, `validate_text` and `validate_file` return a
`ValidationResult`; invalid skill input is reported as diagnostics rather than
a Python traceback. `read_document` and `write_document` raise `DocumentError`
with a `diagnostic` attribute on invalid input. `write_document` validates before
serializing, does not mutate the input and returns text rather than writing
files. JSON/YAML semantic read/write round trips are supported; comments,
formatting, COSE envelopes and signatures are not preserved. None of these
functions downloads resources or runs skill actions.

### Delphi and a future C interface

The immediate language-neutral boundary is UTF-8 source plus JSON diagnostics:
Delphi can launch `rs-validate --json file.yaml`, inspect its exit code and parse
stdout. A JSON-mode result has the following envelope:

```json
{
  "api_version": 1,
  "profile": "rs-0.1-authoring-v1",
  "passed": true,
  "results": [
    {
      "file": "skill.yaml",
      "profile": "rs-0.1-authoring-v1",
      "valid": true,
      "diagnostics": []
    }
  ]
}
```

Each diagnostic has `severity`, `code`, `path`, `message`, `line` and `column`.
Paths are JSON Pointers (an empty path denotes the root). Positions are
1-based where a source parser provides them, otherwise `null`. Schema and
semantic diagnostics use paths, not source line numbers. Diagnostic messages
are for display; integrations should use codes and paths. `valid` means no
errors under this profile; top-level `passed` also accounts for
`--warnings-as-errors`.

A future C ABI can wrap the same library using UTF-8 buffers with explicit
lengths, a returned JSON diagnostic buffer, and an exported free function. It
will need an explicit Python-runtime deployment/embedding strategy and ABI
versioning. No DLL, C ABI, Delphi unit or `.rsk` reader/writer is implemented yet;
those should not require duplicating the validation rules.

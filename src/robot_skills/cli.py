"""Command-line entry point with a versioned, JSON-serializable result."""

import argparse
import json
from pathlib import Path

from .validator import PROFILE, validate_file


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate RS YAML/JSON authoring sources, not robot safety.")
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true", help="Emit structured JSON diagnostics.")
    parser.add_argument("--warnings-as-errors", action="store_true", help="Fail if any check is incomplete or recommended field is missing.")
    args = parser.parse_args(argv)
    results = [(str(path), validate_file(path)) for path in args.files]
    passed = all(
        result.valid and not (args.warnings_as_errors and result.diagnostics)
        for _, result in results
    )
    if args.json:
        print(json.dumps({
            "api_version": 1,
            "profile": PROFILE,
            "passed": passed,
            "results": [{"file": name, **result.to_dict()} for name, result in results],
        }, ensure_ascii=True, allow_nan=False))
    else:
        for name, result in results:
            print(f"{name}: {'VALID' if result.valid else 'INVALID'} ({PROFILE})")
            for item in result.diagnostics:
                location = item.path or "/"
                if item.line is not None:
                    location += f" (line {item.line}, column {item.column})"
                print(f"  {item.severity} {item.code} {location}: {item.message}")
    return 0 if passed else 1

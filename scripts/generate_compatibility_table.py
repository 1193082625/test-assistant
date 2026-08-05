"""Validate and render the versioned compatibility manifest."""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs" / "compatibility.json"
DEFAULT_OUTPUT = ROOT / "docs" / "compatibility.md"
ALLOWED_STATES = frozenset({"supported", "experimental", "unsupported"})
CATEGORY_LABELS = {
    "operating_system": "Operating systems",
    "python": "Python",
    "pytest": "pytest",
    "path": "Paths and filesystems",
}


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def load_manifest(path: Path) -> dict[str, Any]:
    """Load and validate schema version 1."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest must be an object")
    if isinstance(payload.get("schema_version"), bool) or payload.get(
        "schema_version"
    ) != 1:
        raise ValueError("schema_version must be 1")

    release = _nonempty_string(payload.get("release"), "release")
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("entries must be a non-empty list")

    normalized_entries: list[dict[str, str]] = []
    identities: set[tuple[str, str]] = set()
    for index, raw_entry in enumerate(entries):
        if not isinstance(raw_entry, dict):
            raise ValueError(f"entries[{index}] must be an object")
        entry = {
            field: _nonempty_string(raw_entry.get(field), f"entries[{index}].{field}")
            for field in ("category", "id", "label", "state", "details")
        }
        if entry["category"] not in CATEGORY_LABELS:
            raise ValueError(f"unsupported category: {entry['category']}")
        if entry["state"] not in ALLOWED_STATES:
            raise ValueError(f"unsupported state: {entry['state']}")
        identity = (entry["category"], entry["id"])
        if identity in identities:
            raise ValueError(f"duplicate compatibility entry: {identity}")
        identities.add(identity)
        normalized_entries.append(entry)

    return {
        "schema_version": 1,
        "release": release,
        "entries": normalized_entries,
    }


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_manifest(manifest: dict[str, Any]) -> str:
    """Render deterministic Markdown grouped by declared category order."""

    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for entry in manifest["entries"]:
        grouped[entry["category"]].append(entry)

    lines = [
        "# Compatibility support",
        "",
        f"> Release: `v{manifest['release']}`",
        "> Generated from `docs/compatibility.json`; do not edit manually.",
        "",
        "States: `supported` is release-blocking evidence, `experimental` is",
        "non-blocking observation, and `unsupported` is outside the release claim.",
    ]
    for category, heading in CATEGORY_LABELS.items():
        lines.extend(
            [
                "",
                f"## {heading}",
                "",
                "| Capability | State | Evidence or reason |",
                "| --- | --- | --- |",
            ]
        )
        for entry in grouped.get(category, []):
            lines.append(
                "| "
                + " | ".join(
                    _escape_cell(value)
                    for value in (
                        entry["label"],
                        f"`{entry['state']}`",
                        entry["details"],
                    )
                )
                + " |"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()

    try:
        rendered = render_manifest(load_manifest(arguments.manifest))
        if arguments.check:
            if not arguments.output.is_file():
                raise ValueError("generated compatibility document is missing")
            if arguments.output.read_text(encoding="utf-8") != rendered:
                raise ValueError("generated compatibility document is stale")
        else:
            arguments.output.write_text(rendered, encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"compatibility manifest error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Collection
from pathlib import Path


def _find_owl_build_errors(
    owl_dir: Path, commit: str, checksum_files: Collection[str]
) -> list[str]:
    variants = ("owl.es.js", "owl.runtime.es.js", "owl.compiler.es.js")
    errors = []
    if set(checksum_files) != set(variants):
        errors.append(
            "owl: checksum pins must cover exactly the full, runtime and compiler builds"
        )
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        return [*errors, "owl: source commit must be a full SHA-1 revision"]
    pattern = rf'var buildHash = "{commit[:8]}";'
    for filename in variants:
        path = owl_dir / filename
        if path.is_file() and not re.search(pattern, path.read_text()):
            errors.append(f"owl: {filename} does not identify source commit {commit}")
    return errors


def find_vendored_library_errors(lib_dir: Path) -> list[str]:
    errors = []
    with (lib_dir / "versions.json").open() as manifest:
        pins = json.load(manifest)["libs"]
    for name, pin in pins.items():
        probe = pin.get("probe")
        if probe:
            path = lib_dir / name / probe["file"]
            pattern = probe["pattern"].replace("{version}", re.escape(pin["version"]))
            if not path.is_file():
                errors.append(f"{name}: missing version probe {probe['file']}")
            elif not re.search(pattern, path.read_text(errors="replace"), re.MULTILINE):
                errors.append(
                    f"{name}: {probe['file']} does not identify version {pin['version']}"
                )
        for filename, expected in pin.get("checksums", {}).items():
            path = lib_dir / name / filename
            if not path.is_file():
                errors.append(f"{name}: missing artifact {filename}")
            elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                errors.append(f"{name}: {filename} does not match its SHA-256 pin")
        if name == "owl":
            errors.extend(
                _find_owl_build_errors(
                    lib_dir / name,
                    pin.get("commit", ""),
                    pin.get("checksums", {}),
                )
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("lib_dir", type=Path)
    args = parser.parse_args()
    errors = find_vendored_library_errors(args.lib_dir)
    for error in errors:
        print(error, file=sys.stderr)
    return int(bool(errors))


if __name__ == "__main__":
    sys.exit(main())

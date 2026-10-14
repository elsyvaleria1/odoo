import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tooling.assets.check_vendored_libs import get_vendored_library_errors


@pytest.fixture
def lib_dir(tmp_path):
    library = tmp_path / "example"
    library.mkdir()
    bundle = b"/* Example 1.2.3 */\nexport const value = 42;\n"
    (library / "bundle.js").write_bytes(bundle)
    (tmp_path / "versions.json").write_text(
        json.dumps(
            {
                "libs": {
                    "example": {
                        "version": "1.2.3",
                        "probe": {"file": "bundle.js", "pattern": r"Example {version}"},
                        "checksums": {"bundle.js": hashlib.sha256(bundle).hexdigest()},
                    },
                    "internal": {"version": "internal"},
                },
            }
        )
    )
    return tmp_path


def test_pinned_bundle_passes(lib_dir):
    assert get_vendored_library_errors(lib_dir) == []


def test_same_size_code_corruption_fails(lib_dir):
    bundle = lib_dir / "example/bundle.js"
    bundle.write_bytes(bundle.read_bytes().replace(b"42", b"43"))
    assert get_vendored_library_errors(lib_dir) == [
        "example: bundle.js does not match its SHA-256 pin",
    ]


def test_a_pin_bumped_without_its_bundle_fails(lib_dir):
    manifest = lib_dir / "versions.json"
    manifest.write_text(manifest.read_text().replace("1.2.3", "1.2.4"))
    assert get_vendored_library_errors(lib_dir) == [
        "example: bundle.js does not match its pinned probe (version 1.2.4)",
    ]


def test_version_probes_treat_the_version_as_literal_text(lib_dir):
    bundle = lib_dir / "example/bundle.js"
    bundle.write_text(bundle.read_text().replace("1.2.3", "1x2x3"))
    assert (
        "example: bundle.js does not match its pinned probe (version 1.2.3)"
        in get_vendored_library_errors(lib_dir)
    )


@pytest.mark.parametrize("bump_source_pin", [False, True])
def test_upstream_source_probes_match_the_pinned_digest(lib_dir, bump_source_pin):
    manifest = lib_dir / "versions.json"
    pins = json.loads(manifest.read_text())
    source_sha256 = "a" * 64
    bundle = lib_dir / "example/bundle.js"
    bundle.write_text(f"/* Example 1.2.3; source SHA-256 {source_sha256} */\n")
    pin = pins["libs"]["example"]
    pin["source_sha256"] = "b" * 64 if bump_source_pin else source_sha256
    pin["probe"]["pattern"] = r"Example {version}; source SHA-256 {source_sha256}"
    pin["checksums"][bundle.name] = hashlib.sha256(bundle.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(pins))
    errors = get_vendored_library_errors(lib_dir)
    assert errors == (
        ["example: bundle.js does not match its pinned probe (version 1.2.3)"]
        if bump_source_pin
        else []
    )


def test_missing_bundle_fails(lib_dir):
    (lib_dir / "example/bundle.js").unlink()
    assert get_vendored_library_errors(lib_dir) == [
        "example: missing version probe bundle.js",
        "example: missing artifact bundle.js",
    ]


@pytest.fixture
def owl_dir(tmp_path):
    library = tmp_path / "owl"
    library.mkdir()
    commit = "a11f5097560346568d0c4e7cea0286bfabde7b7f"
    bundle = b'var version = "3.0.0-alpha.49";\nvar buildHash = "a11f5097";\n'
    variants = ("owl.es.js", "owl.runtime.es.js", "owl.compiler.es.js")
    for name in variants:
        (library / name).write_bytes(bundle)
    pin = {
        "version": "3.0.0-alpha.49",
        "commit": commit,
        "probe": {"file": "owl.es.js", "pattern": 'var version = "{version}"'},
        "checksums": dict.fromkeys(variants, hashlib.sha256(bundle).hexdigest()),
    }
    (tmp_path / "versions.json").write_text(json.dumps({"libs": {"owl": pin}}))
    return tmp_path


def test_all_three_owl_artifacts_match_the_pinned_source(owl_dir):
    assert get_vendored_library_errors(owl_dir) == []


@pytest.mark.parametrize("field", ["commit", "checksums"])
def test_owl_provenance_cannot_be_omitted(owl_dir, field):
    manifest = owl_dir / "versions.json"
    with manifest.open() as stream:
        pins = json.load(stream)
    del pins["libs"]["owl"][field]
    manifest.write_text(json.dumps(pins))
    assert get_vendored_library_errors(owl_dir)


def test_owl_source_revision_cannot_be_bumped_without_its_build(owl_dir):
    manifest = owl_dir / "versions.json"
    manifest.write_text(manifest.read_text().replace("a11f5097", "b22f5097"))
    errors = get_vendored_library_errors(owl_dir)
    assert len(errors) == 3
    assert all("does not identify source commit" in error for error in errors)


def test_a_compiler_from_another_build_fails_even_with_its_correct_checksum(owl_dir):
    compiler = owl_dir / "owl/owl.compiler.es.js"
    compiler.write_bytes(compiler.read_bytes().replace(b"a11f5097", b"b22f5097"))
    manifest = owl_dir / "versions.json"
    with manifest.open() as stream:
        pins = json.load(stream)
    pins["libs"]["owl"]["checksums"][compiler.name] = hashlib.sha256(
        compiler.read_bytes()
    ).hexdigest()
    manifest.write_text(json.dumps(pins))
    errors = get_vendored_library_errors(owl_dir)
    assert len(errors) == 1
    assert errors[0].startswith(
        "owl: owl.compiler.es.js does not identify source commit"
    )


@pytest.mark.parametrize("corrupt", [False, True])
def test_cli_checks_the_requested_checkout(lib_dir, corrupt):
    if corrupt:
        bundle = lib_dir / "example/bundle.js"
        bundle.write_bytes(bundle.read_bytes().replace(b"42", b"43"))
    script = Path(__file__).with_name("check_vendored_libs.py")
    result = subprocess.run(
        [sys.executable, str(script), str(lib_dir)],
        capture_output=True,
        text=True,
        check=False,
        cwd=lib_dir,
    )
    assert result.returncode == int(corrupt)
    assert bool(result.stderr) == corrupt

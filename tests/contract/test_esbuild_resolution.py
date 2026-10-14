from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from odoo.tools.assets import esbuild, esm_registry


@pytest.mark.parametrize(
    ("specifier", "external"),
    [
        ("@odoo/reserved_namespace", True),
        ("declared_library", True),
        ("unknown_library", False),
    ],
)
def test_external_specifier_classifies_names_without_claiming_the_file_exists(
    monkeypatch, specifier, external
):
    monkeypatch.setattr(
        esm_registry, "external_bare_specifiers", lambda: {"declared_library"}
    )
    assert esbuild.EsbuildCompiler.is_external_specifier(specifier) is external


def test_partial_symlink_creation_leaves_no_staging_directory(tmp_path, monkeypatch):
    base = tmp_path / "shared"
    base.mkdir()
    roots = {"@first": tmp_path / "first", "@second": tmp_path / "second"}
    real_symlink = Path.symlink_to

    def create_symlink(path, target, **kwargs):
        if path.name == "@second":
            raise OSError("symlink creation failed")
        real_symlink(path, target, **kwargs)

    monkeypatch.setattr(Path, "symlink_to", create_symlink)
    with pytest.raises(OSError, match="symlink creation failed"):
        esbuild._get_or_create_resolution_root(base, "sample", roots)
    assert sorted(path.name for path in base.iterdir()) == ["sample.lock"]


def test_concurrent_publication_reuses_one_complete_resolution_root(tmp_path):
    base = tmp_path / "shared"
    base.mkdir()
    roots = {"@first": tmp_path / "first", "@second": tmp_path / "second"}
    for source in roots.values():
        source.mkdir()
    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(
            workers.map(
                lambda _: esbuild._get_or_create_resolution_root(base, "sample", roots),
                range(12),
            )
        )
    assert all(path == base / "sample" for path in results)
    assert esbuild._has_exact_addon_roots(results[0], roots)
    assert sorted(path.name for path in base.iterdir()) == ["sample", "sample.lock"]
    inode = results[0].stat().st_ino
    assert (
        esbuild._get_or_create_resolution_root(base, "sample", roots).stat().st_ino
        == inode
    )


def test_changed_roots_replace_the_published_mapping(tmp_path):
    base = tmp_path / "shared"
    base.mkdir()
    first = {"@addon": tmp_path / "first"}
    second = {"@addon": tmp_path / "second"}
    root = esbuild._get_or_create_resolution_root(base, "sample", first)
    assert esbuild._has_exact_addon_roots(root, first)
    assert esbuild._get_or_create_resolution_root(base, "sample", second) == root
    assert esbuild._has_exact_addon_roots(root, second)
    assert sorted(path.name for path in base.iterdir()) == ["sample", "sample.lock"]


@pytest.mark.parametrize(
    "live_links", [(), (True,), (False,), (False, True), (False, False)]
)
def test_a_root_is_dangling_only_when_every_addon_link_is_dangling(
    tmp_path, live_links
):
    root = tmp_path / "root"
    root.mkdir()
    for index, live in enumerate(live_links):
        target = tmp_path / f"source_{index}"
        if live:
            target.mkdir()
        (root / f"@source_{index}").symlink_to(target, target_is_directory=True)
    assert esbuild._is_resolution_root_dangling(root) == (
        bool(live_links) and not any(live_links)
    )


def test_standalone_external_flags_leave_caller_aliases_unchanged(
    tmp_path, monkeypatch
):
    compiler = esbuild.EsbuildCompiler("probe", [], standalone=True)
    monkeypatch.setattr(
        compiler, "_get_standalone_alias_flags", lambda *_: ["--alias:extra=./extra.js"]
    )
    aliases = ["--alias:original=./original.js"]
    for _ in range(2):
        external, result = compiler._get_esbuild_external_flags(tmp_path, aliases)
        assert external == []
        assert result == ["--alias:original=./original.js", "--alias:extra=./extra.js"]
        assert aliases == ["--alias:original=./original.js"]


def test_asset_header_aliases_leave_provider_flags_unchanged(tmp_path):
    flags = ["--alias:@sample=./sample/static/src"]
    asset = SimpleNamespace(
        url="/sample/static/src/main.js",
        module_path="@sample/main",
        _filename=str(tmp_path / "sample/static/src/main.js"),
        raw_content="",
        parsed_header={"alias": "@odoo/sample_legacy"},
    )
    compiler = esbuild.EsbuildCompiler(
        "probe", [asset], addon_flags_provider=lambda _: (flags, [])
    )
    for _ in range(2):
        aliases, external = compiler._get_esbuild_flags(tmp_path, None)
        assert aliases == [
            *flags,
            "--alias:@odoo/sample_legacy=./sample/static/src/main.js",
        ]
        assert external == []
        assert flags == ["--alias:@sample=./sample/static/src"]


def test_entry_preparation_needs_no_directory_and_writes_no_files(
    tmp_path, monkeypatch
):
    asset = SimpleNamespace(
        url="/sample/static/src/main.js",
        module_path="@sample/main",
        _filename=str(tmp_path / "sample/static/src/main.js"),
        raw_content="",
        parsed_header=None,
    )
    monkeypatch.setattr(esm_registry, "external_lib_aliases", dict)
    compiler = esbuild.EsbuildCompiler("probe", [asset], standalone=True)
    entry_dir = tmp_path / "not_created"
    texts = compiler._prepare_esbuild_entry_files(
        {"sample": [asset], "empty": []}, entry_dir, tmp_path
    )
    assert list(texts) == [str(entry_dir / "sample.js")]
    assert '"@sample/main": __m0' in next(iter(texts.values()))
    assert not entry_dir.exists()


def test_shared_directory_failure_uses_the_compile_private_directory(
    tmp_path, monkeypatch
):
    private_dir = tmp_path / "private"
    private_dir.mkdir()
    compiler = esbuild.EsbuildCompiler("probe", [])
    monkeypatch.setattr(
        esbuild,
        "_create_private_dir",
        Mock(side_effect=PermissionError("shared directory unavailable")),
    )
    kept, node_path = compiler._get_or_create_addon_resolution_root(
        ["--alias:@sample=./sample/static/src", "--alias:library=./library.js"],
        tmp_path,
        str(private_dir),
    )
    assert kept == ["--alias:library=./library.js"]
    assert node_path == str(private_dir / "roots")
    assert (Path(node_path) / "@sample").readlink() == tmp_path / "sample/static/src"

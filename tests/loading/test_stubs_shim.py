from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from odoo.cli.stubs import write_addons_shim

from .conftest import REPO_ROOT


def _addon(root: Path, name: str, body: str = "") -> Path:
    path = root / name
    path.mkdir(parents=True)
    (path / "__init__.py").write_text("")
    (path / "models.py").write_text(body)
    return path


def test_the_shim_links_each_addon_and_follows_a_moved_one(tmp_path):
    first = _addon(tmp_path / "one", "alpha")
    second = _addon(tmp_path / "two", "beta")
    shim = write_addons_shim(tmp_path / "shim", {"alpha": first, "beta": second})

    addons = shim / "odoo" / "addons"
    assert (addons / "alpha").resolve() == first
    assert (addons / "beta").resolve() == second
    assert not (shim / "odoo" / "__init__.py").exists()
    assert not (addons / "__init__.py").exists()

    moved = _addon(tmp_path / "three", "alpha")
    write_addons_shim(shim, {"alpha": moved})

    assert (addons / "alpha").resolve() == moved
    assert not (addons / "beta").exists()


def test_the_shim_leaves_what_it_did_not_link(tmp_path):
    shim = tmp_path / "shim"
    addons = shim / "odoo" / "addons"
    addons.mkdir(parents=True)
    (addons / "notes.txt").write_text("kept")

    write_addons_shim(shim, {})

    assert (addons / "notes.txt").read_text() == "kept"


def test_the_shim_refuses_to_replace_a_directory_it_did_not_link(tmp_path):
    addon = _addon(tmp_path / "addons", "gamma")
    shim = tmp_path / "shim"
    squatter = shim / "odoo" / "addons" / "gamma"
    squatter.mkdir(parents=True)
    (squatter / "keep.py").write_text("kept")

    with pytest.raises(FileExistsError, match="not a link this command wrote"):
        write_addons_shim(shim, {"gamma": addon})

    assert (squatter / "keep.py").read_text() == "kept"


def test_mypy_resolves_an_addon_outside_the_framework_through_the_shim(tmp_path):
    addon = _addon(
        tmp_path / "addons", "shimmed_addon", "class Thing:\n    size: int\n"
    )
    shim = write_addons_shim(tmp_path / "shim", {"shimmed_addon": addon})
    config = tmp_path / "mypy.ini"
    config.write_text(
        "[mypy]\npython_version = 3.14\nfollow_imports = silent\n"
        "ignore_missing_imports = True\n"
        f"cache_dir = {tmp_path / 'cache'}\n"
    )
    client = tmp_path / "client.py"
    client.write_text(
        "from odoo.addons.shimmed_addon.models import Thing\n"
        "reveal_type(Thing().size)\n"
    )

    def revealed(mypypath: str) -> str:
        checked = subprocess.run(
            [
                sys.executable,
                "-m",
                "mypy",
                "--no-incremental",
                "--config-file",
                str(config),
                str(client),
            ],
            cwd=REPO_ROOT,
            env={**os.environ, "MYPYPATH": mypypath},
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        return checked.stdout + checked.stderr

    assert 'Revealed type is "int"' in revealed(str(shim))
    assert 'Revealed type is "Any"' in revealed(str(tmp_path / "empty"))

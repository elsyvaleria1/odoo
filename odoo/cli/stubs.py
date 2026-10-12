import stat
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import override

from odoo.api import Environment
from odoo.libs.debug_log import DebugLog
from odoo.orm.stubs import STUB_MODULE, render_registry

from . import DatabaseCommand, open_environment

_debug = DebugLog(__name__)


SHIM_DIRECTORY = "addons_shim"


def installed_module_paths(env: Environment) -> dict[str, Path]:
    import odoo
    from odoo.modules import Manifest

    framework_addons = (Path(odoo.__file__).parent / "addons").resolve()
    paths: dict[str, Path] = {}
    for name in sorted(env.registry.loaded_modules):
        manifest = Manifest.for_addon(name, display_warning=False)
        if manifest is None:
            continue
        path = Path(manifest.path).resolve()
        if path.parent != framework_addons:
            paths[name] = path
    return paths


def write_addons_shim(root: Path, paths: Mapping[str, Path]) -> Path:
    addons = root / "odoo" / "addons"
    addons.mkdir(parents=True, exist_ok=True)
    for entry in addons.iterdir():
        if entry.is_symlink() and entry.name not in paths:
            entry.unlink()
    for name, path in paths.items():
        link = addons / name
        if link.is_symlink():
            if link.resolve() == path:
                continue
            link.unlink()
        elif link.exists():
            raise FileExistsError(
                f"{link} is not a link this command wrote; remove it so the "
                f"shim can link {name} to {path}"
            )
        link.symlink_to(path, target_is_directory=True)
    return root


def _write_stubs(target: Path, source: str) -> None:
    try:
        mode = stat.S_IMODE(target.stat().st_mode)
    except FileNotFoundError:
        mode = None
    with tempfile.TemporaryDirectory(
        dir=target.parent, prefix=f".{target.name}."
    ) as directory:
        temporary_path = Path(directory) / target.name
        temporary_path.write_text(source, encoding="utf-8")
        if mode is not None:
            temporary_path.chmod(mode)
        temporary_path.replace(target)


class Stubs(DatabaseCommand):
    description = (
        "Write typed stubs of a database's registry, one class per model, "
        "for mypy through mypy_registry_plugin"
    )

    def __init__(self) -> None:
        super().__init__()
        self.add_config_arguments(self.parser)
        self.parser.add_argument(
            "-o",
            "--output",
            dest="output",
            help=(
                f"directory that receives {STUB_MODULE}.pyi and the {SHIM_DIRECTORY}/ "
                "tree linking each installed addon as odoo.addons.<module> "
                "(default: the data dir)"
            ),
        )

    @override
    def run(self, cmdargs: list[str]) -> None:
        parsed_args, unknown = self.parse_args(cmdargs)
        db_name = self.bootstrap_config(parsed_args, extra_args=unknown)
        with open_environment(db_name, readonly=True) as env:
            source = render_registry(env.registry)
            models = len(env.registry.models)
            module_paths = installed_module_paths(env)
        if parsed_args.output:
            directory = Path(parsed_args.output)
        else:
            from odoo.tools import config

            directory = Path(config["data_dir"]) / "stubs" / db_name
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{STUB_MODULE}.pyi"
        _write_stubs(target, source)
        shim = write_addons_shim(directory / SHIM_DIRECTORY, module_paths)
        _debug.lifecycle(
            "cli.stubs.written",
            db=db_name,
            models=models,
            path=str(target),
            shimmed=len(module_paths),
        )
        print(
            f"{target}: {models} models; MYPYPATH={directory}:{shim}",
            file=sys.stderr,
        )

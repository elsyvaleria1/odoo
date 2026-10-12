import pkgutil
from collections.abc import Iterator
from pathlib import Path

import odoo
from odoo.tests.common import BaseCase, no_retry

from ._checker_pep649 import scan_module

_SKIPPED = frozenset({"addons", "_vendor", "__main__"})


def _iter_core_modules(path: Path, prefix: str) -> Iterator[str]:
    for info in pkgutil.iter_modules([str(path)]):
        if info.name in _SKIPPED:
            continue
        name = f"{prefix}.{info.name}"
        yield name
        if info.ispkg:
            yield from _iter_core_modules(path / info.name, name)


def get_core_modules() -> list[str]:
    return ["odoo", *_iter_core_modules(Path(odoo.__path__[0]), "odoo")]


@no_retry
class TestPEP649Annotations(BaseCase):
    def test_core_modules_introspect(self):
        modules = get_core_modules()
        self.assertGreater(len(modules), 400)
        for modname in modules:
            with self.subTest(module=modname):
                fails = scan_module(modname)
                self.assertFalse(
                    fails,
                    msg=(
                        f"{modname} has annotation-resolution failures.  "
                        f"Move the offending import out of `if TYPE_CHECKING:`, "
                        f"or — if a runtime import would cycle — keep the "
                        f"TYPE_CHECKING import and add a ``typing.Any`` "
                        f"fallback in an ``else:`` branch.  Failures:\n  "
                        + "\n  ".join(fails)
                    ),
                )

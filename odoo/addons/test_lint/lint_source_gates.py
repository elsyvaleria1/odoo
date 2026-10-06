# The test_lint gates that read only the tree, run without a database, so
# they hold in seconds instead of after a module install.
#
#   python odoo/addons/test_lint/lint_source_gates.py            every source gate
#   python odoo/addons/test_lint/lint_source_gates.py test_pep649 test_naming
#
# Run from the checkout with the workspace venv's interpreter. The addons path is
# the narrow scope the floors are defined at (odoo/addons, addons). A test that
# asks for a database skips instead of failing: the narrow test_lint run on a
# database grades it, and still grades everything this one does.
import importlib
import logging
import multiprocessing
import os
import sys
import time
import unittest
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

CHECKOUT = Path(__file__).resolve().parents[3]
TESTS = Path(__file__).resolve().parent / "tests"
_logger = logging.getLogger("odoo.addons.test_lint.source_gates")


def _no_database() -> str:
    raise unittest.SkipTest("needs a database: graded by the narrow test_lint run")


def main(names: list[str]) -> int:
    sys.argv = sys.argv[:1]
    sys.path.insert(0, str(CHECKOUT))
    from odoo.tools import config

    config.parse_config(
        [f"--addons-path={CHECKOUT / 'odoo' / 'addons'},{CHECKOUT / 'addons'}"]
    )
    from odoo.modules.module import initialize_sys_path

    initialize_sys_path()

    import odoo.tests.utils
    from odoo.logutils import init_logger

    init_logger()
    # every module that already bound `from ... import get_db_name` gets the
    # stand-in too; test modules imported below bind it from these
    original = odoo.tests.utils.get_db_name
    for module in list(sys.modules.values()):
        if getattr(module, "get_db_name", None) is original:
            module.get_db_name = _no_database

    started = time.monotonic()
    # largest test files first, so the long scans are not the tail of the run
    names = names or sorted(
        (p.stem for p in TESTS.glob("test_*.py")),
        key=lambda stem: -(TESTS / f"{stem}.py").stat().st_size,
    )
    # forked after the setup above, so a worker inherits the configured odoo and
    # the stand-in instead of importing them again; 3.14 defaults to forkserver
    jobs = max(1, min(len(names), (os.process_cpu_count() or 2) // 2))
    with ProcessPoolExecutor(
        jobs, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        results = list(pool.map(_run_module, names))
    totals = [sum(column) for column in zip(*(r[1:] for r in results), strict=True)]
    run, skipped, failed, errors, skipped_modules = totals
    _logger.info(
        "test_lint source gates: %s run, %s skipped (database), %s modules skipped "
        "at import, %s failed, %s errors in %.0fs over %s workers",
        run,
        skipped,
        skipped_modules,
        failed,
        errors,
        time.monotonic() - started,
        jobs,
    )
    return 0 if run and not failed and not errors else 1


def _run_module(name: str) -> tuple[str, int, int, int, int, int]:
    from odoo.tests.result import OdooTestResult

    try:
        module = importlib.import_module(f"odoo.addons.test_lint.tests.{name}")
    except unittest.SkipTest:
        return name, 0, 0, 0, 0, 1
    report = OdooTestResult()
    unittest.defaultTestLoader.loadTestsFromModule(module).run(report)
    return (
        name,
        report.testsRun,
        report.skipped,
        report.failures_count,
        report.errors_count,
        0,
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

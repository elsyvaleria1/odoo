import tempfile
import tomllib
from pathlib import Path

import psutil

import odoo
from odoo import addons

from . import _parallel, _py_scan, _rules
from .lint_case import LintCase


def _ruff_configs() -> set[Path]:
    configs = set()
    for root in map(Path, (*addons.__path__, odoo.__path__[0])):
        for directory in (root, *root.parents):
            if (directory / "ruff.toml").is_file():
                configs.add(directory / "ruff.toml")
                break
    return configs


class TestPythonLint(LintCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _py_scan.findings()

    def test_every_rule_is_held_at_its_floor(self):
        for rule in _rules.RULES:
            with self.subTest(rule=rule.name):
                self.assert_ratchet_per_repository(
                    {
                        repo: sorted(found, key=lambda finding: finding.sort_key)
                        for repo, found in _py_scan.findings_by_repository(
                            rule.name
                        ).items()
                    },
                    rule.gate,
                    f"{rule.name} finding(s) in <repo>"
                    + (f" [{rule.code}]" if rule.code else ""),
                    f"{rule.advice}.",
                )

    def test_no_source_in_the_corpus_is_unreadable(self):
        broken = _py_scan.findings().get("unreadable-source", [])
        self.assertFalse(
            broken,
            f"{len(broken)} file(s) in the corpus could not be read, so every "
            f"other rule skipped them in silence:\n  "
            + "\n  ".join(str(finding) for finding in broken),
        )

    def test_every_rule_reaches_the_scan(self):
        self.assertEqual(
            sorted(_py_scan.findings().keys() - _rules.BY_NAME.keys()),
            [],
            "these rules produce findings but are not declared in _rules.RULES",
        )
        self.assertEqual(
            sorted(_rules.BY_NAME.keys() - _rules.CROSS_UNIT_RULES),
            [],
            "these rules are declared but nothing can ever emit them: a per-file "
            "rule belongs to the ruff fork",
        )

    def test_every_short_code_is_declared_external_to_ruff(self):
        codes = {rule.code for rule in _rules.RULES if rule.code}
        configs = _ruff_configs()
        self.assertIn(Path(odoo.__path__[0]).parent / "ruff.toml", configs)
        for ruff_toml in configs:
            lint = tomllib.loads(ruff_toml.read_text()).get("lint", {})
            if "external" not in lint:
                continue
            with self.subTest(config=str(ruff_toml)):
                self.assertEqual(
                    sorted(codes - set(lint["external"])),
                    [],
                    f"these checker codes are not in {ruff_toml}'s lint.external, "
                    "so ruff reports RUF102 on any noqa that uses them",
                )

    def test_the_scan_leaves_no_child_process_behind(self):
        _py_scan.findings()
        _parallel.run_chunks(_py_scan.scan_many, [], 2)
        self.assertEqual(
            [f"{child.pid} {child.name()}" for child in psutil.Process().children()],
            [],
            "a worker pool must reap its own helpers, or every test class "
            "after this one waits ten seconds for them",
        )

    def test_the_parallel_scan_agrees_with_the_serial_one(self):
        # Every file the full scan reported on, and a stride of the rest: the
        # model classes the cross-unit rules fold are what the two must agree on.
        reported = {
            finding.path for found in _py_scan.findings().values() for finding in found
        }
        sample = [
            source.path
            for index, source in enumerate(_py_scan.corpus())
            if source.path in reported or index % 100 == 0
        ]
        self.assertTrue(sample, "no files to compare the two scans on")

        serial_rows, serial_units = _py_scan.scan_many(sample)
        parts = _parallel.run_chunks(_py_scan.scan_many, sample, 4)
        parallel_rows = [row for rows, _units in parts for row in rows]
        parallel_units = [unit for _rows, units in parts for unit in units]
        self.assertTrue(serial_units, "the sample holds no model class to compare")
        self.assertEqual(sorted(parallel_rows), sorted(serial_rows))
        self.assertEqual(
            sorted(path for path, *_infos in parallel_units),
            sorted(path for path, *_infos in serial_units),
        )

    def test_an_unreadable_file_is_a_finding_not_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "half_written.py"
            broken.write_text("def f(:\n")
            rows, units = _py_scan.scan_many([str(broken)])
        self.assertEqual([row[0] for row in rows], ["unreadable-source"])
        self.assertEqual(units, [])

    def test_the_corpus_is_not_empty(self):
        corpus = _py_scan.corpus()
        self.assertGreater(len(corpus), 5000, "the corpus scan reached almost nothing")
        self.assertTrue(
            any(not source.in_module for source in corpus),
            "the framework (odoo/orm, odoo/tools, ...) is missing from the "
            "corpus again",
        )
        self.assertFalse(
            [source for source in corpus if "/_vendor/" in source.path],
            "vendored third-party code is being linted; nobody here may fix a "
            "finding in it, and the next vendoring would revert the fix anyway",
        )

    def test_the_unique_constraint_scans_reach_the_models(self):
        models, rules = _py_scan.model_class_scale()
        self.assertGreater(models, 1000, "the scan reached almost no models")
        self.assertGreater(rules, 100, "the scan found almost no constraints")

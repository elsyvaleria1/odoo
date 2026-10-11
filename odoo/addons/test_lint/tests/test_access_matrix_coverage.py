import ast
import tempfile
from collections import defaultdict
from pathlib import Path

from . import _access_index as index
from . import lint_case

MATRIX_FILE = Path("tests") / "test_access_matrix.py"


def granted_models(rows, models) -> dict[str, set[str]]:
    granted: defaultdict[str, set[str]] = defaultdict(set)
    for row in rows:
        if (
            row.creates
            and row.kind == "permission"
            and not row.module.startswith("test_")
            and (info := models.get(row.model)) is not None
            and info.kind == "model"
        ):
            granted[row.module].add(row.model)
    return granted


def matrix_models(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and (getattr(node.func, "id", None) or getattr(node.func, "attr", None))
            == "Cell"
        ):
            continue
        candidates = node.args[:1] + [
            keyword.value for keyword in node.keywords if keyword.arg == "model"
        ]
        found.update(
            candidate.value
            for candidate in candidates
            if isinstance(candidate, ast.Constant) and isinstance(candidate.value, str)
        )
    return found


def matrices() -> dict[str, Path]:
    return {
        manifest.name: path
        for manifest in index._module_manifests()
        if (path := Path(manifest.path) / MATRIX_FILE).is_file()
    }


def coverage_findings(granted, found_matrices) -> list[str]:
    return sorted(
        f"{path}: {module} grants {model}, which no cell names"
        for module, path in found_matrices.items()
        for model in granted.get(module, set()) - matrix_models(path)
    )


def missing_findings(granted, found_matrices) -> list[str]:
    return sorted(
        f"{module} ({len(models)} model(s))"
        for module, models in granted.items()
        if models and module not in found_matrices
    )


class TestAccessMatrixCoverage(lint_case.LintCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.coverage, cls.missing = {}, {}
        for repo in lint_case.repositories():
            with index.scope(lint_case.visible(repo)):
                rows = [
                    row
                    for row in index.rows()
                    if index.repo_of_module(row.module) == repo
                ]
                granted = granted_models(rows, index.models())
                found = {
                    module: path
                    for module, path in matrices().items()
                    if index.repo_of_module(module) == repo
                }
            cls.coverage[repo] = coverage_findings(granted, found)
            cls.missing[repo] = missing_findings(granted, found)

    def test_a_matrix_names_every_model_its_module_grants(self):
        self.assert_ratchet_per_repository(
            self.coverage,
            "access_matrix_coverage",
            "model(s) a module with an access matrix grants and no cell names in <repo>",
            "Add a Cell for the model to the module's tests/test_access_matrix.py: "
            "a record, and what each persona may do with it (every persona a cell "
            "does not name expects nothing).",
        )

    def test_modules_without_a_matrix_only_go_down(self):
        self.assert_ratchet_per_repository(
            self.missing,
            "access_matrix_missing",
            "module(s) shipping permission rows without an access matrix in <repo>",
            "Ship tests/test_access_matrix.py (odoo.addons.base.tests.access_matrix): "
            "personas, records and cells for every model the module grants. The "
            "floor only goes down.",
        )


class TestAccessMatrixCoverageSeesItsFaults(lint_case.LintCase):
    def test_a_model_no_cell_names(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "test_access_matrix.py"
        path.write_text(
            "cells = (\n"
            "    Cell('planted.order', 'o', salesman='r'),\n"
            "    Cell(model='planted.line', record='l'),\n"
            ")\n"
        )
        self.assertEqual(matrix_models(path), {"planted.order", "planted.line"})
        granted = {"planted": {"planted.order", "planted.line", "planted.tag"}}
        self.assertEqual(len(coverage_findings(granted, {"planted": path})), 1)
        self.assertFalse(missing_findings(granted, {"planted": path}))
        self.assertEqual(len(missing_findings(granted, {})), 1)

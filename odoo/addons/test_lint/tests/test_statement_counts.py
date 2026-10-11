import ast
from collections import defaultdict
from pathlib import Path

from odoo.modules import Manifest
from odoo.tests import tagged

from . import lint_case

COUNTER_TESTS = frozenset({("base", "tests/test_db_cursor.py")})


def raw_reads(tree: ast.AST) -> list[int]:
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr == "sql_statement_count"
        and isinstance(node.ctx, ast.Load)
    ]


def raw_statement_count_findings() -> dict[str, list[str]]:
    found = defaultdict(list)
    for manifest in Manifest.get_all_addon_manifests():
        root = Path(manifest.path)
        repo = lint_case.repo_of(str(root))
        for path in sorted(root.rglob("*.py")):
            relative = path.relative_to(root)
            if "tests" not in relative.parts:
                continue
            if (manifest.name, relative.as_posix()) in COUNTER_TESTS:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError, UnicodeDecodeError:
                continue
            found[repo].extend(
                f"{manifest.name}/{relative.as_posix()}:{line}"
                for line in raw_reads(tree)
            )
    return found


@tagged("post_install", "-at_install")
class TestStatementCounts(lint_case.LintCase):
    def test_a_test_counts_statements_under_observation(self):
        self.assert_ratchet_per_repository(
            raw_statement_count_findings(),
            "raw_statement_count",
            "raw read(s) of cr.sql_statement_count in the tests of <repo>",
            "rust_engine serves a read on its own connection and counts its "
            "statements on the cursor only by its own reckoning; while the "
            "cursor's statements are observed it leaves every read to Python. "
            "Measure with `with counting_statements(cr) as statements:` "
            "(odoo.tests) and read `statements.count`.",
        )


class TestStatementCountGateSeesItsFaults(lint_case.LintCase):
    def test_a_raw_read_is_found_and_the_helper_is_not(self):
        raw = (
            "def measure(self):\n"
            "    before = self.env.cr.sql_statement_count\n"
            "    work()\n"
            "    return self.env.cr.sql_statement_count - before\n"
        )
        self.assertEqual(raw_reads(ast.parse(raw)), [2, 4])
        counted = (
            "def measure(self):\n"
            "    with counting_statements(self.env.cr) as statements:\n"
            "        work()\n"
            "    return statements.count\n"
        )
        self.assertEqual(raw_reads(ast.parse(counted)), [])

    def test_a_write_of_the_counter_is_not_a_read(self):
        self.assertEqual(raw_reads(ast.parse("cr.sql_statement_count = 0\n")), [])

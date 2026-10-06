import io
import re
import tempfile
import tokenize
from pathlib import Path

from . import lint_case

_RETIRED_ACCESS_NAMES = re.compile(
    r"\bir_rule\b|\bir_model_access\b|\brule_group_rel\b"
    r"|\bir\.rule\b|\bir\.model\.access\b"
    # the retired models' fields: env.ref() of a converted rule answers an
    # ir.access row, which has none of them
    r"|\bdomain_force\b|\bperm_(?:read|write|create|unlink)\b|\brule_groups\b"
)


def _is_migration(path) -> bool:
    parts = Path(path).parts
    return path.endswith(".py") and ("migrations" in parts or "upgrades" in parts)


def migration_findings(paths):
    # every module migrates after base 1.97 has converted both tables, so
    # a script still aimed at them edits rows nothing reads any more
    findings = []
    for path in paths:
        if not _is_migration(path):
            continue
        try:
            source = Path(path).read_text(encoding="utf-8")
            tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
        except OSError, UnicodeDecodeError, SyntaxError, tokenize.TokenError:
            continue
        findings.extend(
            f"{path}:{token.start[0]} {match.group()}"
            for token in tokens
            if token.type != tokenize.COMMENT
            and (match := _RETIRED_ACCESS_NAMES.search(token.string))
        )
    return findings


class TestMigrationsReadIrAccess(lint_case.LintCase):
    def test_no_migration_reaches_for_the_retired_tables(self):
        self.assert_ratchet(
            migration_findings(lint_case.module_file_paths()),
            "access_migration_retired_tables",
            "migration script(s) reading or writing ir_rule or ir_model_access",
            "Base converts both tables before any other module migrates, so the "
            "script edits rows nothing reads: aim it at ir_access.",
        )

    def test_a_migration_reaching_for_the_retired_tables(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        scripts = {
            "sale/migrations/1.2/post-migrate.py": (
                "def migrate(cr, version):\n"
                '    cr.execute("UPDATE ir_rule SET active = false")\n'
                "    env['ir.model.access'].search([])\n"
            ),
            "sale/migrations/1.3/post-migrate.py": (
                "def migrate(cr, version):\n"
                "    # the rule ir_rule_sale_x lived in ir_rule once\n"
                '    cr.execute("UPDATE ir_access SET active = false")\n'
                "    rewrite_converted_domain(cr, 'sale', 'ir_rule_sale_x', '[]')\n"
            ),
            "sale/migrations/1.4/post-migrate.py": (
                "def migrate(cr, version):\n"
                "    rule = env.ref('sale.rule')\n"
                "    rule.write({'domain_force': '[]', 'perm_unlink': False})\n"
            ),
            "sale/models/sale.py": "q = 'SELECT 1 FROM ir_rule'\n",
        }
        for name, text in scripts.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(text)
        findings = migration_findings(str(root / name) for name in scripts)
        self.assertEqual(
            sorted(finding.split(str(root) + "/")[1] for finding in findings),
            [
                "sale/migrations/1.2/post-migrate.py:2 ir_rule",
                "sale/migrations/1.2/post-migrate.py:3 ir.model.access",
                "sale/migrations/1.4/post-migrate.py:3 domain_force",
                "sale/migrations/1.4/post-migrate.py:3 perm_unlink",
            ],
        )

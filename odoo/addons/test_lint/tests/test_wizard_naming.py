import ast
import logging
from pathlib import Path

from . import lint_case
from .test_fixture_models import core_module_roots_by_name, module_of

_logger = logging.getLogger(__name__)

# Transient models that are not a dialog performing one operation keep their
# names (coding guidelines §2.2.3): the settings protocol and its ancestor, the
# engine the import action drives, a dashboard, two logs, a report engine, and
# the rows a bank-transaction preview lists.
NOT_WIZARDS = frozenset(
    {
        "res.config.settings",
        "res.config",
        "base_import.import",
        "approval.dashboard",
        "auth.totp.rate.limit.log",
        "ir.access.sod.conflict",
        "ir.demo_failure",
        "stock.traceability.report",
        "account.online.transaction.preview",
    }
)


def _is_transient(node: ast.ClassDef) -> bool:
    return any(
        (isinstance(base, ast.Attribute) and base.attr == "TransientModel")
        or (isinstance(base, ast.Name) and base.id == "TransientModel")
        for base in node.bases
    )


def declared_transient_names(source: str):
    """Yield the ``_name`` a TransientModel class declares, not one it extends."""
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ClassDef) or not _is_transient(node):
            continue
        name = lint_case._string(lint_case._class_attribute(node, "_name"))
        inherit = lint_case._class_attribute(node, "_inherit")
        elements = (
            inherit.elts if isinstance(inherit, (ast.List, ast.Tuple)) else [inherit]
        )
        inherited = {lint_case._string(element) for element in elements if element}
        if name and name not in inherited:
            yield name


class TestWizardNaming(lint_case.LintCase):
    def test_a_wizard_name_begins_with_wizard(self):
        roots = core_module_roots_by_name()
        scanned = 0
        findings = []
        for path in lint_case.iter_module_files("*.py"):
            if not lint_case.is_core_path(path) or "/migrations/" in path:
                continue
            module = module_of(path, roots)
            if module is None or module.startswith("test_"):
                continue
            source = Path(path).read_text(encoding="utf-8")
            if "TransientModel" not in source:
                continue
            scanned += 1
            findings.extend(
                f"{path}: {name}"
                for name in declared_transient_names(source)
                if not name.startswith("wizard.") and name not in NOT_WIZARDS
            )
        _logger.info("scanned %s python file(s) declaring a TransientModel", scanned)
        self.assert_ratchet(
            findings,
            "lint_wizard_naming",
            "TransientModel(s) whose _name does not begin with wizard.",
            "Name the wizard wizard.<subject>.<operation> (coding guidelines "
            "§2.2.3); a transient model that is not a dialog goes in NOT_WIZARDS "
            "with the reason.",
        )

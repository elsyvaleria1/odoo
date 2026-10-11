from odoo.libs.parse_version import parse_version
from odoo.modules.module import adapt_version
from odoo.tools import SQL
from odoo.tools.module_data import fold_module

# the migrations of a module folded into base leave with it, so no database
# may cross the fold below the last version they bring it to: uom has none,
# resource's last is 1.39
FOLDABLE = {"uom": "1.2", "resource": "1.39"}


def _installed_version(cr, module: str) -> str | None:
    cr.execute(
        SQL(
            "SELECT db_version FROM ir_module_module "
            "WHERE name = %s AND state != 'uninstalled'",
            module,
        )
    )
    row = cr.fetchone()
    return (row[0] or "") if row else None


def migrate(cr, version):
    if not version:
        return
    # units of measure are as basic as currencies, and everything in the ERP
    # can be a resource: base holds both
    for module, foldable in FOLDABLE.items():
        installed = _installed_version(cr, module)
        if installed is None:
            continue
        if parse_version(installed) < parse_version(adapt_version(foldable)):
            raise RuntimeError(
                f"{module} is at {installed}: upgrade it to {foldable} on a "
                "commit before its fold into base, then upgrade again"
            )
        fold_module(cr, module, "base")

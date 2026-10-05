from odoo.db.schema import table_exists
from odoo.tools import module_data

# what describes or follows a thing is named for the resource it is; the
# modules that declare these models load after this one, onto the new names
RENAMED = (
    ("resource.asset.kind.document", "resource.kind.document"),
    ("resource.asset.kind.position", "resource.kind.position"),
    ("resource.asset.kind", "resource.kind"),
    ("resource.asset.log", "resource.log"),
    ("resource.asset.part.flag", "resource.part.flag"),
    ("resource.asset.part", "resource.part"),
    ("resource.asset.tag", "resource.tag"),
)


def migrate(cr, version):
    if not version:
        return
    for old, new in RENAMED:
        if table_exists(cr, old.replace(".", "_")) and not table_exists(
            cr, new.replace(".", "_")
        ):
            module_data.rename_model(cr, old, new)

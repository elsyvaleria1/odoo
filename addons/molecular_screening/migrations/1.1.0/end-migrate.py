from odoo.db import schema


def migrate(cr, version):
    if not version:
        return
    schema.drop_columns(
        cr, "molecular_docking_result", ("campaign_id", "target_id", "compound_id")
    )
    schema.drop_columns(cr, "molecular_validation_run", ("campaign_id",))
    schema.drop_columns(
        cr, "molecular_target", ("rmsd_top", "rmsd_best", "affinity_top")
    )

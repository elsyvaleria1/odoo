from odoo.tools import module_data

RENAMED = (("partner_id", "vendor_id"), ("partner_ref", "vendor_ref"))


def migrate(cr, version):
    if not version:
        return
    # every model of the table tree and the depreciation board, which
    # inherits the asset's fields, reflects its own copy of each field
    cr.execute(
        """
        SELECT DISTINCT model FROM ir_model_fields
         WHERE name = 'partner_ref'
           AND (model = 'resource.asset' OR model LIKE 'resource.asset.%%'
                OR model = 'account.depreciation.board')
        """
    )
    models = sorted(
        (row[0] for row in cr.fetchall()), key=lambda model: model != "resource.asset"
    )
    for model in models:
        for old, new in RENAMED:
            module_data.rename_field(cr, model, old, new)

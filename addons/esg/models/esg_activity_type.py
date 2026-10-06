from odoo import fields, models

from odoo.addons.base.models.mixin_catalog import name_uniq_index


class EsgActivityType(models.Model):
    _name = "esg.activity.type"
    _description = "Activity Type"

    name = fields.Char(
        translate=True,
        required=True,
    )

    _name_src_uniq = name_uniq_index(
        message="A tag with the same name already exists.",
    )

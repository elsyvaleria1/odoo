from odoo import fields, models


class Data_MergeRule(models.Model):
    _name = "data_merge.rule"
    _description = "Deduplication Rule"
    _order = "sequence, field_id"

    model_id = fields.Many2one(
        comodel_name="data_merge.model",
        string="Deduplication Model",
        index=True,
        required=True,
        ondelete="cascade",
    )
    res_model_id = fields.Many2one(
        related="model_id.res_model_id",
        readonly=True,
    )
    field_id = fields.Many2one(
        comodel_name="ir.model.fields",
        string="Unique ID Field",
        required=True,
        domain="[('model_id', '=', res_model_id), ('ttype', 'in', ('char', 'text', 'many2one')), ('store', '=', True)]",
        ondelete="cascade",
    )
    match_mode = fields.Selection(
        selection=lambda self: self._available_match_modes(),
        string="Merge If",
        default="exact",
        required=True,
    )
    sequence = fields.Integer(default=1)

    _uniq_model_id_field_id = models.Constraint(
        "unique(model_id, field_id)",
        "A field can only appear once!",
    )

    def _available_match_modes(self):
        modes = [("exact", self.env._("Exact Match"))]
        # can't conditionally set demo data...
        if self.env.context.get("install_mode") or self.env.registry.unaccent_status:
            modes.append(("accent", self.env._("Case/Accent Insensitive Match")))
        return modes

    def _update_default_rules(self) -> None:
        if self.env.registry.unaccent_status:
            self.match_mode = "accent"

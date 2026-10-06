from odoo import api, fields, models


class PosPrepStage(models.Model):
    _name = "pos.prep.stage"
    _description = "Pos Preparation Stage"
    _inherit = ["mixin.pos.load"]
    _order = "sequence, id"

    name = fields.Char(required=True)
    color = fields.Char()
    alert_timer = fields.Integer(
        string="Alert timer (min)",
        help="Timer after which the order will be highlighted",
    )
    prep_display_id = fields.Many2one(
        comodel_name="pos.prep.display",
        string="Preparation display",
        index="btree_not_null",
        ondelete="cascade",
    )
    sequence = fields.Integer()

    @api.model
    def _load_pos_preparation_data_domain(self, data):
        stage_ids = data["pos.prep.display"][0]["stage_ids"]
        return [("id", "in", stage_ids)]

    def is_stage_position(self, position) -> bool:
        stage_ids = self.prep_display_id.stage_ids
        return len(stage_ids) >= abs(position) and self.id == stage_ids[position].id

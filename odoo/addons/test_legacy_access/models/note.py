from odoo import fields, models


class TestLegacyAccessNote(models.Model):
    _name = "test_legacy_access.note"
    _description = "A note guarded as a stock module guards its records"

    name = fields.Char()
    user_id = fields.Many2one(comodel_name="res.users")
    public = fields.Boolean()
    state = fields.Selection(
        selection=[("draft", "Draft"), ("cancel", "Cancelled")],
        default="draft",
    )

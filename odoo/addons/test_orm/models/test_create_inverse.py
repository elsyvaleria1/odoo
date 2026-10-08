from odoo import api, fields, models


class TestOrmDelegateBase(models.Model):
    _name = "test_orm.delegate_base"
    _description = "Row whose fields a delegating record inherits"

    name = fields.Char()
    note = fields.Html()
    tag_ids = fields.Many2many("test_orm.category")


class TestOrmDelegating(models.Model):
    _name = "test_orm.delegating"
    _description = "Record whose inverse flushes while its create applies it"
    _inherits = {"test_orm.delegate_base": "base_id"}

    base_id = fields.Many2one(
        "test_orm.delegate_base", required=True, ondelete="cascade"
    )
    signature = fields.Char(compute="_compute_signature", store=True, readonly=False)
    note_text = fields.Char(compute="_compute_note_text", store=True)
    tag_count = fields.Integer(compute="_compute_tag_count", store=True)
    preference = fields.Char(
        compute="_compute_preference", inverse="_inverse_preference"
    )

    @api.depends("name")
    def _compute_signature(self):
        for record in self:
            record.signature = record.name and f"-- {record.name}"

    @api.depends("note")
    def _compute_note_text(self):
        for record in self:
            record.note_text = record.note and str(record.note)

    @api.depends("tag_ids")
    def _compute_tag_count(self):
        for record in self:
            record.tag_count = len(record.tag_ids)

    def _compute_preference(self):
        for record in self:
            record.preference = False

    def _inverse_preference(self):
        self.env.flush_all()

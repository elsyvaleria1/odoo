from odoo import fields, models


class TestOrmBigint(models.Model):
    _name = "test_orm.bigint"
    _description = "A 64-bit integer beside a 32-bit one"

    amount = fields.Integer(bigint=True)
    count = fields.Integer()
    parent_id = fields.Many2one("test_orm.bigint")
    parent_amount = fields.Integer(related="parent_id.amount", store=True)

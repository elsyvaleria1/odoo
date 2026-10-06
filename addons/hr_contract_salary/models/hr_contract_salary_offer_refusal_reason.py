from odoo import fields, models


class HrContractSalaryOfferRefusalReason(models.Model):
    _name = "hr.contract.salary.offer.refusal.reason"
    _description = "Salary Offer Refusal Reasons"
    _order = "sequence, id"

    name = fields.Char(string="Description")
    sequence = fields.Integer()

from odoo import fields, models


class Data_CleaningTestModel(models.Model):
    _name = "data_cleaning.test.model"
    _description = "Tests: Data Cleaning Test Model"

    active = fields.Boolean(default=True)
    name = fields.Char()
    phone = fields.Char()
    note = fields.Text()
    translated_field = fields.Char(translate=True)
    country_id = fields.Many2one(
        comodel_name="res.country",
        default=lambda x: x.env.company.country_id.id,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda x: x.env.company.id,
    )

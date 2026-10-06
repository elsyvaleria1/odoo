from odoo import fields, models


class WizardResourceScheduleExceptionLoadPublicHolidayLine(models.TransientModel):
    _name = "wizard.resource.schedule.exception.load.public.holiday.line"
    _description = "Load Public Holidays Line"
    _order = "company_id, start_date, name"

    wizard_id = fields.Many2one(
        comodel_name="wizard.resource.schedule.exception.load.public.holiday",
        required=True,
        ondelete="cascade",
    )
    name = fields.Char(required=True)
    start_date = fields.Date(required=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        required=True,
    )

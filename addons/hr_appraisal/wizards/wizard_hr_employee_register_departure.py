from odoo import fields, models


class WizardHrEmployeeRegisterDeparture(models.TransientModel):
    _inherit = "wizard.hr.employee.register.departure"

    delete_appraisal = fields.Boolean(
        string="Delete Future Appraisals",
        default=True,
        help="Delete draft appraisals and archive ongoing ones scheduled after the contract end date.",
    )

    def action_register_departure(self):
        action = super().action_register_departure()
        if self.delete_appraisal:
            future_appraisals = self.env["hr.appraisal"].search(
                [
                    ("employee_id", "in", self.employee_ids.ids),
                    ("state", "in", ["1_new", "2_pending"]),
                    ("date_close", ">", self.departure_date),
                ]
            )
            # Only drafts can be deleted - `_unlink_if_new_or_cancel` raises for
            # anything else, which used to make the whole departure fail. An
            # ongoing appraisal is archived instead, so the record of it stays.
            drafts = future_appraisals.filtered(lambda a: a.state == "1_new")
            (future_appraisals - drafts).action_archive()
            drafts.unlink()
        return action

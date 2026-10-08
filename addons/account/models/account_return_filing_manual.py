from odoo import fields, models
from odoo.exceptions import UserError


class AccountReturnFilingManual(models.AbstractModel):
    _name = "account.return.filing.manual"
    _inherit = ["mixin.account.return.filing.channel"]
    _description = "Tax Return Filed Outside Odoo"

    def _send_submission(self, submission) -> dict | None:
        if not submission.external_ref and not submission.receipt_attachment_ids:
            raise UserError(
                self.env._(
                    "Record the authority's reference or attach its receipt: that is the "
                    "evidence the return was filed."
                )
            )
        submission._update_from_channel("accepted", date_sent=fields.Datetime.now())
        return None

    def _update_submission_status(self, submission) -> None:
        return None

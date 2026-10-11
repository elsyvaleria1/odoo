from odoo import models


class MixinAccountReturnFilingChannel(models.AbstractModel):
    _name = "mixin.account.return.filing.channel"
    _description = "Tax Return Filing Channel"

    def _send_submission(self, submission) -> dict | None:
        raise NotImplementedError

    def _update_submission_status(self, submission) -> None:
        raise NotImplementedError

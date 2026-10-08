from odoo import models


class MixinAccountReturnFilingChannel(models.AbstractModel):
    _name = "mixin.account.return.filing.channel"
    _description = "Tax Return Filing Channel"

    def _send_submission(self, submission) -> dict | None:
        """Transmit ``submission`` and record the authority's first answer on it.

        Return an action when the user must act before anything is sent (a login at the
        authority); the submission is then sent again once that is done.
        """
        raise NotImplementedError

    def _update_submission_status(self, submission) -> None:
        raise NotImplementedError

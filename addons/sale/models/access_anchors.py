from odoo import models
from odoo.tools import frozendict


class AccountMoveSendBatchWizard(models.TransientModel):
    _inherit = "wizard.account.move.send.batch"

    _access_anchors = frozendict(
        {
            "owner": models.Anchor("move_ids.invoice_user_id", shared=True),
        }
    )


class AccountMoveSendWizard(models.TransientModel):
    _inherit = "wizard.account.move.send"

    _access_anchors = frozendict(
        {
            "owner": models.Anchor("move_id.invoice_user_id", shared=True),
        }
    )

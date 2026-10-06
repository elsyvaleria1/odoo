from typing import TYPE_CHECKING

from odoo import api, models

if TYPE_CHECKING:
    import requests

    from odoo.addons.base.models.ir_egress import PolicyName


class IrEgress(models.AbstractModel):
    _inherit = "ir.egress"

    @api.model
    def _configure_session(
        self, session: requests.Session, *, purpose: str, policy: PolicyName
    ) -> None:
        self.env["integration.ml.policy"]._check_allowed(self.env.company, purpose)
        super()._configure_session(session, purpose=purpose, policy=policy)

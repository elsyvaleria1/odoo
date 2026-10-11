from odoo import models


class ApprovalCategory(models.Model):
    _inherit = "approval.category"

    def _steps_are_generated(self) -> bool:
        return (
            self
            == self.env.ref("mrp_plm.approval_category_eco", raise_if_not_found=False)
            or super()._steps_are_generated()
        )

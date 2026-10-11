from odoo import fields, models


class EventRegistration(models.Model):
    _inherit = "event.registration"

    sale_status = fields.Selection(
        selection=[
            ("to_pay", "Not Sold"),
            ("sold", "Sold"),
            ("free", "Free"),
        ],
        compute="_compute_registration_status",
        precompute=True,
        compute_sudo=True,
        store=True,
        readonly=True,
    )

    def _has_order(self) -> bool:
        return False

    def _compute_registration_status(self) -> None:
        if not self._has_order():
            for reg in self:
                if not reg.sale_status:
                    reg.sale_status = "free"

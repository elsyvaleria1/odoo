from odoo import models

BOOKABLE_STATES = ("available", "in_service", "maintenance")


class ResourceResource(models.Model):
    _inherit = "resource.resource"

    def _accepts_bookings(self) -> bool:
        self.check_singleton()
        return not self.kind_id or self.state in BOOKABLE_STATES

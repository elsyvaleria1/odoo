from odoo import models


class QualityPoint(models.Model):
    _inherit = "quality.point"

    def _get_sync_values(self):
        if not self:
            return ()
        self.check_singleton()
        return (self.test_type_id, self.title, self.component_id)

from odoo import models
from odoo.tools import ormcache


class ResCompany(models.Model):
    _inherit = "res.company"

    def _hr_presence_valid_ips(self) -> set:
        self.check_singleton()
        raw = self.hr_config_id.hr_presence_control_ip_list or ""
        return {part.strip() for part in raw.split(",") if part.strip()}

    @ormcache()
    def _is_presence_ip_tracking_enabled(self) -> bool:
        return bool(
            self.env["hr.config"]
            .sudo()
            .search_count([("hr_presence_control_ip", "=", True)], limit=1)
        )

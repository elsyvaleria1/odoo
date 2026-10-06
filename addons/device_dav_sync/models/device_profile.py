from odoo import api, fields, models


class DeviceConfig(models.Model):
    _inherit = "device.profile"

    dav_enabled = fields.Boolean(
        default=False,
        help="Enable CalDAV/CardDAV server functionality",
    )
    dav_addressbook_enabled = fields.Boolean(
        default=True,
        help="Enable CardDAV addressbook synchronization",
    )
    dav_calendar_enabled = fields.Boolean(
        default=True,
        help="Enable CalDAV calendar synchronization",
    )
    dav_base_url = fields.Char(
        compute="_compute_dav_base_url",
        help="Base URL for DAV services (e.g., https://odoo.example.com/dav)",
    )

    dav_sync_window_days = fields.Integer(
        default=90,
        help="Number of days to sync (past and future events/tasks)",
    )
    dav_max_items_per_sync = fields.Integer(
        default=1000,
        help="Maximum number of items to return in a single sync request",
    )

    @api.depends()
    def _compute_dav_base_url(self) -> None:
        for config in self:
            base_url = self.env.registry.settings.get(
                self.env, "web.base.url", "http://localhost:8069"
            )
            config.dav_base_url = f"{base_url}/dav"

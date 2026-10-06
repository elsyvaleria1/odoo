from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    maintenance_duration_hours = fields.Float(
        string="Default Maintenance Duration (Hours)",
        default=1.0,
        config_parameter="asset_ledger_maintenance.default_duration",
        help="Default duration in hours for maintenance operations. "
        "This value will be used when creating new maintenance plans, "
        "templates, and manual maintenance orders.",
    )

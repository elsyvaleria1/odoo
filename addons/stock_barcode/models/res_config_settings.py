from odoo import api, fields, models

from odoo.addons.barcodes.models.ir_http import DEFAULT_MAX_TIME_BETWEEN_KEYS_MS


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    barcode_nomenclature_id = fields.Many2one(
        comodel_name="barcode.nomenclature",
        related="company_id.barcodes_config_id.nomenclature_id",
        readonly=False,
    )
    stock_barcode_demo_active = fields.Boolean(
        string="Demo Data Active",
        compute="_compute_stock_barcode_demo_active",
    )
    show_barcode_nomenclature = fields.Boolean(
        compute="_compute_show_barcode_nomenclature"
    )
    stock_barcode_mute_sound_notifications = fields.Boolean(
        string="Mute Barcode application sounds",
        config_parameter="stock_barcode.mute_sound_notifications",
    )
    barcode_max_time_between_keys_in_ms = fields.Integer(
        string="Max time between each key",
        default=DEFAULT_MAX_TIME_BETWEEN_KEYS_MS,
        config_parameter="barcode.max_time_between_keys_in_ms",
        help="Maximum delay between each key in ms (150 ms by default)",
    )
    barcode_rfid_batch_time = fields.Integer(
        string="RFID Timer",
        config_parameter="stock_barcode.barcode_rfid_batch_time",
    )
    barcode_separator_regex = fields.Char(
        string="Multiscan Separator",
        config_parameter="stock_barcode.barcode_separator_regex",
        help="This regex is used in the Barcode application to separate individual barcodes when "
        "an aggregate barcode (i.e. single barcode consisting of multiple barcode encodings) is scanned.",
    )

    @api.depends("company_id")
    def _compute_show_barcode_nomenclature(self) -> None:
        barcode_nomenclature_count = self.env["barcode.nomenclature"].search_count([])
        for rec in self:
            rec.show_barcode_nomenclature = (
                rec.module_stock_barcode and barcode_nomenclature_count > 1
            )

    @api.depends("company_id")
    def _compute_stock_barcode_demo_active(self) -> None:
        self.stock_barcode_demo_active = bool(
            self.env["ir.module.module"].search_count(
                [("name", "=", "stock_barcode"), ("demo", "=", True)], limit=1
            )
        )

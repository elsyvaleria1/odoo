from odoo import api, fields, models


class ProductTrace(models.Model):
    _name = "product.trace"
    _inherit = ["product.trace", "mixin.gps"]

    gps_device_id = fields.Many2one(
        related="asset_id.gps_device_id",
        readonly=False,
    )

    def _gps_resource(self):
        self.check_singleton()
        return self.asset_id

    @api.model
    def _asset_ledger_field_map(self):
        return {**super()._asset_ledger_field_map(), "gps_device_id": "gps_device_id"}

    @api.model
    def _gps_odometer_lookback_days(self):
        return self.env["resource.resource"]._gps_odometer_lookback_days()

    @api.model
    def _gps_odometer_today(self, company):
        return self.env["resource.resource"]._gps_odometer_today(company)

    @api.model
    def _gps_odometer_split_ledgers(self, assets):
        split = self.env["resource.resource"]._gps_odometer_split_ledgers(
            assets.asset_id
        )
        return assets.filtered(lambda lot: lot.asset_id in split)

    @api.model
    def _cron_record_gps_odometer(self):
        return self.env["resource.resource"]._cron_record_gps_odometer()

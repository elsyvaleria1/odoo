from odoo import api, models

MOBILE_CATEGORY_CODE = "mobile_phone"


class DeviceDevice(models.Model):
    _inherit = "device.device"

    @api.model
    def _device_kind_categories(self, kind):
        # A company phone reports its position like a tracker does, so it is a
        # GPS device. It used to qualify by carrying an IMEI, which also made a
        # SIM-equipped access terminal one.
        codes = super()._device_kind_categories(kind)
        if kind == "gps":
            return [*codes, MOBILE_CATEGORY_CODE]
        return codes

    @api.model
    def _call_reporter_category_codes(self) -> set:
        return {*super()._call_reporter_category_codes(), MOBILE_CATEGORY_CODE}

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.phone_call.models.phone_call import number_key

MOBILE_CATEGORY_CODE = "mobile_phone"


class DeviceDevice(models.Model):
    _inherit = "device.device"

    device_category_code = fields.Char(related="device_category_id.code")
    line_number = fields.Char(
        string="Phone Number",
        help="The number of the phone's SIM, as the carrier issued it.",
    )
    line_number_digits = fields.Char(
        compute="_compute_line_number_digits",
        store=True,
        index="btree_not_null",
        help="The number's last digits, as calls and other numbers are matched "
        "to it whatever prefix they carry.",
    )

    @api.depends("line_number")
    def _compute_line_number_digits(self) -> None:
        for device in self:
            device.line_number_digits = number_key(device.line_number) or False

    @api.constrains("line_number_digits", "active", "device_category_id")
    def _check_line_number_digits(self) -> None:
        phones = self.filtered(
            lambda device: (
                device.line_number_digits
                and device.active
                and device.device_category_code == MOBILE_CATEGORY_CODE
            )
        )
        if not phones:
            return
        twins = self.search(
            [
                ("id", "not in", phones.ids),
                ("line_number_digits", "in", phones.mapped("line_number_digits")),
                ("device_category_id.code", "=", MOBILE_CATEGORY_CODE),
            ]
        )
        taken = {twin.line_number_digits: twin for twin in twins}
        seen = {}
        for phone in phones:
            twin = taken.get(phone.line_number_digits) or seen.get(
                phone.line_number_digits
            )
            if twin:
                raise ValidationError(
                    self.env._(
                        "%(number)s is already the number of %(twin)s.",
                        number=phone.line_number,
                        twin=twin.display_name,
                    )
                )
            seen[phone.line_number_digits] = phone

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

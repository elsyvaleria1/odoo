from odoo import fields, models
from odoo.fields import Domain
from odoo.http import request
from odoo.libs.datetime import all_timezones, timezone


class Website(models.Model):
    _inherit = "website"

    tz = fields.Selection(
        selection="_selection_timezones",
        string="Timezone",
        default=lambda self: self.env.user.tz or "UTC",
        required=True,
        help="Select your website timezone here.",
    )

    def _selection_timezones(self):
        return [
            (tz, f"{tz} {self._get_utc_offset(tz)}")
            for tz in sorted(
                all_timezones(), key=lambda tz: tz if not tz.startswith("Etc/") else "_"
            )
        ]

    def _product_domain(self):
        return Domain.OR([[("rent_ok", "=", True)], super()._product_domain()])

    def _is_customer_in_the_same_timezone(self) -> bool:
        now = fields.Datetime.now()
        customer_tz = request.cookies.get("tz") if request else None

        return (
            now.replace(tzinfo=timezone(self.tz)).utcoffset()
            == now.replace(tzinfo=timezone(customer_tz or "UTC")).utcoffset()
        )

    def _get_utc_offset(self, tz) -> str:
        utcoffset = fields.Datetime.now().replace(tzinfo=timezone(tz)).strftime("%z")
        return f"(UTC {utcoffset[0]} {utcoffset[1:3]}:{utcoffset[3:5]})"

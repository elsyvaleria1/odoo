from urllib.parse import urljoin as url_join

from odoo import Command, api, fields, models
from odoo.exceptions import ValidationError

from ..tools.google_reserve_iap import GoogleReserveIAP


class GoogleReserveMerchant(models.Model):
    _name = "google.reserve.merchant"
    _description = "Google Reserve Merchant"
    _inherit = ["mixin.mail.thread.phone"]

    def _default_website_id(self):
        default_website_url = False
        if default_website := self.env.ref(
            "website.default_website", raise_if_not_found=False
        ):
            default_website_url = default_website.get_base_url()
            if default_website.homepage_url:
                default_website_url = url_join(
                    default_website_url, default_website.homepage_url
                )

        return default_website_url

    name = fields.Char(
        string="Merchant Name",
        default=lambda self: self.env.company.name,
        required=True,
    )
    appointment_type_ids = fields.One2many(
        comodel_name="appointment.type",
        inverse_name="google_reserve_merchant_id",
        string="Appointments",
    )

    business_category = fields.Char(
        required=True,
        help="Used by Google to try to match your physical address to your business.",
    )
    phone_ids = fields.Many2many(
        comodel_name="phone.number",
        relation="google_reserve_merchant_phone_number_rel",
        column1="merchant_id",
        column2="phone_number_id",
        default=lambda self: [Command.set(self.env.company.phone_ids.ids)],
        help="Used by Google to properly match merchants and partners, recommended.",
    )
    website_url = fields.Char(
        string="Website URL",
        default=lambda self: self._default_website_id(),
        help="Used by Google to properly match merchants and partners, recommended.",
    )
    location_id = fields.Many2one(
        comodel_name="res.partner",
        string="Address",
        default=lambda self: self.env.company.partner_id,
        required=True,
        help="Used by Google to try to match your physical address to your business.",
    )
    location_country_id = fields.Many2one(
        comodel_name="res.country",
        related="location_id.country_id",
    )

    @api.constrains("location_id")
    def _check_location(self) -> None:
        for merchant in self:
            if not all(
                merchant.location_id[field]
                for field in ["country_id", "city", "zip", "street"]
            ):
                raise ValidationError(
                    self.env._(
                        "Google Reserve requires a complete address."
                        "Including a Country, a City, a Postal Code and a Street"
                    )
                )

    def write(self, vals):
        res = super().write(vals)
        for merchant in self:
            GoogleReserveIAP().update_merchant(merchant)

        return res

    @api.model
    def _google_reserve_upload_feed(self) -> None:
        google_reserve_iap = GoogleReserveIAP()

        merchants = self.env["google.reserve.merchant"].search([])
        google_reserve_iap.upload_availabilities_feed(merchants)

        appointments_pending_sync = self.env["appointment.type"].search(
            [("google_reserve_pending_sync", "=", True)]
        )
        if appointments_pending_sync:
            appointments_pending_sync.google_reserve_pending_sync = False

    def _get_google_reserve_iap_endpoint(self):
        return self.env.registry.settings.get(
            self.env,
            "appointment_google_reserve.google_reserve_iap_endpoint",
            "https://google-reserve.api.odoo.com",
        )

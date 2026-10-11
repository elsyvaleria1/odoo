"""Lazada Shop Creation Wizard.

Allows users to create Lazada shops by entering API credentials and authorizing
the connection with Lazada.
"""

from odoo import fields, models


class WizardLazadaShopCreate(models.TransientModel):
    _name = "wizard.lazada.shop.create"
    _description = "Lazada Shop Creation Wizard"

    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
    )
    app_key = fields.Char(
        required=True,
        help="Your Lazada application key (App Key). You can find this in your Lazada "
        "Service Provider Center after creating an application. Enter this before "
        "authorizing the connection.",
    )
    app_secret = fields.Char(
        required=True,
        help="Your Lazada application secret (App Secret). This is provided alongside your "
        "App Key in the Lazada Service Provider Center. Keep this confidential "
        "and enter it before authorizing the connection.",
    )

    def action_create_shop(self):
        self.check_singleton()
        shop = self.env["lazada.shop"].create(
            {
                "name": self.env._("New Lazada Shop"),
                "app_key": self.app_key,
                "app_secret": self.app_secret,
                "company_id": self.company_id.id,
            }
        )

        return shop.action_view_auth_link()

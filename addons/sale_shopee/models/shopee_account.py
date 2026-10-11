import time
from urllib.parse import urlencode as url_encode

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sale_shopee import const, utils
from odoo.addons.sale_shopee.controllers.onboarding import issue_authorization_state


class ShopeeAccount(models.Model):
    _name = "shopee.account"
    _inherit = ["mixin.credential.holder"]
    _description = "Shopee Account"
    _credential_holder_field = "account_credential_id"
    _credential_purpose = "sale_shopee:account"
    _CREDENTIAL_FIELDS = {
        "partner_key": "partner_key",
    }

    name = fields.Char(
        readonly=False,
        required=True,
        help="The user-defined name of the account.",
    )
    api_endpoint = fields.Selection(
        selection=[
            ("production_singapore", "Shopee Production Endpoint (Singapore)"),
            ("production_china", "Shopee Production Endpoint (China)"),
            ("production_brazil", "Shopee Production Endpoint (Brazil)"),
            ("test", "Shopee Testing Endpoint"),
            ("test_china", "Shopee Testing Endpoint (China)"),
        ],
        string="API Endpoint",
        required=True,
        help="The API endpoint to use for the Shopee API calls. There are production and testing"
        " endpoints. Among the endpoints, choose the one that is geographically closest to"
        " the marketplace you are targeting.",
    )
    company_ids = fields.Many2many(
        comodel_name="res.company",
        string="Allowed Company",
        help="If this field is empty, all companies will be allowed.",
    )
    partner_identifier = fields.Integer(
        string="Partner ID",
        required=True,
    )
    account_credential_id = fields.Many2one(
        comodel_name="credential.credential",
        string="Credential",
        copy=False,
        ondelete="restrict",
        groups="base.group_system",
        help="Holds this account's Shopee partner key.",
    )
    partner_key = fields.Char(
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        required=True,
    )
    shop_ids = fields.One2many(
        comodel_name="shopee.shop",
        inverse_name="account_id",
        string="Shops",
    )
    shop_count = fields.Count(count_of="shop_ids")


    @api.onchange("api_endpoint")
    def _onchange_api_endpoint(self) -> dict | None:
        if self.shop_ids:
            return {
                "warning": {
                    "title": self.env._("Warning"),
                    "message": self.env._(
                        "Changing API endpoint will reset the authorization of the shops."
                    ),
                }
            }
        return None


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") and vals.get("partner_identifier"):
                vals["name"] = self.env._(
                    "Shopee API Account - %(partner_id)s",
                    partner_id=vals["partner_identifier"],
                )

        return super().create(vals_list)

    def write(self, vals):
        if "api_endpoint" in vals:
            if vals["api_endpoint"] != self.api_endpoint:
                self.shop_ids._reset_tokens()
        return super().write(vals)


    def action_view_shops(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Shops"),
            "res_model": "shopee.shop",
            "view_mode": "list,form",
            "domain": [("id", "in", self.shop_ids.ids)],
        }

    def action_view_auth_link(self) -> dict:
        self.check_singleton()

        path = const.API_OPERATIONS_MAPPING["auth_partner"]["url_path"]
        timestamp = int(time.time())
        sign = utils.get_public_sign(self, path, timestamp)
        redirect_url = (
            self.get_base_url()
            + f"/shopee/return_from_authorization/{issue_authorization_state(self)}"
        )
        params = {
            "partner_id": self.partner_identifier,
            "timestamp": timestamp,
            "sign": sign,
            "redirect": redirect_url,
        }
        url = f"{const.API_PATHS[self.api_endpoint]}{path}?{url_encode(params)}"
        response = self.env["ir.egress"].request(
            "GET", url, purpose="shopee", timeout=60
        )
        if response.status_code != 200:
            content = response.json()
            if content.get("error"):
                raise UserError(
                    self.env._(
                        "Failed to authorize shop due to the following error:\n- %(message)s\n\n"
                        "One of the following input could be incorrect: Partner ID, Partner Key, or"
                        " API Endpoint.",
                        message=content.get("message"),
                    )
                )

        return {
            "type": "ir.actions.act_url",
            "url": url,
            "target": "self",
        }

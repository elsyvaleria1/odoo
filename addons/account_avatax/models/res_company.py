import logging

from odoo import Command, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"
    _CREDENTIAL_FIELDS = {
        "avalara_api_key": "avalara_api_key",
    }

    avalara_api_id = fields.Char(
        string="Avalara API ID",
        groups="base.group_system",
    )
    avalara_api_key = fields.Char(
        string="Avalara API KEY",
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        classification="secret.credential",
        groups="base.group_system",
    )
    avalara_environment = fields.Selection(
        selection=[
            ("sandbox", "Sandbox"),
            ("production", "Production"),
        ],
        default="sandbox",
        required=True,
    )
    avalara_commit = fields.Boolean(string="Commit in Avatax")
    avalara_address_validation = fields.Boolean()
    avalara_use_upc = fields.Boolean(
        string="Use UPC",
        default=True,
    )
    setting_account_avatax = fields.Boolean(
        string="Use AvaTax",
        store=True,
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    avalara_api_id = fields.Char(
        related="company_id.avalara_api_id",
        string="Avalara API ID",
        readonly=False,
    )
    avalara_api_key = fields.Char(
        related="company_id.avalara_api_key",
        string="Avalara API KEY",
        readonly=False,
    )
    avalara_partner_code = fields.Char(
        related="company_id.partner_id.avalara_partner_code",
        string="Avalara Company Code",
        readonly=False,
        help="The Avalara Company Code for this company. Avalara will interpret as DEFAULT if it"
        " is not set.",
    )
    avalara_environment = fields.Selection(
        related="company_id.avalara_environment",
        string="Avalara Environment",
        readonly=False,
        required=True,
    )
    avalara_commit = fields.Boolean(
        related="company_id.avalara_commit",
        string="Commit in Avatax",
        readonly=False,
        help="The transactions will be committed for reporting in Avatax.",
    )
    avalara_address_validation = fields.Boolean(
        related="company_id.avalara_address_validation",
        string="Avalara Address Validation",
        readonly=False,
        help="Validate and correct the addresses of partners in North America with Avalara.",
    )
    avalara_use_upc = fields.Boolean(
        related="company_id.avalara_use_upc",
        string="Use UPC",
        readonly=False,
        help="Use Universal Product Code instead of custom defined codes in Avalara.",
    )
    setting_account_avatax = fields.Boolean(
        related="company_id.setting_account_avatax",
        readonly=False,
    )

    def avatax_sync_company_params(self) -> bool:

        def get_countries(code_list):
            uncached = set(code_list) - set(country_cache)
            if uncached:
                country_cache.update(
                    {
                        country.code: country.id
                        for country in self.env["res.country"].search(
                            [("code", "in", tuple(uncached))]
                        )
                    }
                )
            return self.env["res.country"].browse(
                [country_cache[code] for code in code_list]
            )

        country_cache = {"*": False}

        existing = {
            exempt["code"]
            for exempt in self.env["avatax.exemption"].search_read(
                domain=[("company_id", "=", self.company_id.id)],
                fields=["code"],
            )
        }
        client = self.env["mixin.account.external.tax"]._get_client(self.company_id)
        response = client.list_entity_use_codes()
        error = self.env["mixin.account.external.tax"]._handle_response(
            response,
            self.env._(
                "Odoo could not fetch the exemption codes of %(company)s",
                company=self.company_id.display_name,
            ),
        )
        if error:
            raise UserError(error)
        self.env["avatax.exemption"].create(
            [
                {
                    "code": vals["code"],
                    "description": vals["description"],
                    "name": vals["name"],
                    "valid_country_ids": [
                        Command.set(get_countries(vals["validCountries"]).ids)
                    ],
                    "company_id": self.company_id.id,
                }
                for vals in response["value"]
                if vals["code"] not in existing
            ]
        )
        return True

    def avatax_ping(self) -> dict:
        client = self.env["mixin.account.external.tax"]._get_client(self.company_id)
        query_result = client.ping()

        html_content = self._format_response(query_result)

        return {
            "name": self.env._("Test Result"),
            "type": "ir.actions.act_window",
            "res_model": "wizard.res.company.view.avatax.connection",
            "res_id": self.env["wizard.res.company.view.avatax.connection"]
            .create({"server_response": html_content})
            .id,
            "target": "new",
            "views": [(False, "form")],
        }

    def _format_response(self, query_result):
        html_content = (
            self.env._("Authentication success.")
            if query_result["authenticated"]
            else self.env._("Authentication failed.")
        )

        html_content += "<ul>"
        for key, value in query_result.items():
            html_content += (
                f'<li><span class="fw-bold">{key.capitalize()}:</span> {value}</li>'
            )
        html_content += "</ul>"
        return html_content

    def avatax_log(self) -> bool:
        self.env["mixin.account.external.tax"]._enable_external_tax_logging(
            "account_avatax.log.end.date"
        )
        return True

from odoo import api, fields, models

from odoo.addons.account_batch_payment.models.sepa_mapping import (
    normalize_communication,
)


class ResCompany(models.Model):
    _inherit = "res.company"
    _inherits_sudo_fields = ("iso20022_lei",)

    account_fiscal_country_group_codes = fields.Json(
        related="account_config_id.account_fiscal_country_group_codes",
    )
    iso20022_orgid_id = fields.Char(
        string="Identification",
        size=35,
        compute="_compute_iso20022_orgid",
        store=True,
        copy=False,
        readonly=False,
        help="Identification assigned by an institution (eg. VAT number).",
    )
    iso20022_orgid_issr = fields.Char(
        string="Issuer",
        size=35,
        compute="_compute_iso20022_orgid",
        store=True,
        copy=False,
        readonly=False,
        help="Entity that assigns the identification (eg. KBE-BCO or Finanzamt Muenchen IV).",
    )
    iso20022_initiating_party_name = fields.Char(
        string="Your Company Name",
        size=70,
        copy=False,
        help="Will appear as the name of the party initiating the payment. Limited to 70 characters.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            name = vals.get("name")
            if name and "iso20022_initiating_party_name" not in vals:
                vals["iso20022_initiating_party_name"] = normalize_communication(name)
        return super().create(vals_list)

    @api.depends("partner_id.country_id")
    def _compute_iso20022_orgid(self) -> None:
        for company in self:
            if company.iso20022_orgid_id or company.iso20022_orgid_issr:
                continue
            if company.partner_id.country_id.code == "BE":
                company.iso20022_orgid_issr = "KBO-BCE"
                company.iso20022_orgid_id = (
                    company.vat[:2].upper() + company.vat[2:].replace(" ", "")
                    if company.vat
                    else ""
                )
            else:
                company.iso20022_orgid_issr = ""
                company.iso20022_orgid_id = ""

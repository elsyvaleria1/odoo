from datetime import datetime, timedelta

from odoo import SUPERUSER_ID, Command, api, fields, models
from odoo.modules.registry import Registry
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT


class MixinAccountExternalTax(models.AbstractModel):
    _name = "mixin.account.external.tax"
    _description = "Mixin to manage common parts of external tax calculation"

    is_tax_computed_externally = fields.Boolean(
        compute="_compute_is_tax_computed_externally",
        help="Technical field to determine if tax is calculated using an external service instead of Odoo.",
    )

    @api.depends("fiscal_position_id")
    def _compute_is_tax_computed_externally(self) -> None:
        self.is_tax_computed_externally = False

    def _get_external_taxes(self):
        return {}

    def _uncommit_external_taxes(self):
        return

    def _void_external_taxes(self):
        return

    def _get_and_set_external_taxes_on_eligible_records(self):
        return

    def _prepare_line_data_for_external_taxes(self):
        return []

    def _prepare_external_tax_service_params(self):
        return {
            "line_data": self._prepare_line_data_for_external_taxes(),
            "company_partner": self.company_id.partner_id,
            "document_date": None,
        }

    @api.model
    def _set_external_taxes(self, mapped_taxes) -> None:
        for line in mapped_taxes:
            line.tax_ids = False

        for line, base_line in mapped_taxes.items():
            extra_tax_data = self.env["account.tax"]._export_base_line_extra_tax_data(
                base_line
            )
            line.write(
                {
                    "extra_tax_data": extra_tax_data,
                    "tax_ids": [
                        Command.set(
                            [
                                int(tax_id)
                                for tax_id in extra_tax_data.get(
                                    "manual_tax_amounts", {}
                                )
                            ]
                        )
                    ],
                }
            )

    @api.model
    def _process_external_taxes(
        self,
        company,
        base_line_with_tax_values,
        tax_key_field,
        search_archived_taxes=False,
    ) -> dict:
        tax_group_names = {
            tax_group_values["name"]: tax_group_values
            for base_line, tax_values_list in base_line_with_tax_values
            for tax_group_values, tax_values, _amount in tax_values_list
        }
        tax_group_by_name = {
            tax_group.name: tax_group
            for tax_group in self.env["account.tax.group"].search(
                [
                    *self.env["account.tax.group"]._check_company_domain(company),
                    ("name", "in", tax_group_names.keys()),
                ]
            )
        }
        missing_tax_groups = (
            self.env["account.tax.group"]
            .sudo()
            .create(
                [
                    tax_group_names[tax_group_name]
                    for tax_group_name in tax_group_names.keys()
                    - tax_group_by_name.keys()
                ]
            )
        )
        for tax_group in missing_tax_groups:
            tax_group_by_name[tax_group.name] = tax_group

        tax_names = {
            tax_values["name"]: tax_values
            for base_line, tax_values_list in base_line_with_tax_values
            for tax_group_values, tax_values, _amount in tax_values_list
        }
        tax_name_x_tax_group = {
            tax_values["name"]: tax_group_values["name"]
            for base_line, tax_values_list in base_line_with_tax_values
            for tax_group_values, tax_values, _amount in tax_values_list
        }

        tax_by_name = {}
        for tax_name, tax_values in tax_names.items():
            price_include_override_domain = []
            type_tax_use_domain = []
            if "price_include_override" in tax_values:
                price_include_override_domain = [
                    (
                        "price_include_override",
                        "=",
                        tax_values["price_include_override"],
                    )
                ]
            if "type_tax_use" in tax_values:
                type_tax_use_domain = [
                    ("type_tax_use", "=", tax_values["type_tax_use"])
                ]

            existing_tax = (
                self.env["account.tax"]
                .with_context(active_test=not search_archived_taxes)
                .search(
                    [
                        *self.env["account.tax"]._check_company_domain(company),
                        (tax_key_field, "in", tax_name),
                        *price_include_override_domain,
                        *type_tax_use_domain,
                    ],
                    limit=1,
                )
            )
            if existing_tax:
                tax_by_name[existing_tax[tax_key_field]] = existing_tax

                if search_archived_taxes and not existing_tax.active:
                    existing_tax.active = True

        missing_taxes = (
            self.env["account.tax"]
            .sudo()
            .create(
                [
                    {
                        **tax_names[tax_name],
                        "tax_group_id": tax_group_by_name[
                            tax_name_x_tax_group[tax_name]
                        ].id,
                    }
                    for tax_name in tax_names.keys() - tax_by_name.keys()
                ]
            )
        )
        for tax in missing_taxes:
            tax_by_name[tax[tax_key_field]] = tax

        for base_line, tax_values_list in base_line_with_tax_values:
            manual_tax_amounts = base_line["manual_tax_amounts"] = {}
            for _tax_group_values, tax_values, manual_amounts in tax_values_list:
                tax_id = str(tax_by_name[tax_values["name"]].id)
                if tax_id in manual_tax_amounts:
                    manual_tax_amounts[tax_id]["tax_amount_currency"] += manual_amounts[
                        "tax_amount_currency"
                    ]
                else:
                    if (
                        base_line["manual_total_excluded_currency"] is None
                        and "base_amount_currency" in manual_amounts
                    ):
                        base_line["manual_total_excluded_currency"] = manual_amounts[
                            "base_amount_currency"
                        ]
                    manual_tax_amounts[tax_id] = manual_amounts

        return {
            base_line["record"]: base_line
            for base_line, _amount in base_line_with_tax_values
        }

    def button_external_tax_calculation(self) -> bool:
        self._get_and_set_external_taxes_on_eligible_records()
        return True

    def _enable_external_tax_logging(self, icp_name) -> None:
        self.env["ir.config_parameter"].sudo().set_param(
            icp_name,
            (fields.Datetime.now() + timedelta(minutes=30)).strftime(
                DEFAULT_SERVER_DATETIME_FORMAT
            ),
        )

    def _log_external_tax_request(self, module_name, icp_name, message) -> None:
        log_end_date = self.env.registry.settings.get(self.env, icp_name, "")
        try:
            log_end_date = datetime.strptime(
                log_end_date, DEFAULT_SERVER_DATETIME_FORMAT
            )
            need_log = fields.Datetime.now() < log_end_date
        except ValueError:
            need_log = False
        if need_log:
            self.env.flush_all()
            dbname = self.env.cr.dbname
            with Registry(dbname).cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                env["ir.logging"].create(
                    {
                        "name": module_name,
                        "type": "server",
                        "level": "INFO",
                        "dbname": dbname,
                        "message": message,
                        "func": "",
                        "path": "",
                        "line": "",
                    }
                )

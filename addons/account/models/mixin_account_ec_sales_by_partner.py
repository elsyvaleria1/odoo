from collections import defaultdict
from collections.abc import Mapping
from typing import Any, TypedDict

from odoo import models


class EcSalesPartnerValues(TypedDict):
    country_code: str
    vat_number: str
    goods: float
    services: float
    triangular: float
    balance: float


def _prepare_ec_sales_partner_values(
    partner_sum: Mapping[str, Any],
) -> EcSalesPartnerValues:
    goods = partner_sum.get("goods") or 0.0
    services = partner_sum.get("services") or 0.0
    triangular = partner_sum.get("triangular") or 0.0
    return {
        "country_code": partner_sum.get("country_code") or "UNKNOWN",
        "vat_number": partner_sum.get("vat_number") or "",
        "goods": goods,
        "services": services,
        "triangular": triangular,
        "balance": goods + services + triangular,
    }


class MixinAccountEcSalesByPartner(models.AbstractModel):
    _name = "mixin.account.ec.sales.by.partner"
    _inherit = "account.ec.sales.report.handler"
    _description = "EC Sales Report by Partner"

    def _dynamic_lines_generator(
        self, report, options, all_column_groups_expression_totals, warnings=None
    ):
        lines = []
        totals_by_column_group = {
            column_group_key: {
                "goods": 0.0,
                "services": 0.0,
                "triangular": 0.0,
                "balance": 0.0,
            }
            for column_group_key in options["column_groups"]
        }
        for partner, results in super()._query_partners(report, options):
            partner_values = defaultdict(dict)
            for column_group_key in options["column_groups"]:
                values = _prepare_ec_sales_partner_values(
                    results.get(column_group_key, {})
                )
                partner_values[column_group_key] = values
                for category in ("goods", "services", "triangular", "balance"):
                    totals_by_column_group[column_group_key][category] += values[
                        category
                    ]
            lines.append(
                (
                    0,
                    super()._get_report_line_partner(
                        report, options, partner, partner_values
                    ),
                )
            )
        lines.append(
            (0, super()._get_report_line_total(report, options, totals_by_column_group))
        )
        return lines

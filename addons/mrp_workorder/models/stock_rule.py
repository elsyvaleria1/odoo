from odoo import models
from odoo.fields import Domain


class StockRule(models.Model):
    _inherit = "stock.rule"

    def _get_domain_mo_for_procurement(self, procurement, bom):
        domain = super()._get_domain_mo_for_procurement(procurement, bom)
        return tuple(
            Domain.AND(
                [
                    Domain(domain),
                    Domain.OR(
                        [
                            [("check_ids", "=", False)],
                            [
                                (
                                    "check_ids",
                                    "not any",
                                    [("quality_state", "!=", "none")],
                                )
                            ],
                        ]
                    ),
                    Domain.OR(
                        [
                            [("workorder_ids", "=", False)],
                            [
                                (
                                    "workorder_ids",
                                    "not any",
                                    [
                                        ("check_ids", "!=", False),
                                        (
                                            "check_ids",
                                            "any",
                                            [("quality_state", "!=", "none")],
                                        ),
                                    ],
                                )
                            ],
                        ]
                    ),
                ]
            )
        )

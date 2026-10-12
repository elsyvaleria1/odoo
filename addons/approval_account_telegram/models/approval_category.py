from typing import TYPE_CHECKING, Self

from odoo import api, fields, models

if TYPE_CHECKING:
    from odoo.addons.base.models.res_company import ResCompany


class ApprovalCategory(models.Model):
    _inherit = "approval.category"

    telegram_intake = fields.Selection(
        selection=[
            ("payment", "Payments recorded with /pago"),
            ("especie", "Payments in kind recorded with /especie"),
        ],
        string="Telegram Intake",
        index=True,
        copy=False,
        help="The Telegram command whose requests are filed in this category. "
        "A company has one category per command; one without a company takes "
        "the requests of every company that has none of its own.",
    )

    _one_telegram_intake_per_company = models.UniqueIndex(
        "(telegram_intake, COALESCE(company_id, 0)) WHERE telegram_intake IS NOT NULL",
        "A company files the requests of each Telegram command in one category.",
    )

    @api.model
    def _get_telegram_intake_category(self, intake: str, company: ResCompany) -> Self:
        categories = self.search(
            [
                ("telegram_intake", "=", intake),
                ("company_id", "in", [company.id, False]),
            ]
        )
        return categories.filtered("company_id")[:1] or categories[:1]

from odoo import fields, models
from odoo.tools import frozendict

from ..models.account_payment import COLLECTION_METHODS

CUSTODY_AGES = [
    ("0_1", "0-1 days"),
    ("2_3", "2-3 days"),
    ("4_plus", "Over 3 days"),
]

TODAY_SQL = "(now() AT TIME ZONE 'UTC')::date"


class AccountCollectionCustodyReport(models.Model):
    _name = "account.collection.custody.report"
    _description = "Collections in Custody by Age"
    _inherit = ["mixin.sql.report"]
    _auto = False
    _rec_name = "payment_id"
    _order = "date"
    _access_anchors = frozendict(
        {"collector": models.Anchor("collector_id", kind="owner")}
    )
    _depends = frozendict(
        {
            "account.payment": (
                "amount_company_currency_signed",
                "collection_method",
                "collector_id",
                "company_id",
                "date",
                "date_custody_due",
                "is_far_from_customer",
                "is_in_custody",
                "journal_id",
                "partner_id",
            ),
            "res.company": ("currency_id",),
        }
    )

    payment_id = fields.Many2one(
        comodel_name="account.payment",
        string="Collection",
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
    )
    collector_id = fields.Many2one(
        comodel_name="res.users",
        readonly=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        readonly=True,
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Custody Journal",
        readonly=True,
    )
    collection_method = fields.Selection(
        selection=COLLECTION_METHODS,
        string="Collected In",
        readonly=True,
    )
    date = fields.Date(
        string="Collected On",
        readonly=True,
    )
    date_custody_due = fields.Date(
        string="Hand In By",
        readonly=True,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        readonly=True,
    )
    amount = fields.Monetary(
        string="Held",
        currency_field="currency_id",
        readonly=True,
    )
    age_days = fields.Integer(
        string="Days Held",
        readonly=True,
        aggregator="max",
    )
    age = fields.Selection(
        selection=CUSTODY_AGES,
        string="Held For",
        readonly=True,
    )
    is_far_from_customer = fields.Boolean(
        string="Far From Customer",
        readonly=True,
    )
    is_overdue = fields.Boolean(
        string="Overdue",
        readonly=True,
        help="Held past the working days the company allows for its method.",
    )

    def _get_fields_select(self) -> dict:
        age_days = f"({TODAY_SQL} - p.date)"
        return {
            "id": "p.id",
            "payment_id": "p.id",
            "company_id": "p.company_id",
            "collector_id": "p.collector_id",
            "partner_id": "p.partner_id",
            "journal_id": "p.journal_id",
            "collection_method": "p.collection_method",
            "date": "p.date",
            "date_custody_due": "p.date_custody_due",
            "currency_id": "c.currency_id",
            "amount": "p.amount_company_currency_signed",
            "age_days": age_days,
            "age": (
                f"CASE WHEN {age_days} <= 1 THEN '0_1' "
                f"WHEN {age_days} <= 3 THEN '2_3' ELSE '4_plus' END"
            ),
            "is_far_from_customer": "COALESCE(p.is_far_from_customer, FALSE)",
            "is_overdue": f"COALESCE(p.date_custody_due < {TODAY_SQL}, FALSE)",
        }

    def _get_from_tables(self) -> list:
        return [
            ("account_payment", "p", None, None),
            ("res_company", "c", "JOIN", "c.id = p.company_id"),
        ]

    def _get_where_conditions(self) -> list:
        return ["p.is_in_custody"]

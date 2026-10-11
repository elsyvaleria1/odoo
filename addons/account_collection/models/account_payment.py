import math
from datetime import datetime, time, timedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import frozendict

from odoo.addons.portal.utils import get_url_with_params

COLLECTION_METHODS = [
    ("cash", "Cash"),
    ("check", "Check"),
    ("transfer", "Transfer"),
    ("card", "Card"),
]

CHECK_STATES = [
    ("custody", "In Custody"),
    ("deposited", "Deposited"),
    ("cleared", "Cleared"),
    ("bounced", "Bounced"),
]


EARTH_RADIUS_KM = 6371.0088


def distance_km(lat1, lon1, lat2, lon2) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    half_dphi = math.radians(lat2 - lat1) / 2
    half_dlambda = math.radians(lon2 - lon1) / 2
    a = (
        math.sin(half_dphi) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(half_dlambda) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def add_working_days(company, day, days):
    if days <= 0:
        return day
    calendar = company.resource_calendar_id
    start = datetime.combine(day + timedelta(days=1), time.min)
    end = calendar and calendar.plan_days(days, start, compute_leaves=True)
    return end.date() if end else day + timedelta(days=days)


class AccountPayment(models.Model):
    _inherit = "account.payment"
    _access_anchors = frozendict(
        {"collector": models.Anchor("collector_id", kind="owner")}
    )

    collector_id = fields.Many2one(
        comodel_name="res.users",
        index="btree_not_null",
        ondelete="restrict",
        tracking=True,
        help="Who received the money from the customer. While the payment is in a "
        "custody journal, the money is in this person's hands.",
    )
    collection_method = fields.Selection(
        selection=COLLECTION_METHODS,
        string="Collected In",
        tracking=True,
        help="The form in which the customer paid the collector.",
    )
    collection_check_date = fields.Date(
        string="Check Date",
        copy=False,
        tracking=True,
        help="The date written on the check. A post-dated check is handed in to the "
        "bank on that date, not before.",
    )
    collection_check_state = fields.Selection(
        selection=CHECK_STATES,
        string="Check Status",
        compute="_compute_collection_check_state",
        store=True,
        help="Where a collected check stands: in the collector's custody, deposited "
        "by a remittance, cleared once the bank reports the deposit, or bounced.",
    )
    collection_bounce_move_id = fields.Many2one(
        comodel_name="account.move",
        string="Bounce Entry",
        index="btree_not_null",
        copy=False,
        readonly=True,
        help="The entry that charged the bounced check back to the customer.",
    )
    collection_latitude = fields.Float(
        string="Collected At (Latitude)",
        digits=(10, 7),
        copy=False,
        readonly=True,
    )
    collection_longitude = fields.Float(
        string="Collected At (Longitude)",
        digits=(10, 7),
        copy=False,
        readonly=True,
    )
    collection_distance_km = fields.Float(
        string="Distance to Customer (km)",
        digits=(16, 2),
        compute="_compute_collection_distance_km",
        store=True,
        help="How far from the customer's geolocated address the collector stood "
        "when recording the collection; empty when either point is unknown.",
    )
    is_far_from_customer = fields.Boolean(
        string="Far From Customer",
        compute="_compute_is_far_from_customer",
        store=True,
        help="Recorded farther from the customer's address than the company "
        "allows. Evidence to review, not a refusal.",
    )
    is_collection_custody = fields.Boolean(
        related="journal_id.is_collection_custody",
    )
    is_in_custody = fields.Boolean(
        string="In Custody",
        compute="_compute_is_in_custody",
        store=True,
        help="Collected, still in the collector's hands: its custody item is not "
        "yet settled by a validated remittance.",
    )
    date_custody_due = fields.Date(
        string="Hand In By",
        compute="_compute_date_custody_due",
        store=True,
        help="The last working day the collector may hold this collection.",
    )
    collection_remittance_ids = fields.Many2many(
        comodel_name="account.collection.remittance",
        relation="account_collection_remittance_payment_rel",
        column1="payment_id",
        column2="remittance_id",
        string="Remittances",
        copy=False,
        readonly=True,
    )
    collection_remittance_id = fields.Many2one(
        comodel_name="account.collection.remittance",
        string="Remittance",
        compute="_compute_collection_remittance_id",
        store=True,
        index="btree_not_null",
        help="The remittance handing this collection in, unless cancelled.",
    )

    @api.depends("collection_remittance_ids.state")
    def _compute_collection_remittance_id(self) -> None:
        for payment in self:
            payment.collection_remittance_id = (
                payment.collection_remittance_ids.filtered(
                    lambda remittance: remittance.state != "cancel"
                )[:1]
            )

    @api.depends(
        "collection_latitude",
        "collection_longitude",
        "partner_id.partner_latitude",
        "partner_id.partner_longitude",
    )
    def _compute_collection_distance_km(self) -> None:
        for payment in self:
            partner = payment.partner_id
            located = (
                payment.collection_latitude or payment.collection_longitude
            ) and (partner.partner_latitude or partner.partner_longitude)
            payment.collection_distance_km = (
                distance_km(
                    payment.collection_latitude,
                    payment.collection_longitude,
                    partner.partner_latitude,
                    partner.partner_longitude,
                )
                if located
                else 0.0
            )

    @api.depends(
        "collection_distance_km",
        "company_id.account_config_id.collection_max_distance_km",
    )
    def _compute_is_far_from_customer(self) -> None:
        for payment in self:
            limit = payment.company_id.account_config_id.collection_max_distance_km
            payment.is_far_from_customer = bool(
                limit and payment.collection_distance_km > limit
            )

    @api.depends(
        "collection_method",
        "state",
        "is_in_custody",
        "collection_remittance_id.state",
        "collection_remittance_id.statement_line_id",
    )
    def _compute_collection_check_state(self) -> None:
        for payment in self:
            remittance = payment.collection_remittance_id
            if payment.collection_method != "check" or payment.state in (
                "draft",
                "canceled",
            ):
                payment.collection_check_state = False
            elif payment.state == "rejected":
                payment.collection_check_state = "bounced"
            elif payment.is_in_custody or remittance.state != "done":
                payment.collection_check_state = "custody"
            elif remittance.statement_line_id:
                payment.collection_check_state = "cleared"
            else:
                payment.collection_check_state = "deposited"

    @api.depends(
        "is_collection_custody",
        "state",
        "liquidity_account_id",
        "move_id.line_ids.reconciled",
    )
    def _compute_is_in_custody(self) -> None:
        for payment in self:
            custody_lines = payment.move_id.line_ids.filtered(
                lambda line, payment=payment: (
                    line.account_id == payment.liquidity_account_id
                )
            )
            payment.is_in_custody = (
                payment.is_collection_custody
                and payment.state in ("in_process", "paid")
                and bool(custody_lines)
                and not all(custody_lines.mapped("reconciled"))
            )

    @api.depends("date", "collection_method", "is_collection_custody", "company_id")
    def _compute_date_custody_due(self) -> None:
        for payment in self:
            payment.date_custody_due = (
                payment._get_custody_due_date()
                if payment.is_collection_custody and payment.date
                else False
            )

    def _get_custody_due_date(self):
        self.check_singleton()
        config = self.company_id.account_config_id
        days = (
            config.collection_custody_days_check
            if self.collection_method == "check"
            else config.collection_custody_days_cash
        )
        return add_working_days(self.company_id, self.date, days)

    @api.depends("journal_id.is_collection_custody")
    def _compute_reconciliation_status(self) -> None:
        super()._compute_reconciliation_status()
        for payment in self.filtered("is_collection_custody"):
            custody_lines = payment.move_id.line_ids.filtered(
                lambda line, payment=payment: (
                    line.account_id == payment.liquidity_account_id
                )
            )
            payment.is_bank_matched = bool(custody_lines) and all(
                custody_lines.mapped("reconciled")
            )

    def _prepare_move_liquidity_lines(self, default_values) -> list:
        lines = super()._prepare_move_liquidity_lines(default_values)
        if self.is_collection_custody and self.collector_id:
            for line in lines:
                line["partner_id"] = self.collector_id.partner_id.id
        return lines

    @api.constrains("journal_id", "collector_id", "payment_type", "partner_type")
    def _check_collection_custody(self) -> None:
        for payment in self.filtered("is_collection_custody"):
            if payment.payment_type != "inbound" or payment.partner_type != "customer":
                raise ValidationError(
                    self.env._(
                        "Journal %(journal)s holds customer collections only.",
                        journal=payment.journal_id.display_name,
                    )
                )
            if not payment.collector_id:
                raise ValidationError(
                    self.env._(
                        "A payment in custody journal %(journal)s names the "
                        "collector who holds the money.",
                        journal=payment.journal_id.display_name,
                    )
                )

    def action_draft(self):
        self._check_not_remitted()
        return super().action_draft()

    def action_cancel(self):
        self._check_not_remitted()
        return super().action_cancel()

    def _check_not_remitted(self) -> None:
        remitted = self.filtered("collection_remittance_id")
        if remitted:
            raise UserError(
                self.env._(
                    "%(payments)s already went to remittance %(remittances)s; cancel "
                    "the remittance first.",
                    payments=", ".join(remitted.mapped("name")),
                    remittances=", ".join(
                        remitted.collection_remittance_id.mapped("name")
                    ),
                )
            )

    def action_open_bounce_wizard(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Check Bounced"),
            "res_model": "wizard.account.payment.bounce",
            "view_mode": "form",
            "target": "new",
            "context": {"default_payment_id": self.id},
        }

    def _bounce_collection_check(self, date, fee, reason) -> None:
        self.check_singleton()
        if self.collection_check_state not in ("deposited", "cleared"):
            raise UserError(
                self.env._(
                    "Only a check handed in to the bank or a till can bounce. A check "
                    "still in custody goes back to the customer by cancelling its "
                    "collection."
                )
            )
        move = (
            self.env["account.move"]
            .with_company(self.company_id)
            .create(self._prepare_bounce_move_vals(date, fee, reason))
        )
        move.action_post()
        receivables = self.move_id.line_ids.filtered(
            lambda line: line.account_id == self.counterpart_account_id
        )
        invoices = self.reconciled_invoice_ids
        receivables.remove_move_reconcile()
        charge_back = move.line_ids.filtered(
            lambda line: (
                line.account_id == self.counterpart_account_id and line.name == move.ref
            )
        )
        (charge_back + receivables).reconcile()
        self.collection_bounce_move_id = move
        self.action_reject()
        note = self.env._(
            "Check %(payment)s bounced: %(reason)s. %(invoices)s are open again; "
            "collect them from the customer.",
            payment=self.name,
            reason=reason,
            invoices=", ".join(invoices.mapped("name")) or self.memo,
        )
        self.message_post(body=note)
        if self.collector_id:
            self.activity_schedule(
                act_type_xmlid="mail.mail_activity_data_todo",
                date_deadline=date,
                summary=self.env._("Check bounced"),
                note=note,
                user_id=self.collector_id.id,
            )

    def _prepare_bounce_move_vals(self, date, fee, reason) -> dict:
        self.check_singleton()
        journal = self.collection_remittance_id.destination_journal_id
        config = self.company_id.account_config_id
        charged_account = (
            journal.default_account_id
            if journal.type == "cash"
            else config.transfer_account_id
        )
        if not charged_account:
            raise UserError(
                self.env._(
                    "Set the inter-bank transfer account of %(company)s: the bounced "
                    "check is charged back where its deposit waited.",
                    company=self.company_id.name,
                )
            )
        if fee and not config.collection_check_fee_account_id:
            raise UserError(
                self.env._(
                    "Set the bounced check fee account of %(company)s to charge the "
                    "customer the bank's fee.",
                    company=self.company_id.name,
                )
            )
        label = self.env._(
            "Bounced check %(payment)s: %(reason)s", payment=self.name, reason=reason
        )
        amount = self.amount_company_currency_signed
        lines = [
            Command.create(
                {
                    "name": label,
                    "account_id": self.counterpart_account_id.id,
                    "partner_id": self.partner_id.id,
                    "balance": amount,
                }
            ),
            Command.create(
                {
                    "name": label,
                    "account_id": charged_account.id,
                    "partner_id": self.partner_id.id,
                    "balance": -amount,
                }
            ),
        ]
        if fee:
            fee_label = self.env._(
                "Bank fee for bounced check %(payment)s", payment=self.name
            )
            lines += [
                Command.create(
                    {
                        "name": fee_label,
                        "account_id": self.counterpart_account_id.id,
                        "partner_id": self.partner_id.id,
                        "balance": fee,
                    }
                ),
                Command.create(
                    {
                        "name": fee_label,
                        "account_id": config.collection_check_fee_account_id.id,
                        "partner_id": self.partner_id.id,
                        "balance": -fee,
                    }
                ),
            ]
        return {
            "move_type": "entry",
            "journal_id": journal.id,
            "company_id": self.company_id.id,
            "date": date,
            "ref": label,
            "line_ids": lines,
        }

    @api.private
    def get_collection_receipt_url(self) -> str:
        self.check_singleton()
        _link, token = self.env["access.link"]._issue(
            self,
            partner=self.partner_id,
            role="comment",
            cause="notification",
        )
        return get_url_with_params(
            f"{self.get_base_url()}/collection/receipt/{self.id}",
            {"access_token": token},
        )

    def _send_collection_receipt(self) -> None:
        template = self.env.ref("account_collection.mail_template_collection_receipt")
        for payment in self:
            if (
                not payment.collector_id
                or not payment.partner_id.email
                or not payment.company_id.account_config_id.collection_send_receipt
            ):
                continue
            payment.message_post_with_source(
                template,
                subtype_xmlid="mail.mt_comment",
                email_layout_xmlid="mail.mail_notification_light",
            )

    def _report_collection_receipt_problem(self, description) -> None:
        self.check_singleton()
        self.message_post(
            author_id=self.partner_id.id,
            body=description,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        supervisor = self.company_id.account_config_id.collection_supervisor_id
        if supervisor:
            self.activity_schedule(
                act_type_xmlid="mail.mail_activity_data_todo",
                summary=self.env._("A customer reports a problem with this receipt"),
                note=description,
                user_id=supervisor.id,
            )

    def _cron_notify_overdue_custody(self) -> None:
        today = fields.Date.context_today(self)
        held = self.search(
            [
                ("is_in_custody", "=", True),
                "|",
                ("collection_remittance_id", "=", False),
                ("collection_remittance_id.state", "=", "draft"),
            ]
        )
        overdue = held.filtered(
            lambda payment: (
                payment.date_custody_due and payment.date_custody_due < today
            )
        )
        overdue._schedule_custody_activity(
            lambda payment: payment.collector_id,
            self.env._("Hand in this collection"),
        )
        escalated = overdue.filtered(
            lambda payment: (
                add_working_days(payment.company_id, payment.date_custody_due, 1)
                < today
            )
        )
        escalated._schedule_custody_activity(
            lambda payment: (
                payment.company_id.account_config_id.collection_supervisor_id
            ),
            self.env._("A collector holds this collection past its due date"),
        )

    def _schedule_custody_activity(self, responsible, summary) -> None:
        today = fields.Date.context_today(self)
        activity_type = self.env.ref("mail.mail_activity_data_todo")
        for payment in self:
            user = responsible(payment)
            if not user or payment.activity_ids.filtered(
                lambda activity, user=user: (
                    activity.activity_type_id == activity_type
                    and activity.user_id == user
                )
            ):
                continue
            payment.activity_schedule(
                act_type_xmlid="mail.mail_activity_data_todo",
                date_deadline=today,
                summary=summary,
                note=self.env._(
                    "Collected on %(date)s by %(collector)s, due to be handed in by "
                    "%(due)s and still in custody: hand it in through a remittance.",
                    date=payment.date,
                    collector=payment.collector_id.name,
                    due=payment.date_custody_due,
                ),
                user_id=user.id,
            )

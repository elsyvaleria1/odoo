import ast
import logging
from collections import defaultdict
from collections.abc import Iterable

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import SQL
from odoo.tools.misc import format_date, get_lang

from .followup_request import FollowupRequest
from odoo.addons.account.tools.aging import ReceivablePosition

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    FOLLOWUP_CRON_BATCH_SIZE = 1000

    followup_next_action_date = fields.Date(
        string="Next reminder",
        copy=False,
        company_dependent=True,
        help="""No follow-up action will be taken before this date.
                Sending a reminder will set this date depending on the levels configuration, and you can change it manually.""",
    )

    unreconciled_aml_ids = fields.One2many(
        comodel_name="account.move.line",
        compute="_compute_total_due",
    )

    unpaid_invoice_ids = fields.One2many(
        comodel_name="account.move",
        compute="_compute_unpaid_invoices",
    )
    unpaid_invoices_count = fields.Integer(compute="_compute_unpaid_invoices")
    total_net_due = fields.Monetary(
        compute="_compute_total_due",
        classification="finance.receivable",
    )
    total_net_overdue = fields.Monetary(
        compute="_compute_total_due",
        classification="finance.receivable",
    )
    total_due = fields.Monetary(
        compute="_compute_total_due",
        aggregator="sum",
        classification="finance.receivable",
    )
    total_overdue = fields.Monetary(
        compute="_compute_total_due",
        aggregator="sum",
        classification="finance.receivable",
    )
    total_overdue_followup = fields.Monetary(
        compute="_compute_total_due",
        classification="finance.receivable",
    )
    followup_status = fields.Selection(
        selection=[
            ("in_need_of_action", "In need of action"),
            ("with_overdue_invoices", "With overdue invoices"),
            ("no_action_needed", "No action needed"),
        ],
        string="Follow-up Status",
        compute="_compute_followup_status",
        search="_search_status",
        classification="finance.receivable",
    )
    followup_line_id = fields.Many2one(
        comodel_name="account_followup.followup.line",
        string="Follow-up Level",
        compute="_compute_followup_status",
        inverse="_inverse_followup_line_id",
        search="_search_followup_line",
        classification="finance.receivable",
    )
    followup_reminder_type = fields.Selection(
        selection=[("automatic", "Automatic"), ("manual", "Manual")],
        string="Reminders",
        default="automatic",
    )
    followup_responsible_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsible",
        copy=False,
        company_dependent=True,
        tracking=True,
        classification="finance.receivable",
        help="The responsible assigned to manual followup activities, if defined in the level.",
    )
    has_moves = fields.Boolean(compute="_compute_has_moves")

    def _search_status(self, operator, value):
        if operator != "in":
            return NotImplemented
        value = set(value) & {
            "in_need_of_action",
            "with_overdue_invoices",
            "no_action_needed",
        }
        if not value:
            return Domain.FALSE
        return [
            (
                "id",
                "in",
                SQL(
                    "SELECT followup.partner_id FROM (%s) followup"
                    " WHERE followup.followup_status = ANY(%s)",
                    self._get_followup_data_query(),
                    list(value),
                ),
            )
        ]

    _FOLLOWUP_LINE_NEGATIVE_OPERATORS = frozenset(
        {"!=", "not in", "not like", "not ilike", "not =like", "not =ilike"}
    )

    def _search_followup_line(self, operator, value):
        if isinstance(value, str) or (
            isinstance(value, Iterable) and all(isinstance(v, str) for v in value)
        ):
            domain = Domain("name", operator, value)
        else:
            domain = Domain("id", operator, value)
        line_ids = set(
            self.env["account_followup.followup.line"]
            ._search_all_applicable(domain)
            .ids
        )
        negative = operator in self._FOLLOWUP_LINE_NEGATIVE_OPERATORS
        asks_about_absence = value is False or (
            not isinstance(value, str)
            and isinstance(value, Iterable)
            and any(v is False for v in value)
        )
        matches_no_level = negative != asks_about_absence
        if not line_ids and not matches_no_level:
            return Domain.FALSE

        return [
            (
                "id",
                "in",
                SQL(
                    "SELECT followup.partner_id FROM (%s) followup"
                    " WHERE followup.followup_line_id = ANY(%s)%s",
                    self._get_followup_data_query(),
                    list(line_ids),
                    SQL(" OR followup.followup_line_id IS NULL")
                    if matches_no_level
                    else SQL(""),
                ),
            )
        ]

    @api.depends("unreconciled_aml_ids", "followup_next_action_date")
    @api.depends_context("company", "allowed_company_ids")
    def _compute_followup_status(self) -> None:
        self._set_followup_status(self._query_followup_data())

    def _set_followup_status(self, all_data) -> None:
        fields_ = (self._fields["followup_status"], self._fields["followup_line_id"])
        with self.env.protecting(fields_, self):
            for partner in self:
                partner_data = all_data.get(
                    partner._origin.id,
                    {"followup_status": "no_action_needed", "followup_line_id": False},
                )
                partner.followup_status = partner_data["followup_status"]
                partner.followup_line_id = partner_data["followup_line_id"]

    @api.depends("invoice_ids.payment_state", "invoice_ids.state")
    @api.depends_context("company", "allowed_company_ids")
    def _compute_unpaid_invoices(self) -> None:
        if not self.env["account.move.line"].has_access("read"):
            self.unpaid_invoice_ids = False
            self.unpaid_invoices_count = 0
            return
        partners_unpaid_receivable_lines = (
            self.env["account.move.line"]
            .search(
                [
                    ("company_id", "child_of", self.env.company.id),
                    ("move_id.commercial_partner_id", "in", self.ids),
                    ("parent_state", "=", "posted"),
                    ("move_id.payment_state", "in", ("not_paid", "partial")),
                    (
                        "move_id.move_type",
                        "in",
                        self.env["account.move"].get_sale_types(),
                    ),
                    ("account_id.account_type", "=", "asset_receivable"),
                ]
            )
            .grouped(lambda line: line.move_id.commercial_partner_id.id)
        )
        for partner in self:
            unpaid_receivable_lines = partners_unpaid_receivable_lines.get(
                partner._origin.id, self.env["account.move.line"]
            )
            unpaid_invoices = unpaid_receivable_lines.move_id
            partner.unpaid_invoice_ids = unpaid_invoices
            partner.unpaid_invoices_count = len(unpaid_invoices)

    def action_view_unpaid_invoices(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "account.action_move_out_invoice_type"
        )
        action["domain"] = [("id", "in", self.unpaid_invoice_ids.ids)]
        action["context"] = {
            "default_move_type": "out_invoice",
            "move_type": "out_invoice",
            "journal_type": "sale",
            "partner_id": self.id,
        }
        return action

    def action_view_overdue_entries(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Overdue Invoices"),
            "res_model": "account.move",
            "domain": [
                ("commercial_partner_id", "=", self.id),
                ("move_type", "in", ("out_invoice", "out_refund")),
            ],
            "views": [
                (
                    self.env.ref("account_followup.view_followup_invoice_list").id,
                    "list",
                ),
                (None, "form"),
            ],
            "context": {"search_default_late": True},
        }

    def action_view_partner_followup_journal_items(self) -> dict:
        report = self.env.ref("account.followup_report")
        options = report.get_options({})
        params = {
            "line_id": report._get_generic_line_id("res.partner", self.id),
        }
        custom_handler = self.env[report.custom_handler_model_name]
        return {
            **custom_handler.open_journal_items(options, params),
            "name": self.env._("Journal Items"),
        }

    def action_view_unreconciled_partner(self):
        action_values = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "account.action_move_line_posted_unreconciled"
        )
        domain = ast.literal_eval(action_values["domain"])
        domain.append(("partner_id", "in", self.ids))
        action_values["domain"] = domain
        return action_values

    @api.depends("invoice_ids.line_ids.no_followup")
    @api.depends_context("company", "allowed_company_ids")
    def _compute_total_due(self) -> None:
        if not self.env["account.move.line"].has_access("read"):
            self.unreconciled_aml_ids = False
            self.total_net_due = 0.0
            self.total_net_overdue = 0.0
            self.total_due = 0.0
            self.total_overdue = 0.0
            self.total_overdue_followup = 0.0
            return
        company = self.env.company
        Line = self.env["account.move.line"]
        positions = Line._read_receivable_position(self, company)
        followed = Line._read_receivable_position(
            self, company, domain=[("no_followup", "=", False)]
        )
        payable_due = defaultdict(float)
        payable_overdue = defaultdict(float)
        unreconciled_aml_ids = defaultdict(list)
        for account_type, overdue, partner, residual, aml_ids in Line._read_group(
            domain=self._get_domain_unreconciled_aml(),
            groupby=["account_type", "followup_overdue", "partner_id"],
            aggregates=["amount_residual:sum", "id:array_agg"],
        ):
            if account_type == "asset_receivable":
                unreconciled_aml_ids[partner.id] += aml_ids
                continue
            payable_due[partner.id] += residual
            if overdue:
                payable_overdue[partner.id] += residual

        empty = ReceivablePosition()
        for partner in self:
            origin_id = partner._origin.id
            key = (partner._origin.commercial_partner_id._origin.id, company.id)
            position = positions.get(key, empty)
            followed_position = followed.get(key, empty)
            partner.total_due = position.open
            partner.total_overdue = position.net_overdue
            partner.total_overdue_followup = followed_position.net_overdue
            partner.total_net_due = position.open + payable_due.get(origin_id, 0.0)
            partner.total_net_overdue = position.net_overdue + payable_overdue.get(
                origin_id, 0.0
            )
            partner.unreconciled_aml_ids = Line.browse(
                unreconciled_aml_ids.get(origin_id, [])
            )

    def _inverse_followup_line_id(self) -> None:
        for partner in self:
            previous_followup_line = self.env[
                "account_followup.followup.line"
            ]._search_applicable(
                Domain("delay", "<", partner.followup_line_id.delay), "delay desc"
            )
            partner.unreconciled_aml_ids.followup_line_id = previous_followup_line
            partner.followup_next_action_date = (
                previous_followup_line._get_next_date()
                if previous_followup_line
                else False
            )

    def _get_domain_unreconciled_aml(self):
        return Domain.AND(
            [
                Domain("reconciled", "=", False),
                Domain(
                    "account_id.account_type",
                    "in",
                    ("asset_receivable", "liability_payable"),
                ),
                Domain("parent_state", "=", "posted"),
                Domain("partner_id", "in", self.ids),
                Domain("company_id", "child_of", self.env.company.id),
            ]
        )

    def _get_followup_responsible(self, multiple_responsible=False):
        self.check_singleton()

        responsible_type = self.followup_line_id.activity_default_responsible_type

        max_amount_aml = max(
            self.unreconciled_aml_ids.filtered("move_id.invoice_user_id"),
            default=self.env["account.move.line"],
            key=lambda line: line.amount_residual,
        )
        candidates = []
        if responsible_type == "account_manager":
            candidates.append(self.user_id)
        if responsible_type == "salesperson":
            candidates.append(
                self.unreconciled_aml_ids.move_id.invoice_user_id
                if multiple_responsible
                else max_amount_aml.move_id.invoice_user_id
            )
        candidates += [
            self.followup_responsible_id,
            self.user_id,
            max_amount_aml.move_id.invoice_user_id,
        ]
        for candidate in candidates:
            active = candidate.filtered("active")
            if active:
                return active
        return super()._get_followup_responsible()

    def _get_followup_contact(self):
        self.check_singleton()
        return self.env["res.partner"].browse(self.address_get(["invoice"])["invoice"])

    def _get_invoices_to_print(self, request):
        self.check_singleton()
        if not request.join_invoices:
            return self.env["account.move"]
        invoices_to_print = self.unreconciled_aml_ids.move_id.filtered(
            lambda move: move.is_invoice(include_receipts=True)
        )
        if request.manual:
            return invoices_to_print.filtered(
                lambda inv: inv.message_main_attachment_id.id in request.attachment_ids
            )
        return invoices_to_print.filtered(lambda inv: inv.message_main_attachment_id)

    @api.model
    def _get_first_followup_level(self):
        return self.env["account_followup.followup.line"]._search_applicable(
            Domain.TRUE, "delay asc"
        )

    def _update_next_followup_action_date(self, followup_line) -> None:
        self.check_singleton()
        if followup_line:
            self.followup_next_action_date = followup_line._get_next_date()
            msg = self.env._(
                "Next Reminder Date set to %s",
                format_date(self.env, self.followup_next_action_date),
            )
            self.message_post(body=msg)

        today = fields.Date.context_today(self)
        Followup = self.env["account_followup.followup.line"]
        candidates = Followup._search_all_applicable(
            Domain("delay", "<=", followup_line.delay), "delay desc"
        )
        company_ids = Followup._applicable_company_ids()
        deepest_first = candidates.sorted(
            key=lambda level: (
                -level.delay,
                -company_ids.index(level.company_id.id),
            )
        )
        amls_per_level = defaultdict(list)
        for aml in self.unreconciled_aml_ids.filtered("date_maturity"):
            overdue_days = (today - aml.date_maturity).days
            reached = next(
                (level for level in deepest_first if overdue_days >= level.delay), None
            )
            if reached:
                amls_per_level[reached].append(aml.id)
        for level, aml_ids in amls_per_level.items():
            self.env["account.move.line"].browse(aml_ids).followup_line_id = level

    def _send_followup_email(self, request) -> None:
        report = self.env["account.followup.report"]
        for record in self:
            report._send_email(request.replace(partner=record))

    def _send_followup_sms(self, request) -> None:
        report = self.env["account.followup.report"]
        for record in self:
            report._send_sms(request.replace(partner=record))

    def get_followup_html(self, request=None):
        request = request or FollowupRequest.prepare(self)
        return (
            self.env["account.followup.report"]
            .with_context(print_mode=True, lang=request.lang)
            .get_followup_report_html(request.replace(partner=self))
        )

    def _query_followup_data(self, all_partners=False) -> dict:
        if not all_partners and not self.ids:
            return {}
        self.env.cr.execute(
            self._get_followup_data_query(None if all_partners else self.ids)
        )
        return {r["partner_id"]: r for r in self.env.cr.dictfetchall()}

    def _followup_aml_rule_scope(self, alias):
        if (
            self.env.su
            or self.env["account.move.line"]._access_domain("read").is_true()
        ):
            return SQL("")
        allowed = self.env["account.move.line"]._search(Domain.TRUE)
        return SQL("AND %s IN %s", SQL.identifier(alias, "id"), allowed.subselect())

    def _get_followup_data_query(self, partner_ids=None):
        self.env["account.move.line"].check_access("read")
        self.env["account.move.line"].flush_model()
        self.env["account.account"].flush_model()
        self.env["res.partner"].flush_model()
        self.env["account_followup.followup.line"].flush_model()

        company_ids = (
            self.env["res.company"]
            .search([("id", "child_of", self.env.company.id)])
            .ids
        )
        followup_company_ids = self.env[
            "account_followup.followup.line"
        ]._applicable_company_ids()
        current_date = fields.Date.context_today(self)
        min_delay = self._get_first_followup_level().delay or 0
        unlevelled = min_delay - 1

        return SQL(
            """
            SELECT partner.id AS partner_id,
                   ful.id AS followup_line_id,
                   CASE WHEN partner.amount_residual <= 0 THEN 'no_action_needed'
                        WHEN status.needs_action
                             AND (partner.followup_next_action_date IS NULL
                                  OR partner.followup_next_action_date <= %(current_date)s)
                             THEN 'in_need_of_action'
                        WHEN status.is_overdue THEN 'with_overdue_invoices'
                        ELSE 'no_action_needed' END AS followup_status
              FROM (
                    SELECT partner.id,
                           %(next_action_date)s AS followup_next_action_date,
                           MAX(COALESCE(next_ful.delay, ful.delay)) AS followup_delay,
                           SUM(aml.amount_residual) AS amount_residual
                      FROM res_partner partner
                      JOIN account_move_line aml ON aml.partner_id = partner.id
                      JOIN account_account account ON account.id = aml.account_id
                 LEFT JOIN account_followup_followup_line ful ON ful.id = aml.followup_line_id
                 LEFT JOIN LATERAL (
                           SELECT next_ful.id, next_ful.delay
                             FROM account_followup_followup_line next_ful
                            WHERE next_ful.delay > COALESCE(ful.delay, %(unlevelled)s)
                              AND next_ful.company_id = ANY(%(followup_company_ids)s)
                         ORDER BY next_ful.delay ASC
                            LIMIT 1
                           ) next_ful ON TRUE
                     WHERE account.active
                       AND account.account_type = 'asset_receivable'
                       AND aml.parent_state = 'posted'
                       AND aml.reconciled IS NOT TRUE
                       AND aml.company_id = ANY(%(company_ids)s)
                       %(partner_scope)s
                       %(aml_rule_scope)s
                  GROUP BY partner.id
                   ) partner
              -- One row per partner. `unique(company_id, delay)` is per company, so
              -- every ancestor defining this delay matches; with no pick here the
              -- extras are silently dropped by whoever collapses the rows. The
              -- branch's own level wins, and `_search_applicable` agrees.
         LEFT JOIN LATERAL (
                   SELECT ful.id
                     FROM account_followup_followup_line ful
                    WHERE ful.delay = partner.followup_delay
                      AND ful.company_id = ANY(%(followup_company_ids)s)
                 ORDER BY array_position(%(followup_company_ids)s, ful.company_id) DESC
                    LIMIT 1
                   ) ful ON TRUE
              -- Both status questions off one pass over the partner's open lines:
              -- is anything overdue at all, and is anything due for its next level.
         LEFT JOIN LATERAL (
                   SELECT bool_or(line.date_maturity < %(current_date)s) AS is_overdue,
                          bool_or(COALESCE(ful.delay, %(unlevelled)s) < partner.followup_delay
                                  AND line.date_maturity + COALESCE(ful.delay, %(unlevelled)s)
                                      < %(current_date)s) AS needs_action
                     FROM account_move_line line
                     JOIN account_account account ON line.account_id = account.id
                LEFT JOIN account_followup_followup_line ful ON ful.id = line.followup_line_id
                    WHERE line.partner_id = partner.id
                      AND account.account_type = 'asset_receivable'
                      AND account.active
                      AND line.no_followup IS NOT TRUE
                      AND line.parent_state = 'posted'
                      AND line.reconciled IS NOT TRUE
                      AND line.balance > 0
                      AND line.company_id = ANY(%(company_ids)s)
                      AND line.date_maturity IS NOT NULL
                      %(line_rule_scope)s
                   ) status ON TRUE
            """,
            current_date=current_date,
            unlevelled=unlevelled,
            company_ids=company_ids,
            followup_company_ids=followup_company_ids,
            next_action_date=self._field_to_sql("partner", "followup_next_action_date"),
            partner_scope=(
                SQL("")
                if partner_ids is None
                else SQL("AND aml.partner_id = ANY(%s)", list(partner_ids))
            ),
            aml_rule_scope=self._followup_aml_rule_scope("aml"),
            line_rule_scope=self._followup_aml_rule_scope("line"),
        )

    def _send_followup(self, request) -> None:
        self.check_singleton()
        if request.is_channel_enabled("email", request.followup_line.send_email):
            self._send_followup_email(request)
        if request.is_channel_enabled("sms", request.followup_line.send_sms):
            self._send_followup_sms(request)

    def _followup_needs_documents(self, request):
        self.check_singleton()
        return request.print_letter or request.is_channel_enabled(
            "email", request.followup_line.send_email
        )

    def _get_followup_statement_attachment_id(self):
        report = self.env.ref("account.followup_report")
        return self._create_partner_account_report_attachment(
            report,
            options=self._get_partner_account_report_options(
                report, export_mode="print"
            ),
        ).id

    def _attach_followup_documents(self, request):
        report_attachment_id = self._get_followup_statement_attachment_id()
        attachment_ids = [report_attachment_id]

        if request.mail_template:
            template_attachments = request.mail_template._prepare_attachment_vals(
                self.ids, {"attachment_ids", "report_template_ids"}
            ).get(self.id, {})
            attachment_ids += template_attachments.get("attachment_ids", [])
            attachment_ids += (
                self.env["ir.attachment"]
                .create(
                    [
                        {
                            "name": name,
                            "datas": datas,
                            "res_model": self._name,
                            "res_id": self.id,
                        }
                        for name, datas in template_attachments.get("attachments", [])
                    ]
                )
                .ids
            )

        if request.join_invoices:
            if request.manual:
                attachment_ids += request.attachment_ids
            else:
                attachment_ids += self._get_invoices_to_print(
                    request
                ).message_main_attachment_id.ids

        return request.replace(
            attachment_ids=attachment_ids, report_attachment_id=report_attachment_id
        )

    def _execute_followup(self, request=None) -> bool:
        self.check_singleton()
        if request is None:
            request = FollowupRequest.prepare(self)
        if not request.manual and self.followup_status != "in_need_of_action":
            return False
        if self._followup_needs_documents(request):
            request = self._attach_followup_documents(request)
        followup_line = request.followup_line

        self._send_followup(request)

        if followup_line.create_activity:
            for user in self._get_followup_responsible(multiple_responsible=True):
                self.activity_schedule(
                    activity_type_id=followup_line.activity_type_id.id
                    or self._get_default_activity_type().id,
                    note=followup_line.activity_note,
                    summary=followup_line.activity_summary,
                    user_id=user.id,
                )
        self._update_next_followup_action_date(followup_line)
        return True

    def _execute_followup_and_print(self, request):
        self.check_singleton()
        sent = self._execute_followup(request=request)
        if request.print_letter and sent:
            return self.env["account.followup.report"]._print_followup_letter(request)
        return None

    def _create_followup_missing_information_wizard(self) -> dict:

        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Missing information"),
            "view_mode": "form",
            "res_model": "wizard.res.partner.view.followup.missing.info",
            "target": "new",
            "context": {"default_partner_ids": self.ids},
        }

    def _followup_template_names_a_recipient(self, template) -> bool:
        return bool(
            template and (template.partner_to or template.email_to or template.email_cc)
        )

    def _has_missing_followup_info(self) -> bool:
        self.check_singleton()

        contact = self._get_followup_contact() or self
        followup_line = self.followup_line_id or self._get_first_followup_level()

        if (
            followup_line.send_email
            and not contact.email
            and not self._followup_template_names_a_recipient(
                followup_line.mail_template_id
            )
        ):
            return True
        return bool(followup_line.send_sms and not contact.phone_ids)

    def action_manually_process_automatic_followups(self):
        partners_with_missing_info = self.env["res.partner"]

        for partner in self:
            if partner.followup_status != "in_need_of_action":
                continue

            if partner._has_missing_followup_info():
                partners_with_missing_info |= partner
                continue

            partner._execute_followup()

        if partners_with_missing_info:
            return (
                partners_with_missing_info._create_followup_missing_information_wizard()
            )
        return None

    def _cron_execute_followup_company(self):
        followup_data = self._query_followup_data(all_partners=True)
        auto_level_ids = set(
            self.env["account_followup.followup.line"]
            .browse({d["followup_line_id"] for d in followup_data.values()} - {None})
            .filtered("auto_execute")
            .ids
        )
        in_need_of_action_auto = (
            self.env["res.partner"]
            .browse(
                [
                    d["partner_id"]
                    for d in followup_data.values()
                    if d["followup_status"] == "in_need_of_action"
                    and d["followup_line_id"] in auto_level_ids
                ]
            )
            .filtered(lambda partner: partner.followup_reminder_type == "automatic")
        )

        capped = len(in_need_of_action_auto) > self.FOLLOWUP_CRON_BATCH_SIZE
        if capped:
            _logger.info(
                "Follow-up cron: %s partners due for %s, sending %s this pass; "
                "the cron is re-triggered for the rest.",
                len(in_need_of_action_auto),
                self.env.company.display_name,
                self.FOLLOWUP_CRON_BATCH_SIZE,
            )
        batch = in_need_of_action_auto[: self.FOLLOWUP_CRON_BATCH_SIZE]
        batch._set_followup_status(followup_data)
        for partner in batch:
            try:
                partner._execute_followup()
            except UserError as e:
                partner._message_log(body=e)
                _logger.warning(e, exc_info=True)
        return capped

    def _cron_execute_followup(self) -> None:
        capped = False
        su = self.env.su
        may_act_for = set(self.env.user._get_company_ids())
        for company in self.env["res.company"].search([]):
            if not su and company.id not in may_act_for:
                _logger.warning(
                    "Follow-up cron: skipping %s, which the scheduler user %s may "
                    "read but not act for. The other companies still run.",
                    company.display_name,
                    self.env.user.display_name,
                )
                continue
            capped |= self.with_context(
                allowed_company_ids=company.ids
            )._cron_execute_followup_company()
        if capped:
            self.env["ir.cron"]._trigger_ref("account_followup.ir_cron_follow_up")

    def _show_pay_now_button(self):
        invoice_online_payment = self.env.registry.settings.get_bool(
            self.env, "account_payment_provider.enable_portal_payment"
        )
        payment_method_available = bool(
            self.env["payment.method"]
            .sudo()
            .search_count([("active", "=", True)], limit=1)
        )
        return invoice_online_payment and payment_method_available

    @api.depends("invoice_ids")
    @api.depends_context("company", "allowed_company_ids")
    def _compute_has_moves(self) -> None:
        if not self.env["account.move"].has_access("read"):
            self.has_moves = False
            return
        field_names = ["partner_id", "partner_shipping_id", "commercial_partner_id"]
        companies = self.env["res.company"].search(
            [("id", "child_of", self.env.company.id)]
        )
        partner_ids = {
            row[0]
            for row in self.env.execute_query(
                SQL("\nUNION ").join(
                    self.env["account.move"]
                    ._search(
                        [
                            ("company_id", "in", companies.ids),
                            (name, "in", self.ids),
                        ]
                    )
                    .subselect("account_move." + name)
                    for name in field_names
                )
            )
        }

        for partner in self:
            partner.has_moves = partner._origin.id in partner_ids

    def _get_followup_letter_pdf(self, request) -> tuple:
        tz_date_str = format_date(
            self.env,
            fields.Date.today(),
            lang_code=self.env.user.lang or get_lang(self.env).code,
        )
        tz_date_str = tz_date_str.replace(".", "-")
        followup_letter_name = self.env._(
            "Follow-up %(partner)s - %(date)s.pdf",
            partner=self.display_name,
            date=tz_date_str,
        )

        action = self.env.ref("account_followup.action_report_followup")
        followup_letter = action.with_context(
            lang=self.lang or self.env.user.lang
        )._render_qweb_pdf(
            "account_followup.report_followup_print_all",
            self.id,
            data={"followup_request": request},
        )[0]

        return followup_letter_name, followup_letter

    def _create_followup_letter_attachment(self, request):

        followup_letter_name, followup_letter = self._get_followup_letter_pdf(request)
        return self.env["ir.attachment"].create(
            {
                "name": followup_letter_name,
                "raw": followup_letter,
                "res_id": self.id,
                "res_model": "res.partner",
                "type": "binary",
                "mimetype": "application/pdf",
            }
        )

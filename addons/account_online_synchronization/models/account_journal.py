import logging

from dateutil.relativedelta import relativedelta
from requests.exceptions import RequestException, Timeout

from odoo import api, fields, models, tools
from odoo.exceptions import RedirectWarning, UserError, ValidationError
from odoo.tools import SQL
from odoo.tools.misc import formatLang

_logger = logging.getLogger(__name__)


class AccountJournal(models.Model):
    _inherit = "account.journal"

    def _selection_bank_statements_source(self):
        rslt = super()._selection_bank_statements_source()
        rslt.append(("online_sync", self.env._("Online Synchronization")))
        return rslt

    next_link_synchronization = fields.Datetime(
        related="account_online_link_id.next_refresh",
        string="Online Link Next synchronization",
    )
    expiring_synchronization_date = fields.Date(
        related="account_online_link_id.expiring_synchronization_date"
    )
    expiring_synchronization_due_day = fields.Integer(
        compute="_compute_expiring_synchronization_due_day"
    )
    account_online_account_id = fields.Many2one(
        comodel_name="account.online.account",
        index="btree_not_null",
        copy=False,
        ondelete="set null",
    )
    account_online_link_id = fields.Many2one(
        comodel_name="account.online.link",
        related="account_online_account_id.account_online_link_id",
        readonly=True,
    )
    account_online_link_state = fields.Selection(
        related="account_online_link_id.state",
        readonly=True,
    )
    renewal_contact_email = fields.Char(
        related="account_online_link_id.renewal_contact_email",
        readonly=False,
    )
    online_sync_fetching_status = fields.Selection(
        related="account_online_account_id.fetching_status",
        readonly=True,
    )

    def write(self, vals):
        if (
            "bank_statements_source" in vals
            and vals.get("bank_statements_source") != "online_sync"
        ):
            for journal in self:
                if journal.bank_statements_source == "online_sync":
                    vals["account_online_account_id"] = False
                    journal.account_online_link_id.has_unlinked_accounts = True
        return super().write(vals)

    @api.depends("expiring_synchronization_date")
    def _compute_expiring_synchronization_due_day(self) -> None:
        for record in self:
            if record.expiring_synchronization_date:
                due_day_delta = (
                    record.expiring_synchronization_date
                    - fields.Date.context_today(record)
                )
                record.expiring_synchronization_due_day = due_day_delta.days
            else:
                record.expiring_synchronization_due_day = 0

    def _update_bank_cash_dashboard_data(self, dashboard_data) -> None:
        super()._update_bank_cash_dashboard_data(dashboard_data)
        self.browse(list(dashboard_data.keys())).fetch(
            ["type", "account_online_account_id"]
        )
        for journal_id, journal_data in dashboard_data.items():
            journal = self.browse(journal_id)
            journal_data["display_connect_bank_in_dashboard"] = (
                journal.type in ("bank", "credit")
                and not journal.account_online_account_id
                and journal.company_id.id == self.env.company.id
            )

    @api.constrains("account_online_account_id")
    def _check_account_online_account_id(self) -> None:
        for journal in self:
            if len(journal.account_online_account_id.journal_ids) > 1:
                raise ValidationError(
                    self.env._(
                        "You cannot have two journals associated with the same Online Account."
                    )
                )

    def _sync_online_transactions(self) -> None:
        for journal in self:
            try:
                journal.account_online_link_id._pop_connection_state_details(
                    journal=journal
                )
                journal.manual_sync()
                self.env["ir.cron"]._commit_progress(processed=1)
            except UserError, RedirectWarning:
                self.env.cr.rollback()

    def get_online_sync_favorite_institutions(self):
        company = self.sudo().company_id if len(self) == 1 else self.env.company
        timeout = (
            int(
                self.env.registry.settings.get(
                    self.env, "account_online_synchronization.request_timeout", False
                )
            )
            or 60
        )
        endpoint_url = self.env["account.online.link"]._get_odoofin_url(
            "/proxy/v2/get_dashboard_institutions"
        )
        params = {
            "country": company.tax_config_id.account_fiscal_country_id.code,
            "limit": 28,
        }
        try:
            resp = self.env["ir.egress"].request(
                "GET",
                endpoint_url,
                purpose="odoofin",
                policy="private",
                params=params,
                timeout=timeout,
            )
            resp_dict = resp.json()
            for institution in resp_dict:
                if institution["picture"].startswith("/"):
                    institution["picture"] = self.env[
                        "account.online.link"
                    ]._get_odoofin_url(institution["picture"])
            return resp_dict
        except (Timeout, ConnectionError, RequestException, ValueError) as e:
            _logger.warning(e)
            return []

    @api.model
    def _cron_import_waiting_online_transactions(self) -> None:

        limit_time = tools.config["limit_time_real_cron"] or -1
        if limit_time <= 0:
            limit_time = tools.config["limit_time_real"] or 120
        journals = self.search(
            [
                "|",
                ("online_sync_fetching_status", "in", ("planned", "waiting")),
                "&",
                ("online_sync_fetching_status", "=", "processing"),
                (
                    "account_online_link_id.last_refresh",
                    "<",
                    fields.Datetime.now() - relativedelta(seconds=limit_time),
                ),
            ]
        )
        journals.with_context(cron=True)._sync_online_transactions()

    @api.model
    def _cron_import_online_transactions(self) -> None:
        journals = self.search([("account_online_account_id", "!=", False)])
        journals.with_context(cron=True)._sync_online_transactions()

    @api.model
    def _cron_send_reminder_email(self) -> None:
        for journal in self.search([("account_online_account_id", "!=", False)]):
            if journal.expiring_synchronization_due_day in {1, 3, 15}:
                journal.action_send_reminder()

    def manual_sync(self):
        self.check_singleton()
        if self.account_online_link_id:
            account = self.account_online_account_id
            return self.account_online_link_id._get_transactions(accounts=account)
        return None

    def unlink(self):
        if self.account_online_account_id:
            self.account_online_account_id.unlink()
        return super().unlink()

    def action_configure_bank_journal(self):
        self.check_singleton()
        return self.env["account.online.link"].action_new_synchronization()

    def action_view_account_online_link(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.account_online_link_id.name,
            "res_model": "account.online.link",
            "target": "main",
            "view_mode": "form",
            "views": [[False, "form"]],
            "res_id": self.account_online_link_id.id,
        }

    def action_extend_consent(self):
        self.check_singleton()
        return self.account_online_link_id._open_iframe(
            mode="updateCredentials",
            include_param={
                "account_online_identifier": self.account_online_account_id.online_identifier,
            },
        )

    def action_reconnect_online_account(self):
        self.check_singleton()
        return self.account_online_link_id.action_reconnect_account()

    def action_send_reminder(self) -> None:
        self.check_singleton()
        self._portal_get_or_create_token()
        template = self.env.ref(
            "account_online_synchronization.email_template_sync_reminder"
        )
        subtype = self.env.ref(
            "account_online_synchronization.bank_sync_consent_renewal",
            raise_if_not_found=False,
        )
        if not subtype:
            subtype = self.env.ref("mail.mt_comment")
        self.message_post_with_source(source_ref=template, subtype_id=subtype.id)

    def action_view_missing_transaction_wizard(self) -> dict:
        journal_id = None
        if len(self) == 1:
            if (
                not self.account_online_account_id
                or self.account_online_link_state != "connected"
            ):
                raise UserError(
                    self.env._(
                        "You can't find missing transactions for a journal that isn't connected."
                    )
                )

            journal_id = self.id

        wizard = self.env["wizard.account.journal.preview.missing.transaction"].create(
            {"journal_id": journal_id}
        )
        return {
            "name": self.env._("Find Missing Transactions"),
            "type": "ir.actions.act_window",
            "res_model": "wizard.account.journal.preview.missing.transaction",
            "res_id": wizard.id,
            "views": [(False, "form")],
            "target": "new",
        }

    def action_view_duplicate_transaction_wizard(self, from_date=None):
        wizard = self.env["wizard.account.bank.statement.line.delete.duplicate"].create(
            {
                "journal_id": self.id if len(self) == 1 else None,
                **({"date": from_date} if from_date else {}),
            }
        )
        return wizard._get_records_action(
            name=self.env._("Find Duplicate Transactions")
        )

    def _has_duplicate_transactions(self, date_from) -> bool:
        self.env.cr.execute(
            SQL.join(
                SQL(""),
                [
                    self._get_duplicate_amount_date_account_transactions_query(
                        date_from
                    ),
                    SQL("LIMIT 1"),
                ],
            )
        )
        return bool(self.env.cr.rowcount)

    def _get_duplicate_transactions(self, date_from) -> list:
        query = SQL.join(
            SQL(""),
            [
                self._get_duplicate_amount_date_account_transactions_query(date_from),
                SQL("UNION"),
                self._get_duplicate_online_transaction_identifier_transactions_query(
                    date_from
                ),
                SQL("ORDER BY ids"),
            ],
        )
        return [res[0] for res in self.env.execute_query(query)]

    def _get_provider_duplicate_transactions(self, date_from) -> list:
        statement_lines = self.env.execute_query(
            SQL(
                """
                SELECT st_line.id
                  FROM account_bank_statement_line st_line
                  JOIN account_move move ON move.id = st_line.move_id
                 WHERE st_line.journal_id = %(journal_id)s
                   AND move.date >= %(date_from)s
                   AND st_line.transaction_details::JSONB->>'duplicated' = 'true';
                """,
                journal_id=self.id,
                date_from=date_from,
            )
        )
        return [res[0] for res in statement_lines]

    def _get_duplicate_amount_date_account_transactions_query(self, date_from):
        self.check_singleton()
        return SQL(
            """
              SELECT ARRAY_AGG(st_line.id ORDER BY st_line.id) AS ids
                FROM account_bank_statement_line st_line
                JOIN account_move move ON move.id = st_line.move_id
               WHERE st_line.journal_id = %(journal_id)s AND move.date >= %(date_from)s
            GROUP BY st_line.currency_id, st_line.amount, st_line.account_number, move.date
              HAVING count(st_line.id) > 1
            """,
            journal_id=self.id,
            date_from=date_from,
        )

    def _get_duplicate_online_transaction_identifier_transactions_query(
        self, date_from
    ):
        return SQL(
            """
              SELECT ARRAY_AGG(st_line.id ORDER BY st_line.id) AS ids
                FROM account_bank_statement_line st_line
                JOIN account_move move ON move.id = st_line.move_id
               WHERE st_line.journal_id = %(journal_id)s AND
                     move.date >= %(prior_date)s AND
                     st_line.online_transaction_identifier IS NOT NULL
            GROUP BY st_line.online_transaction_identifier
              HAVING count(st_line.id) > 1 AND BOOL_OR(move.date >= %(date_from)s)  -- at least one date is > date_from
                """,
            journal_id=self.id,
            date_from=date_from,
            prior_date=date_from
            - relativedelta(
                months=3
            ),
        )

    def action_view_dashboard_asynchronous_action(self):
        self.check_singleton()

        if not self.account_online_account_id:
            raise UserError(
                self.env._(
                    "You can only execute this action for bank-synchronized journals."
                )
            )

        link = self.account_online_link_id
        connection_state_details = link._pop_connection_state_details(journal=self)
        if connection_state_details and connection_state_details.get("action"):
            if connection_state_details.get("error_type") == "redirect_warning":
                link._replay_on_rollback("_pop_connection_state_details", self)
                raise RedirectWarning(
                    connection_state_details["error_message"],
                    connection_state_details["action"],
                    self.env._("Report Issue"),
                )
            return connection_state_details["action"]

        return {"type": "ir.actions.client", "tag": "soft_reload"}

    def _get_journal_dashboard_data_batched(self):
        dashboard_data = super()._get_journal_dashboard_data_batched()
        for journal in self.filtered(lambda j: j.type in ("bank", "credit")):
            if journal.account_online_account_id:
                if journal.company_id.id not in self.env.companies.ids:
                    continue
                connection_state_details = (
                    journal.account_online_link_id._get_connection_state_details(
                        journal=journal
                    )
                )
                if (
                    not connection_state_details
                    and journal.account_online_account_id.fetching_status
                    in ("waiting", "processing")
                ):
                    connection_state_details = {"status": "fetching"}
                dashboard_data[journal.id]["connection_state_details"] = (
                    connection_state_details
                )
                dashboard_data[journal.id]["show_sync_actions"] = (
                    journal.account_online_link_id.show_sync_actions
                )
        return dashboard_data

    def get_related_connection_state_details(self):
        self.check_singleton()
        connection_state_details = (
            self.account_online_link_id._get_connection_state_details(journal=self)
        )
        if (
            not connection_state_details
            and self.account_online_account_id.fetching_status
            in ("waiting", "processing")
        ):
            connection_state_details = {"status": "fetching"}
        return connection_state_details

    def _consume_connection_state_details(self) -> None:
        self.check_singleton()
        if self.account_online_link_id and self.env.user.has_group(
            "account.group_account_manager"
        ):
            self.account_online_link_id._pop_connection_state_details(journal=self)

    def open_action(self):
        if (
            not self.env.context.get("action_name")
            and self.type == "bank"
            and self.bank_statements_source == "online_sync"
        ):
            self._consume_connection_state_details()
            return self.env[
                "account.bank.statement.line"
            ]._action_view_bank_reconciliation_widget(
                default_context={"search_default_journal_id": self.id},
            )
        return super().open_action()

    def action_view_reconcile(self):
        self._consume_connection_state_details()
        return super().action_view_reconcile()

    def action_view_bank_transactions(self):
        self._consume_connection_state_details()
        return super().action_view_bank_transactions()

    def action_view_pending_bank_statement_lines(self) -> dict:
        self.check_singleton()
        account = self.account_online_account_id
        pendings = account._get_transactions_from_provider(
            date=fields.Datetime.now() - relativedelta(days=7),
            transactions_type="pending",
        )
        if not pendings:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": self.env._("No Pending Transactions"),
                    "type": "warning",
                    "message": self.env._(
                        "There are no pending transactions for this journal."
                    ),
                },
            }

        values = [{**pending, "state": "pending"} for pending in pendings]
        pending_transactions = self.env["account.online.transaction.preview"].create(
            values
        )
        return {
            "name": self.env._("Pending Transactions"),
            "type": "ir.actions.act_window",
            "res_model": "account.online.transaction.preview",
            "view_mode": "list",
            "views": [(False, "list")],
            "domain": [("id", "in", pending_transactions.ids)],
            "context": {
                "has_manual_entries": False,
                "has_cancelled_entries": False,
                "is_fetch_before_creation": False,
                "search_default_filter_posted": False,
                "disable_import": True,
            },
        }

    @api.model
    def _toggle_asynchronous_fetching_cron(self) -> None:
        cron = self.env.ref(
            "account_online_synchronization.online_sync_cron_waiting_synchronization",
            raise_if_not_found=False,
        )
        if cron:
            cron.sudo().toggle(
                model=self._name, domain=[("account_online_account_id", "!=", False)]
            )

    def get_total_journal_amount(self) -> dict:
        info_data = super().get_total_journal_amount()

        available_balance = ""
        if self.exists() and any(
            company in self.company_id._get_accessible_branches()
            for company in self.env.companies
        ):
            if self.account_online_account_id.available_balance:
                available_balance = formatLang(
                    self.env,
                    self.account_online_account_id.available_balance,
                    currency_obj=self.currency_id or self.company_id.sudo().currency_id,
                )
        return {**info_data, "available_balance_amount": available_balance}

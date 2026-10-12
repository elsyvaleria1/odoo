import base64
import datetime
import logging
import re
import urllib.parse
import uuid

from dateutil.relativedelta import relativedelta
from markupsafe import Markup
from requests.exceptions import RequestException

import odoo.release
from odoo import api, fields, models, tools
from odoo.exceptions import (
    CacheMiss,
    MissingError,
    RedirectWarning,
    UserError,
    ValidationError,
)
from odoo.http import request
from odoo.tools import LazyTranslate, frozendict
from odoo.tools.misc import format_amount, format_date, get_lang

from odoo.addons.account_online_synchronization.models.odoofin_auth import OdooFinAuth

_lt = LazyTranslate(__name__)
_logger = logging.getLogger(__name__)

_UNSET = object()
pattern = re.compile(r"^[a-z0-9-_]+$")
runbot_pattern = re.compile(r"^https:\/\/[a-z0-9-_]+\.[a-z0-9-_]+\.odoo\.com$")


class OdooFinRedirectException(UserError):
    def __init__(self, message=None, mode="link") -> None:
        self.mode = mode
        super().__init__(message or _lt("Redirect"))


class AccountOnlineAccount(models.Model):
    _name = "account.online.account"
    _description = "representation of an online bank account"
    _access_anchors = frozendict(
        {
            "company": models.Anchor(
                "account_online_link_id.company_id", shared=False, hierarchy="parent_of"
            ),
        }
    )

    name = fields.Char(
        string="Account Name",
        help="Account Name as provided by third party provider",
    )
    online_identifier = fields.Char(
        readonly=True,
        help="Id used to identify account by third party provider",
    )
    balance = fields.Float(
        readonly=True,
        help="Balance of the account sent by the third party provider",
    )
    available_balance = fields.Float(
        readonly=True,
        help="Available balance of the account sent by the third party provider. This is typically "
        "the balance plus/minus pending transactions.",
    )
    account_number = fields.Char(
        help="Set if third party provider has the full account number"
    )
    account_data = fields.Char(
        readonly=True,
        help="Extra information needed by third party provider",
    )

    account_online_link_id = fields.Many2one(
        comodel_name="account.online.link",
        index=True,
        readonly=True,
        ondelete="cascade",
    )
    journal_ids = fields.One2many(
        comodel_name="account.journal",
        inverse_name="account_online_account_id",
        domain="[('type', 'in', ('bank', 'credit')), ('company_id', '=', company_id)]",
    )
    last_sync = fields.Date(string="Last Transaction Synchronized on")
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="account_online_link_id.company_id",
    )
    currency_id = fields.Many2one(comodel_name="res.currency")
    fetching_status = fields.Selection(
        selection=[
            (
                "planned",
                "Planned",
            ),
            (
                "waiting",
                "Waiting",
            ),
            ("processing", "Processing"),
            ("done", "Done"),
        ]
    )

    inverse_balance_sign = fields.Boolean(
        help="If checked, the balance sign will be inverted"
    )
    inverse_transaction_sign = fields.Boolean(
        help="If checked, the transaction sign will be inverted"
    )

    @api.constrains("journal_ids")
    def _check_journal_ids(self) -> None:
        for online_account in self:
            if len(online_account.journal_ids) > 1:
                raise ValidationError(
                    self.env._(
                        "You cannot have two journals associated with the same Online Account."
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        result = super().create(vals_list)
        if any(
            data.get("fetching_status") in {"waiting", "processing", "planned"}
            for data in vals_list
        ):
            self.env["account.journal"]._toggle_asynchronous_fetching_cron()
        return result

    def write(self, vals):
        result = super().write(vals)
        if vals.get("fetching_status") in {"waiting", "processing", "planned"}:
            self.env["account.journal"]._toggle_asynchronous_fetching_cron()
        return result

    def unlink(self):
        result = super().unlink()
        self.env["account.journal"]._toggle_asynchronous_fetching_cron()
        return result

    def _update_journal(self, swift_code=False, journal_type="bank") -> None:
        currency_id = (
            self.currency_id.id
            if not self.currency_id.is_current_company_currency
            else False
        )
        existing_journal = self.env["account.journal"].search(
            [
                ("bank_acc_number", "=", self.account_number),
                ("currency_id", "=", currency_id),
                ("type", "=", "bank"),
                ("account_online_account_id", "=", False),
            ],
            limit=1,
        )

        self.check_singleton()
        if (active_id := self.env.context.get("active_id")) and self.env.context.get(
            "active_model"
        ) == "account.journal":
            journal = self.env["account.journal"].browse(active_id)
            if journal.account_online_link_id:
                journal.account_online_link_id.unlink()

            if self.currency_id.id != journal.currency_id.id:
                statement_lines_in_other_currency = self.env[
                    "account.bank.statement.line"
                ].search_count(
                    [
                        ("journal_id", "=", journal.id),
                        ("currency_id", "not in", (False, self.currency_id.id)),
                    ],
                    limit=1,
                )
                if statement_lines_in_other_currency:
                    raise UserError(
                        self.env._(
                            "Journal %(journal_name)s has been set up with a different currency and already has existing entries. "
                            "You can't link selected bank account in %(currency_name)s to it",
                            journal_name=journal.name,
                            currency_name=self.currency_id.name,
                        )
                    )
                move_lines_in_other_currency = self.env[
                    "account.move.line"
                ].search_count(
                    [
                        ("account_id", "=", journal.default_account_id.id),
                        ("currency_id", "!=", self.currency_id.id),
                    ],
                    limit=1,
                )
                if not move_lines_in_other_currency:
                    journal.sudo().currency_id = self.currency_id.id
        elif existing_journal:
            journal = existing_journal
        else:
            new_journal_code = self.env[
                "account.journal"
            ]._get_next_journal_default_code(journal_type, self.env.company)
            journal = self.env["account.journal"].create(
                {
                    "name": self.account_number or self.display_name,
                    "code": new_journal_code,
                    "type": journal_type,
                    "company_id": self.env.company.id,
                    "currency_id": (
                        self.currency_id.id != self.env.company.currency_id.id
                        and self.currency_id.id
                    )
                    or False,
                }
            )

        self.sudo().journal_ids = journal

        journal_vals = {
            "bank_statements_source": "online_sync",
        }
        if self.account_number and not self.journal_ids.bank_acc_number:
            journal_vals["bank_acc_number"] = self.account_number
        self.journal_ids.sudo().write(journal_vals)
        self.account_online_link_id._update_connection_status()

        lock_date = self.env.company._get_user_fiscal_lock_date(journal)
        last_sync = (
            lock_date + relativedelta(days=1)
            if lock_date and lock_date > datetime.date.min
            else None
        )
        bnk_stmt_line = self.env["account.bank.statement.line"].search(
            [("journal_id", "in", self.journal_ids.ids)], order="date desc", limit=1
        )
        if bnk_stmt_line:
            last_sync = bnk_stmt_line.date
        self.last_sync = last_sync

        if swift_code:
            if self.journal_ids.bank_account_id.bank_id:
                if not self.journal_ids.bank_account_id.bank_id.bic:
                    self.journal_ids.bank_account_id.bank_id.bic = swift_code
            else:
                bank_rec = self.env["res.bank"].search(
                    [("bic", "=", swift_code)], limit=1
                )
                if not bank_rec:
                    bank_rec = self.env["res.bank"].create(
                        {
                            "name": self.account_online_link_id.display_name,
                            "bic": swift_code,
                        }
                    )
                self.journal_ids.bank_account_id.bank_id = bank_rec.id

    def _refresh(self) -> dict:
        data = {"account_id": self.online_identifier}
        while True:
            data.update(
                {
                    "account_data": self.account_data,
                    "fetching_status": self.fetching_status,
                }
            )
            resp_json = self.account_online_link_id._get_odoo_fin(
                "/proxy/v1/refresh", data=data
            )
            if resp_json.get("account_data"):
                self.account_data = resp_json["account_data"]
            currently_fetching = resp_json.get("currently_fetching")
            success = resp_json.get("success", True)
            if currently_fetching:
                self.fetching_status = "waiting"
            if not resp_json.get("next_data"):
                break
            data["next_data"] = resp_json.get("next_data") or {}
        return {
            "success": not currently_fetching and success,
            "data": resp_json.get("data", {}),
        }

    def _get_transactions_from_provider(self, date=None, transactions_type="posted"):
        last_stmt_line = self.env["account.bank.statement.line"].search(
            [
                ("date", "<=", self.last_sync or fields.Date().today()),
                ("online_transaction_identifier", "!=", False),
                ("journal_id", "in", self.journal_ids.ids),
                ("online_account_id", "=", self.id),
            ],
            order="date desc",
            limit=1,
        )
        transactions = []

        start_date = date or last_stmt_line.date or self.last_sync
        data = {
            "start_date": start_date
            and format_date(self.env, start_date, date_format="yyyy-MM-dd"),
            "account_id": self.online_identifier,
            "last_transaction_identifier": last_stmt_line.online_transaction_identifier
            if transactions_type == "posted"
            else None,
            "currency_code": self.currency_id.name
            or self.journal_ids[:1].currency_id.name
            or self.company_id.currency_id.name,
            "include_foreign_currency": True,
        }
        while True:
            data.update(
                {
                    "account_data": self.account_data,
                }
            )
            resp_json = self.account_online_link_id._get_odoo_fin(
                f"/proxy/v2/transactions/{transactions_type}", data=data
            )
            sign = -1 if self.inverse_balance_sign else 1
            if resp_json.get("balance"):
                if self.balance != resp_json.get("balance") and not resp_json.get(
                    "available_balance"
                ):
                    self.available_balance = None
                self.balance = sign * resp_json["balance"]
            if resp_json.get("available_balance"):
                self.available_balance = sign * resp_json["available_balance"]
            if resp_json.get("account_data"):
                self.account_data = resp_json["account_data"]
            transactions += resp_json.get("transactions", [])
            if not resp_json.get("next_data"):
                break
            data["next_data"] = resp_json.get("next_data") or {}

        return self._format_transactions(transactions)

    def get_formatted_balances(self):
        balances = {}
        for account in self:
            if account.currency_id:
                formatted_balance = format_amount(
                    self.env, account.balance, account.currency_id
                )
            else:
                formatted_balance = "%.2f" % account.balance
            balances[account.id] = [formatted_balance, account.balance]
        return balances

    def _get_filtered_transactions(self, new_transactions):
        self.check_singleton()

        journal_id = self.journal_ids[:1]
        existing_bank_statement_lines = self.env[
            "account.bank.statement.line"
        ].search_fetch(
            [
                ("journal_id", "=", journal_id.id),
                (
                    "online_transaction_identifier",
                    "in",
                    [
                        transaction["online_transaction_identifier"]
                        for transaction in new_transactions
                        if transaction.get("online_transaction_identifier")
                    ],
                ),
            ],
            ["online_transaction_identifier"],
        )
        existing_online_transaction_identifier = set(
            existing_bank_statement_lines.mapped("online_transaction_identifier")
        )

        filtered_transactions = []
        for transaction in new_transactions:
            if transaction_identifier := transaction["online_transaction_identifier"]:
                if transaction_identifier in existing_online_transaction_identifier:
                    continue
                existing_online_transaction_identifier.add(transaction_identifier)

            filtered_transactions.append(transaction)
        return filtered_transactions

    def _format_transactions(self, new_transactions):
        self.check_singleton()
        transaction_sign = -1 if self.inverse_transaction_sign else 1
        currencies = self.env["res.currency"].with_context(active_test=False).search([])
        currency_code_mapping = {currency.name: currency for currency in currencies}
        is_iso20022_installed = (
            self.env["ir.module.module"]._get("account_iso20022").state == "installed"
        )

        formatted_transactions = []
        for transaction in new_transactions:
            if transaction.get("foreign_currency_code"):
                currency = currency_code_mapping.get(
                    transaction.pop("foreign_currency_code")
                )
                if currency:
                    transaction.update({"foreign_currency_id": currency.id})
                    if not currency.active:
                        currency.active = True

            if not is_iso20022_installed:
                transaction.pop("end_to_end_uuid", False)

            formatted_transactions.append(
                {
                    **transaction,
                    "amount": transaction["amount"] * transaction_sign,
                    "date": fields.Date.from_string(transaction["date"]),
                    "online_account_id": self.id,
                    "journal_id": self.journal_ids[:1].id,
                    "company_id": self.company_id.id,
                }
            )
        return formatted_transactions

    def action_reset_fetching_status(self) -> None:
        self.fetching_status = None


class AccountOnlineLink(models.Model):
    _name = "account.online.link"
    _description = "Bank Connection"
    _inherit = ["mixin.mail.thread", "mixin.mail.activity"]
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", hierarchy="parent_of"),
        }
    )

    def _compute_next_synchronization(self) -> None:
        for rec in self:
            rec.next_refresh = (
                self.env["ir.cron"]
                .sudo()
                .search(
                    [
                        (
                            "id",
                            "=",
                            self.env.ref(
                                "account_online_synchronization.online_sync_cron"
                            ).id,
                        )
                    ],
                    limit=1,
                )
                .nextcall
            )

    account_online_account_ids = fields.One2many(
        comodel_name="account.online.account",
        inverse_name="account_online_link_id",
    )
    last_refresh = fields.Datetime(
        string="Last Synchronization",
        default=fields.Datetime.now,
        readonly=True,
    )
    next_refresh = fields.Datetime(
        string="Next synchronization",
        compute="_compute_next_synchronization",
    )
    state = fields.Selection(
        selection=[
            ("connected", "Connected"),
            ("error", "Error"),
            ("disconnected", "Not Connected"),
        ],
        default="disconnected",
        readonly=True,
        required=True,
        tracking=True,
    )
    connection_state_details = fields.Json()
    auto_sync = fields.Boolean(
        string="Automatic synchronization",
        default=True,
        help="""If possible, we will try to automatically fetch new transactions for this record
                \nIf the automatic sync is disabled. that will be due to security policy on the bank's end. So, they have to launch the sync manually""",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
    )
    has_unlinked_accounts = fields.Boolean(
        default=True,
        help="True if that connection still has accounts that are not linked to an Odoo journal",
    )
    show_sync_actions = fields.Boolean(compute="_compute_show_sync_actions")

    name = fields.Char(
        readonly=True,
        help="Institution Name",
    )
    client_id = fields.Char(
        readonly=True,
        help="Represent a link for a given user towards a banking institution",
    )
    credential_id = fields.Many2one(
        comodel_name="credential.credential",
        copy=False,
        readonly=True,
        ondelete="restrict",
        groups="base.group_system",
        help="Holds this connection's OdooFin tokens.",
    )
    refresh_token = fields.Char(
        compute="_compute_odoofin_tokens",
        inverse="_inverse_refresh_token",
        readonly=True,
        classification="secret.credential",
        groups="base.group_system",
        help="Token used to sign API request, Never disclose it",
    )
    access_token = fields.Char(
        compute="_compute_odoofin_tokens",
        inverse="_inverse_access_token",
        readonly=True,
        groups="account.group_account_basic",
        help="Token used to access API.",
    )
    expiring_synchronization_date = fields.Date(
        readonly=True,
        help="Date when the consent for this connection expires",
    )
    journal_ids = fields.One2many(
        comodel_name="account.journal",
        compute="_compute_journal_ids",
    )
    provider_type = fields.Char(
        readonly=True,
        help="Third Party Provider",
    )
    renewal_contact_email = fields.Char(
        string="Connection Requests",
        default=lambda self: self.env.user.email,
        help="Comma separated list of email addresses to send consent renewal notifications 15, 3 and 1 days before expiry",
    )

    @api.depends("account_online_account_ids")
    def _compute_journal_ids(self) -> None:
        for online_link in self:
            online_link.journal_ids = online_link.account_online_account_ids.journal_ids

    @api.depends("company_id")
    @api.depends_context("allowed_company_ids")
    def _compute_show_sync_actions(self) -> None:
        for online_link in self:
            online_link.show_sync_actions = online_link.company_id in self.env.companies

    def create_new_bank_account_action(self, data) -> dict:
        self.check_singleton()
        journal_type = data.get("journal_type") or "bank"
        assert journal_type in ("bank", "credit")
        if journal_type == "bank":
            view_xml_id = "account.setup_bank_account_wizard"
            name = self.env._("Setup Bank Account")
        else:
            view_xml_id = "account.setup_credit_card_account_wizard"
            name = self.env._("Setup Credit Card Account")

        if not data or not data.get("account_number"):
            ctx = {**self.env.context, "journal_type": journal_type}
            if self.env.context.get("active_model") == "account.journal":
                ctx = {
                    **ctx,
                    "default_linked_journal_id": ctx.get("active_id", False),
                    "dialog_size": "medium",
                }
            return {
                "type": "ir.actions.act_window",
                "name": name,
                "res_model": "wizard.res.partner.bank.account.create",
                "target": "new",
                "view_mode": "form",
                "context": ctx,
                "views": [[self.env.ref(view_xml_id).id, "form"]],
            }

        self.check_access("write")
        bank = self.env["res.bank"]
        if data.get("name"):
            bank = (
                self.env["res.bank"]
                .sudo()
                .create(
                    {
                        "name": data["name"],
                        "bic": data.get("swift_code"),
                    }
                )
            )

        bank_account = (
            self.env["res.partner.bank.account"]
            .sudo()
            .create(
                {
                    "acc_number": data.get("account_number"),
                    "bank_id": bank.id,
                    "partner_id": self.company_id.partner_id.id,
                }
            )
        )

        self.env["account.journal"].sudo().create(
            {
                "name": data.get("account_number"),
                "type": journal_type,
                "bank_account_id": bank_account.id,
                "company_id": self.company_id.id,
            }
        )

        return {"type": "ir.actions.client", "tag": "soft_reload"}

    def _link_accounts_to_journals_action(self, swift_code, journal_type) -> dict:
        self.check_singleton()
        account_bank_selection_wizard = self.env[
            "wizard.account.online.link.connect.account"
        ].create(
            {
                "account_online_link_id": self.id,
            }
        )

        return {
            "name": self.env._("Select a Bank Account")
            if journal_type == "bank"
            else self.env._("Select a Credit Card Account"),
            "type": "ir.actions.act_window",
            "res_model": "wizard.account.online.link.connect.account",
            "views": [[False, "form"]],
            "target": "new",
            "res_id": account_bank_selection_wizard.id,
            "context": dict(
                self.env.context, swift_code=swift_code, journal_type=journal_type
            ),
        }

    @api.model
    def _show_fetched_transactions_action(
        self, stmt_lines, duplicates_from_date, journal
    ):
        default_context = {
            "duplicates_from_date": duplicates_from_date or {},
            "search_default_fetched_lines": True,
            "search_default_journal_id": journal.id,
            "fetched_stmt_line_ids": stmt_lines.ids,
        }

        return self.env[
            "account.bank.statement.line"
        ]._action_view_bank_reconciliation_widget(
            name=self.env._("Fetched Transactions"),
            default_context=default_context,
        )

    def _get_connection_state_details(self, journal):
        self.check_singleton()
        if self.connection_state_details and self.connection_state_details.get(
            str(journal.id)
        ):
            return self.connection_state_details[str(journal.id)]
        return None

    def _pop_connection_state_details(self, journal):
        self.check_singleton()
        if journal_connection_state_details := self._get_connection_state_details(
            journal
        ):
            self._set_connection_state_details(journal, {})
            return journal_connection_state_details
        return None

    def _set_connection_state_details(self, journal, connection_state_details) -> None:
        self.check_singleton()
        existing_connection_state_details = self.connection_state_details or {}
        self.connection_state_details = {
            **existing_connection_state_details,
            str(journal.id): connection_state_details,
        }

    def _notify_connection_update(self, journal, connection_state_details) -> None:
        self.check_singleton()
        self._record_connection_update(journal, connection_state_details)
        if connection_state_details["status"] == "error":
            self._replay_on_rollback(
                "_record_connection_update", journal, connection_state_details
            )

    def _record_connection_update(self, journal, connection_state_details) -> None:
        connection_state_details_status = connection_state_details["status"]
        if not (
            connection_state_details_status == "success"
            and connection_state_details.get("nb_fetched_transactions", 0) == 0
        ):
            self._set_connection_state_details(
                journal=journal,
                connection_state_details=connection_state_details,
            )
        self.env.ref("account.group_account_user").all_user_ids._bus_send(
            "online_sync",
            {
                "id": journal.id,
                "connection_state_details": {
                    key: value
                    for key, value in connection_state_details.items()
                    if key in ("status", "error_type", "nb_fetched_transactions")
                },
            },
        )

    def _replay_on_rollback(self, method, *args) -> None:
        self.check_singleton()
        registry, link_id = self.env.registry, self.id
        uid, context = self.env.uid, dict(self.env.context)

        @self.env.cr.postrollback.add
        def replay_on_own_cursor():
            try:
                with registry.cursor() as cr:
                    env = api.Environment(cr, uid, context)
                    link = env[self._name].browse(link_id).exists()
                    if link:
                        getattr(link, method)(
                            *(
                                arg.with_env(env)
                                if isinstance(arg, models.BaseModel)
                                else arg
                                for arg in args
                            )
                        )
            except Exception:
                _logger.exception(
                    "Could not replay %s on online link %s after a rollback",
                    method,
                    link_id,
                )

    def _handle_odoofin_redirect_exception(self, mode="link"):
        if mode == "link":
            return self.with_context(
                {"redirect_reconnection": True}
            ).action_new_synchronization()
        return self.with_context({"redirect_reconnection": True})._open_iframe(
            mode=mode
        )

    @api.model
    def _get_odoofin_url(self, url):
        proxy_mode = (
            self.env.registry.settings.get(
                self.env, "account_online_synchronization.proxy_mode", False
            )
            or "production"
        )
        if not pattern.match(proxy_mode) and not runbot_pattern.match(proxy_mode):
            raise UserError(
                self.env._("Invalid value for proxy_mode config parameter.")
            )
        endpoint_url = "https://%s.odoofin.com%s" % (proxy_mode, url)
        if runbot_pattern.match(proxy_mode):
            endpoint_url = "%s%s" % (proxy_mode, url)
        return endpoint_url

    def _get_odoo_fin(self, url, data=None, ignore_status=False):
        if not data:
            data = {}
        if self.state == "disconnected" and not ignore_status:
            raise UserError(self.env._("Please reconnect your online account."))
        if not url.startswith("/"):
            raise UserError(self.env._("Invalid URL"))

        timeout = (
            int(
                self.env.registry.settings.get(
                    self.env, "account_online_synchronization.request_timeout", False
                )
            )
            or 60
        )
        endpoint_url = self._get_odoofin_url(url)
        cron = self.env.context.get("cron", False)
        data["utils"] = {
            "request_timeout": timeout,
            "lang": get_lang(self.env).code,
            "server_version": odoo.release.serie,
            "db_uuid": self.env.registry.settings.get(self.env, "database.uuid", False),
            "cron": cron,
        }
        if request:
            data["utils"]["psu_info"] = {
                "ip": request.httprequest.remote_addr,
                "user_agent": request.httprequest.user_agent.string,
            }

        try:
            resp = self.env["ir.egress"].request(
                "POST",
                endpoint_url,
                purpose="odoofin",
                policy="private",
                json=data,
                timeout=timeout,
                auth=OdooFinAuth(record=self.sudo()),
            )
            resp_json = resp.json()
            return self._handle_response(resp_json, url, data, ignore_status)
        except (RequestException, ValueError) as error:
            _logger.warning("synchronization error")
            raise UserError(
                self.env._(
                    "The online synchronization service is not available at the moment. "
                    "Please try again later."
                )
            ) from error

    def _handle_response(self, resp_json, url, data, ignore_status=False):
        if not resp_json.get("error"):
            result = resp_json.get("result")
            state = result.get("odoofin_state") or False
            message = result.get("display_message") or False
            subject = (message and self.env._("Message")) or False
            self._log_information(state=state, message=message, subject=subject)
            return result
        else:
            error = resp_json.get("error")
            if error.get("code") == 101:
                self._update_access_token()
                return self._get_odoo_fin(url, data, ignore_status)
            elif error.get("code") == 102:
                self._update_refresh_token()
                self._update_access_token()
                link = self.sudo()
                self._replay_on_rollback(
                    "_store_tokens",
                    {
                        "refresh_token": link.refresh_token,
                        "access_token": link.access_token,
                    },
                )
                if self.journal_ids:
                    self._update_connection_status()
                return self._get_odoo_fin(url, data, ignore_status)
            elif error.get("code") == 300:
                raise OdooFinRedirectException(
                    mode=error.get("data", {}).get("mode", "link")
                )
            elif error.get("code") in (100, 104, 106) and self.env.context.get(
                "delete_sync"
            ):
                return {"delete": True}
            error_details = error.get("data")
            subject = error.get("message")
            message = error_details.get("message")
            state = error_details.get("odoofin_state") or "error"
            ctx = self.env.context.copy()
            ctx["error_reference"] = error_details.get("error_reference")
            ctx["provider_type"] = error_details.get("provider_type")
            ctx["redirect_warning_url"] = error_details.get("redirect_warning_url")

            self.with_context(ctx)._log_information(
                state=state, subject=subject, message=message, raise_error=True
            )
        return None

    def _log_information(
        self, state, subject=None, message=None, raise_error=False
    ) -> None:
        try:
            report, url, button_label = self._record_information(
                state, subject, message, raise_error
            )
        except CacheMiss, MissingError:
            return
        if not raise_error:
            return
        self._replay_on_rollback("_record_information", state, subject, message, True)
        if url:
            action_id = {
                "type": "ir.actions.act_url",
                "url": url,
            }
            raise RedirectWarning(report, action_id, button_label)
        raise UserError(report)

    def _record_information(self, state, subject, message, report) -> tuple:
        if state == "error" and self.state == "disconnected":
            state = "disconnected"
        if state and self.state != state:
            self.write({"state": state})
        if state in ("error", "disconnected"):
            self.account_online_account_ids.fetching_status = "done"
        context = self.env.context
        button_label = url = None
        if report and subject and message:
            message_post = message
            error_reference = context.get("error_reference")
            provider = context.get("provider_type")
            odoo_help_description = f"""ClientID: {self.client_id}\nInstitution: {self.name}\nError Reference: {error_reference}\nError Message: {message_post}\n"""
            odoo_help_summary = f"Bank sync error ref: {error_reference} - Provider: {provider} - Client ID: {self.client_id}"
            if context.get("redirect_warning_url"):
                if context["redirect_warning_url"] == "odoo_support":
                    url_params = urllib.parse.urlencode(
                        {
                            "stage": "bank_sync",
                            "summary": odoo_help_summary,
                            "description": odoo_help_description[:1500],
                        }
                    )
                    url = f"https://www.odoo.com/help?{url_params}"
                    message += self.env._(
                        "\n\nIf you've already opened a ticket for this issue, don't report it again: a support agent will contact you shortly."
                    )
                    message_post = Markup('%s<br>%s <a href="%s" >%s</a>') % (
                        message,
                        self.env._("You can contact Odoo support"),
                        url,
                        self.env._("Here"),
                    )
                    button_label = self.env._("Report issue")
                else:
                    url = "https://www.odoo.com/documentation/latest/applications/finance/accounting/bank/bank_synchronization.html#faq"
                    message_post = Markup('%s<br>%s <a href="%s" >%s</a>') % (
                        message_post,
                        self.env._("Check the documentation"),
                        url,
                        self.env._("Here"),
                    )
                    button_label = self.env._("Check the documentation")
            self.message_post(body=message_post, subject=subject)
        return message, url, button_label

    @api.depends("credential_id")
    def _compute_odoofin_tokens(self) -> None:
        for link in self:
            credential = link.sudo().credential_id.sudo()
            tokens = (
                credential._use_secret_payload("account_online_synchronization:tokens")
                if credential
                else {}
            )
            link.access_token = tokens.get("oauth_access_token") or False
            link.refresh_token = tokens.get("oauth_refresh_token") or False

    def _inverse_access_token(self) -> None:
        for link in self:
            link._odoofin_store_tokens(access_token=link.access_token)

    def _inverse_refresh_token(self) -> None:
        for link in self:
            link._odoofin_store_tokens(refresh_token=link.refresh_token)

    def _odoofin_store_tokens(self, access_token=_UNSET, refresh_token=_UNSET) -> None:
        self.check_singleton()
        values = {}
        if access_token is not _UNSET:
            values["oauth_access_token"] = access_token or False
        if refresh_token is not _UNSET:
            values["oauth_refresh_token"] = refresh_token or False

        link = self.sudo()
        credential = link.credential_id.sudo()
        if credential:
            if any(values.values()):
                credential.write(values)
            else:
                link.credential_id = False
                credential.unlink()
            return
        if not any(values.values()):
            return
        link.credential_id = (
            self.env["credential.credential"]
            .sudo()
            .create(
                {
                    "name": self.env._("OdooFin: %(name)s", name=self.name or self.id),
                    "category_id": self.env.ref(
                        "credential.credential_category_oauth2"
                    ).id,
                    "company_id": self.company_id.id,
                    **values,
                }
            )
            .id
        )

    def _update_access_token(self) -> None:
        for link in self:
            resp_json = link._get_odoo_fin(
                "/proxy/v1/get_access_token", ignore_status=True
            )
            link.access_token = resp_json.get("access_token", False)

    def _store_tokens(self, tokens) -> None:
        self.sudo().write(tokens)

    def _update_refresh_token(self) -> None:
        for link in self.sudo():
            resp_json = link._get_odoo_fin("/proxy/v1/renew_token", ignore_status=True)
            link.refresh_token = resp_json.get("refresh_token", False)

    def unlink(self):
        to_unlink = self.env["account.online.link"]
        for link in self:
            try:
                resp_json = link.with_context(delete_sync=True)._get_odoo_fin(
                    "/proxy/v1/delete_user", ignore_status=True
                )
                if resp_json.get("delete", True) is True:
                    to_unlink += link
            except OdooFinRedirectException, UserError, RedirectWarning:
                to_unlink += link
                continue
        result = super(AccountOnlineLink, to_unlink).unlink()
        self.env["account.journal"]._toggle_asynchronous_fetching_cron()
        return result

    def _sync_accounts(self, online_identifier=False):
        self.check_singleton()
        if online_identifier:
            matching_account = self.account_online_account_ids.filtered(
                lambda l: l.online_identifier == online_identifier
            )
            if matching_account and matching_account.journal_ids:
                return matching_account
            elif matching_account and not matching_account.journal_ids:
                matching_account.unlink()
        accounts = {}
        data = {
            "currency_code": self.company_id.currency_id.name,
        }
        swift_code = False
        while True:
            if online_identifier:
                data["online_identifier"] = online_identifier

            resp_json = self._get_odoo_fin("/proxy/v1/accounts", data)
            for acc in resp_json.get("accounts", []):
                acc["account_online_link_id"] = self.id
                currency_id = (
                    self.env["res.currency"]
                    .with_context(active_test=False)
                    .search([("name", "=", acc.pop("currency_code", ""))], limit=1)
                )
                if currency_id:
                    if not currency_id.active:
                        currency_id.sudo().active = True
                    acc["currency_id"] = currency_id.id
                accounts[str(acc.get("online_identifier"))] = acc
            swift_code = resp_json.get("swift_code")
            if not resp_json.get("next_data"):
                break
            data["next_data"] = resp_json.get("next_data")

        if accounts:
            self.has_unlinked_accounts = True
            return self.env["account.online.account"].create(
                list(accounts.values())
            ), swift_code
        return False, False

    def _can_get_transactions(self) -> bool:
        self.check_singleton()
        limit_time = tools.config["limit_time_real_cron"] or -1
        if limit_time <= 0:
            limit_time = tools.config["limit_time_real"] or 120
        limit_time += 20
        if (
            self.account_online_account_ids.filtered(
                lambda account: account.fetching_status == "processing"
            )
            and self.last_refresh + relativedelta(seconds=limit_time)
            > fields.Datetime.now()
        ):
            return False
        return not (
            self.env.context.get("cron")
            and not self.auto_sync
            and not self.account_online_account_ids.filtered(
                lambda acc: acc.fetching_status in ("planned", "waiting", "processing")
            )
        )

    def _get_transactions(self, refresh=True, accounts=False, check_duplicates=False):
        self.check_singleton()
        if not self._can_get_transactions():
            return None

        is_cron_running = self.env.context.get("cron")
        acc = (accounts or self.account_online_account_ids).filtered("journal_ids")
        self.last_refresh = fields.Datetime.now()
        try:
            accounts_to_synchronize = acc
            if not is_cron_running:
                accounts_not_to_synchronize = self.env["account.online.account"]
                account_to_reauth = False
                for online_account in acc:
                    if refresh and online_account.fetching_status not in (
                        "planned",
                        "processing",
                    ):
                        refresh_res = online_account._refresh()
                        if not refresh_res["success"]:
                            if refresh_res["data"].get("mode") == "updateCredentials":
                                account_to_reauth = online_account
                            accounts_not_to_synchronize += online_account
                            continue
                    online_account.fetching_status = "waiting"
                if account_to_reauth:
                    return self._open_iframe(
                        mode="updateCredentials",
                        include_param={
                            "account_online_identifier": account_to_reauth.online_identifier,
                        },
                    )
                accounts_to_synchronize = acc - accounts_not_to_synchronize
                if not accounts_to_synchronize:
                    return None

            def get_duplicates_from_date(statement_lines, journal):
                if check_duplicates and statement_lines:
                    from_date = fields.Date.to_string(
                        statement_lines.sorted("date")[0].date
                    )
                    if journal._has_duplicate_transactions(from_date):
                        return from_date
                return None

            for online_account in accounts_to_synchronize:
                journal = online_account.journal_ids[0]
                online_account.fetching_status = "processing"
                self.env["ir.cron"]._commit_progress()
                try:
                    transactions = online_account._get_transactions_from_provider()
                except RedirectWarning as redirect_warning:
                    self._notify_connection_update(
                        journal=journal,
                        connection_state_details={
                            "status": "error",
                            "error_type": "redirect_warning",
                            "error_message": redirect_warning.args[0],
                            "action": redirect_warning.args[1],
                        },
                    )
                    raise
                except OdooFinRedirectException as redirect_exception:
                    self._notify_connection_update(
                        journal=journal,
                        connection_state_details={
                            "status": "error",
                            "error_type": "odoofin_redirect",
                            "action": self._handle_odoofin_redirect_exception(
                                mode=redirect_exception.mode
                            ),
                        },
                    )
                    raise

                sorted_transactions = sorted(
                    transactions, key=lambda transaction: transaction["date"]
                )
                if not is_cron_running:
                    total = sum(transaction["amount"] for transaction in transactions)
                    statement_lines = (
                        self.env["account.bank.statement.line"]
                        .with_context(transactions_total=total)
                        ._online_sync_bank_statement(
                            sorted_transactions[:100], online_account
                        )
                    )
                    online_account.fetching_status = (
                        "planned" if len(transactions) > 100 else "done"
                    )

                    duplicates_from_date = get_duplicates_from_date(
                        statement_lines, journal
                    )
                    return self.env[
                        "account.bank.statement.line"
                    ]._action_view_bank_reconciliation_widget(
                        name=self.env._("Fetched Transactions"),
                        default_context={
                            **self.env.context,
                            "active_id": journal.id,
                            "default_journal_id": journal.id,
                            "duplicates_from_date": duplicates_from_date,
                            "search_default_journal_id": journal.id,
                            "search_default_fetched_lines": True,
                            "fetched_stmt_line_ids": statement_lines.ids
                            if statement_lines
                            else [],
                        },
                    )
                else:
                    statement_lines = self.env[
                        "account.bank.statement.line"
                    ]._online_sync_bank_statement(sorted_transactions, online_account)
                    online_account.fetching_status = "done"
                    duplicates_from_date = get_duplicates_from_date(
                        statement_lines, journal
                    )
                    self._notify_connection_update(
                        journal=journal,
                        connection_state_details={
                            "status": "success",
                            "nb_fetched_transactions": len(statement_lines),
                            "action": self._show_fetched_transactions_action(
                                statement_lines, duplicates_from_date, journal
                            ),
                        },
                    )
            return None
        except OdooFinRedirectException as e:
            return self._handle_odoofin_redirect_exception(mode=e.mode)

    def _update_expiring_date(self, data) -> None:
        self.check_singleton()

        if data.get("consent_expiring_date"):
            expiring_synchronization_date = fields.Date.to_date(
                data["consent_expiring_date"]
            )
            if expiring_synchronization_date != self.expiring_synchronization_date:
                bank_sync_activity_type_id = self.env.ref(
                    "mail.mail_activity_data_todo"
                )
                account_journal_model_id = self.env["ir.model"]._get_id(
                    "account.journal"
                )

                self.env["mail.activity"].search(
                    [
                        ("res_id", "in", self.journal_ids.ids),
                        ("res_model", "=", "account.journal"),
                        ("activity_type_id", "=", bank_sync_activity_type_id.id),
                        ("date_deadline", "<=", self.expiring_synchronization_date),
                        ("user_id", "=", self.env.user.id),
                    ]
                ).unlink()

                self.expiring_synchronization_date = expiring_synchronization_date
                new_activity_vals = [
                    {
                        "res_id": journal.id,
                        "res_model_id": account_journal_model_id,
                        "date_deadline": self.expiring_synchronization_date,
                        "summary": self.env._(
                            "Bank Synchronization: Update your consent"
                        ),
                        "note": data.get("activity_message") or "",
                        "activity_type_id": bank_sync_activity_type_id.id,
                    }
                    for journal in self.journal_ids
                ]
                self.env["mail.activity"].create(new_activity_vals)
        elif (
            self.expiring_synchronization_date
            and self.expiring_synchronization_date < fields.Date.context_today(self)
        ):
            self.expiring_synchronization_date = None

    def _update_connection_status(self):
        self.check_singleton()
        resp_json = self._get_odoo_fin(
            "/proxy/v2/connection_status", ignore_status=True
        )

        self._update_expiring_date(resp_json)

        return resp_json

    def _authorize_access(self, data_access_token) -> None:
        self.check_singleton()
        data = {
            "linked_accounts": self.account_online_account_ids.filtered(
                "journal_ids"
            ).mapped("online_identifier"),
            "record_access_token": data_access_token,
        }
        try:
            resp_json = self._get_odoo_fin("/proxy/v1/authorize_access", data)
            self.has_unlinked_accounts = resp_json.get("has_unlinked_accounts")
        except UserError:
            pass

    @api.model
    def _cron_remove_unused_connection(self) -> None:
        account_online_links = self.search(
            [
                ("write_date", "<=", fields.Datetime.now() - relativedelta(months=1)),
            ]
        )
        for link in account_online_links:
            if not link.account_online_account_ids.filtered("journal_ids"):
                link.unlink()

    def _message_post_prepare_values(self, post_values) -> None:
        for journal in self.journal_ids:
            journal.message_post(**post_values)
        super()._message_post_prepare_values(post_values)

    def success(self, mode, data):
        journal_type = "bank"
        if data:
            journal_type = data.pop("journal_type", None) or "bank"
            if consent_token := data.pop("manage_consent", None):
                url = self._get_odoofin_url(
                    f"/manage-consent?consent_token={consent_token}"
                )
                self.message_post(
                    body=self.env._(
                        "You can manage your bank synchronization consent for this connection %s",
                        Markup("<a href='%s' target='_blank'>%s</a>")
                        % (url, self.env._("here.")),
                    )
                )

            self.write(data)

            self._update_connection_status()

        if mode == "none":
            return {"type": "ir.actions.client", "tag": "reload"}
        try:
            method_name = "_success_%s" % mode
            method = getattr(self.with_context(journal_type=journal_type), method_name)
        except AttributeError:
            message = self.env._(
                "This version of Odoo appears to be outdated and does not support the '%s' sync mode. "
                "Installing the latest update might solve this.",
                mode,
            )
            _logger.info("Online sync: %s", message)
            self._log_information(
                state="error",
                subject=self.env._("Internal Error"),
                message=message,
                raise_error=True,
            )
            raise UserError(message) from None
        action = method()
        return action or self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "account.open_account_journal_dashboard_kanban"
        )

    @api.model
    def connect_existing_account(self, data):
        client_id = data.get("client_id")
        online_identifier = data.get("online_identifier")
        if client_id and online_identifier:
            online_link = self.search([("client_id", "=", client_id)], limit=1)
            if not online_link:
                return {"type": "ir.actions.client", "tag": "reload"}
            new_account, swift_code = online_link._sync_accounts(
                online_identifier=online_identifier
            )
            if new_account:
                new_account._update_journal(
                    swift_code, data.get("journal_type", "bank")
                )
                action = online_link._get_transactions(
                    accounts=new_account, check_duplicates=True
                )
                return action or self.env[
                    "ir.actions.act_window"
                ]._get_action_dict_by_xml_id(
                    "account.open_account_journal_dashboard_kanban"
                )
            raise UserError(
                self.env._("The consent for the selected account has expired.")
            )
        return {"type": "ir.actions.client", "tag": "reload"}

    def exchange_token(self, exchange_token) -> bool:
        self.check_singleton()
        self.check_access("write")
        data = {
            "exchange_token": exchange_token,
            "company_id": self.env.company.id,
            "user_id": self.env.user.id,
        }
        resp_json = self._get_odoo_fin(
            "/proxy/v1/exchange_token", data=data, ignore_status=True
        )
        self.sudo().write(
            {
                "client_id": resp_json.get("client_id"),
                "refresh_token": resp_json.get("refresh_token"),
                "access_token": resp_json.get("access_token"),
            }
        )
        return True

    def _success_link(self):
        self.check_singleton()
        self._log_information(state="connected")
        account_online_accounts, swift_code = self._sync_accounts()
        if account_online_accounts and len(account_online_accounts) == 1:
            account_online_accounts._update_journal(
                swift_code, self.env.context.get("journal_type", "bank")
            )
            return self._get_transactions(
                accounts=account_online_accounts, check_duplicates=True
            )
        return self._link_accounts_to_journals_action(
            swift_code, self.env.context.get("journal_type")
        )

    def _success_updateCredentials(self):
        self.check_singleton()
        return self._get_transactions(refresh=False)

    def _success_refreshAccounts(self):
        self.check_singleton()
        return self._get_transactions(refresh=False)

    def _success_reconnect(self):
        self.check_singleton()
        self._log_information(state="connected")
        return self._get_transactions(check_duplicates=True)

    def action_new_synchronization(
        self, preferred_inst=None, journal_id=False, journal_type="bank"
    ):
        online_link = self
        if not online_link or online_link.provider_type:
            online_link = self.search(
                [
                    ("account_online_account_ids", "=", False),
                    ("provider_type", "=", False),
                ],
                limit=1,
            )
        if not online_link or online_link.provider_type:
            online_link = self.create({})
        return online_link._open_iframe(
            "link",
            preferred_institution=preferred_inst,
            journal_id=journal_id,
            journal_type=journal_type,
        )

    def action_update_credentials(self):
        return self._open_iframe("updateCredentials")

    def action_fetch_transactions(self):
        self.account_online_account_ids.fetching_status = None
        action = self._get_transactions()
        return action or self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "account.open_account_journal_dashboard_kanban"
        )

    def action_reconnect_account(self):
        return self._open_iframe("reconnect")

    def _open_iframe(
        self,
        mode="link",
        include_param=None,
        preferred_institution=False,
        journal_id=False,
        journal_type="bank",
    ):
        self.check_singleton()
        if self.client_id and self.sudo().refresh_token:
            try:
                self._update_access_token()
            except OdooFinRedirectException:
                self.unlink()
                return self.create({})._open_iframe("link")

        proxy_mode = (
            self.env.registry.settings.get(
                self.env, "account_online_synchronization.proxy_mode", False
            )
            or "production"
        )
        country = (
            self.env["account.journal"]
            .browse(journal_id)
            .company_id.tax_config_id.account_fiscal_country_id
            or self.env.company.country_id
        )
        action = {
            "type": "ir.actions.client",
            "tag": "odoo_fin_connector",
            "id": self.id,
            "params": {
                "proxyMode": proxy_mode,
                "clientId": self.client_id,
                "accessToken": self.access_token,
                "mode": mode,
                "includeParam": {
                    "lang": get_lang(self.env).code,
                    "dbURL": self.get_base_url(),
                    "countryCode": country.code,
                    "countryName": country.display_name,
                    "redirect_reconnection": self.env.context.get(
                        "redirect_reconnection"
                    ),
                    "serverVersion": odoo.release.serie,
                    "mfa_type": self.env.user._get_mfa_type(),
                    "journal_type": journal_type,
                },
            },
            "context": {
                "dialog_size": "medium",
            },
        }
        if preferred_institution:
            action["params"]["includeParam"]["clickedInstitution"] = (
                preferred_institution
            )
        if journal_id:
            action["context"]["active_model"] = "account.journal"
            action["context"]["active_id"] = journal_id

        if mode == "link":
            user_email = (
                self.env.user.email or self.env.ref("base.user_admin").email or ""
            )
            action["params"]["includeParam"]["dbUuid"] = self.env.registry.settings.get(
                self.env, "database.uuid", False
            )
            action["params"]["includeParam"]["userEmail"] = user_email
            existing_link = self.search(
                [("state", "!=", "disconnected"), ("has_unlinked_accounts", "=", True)]
            )
            if existing_link:
                record_access_token = base64.b64encode(uuid.uuid4().bytes).decode(
                    "utf-8"
                )
                for link in existing_link:
                    link._authorize_access(record_access_token)
                action["params"]["includeParam"]["recordAccessToken"] = (
                    record_access_token
                )

        if include_param:
            action["params"]["includeParam"].update(include_param)
        return action

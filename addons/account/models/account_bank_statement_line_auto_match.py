import logging
from datetime import timedelta

from odoo import api, fields, models, modules, service
from odoo.db.errors import PG_RETRY_EXCEPTIONS
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL

_logger = logging.getLogger(__name__)

_debug = DebugLog(__name__)

MAX_BARREN_CRON_ROUNDS = 3
AUTO_RECONCILE_RETRY_DAYS = 90
AUTO_RECONCILE_WAKE_UP_MINUTES = 5


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    auto_reconcile_rule = fields.Selection(
        selection=[
            ("end_to_end", "Payment identifier"),
            ("outstanding", "Outstanding payment"),
            ("reference", "Document reference"),
            ("amount", "Partner and amount"),
            ("charges", "The bank's charges for the month"),
            ("amount_alone", "Amount alone, to review"),
            ("model", "Reconciliation model"),
        ],
        string="Matched Automatically By",
        copy=False,
        readonly=True,
        help="The automatic rule that finished matching this transaction. Empty "
        "when a person matched it, or changed what the rule had matched.",
    )

    @_debug.perf.timed
    def _cron_try_auto_reconcile_statement_lines(
        self, batch_size=None, limit_time=0, company_id=None
    ) -> None:
        _debug.lifecycle("_cron_try_auto_reconcile_statement_lines", records=self)
        if limit_time <= 0:
            cron_limit_time = service.get_cron_real_time_budget() or -1
            limit_time = cron_limit_time if 0 < cron_limit_time < 180 else 180

        _debug.logic(
            "cron_budget_resolved",
            limit_time=limit_time,
            batch_size=batch_size,
            company=company_id,
        )
        if limit_time and not batch_size:
            _logger.warning(
                "_cron_try_auto_reconcile_statement_lines called with "
                "limit_time=%r but batch_size=%r won't limit anything",
                limit_time,
                batch_size,
            )

        run_start = self.env.cr.now().replace(microsecond=0)

        def compute_st_lines_to_reconcile(company_id=None):
            remaining_line_id = None
            limit = batch_size + 1 if batch_size else None
            domain = self._get_domain_auto_reconcile_due(run_start)
            if company_id is not None:
                domain &= Domain(
                    self.env["account.reconcile.model"]._check_company_domain(
                        company_id
                    )
                )
            if self:
                domain &= Domain("id", "in", self.ids)
            st_lines = self.search(
                domain, limit=limit, order="cron_last_check ASC NULLS FIRST, id"
            )
            _logger.info(
                "_cron_try_auto_reconcile_statement_lines found %s statement lines",
                len(st_lines),
            )
            if batch_size and len(st_lines) > batch_size:
                remaining_line_id = st_lines[batch_size].id
                st_lines = st_lines[:batch_size]
            _debug.pipeline(
                "cron_batch_selected",
                automatch=st_lines,
                count=len(st_lines),
                remaining_line_id=remaining_line_id,
            )
            return st_lines, remaining_line_id

        def is_limit_time_exceeded() -> bool:
            if batch_size and limit_time:
                return (
                    fields.Datetime.now().timestamp() - start_time.timestamp()
                    > limit_time
                )
            return False

        can_commit = not modules.module.current_test and not self.env.context.get(
            "import_file", False
        )
        remaining_line_id = None

        start_time = fields.Datetime.now()

        def rollback_and_retire(st_lines, exc):
            _logger.warning(
                "Error while processing statement lines: %s", exc, exc_info=exc
            )
            fresh_snapshot = isinstance(exc, PG_RETRY_EXCEPTIONS) and can_commit
            if fresh_snapshot:
                _logger.warning(
                    "_cron_try_auto_reconcile_statement_lines will rollback the cursor"
                )
                self.env.cr.rollback()
            given_up = st_lines._auto_reconcile_isolating_failures(
                company_id=company_id
            )
            _debug.pipeline(
                "cron_batch_retried_per_line",
                automatch=st_lines,
                error=type(exc).__name__,
                rolled_back=fresh_snapshot,
                given_up=given_up,
            )

        barren_rounds = 0

        while not is_limit_time_exceeded():
            st_lines = self.browse()
            try:
                st_lines, remaining_line_id = compute_st_lines_to_reconcile(
                    company_id=company_id
                )

                if not st_lines:
                    return

                with (
                    _debug.perf(
                        "automatch_cron_batch",
                        cr=self.env.cr,
                        st_lines_count=len(st_lines),
                    ),
                    self.env.cr.savepoint(),
                ):
                    st_lines._try_auto_reconcile_statement_lines(company_id=company_id)
                st_lines.cron_last_check = self.env.cr.now()
                barren_rounds = 0
            except Exception as e:
                rollback_and_retire(st_lines, e)
                if st_lines:
                    barren_rounds = 0
                else:
                    barren_rounds += 1
                    _debug.logic(
                        "cron_barren_round",
                        barren_rounds=barren_rounds,
                        error=type(e).__name__,
                    )
                    if barren_rounds >= MAX_BARREN_CRON_ROUNDS:
                        _logger.error(
                            "_cron_try_auto_reconcile_statement_lines gave up after %s "
                            "rounds that processed no statement line; last error: %s",
                            barren_rounds,
                            e,
                        )
                        return

            if can_commit:
                self.env["ir.cron"]._commit_progress()

        _debug.logic(
            "cron_time_budget_exhausted",
            remaining_line_id=remaining_line_id,
            barren_rounds=barren_rounds,
            rescheduled=bool(remaining_line_id),
        )
        if remaining_line_id:
            _logger.info(
                "_cron_try_auto_reconcile_statement_lines remaining line found (%s), the cron will be triggered again",
                remaining_line_id,
            )
            self.env["ir.cron"]._trigger_ref(
                "account.auto_reconcile_bank_statement_line"
            )

    @api.model
    def _get_domain_auto_reconcile_due(self, run_start) -> Domain:
        retry_days = self.env.registry.settings.get_int(
            self.env, "account.bank_rec_retry_days", AUTO_RECONCILE_RETRY_DAYS
        )
        revisit = Domain("cron_last_check", "<", run_start) & Domain(
            "create_date", ">=", run_start - timedelta(days=retry_days)
        )
        return (
            Domain("is_reconciled", "=", False)
            & (Domain("cron_last_check", "=", False) | revisit)
            & ~self._get_domain_settled_elsewhere()
        )

    def _get_domain_settled_elsewhere(self) -> Domain:
        return Domain.FALSE

    def _auto_reconcile_isolating_failures(self, company_id=None, retire=True):
        given_up = 0
        for st_line in self.exists():
            try:
                with self.env.cr.savepoint():
                    st_line._try_auto_reconcile_statement_lines(company_id=company_id)
            except PG_RETRY_EXCEPTIONS:
                raise
            except Exception as line_exc:
                _logger.warning(
                    "_auto_reconcile_isolating_failures giving up on statement line %s: %s",
                    st_line.id,
                    line_exc,
                    exc_info=True,
                )
                given_up += 1
            if retire:
                st_line.cron_last_check = self.env.cr.now()
        return given_up

    def _update_auto_reconcile_rule(self, rule) -> None:
        matched = self.filtered(
            lambda st_line: st_line.is_reconciled and not st_line.auto_reconcile_rule
        )
        _debug.pipeline("auto_reconcile_rule_recorded", automatch=matched, rule=rule)
        matched.auto_reconcile_rule = rule

    def _get_unmatched_amounts(self) -> tuple:
        self.check_singleton()
        _liquidity_lines, suspense_lines, _other_lines = self._seek_for_lines()
        (
            transaction_amount,
            transaction_currency,
            journal_amount,
            journal_currency,
            company_amount,
            company_currency,
        ) = self._get_accounting_amounts_and_currencies()
        if not self.checked:
            return company_amount, journal_amount, transaction_amount
        if suspense_lines.account_id.reconcile:
            company_unmatched = -sum(suspense_lines.mapped("amount_residual"))
            transaction_unmatched = -sum(
                suspense_lines.mapped("amount_residual_currency")
            )
        else:
            company_unmatched = -sum(suspense_lines.mapped("balance"))
            transaction_unmatched = -sum(suspense_lines.mapped("amount_currency"))
        if journal_currency == company_currency:
            journal_unmatched = company_unmatched
        elif journal_currency == transaction_currency:
            journal_unmatched = transaction_unmatched
        else:
            journal_unmatched = journal_currency.round(
                company_unmatched * journal_amount / company_amount
                if company_amount
                else 0.0
            )
        return company_unmatched, journal_unmatched, transaction_unmatched

    def _settles_residual(
        self,
        currency,
        amount,
        residual,
        discounted,
        discount_date,
        date,
        tolerance,
        limit=0.0,
    ) -> bool:
        if currency.compare_amounts(residual, amount) == 0:
            return True
        if self._is_payment_difference_written_off(currency, amount - residual, limit):
            return True
        if (
            discount_date
            and currency.compare_amounts(discounted, amount) == 0
            and date <= discount_date
        ):
            return True
        return abs(amount - residual) <= tolerance * abs(residual)

    @_debug.perf.timed
    def _invoice_matching_post_process(self, st_line, amls):
        candidate_amls = self.env["account.move.line"]
        tolerance = self._get_payment_tolerance()
        limit = st_line._get_payment_difference_limit()
        company_unmatched, journal_unmatched, transaction_unmatched = (
            st_line._get_unmatched_amounts()
        )
        for aml in amls:
            readings = (
                (
                    aml.company_currency_id == st_line.currency_id,
                    aml.company_currency_id,
                    aml.amount_residual,
                    aml.discount_balance,
                    company_unmatched,
                ),
                (
                    aml.currency_id == st_line.currency_id,
                    aml.currency_id,
                    aml.amount_residual_currency,
                    aml.discount_amount_currency,
                    journal_unmatched,
                ),
                (
                    aml.currency_id == st_line.foreign_currency_id,
                    aml.currency_id,
                    aml.amount_residual_currency,
                    aml.discount_amount_currency,
                    transaction_unmatched,
                ),
            )
            if any(
                applies
                and st_line._settles_residual(
                    currency,
                    amount,
                    residual,
                    discounted,
                    aml.discount_date,
                    st_line.date,
                    tolerance,
                    limit,
                )
                for applies, currency, residual, discounted, amount in readings
            ):
                candidate_amls += aml

        prior_amls = candidate_amls.filtered(
            lambda aml: aml.invoice_date and aml.invoice_date <= st_line.date
        )
        _debug.logic(
            "invoice_matching_within_before",
            automatch=st_line,
            candidate_amls_count=len(candidate_amls),
            amls_count=len(amls),
            tolerance=tolerance,
            prior_amls_count=len(prior_amls),
        )
        if len(candidate_amls) == 1:
            return candidate_amls
        if len(prior_amls) == 1:
            return prior_amls
        return None

    @_debug.perf.timed
    def _handle_reconciliation_matching_amount(
        self, st_move_ids, account_ids, remaining_st_line_ids, match_journal=False
    ):
        processed_st_line_ids = set()
        journal_clause = (
            SQL("AND aml.journal_id = st_line.journal_id") if match_journal else SQL("")
        )
        query = SQL(
            """
                SELECT st_line.id AS st_line_id,
                       ARRAY_AGG(aml.id ORDER BY aml.id ASC) AS all_aml_ids,
                       SUM(aml.amount_residual) AS total_residual
                  FROM account_bank_statement_line st_line
                  JOIN account_move_line aml
                    ON st_line.partner_id = aml.partner_id
                   AND aml.company_id = st_line.company_id
                   AND SIGN(st_line.amount) = SIGN(aml.balance)
                       %s
                 WHERE st_line.partner_id IS NOT NULL
                   AND aml.move_id != ALL(%s)
                   AND aml.reconciled IS NOT TRUE
                   AND aml.account_id = ANY(%s)
                   AND aml.parent_state = %s
                   AND COALESCE(aml.pending_match_amount, 0) = 0
                   AND st_line.id = ANY(%s)
              GROUP BY st_line.id
        """,
            journal_clause,
            list(st_move_ids),
            list(account_ids),
            self._get_matching_parent_state(),
            list(remaining_st_line_ids),
        )
        self.env.cr.execute(query)
        _debug.perf.count("matching_amount_rows_fetched", rows=self.env.cr.rowcount)

        for st_line_id, all_aml_ids, total_residual in self.env.cr.fetchall():
            st_line = self.browse(st_line_id).with_prefetch(self._prefetch_ids)
            unmatched = st_line._get_unmatched_amounts()[0]
            exact = (
                st_line.company_currency_id.compare_amounts(total_residual, unmatched)
                == 0
            )
            _debug.logic(
                "matching",
                automatch=st_line_id,
                journal=match_journal,
                count=len(all_aml_ids or ()),
                residual=total_residual,
                amount=unmatched,
                exact=exact,
            )
            if exact:
                st_line.set_line_bank_statement_line(all_aml_ids)
                _logger.info(
                    "try_auto_reconcile - match amount - st_line: %s set lines %s",
                    st_line.id,
                    all_aml_ids,
                )
            elif all_aml_ids:
                amls = self.env["account.move.line"].browse(all_aml_ids)
                candidate_amls = self._invoice_matching_post_process(st_line, amls)
                if candidate_amls:
                    st_line.set_line_bank_statement_line(candidate_amls.ids)
                    _logger.info(
                        "try_auto_reconcile - _invoice_matching_post_process - st_line: %s set lines %s",
                        st_line.id,
                        candidate_amls.ids,
                    )
            if st_line._get_transaction_currency().is_zero(st_line.amount_residual):
                processed_st_line_ids.add(st_line.id)
        return processed_st_line_ids

    @_debug.perf.timed
    def _flush_before_matching_queries(self) -> None:
        self.env["account.account"].flush_model(["account_type", "active"])
        self.env["account.move"].flush_model(
            [
                "date",
                "invoice_date",
                "amount_total",
                "amount_total_signed",
                "state",
                "move_type",
                "statement_line_id",
            ]
        )
        self.env["account.move.line"].flush_model(
            [
                "ref",
                "move_id",
                "move_name",
                "account_id",
                "partner_id",
                "company_id",
                "balance",
                "parent_state",
                "pending_match_amount",
                "reconciled",
                "company_currency_id",
                "amount_residual",
                "currency_id",
                "amount_residual_currency",
                "discount_date",
                "discount_balance",
                "discount_amount_currency",
            ]
        )
        self.flush_recordset(
            [
                "move_id",
                "partner_id",
                "company_id",
                "currency_id",
                "amount",
                "foreign_currency_id",
                "amount_currency",
                "payment_ref",
            ]
        )
        self.env["account.payment"].flush_model(["move_id", "journal_id", "memo"])

    def _filtered_auto_reconcilable(self):
        return self.filtered(
            lambda st_line: not st_line.is_reconciled
        ) - self.filtered_domain(self._get_domain_settled_elsewhere())

    def _try_auto_reconcile_statement_lines(
        self, company_id=None, detect_partner=True
    ) -> None:
        st_lines = self._filtered_auto_reconcilable()
        if st_lines != self:
            _debug.logic("automatch_lines_left_alone", automatch=self - st_lines)
        if st_lines:
            st_lines._match_by_auto_reconcile_rules(
                company_id=company_id, detect_partner=detect_partner
            )

    @_debug.perf.timed
    def _match_by_auto_reconcile_rules(
        self, company_id=None, detect_partner=True
    ) -> None:
        st_move_ids = self.mapped("move_id").ids
        self.lock_for_update()

        domain = []
        if company_id is not None:
            domain = Domain(
                self.env["account.reconcile.model"]._check_company_domain(company_id)
            )
        reco_models = self.env["account.reconcile.model"].search(domain)

        if detect_partner:
            self._set_partner_from_transaction()
        self._partner_mapping(reco_models)
        self._flush_before_matching_queries()

        account_ids = self._get_matchable_account_ids()
        _debug.pipeline(
            "start_model_account",
            automatch=self,
            reco_models_count=len(reco_models),
            account_ids_count=len(account_ids),
        )

        matched_ids = self._match_end_to_end_uuid(st_move_ids, account_ids)
        self.browse(matched_ids)._update_auto_reconcile_rule("end_to_end")
        remaining_st_line_ids = set(self.ids) - matched_ids
        _debug.pipeline(
            "after_end_end_uuid",
            automatch=self,
            remaining_st_line_ids_count=len(remaining_st_line_ids),
        )
        if not remaining_st_line_ids:
            return

        outstanding_accounts = self._get_outstanding_payment_accounts()
        if outstanding_accounts:
            candidate_ids = set(remaining_st_line_ids)
            remaining_st_line_ids = self._match_outstanding_accounts(
                st_move_ids, outstanding_accounts, remaining_st_line_ids
            )
            self.browse(
                candidate_ids - remaining_st_line_ids
            )._update_auto_reconcile_rule("outstanding")
            _debug.pipeline(
                "after_outstanding_accounts",
                automatch=self,
                outstanding_accounts=outstanding_accounts,
                remaining_st_line_ids_count=len(remaining_st_line_ids),
            )

        account_ids = list(set(account_ids) - set(outstanding_accounts.ids))
        if not (remaining_st_line_ids and account_ids):
            return

        candidate_ids = set(remaining_st_line_ids)
        remaining_st_line_ids = self._match_payment_references(
            st_move_ids, account_ids, remaining_st_line_ids
        )
        self.browse(candidate_ids - remaining_st_line_ids)._update_auto_reconcile_rule(
            "reference"
        )
        _debug.pipeline(
            "after_payment_references",
            automatch=self,
            remaining_st_line_ids_count=len(remaining_st_line_ids),
        )
        if not remaining_st_line_ids:
            return

        matched_ids = self._handle_reconciliation_matching_amount(
            st_move_ids, account_ids, remaining_st_line_ids
        )
        self.browse(matched_ids)._update_auto_reconcile_rule("amount")
        remaining_st_line_ids -= matched_ids
        _debug.pipeline(
            "after_amount_matching",
            automatch=self,
            remaining_st_line_ids_count=len(remaining_st_line_ids),
        )
        if not remaining_st_line_ids:
            return

        matched_ids = self._match_period_charges(remaining_st_line_ids)
        self.browse(matched_ids)._update_auto_reconcile_rule("charges")
        remaining_st_line_ids -= matched_ids
        _debug.pipeline(
            "after_period_charges",
            automatch=self,
            remaining_st_line_ids_count=len(remaining_st_line_ids),
        )
        if not remaining_st_line_ids:
            return

        matched_ids = self._match_amount_alone(account_ids, remaining_st_line_ids)
        self.browse(matched_ids)._update_auto_reconcile_rule("amount_alone")
        remaining_st_line_ids -= matched_ids
        _debug.pipeline(
            "after_amount_alone",
            automatch=self,
            remaining_st_line_ids_count=len(remaining_st_line_ids),
        )
        if not remaining_st_line_ids:
            return

        remaining_st_lines = self.browse(list(remaining_st_line_ids)).with_prefetch(
            self._prefetch_ids
        )
        reco_models._apply_reconcile_models(remaining_st_lines)
        remaining_st_lines.filtered("is_reconciled")._update_auto_reconcile_rule(
            "model"
        )
        _logger.info(
            "try_auto_reconcile - apply reco models - st_lines: %s - reco models %s",
            remaining_st_lines.ids,
            reco_models.ids,
        )


class AccountMove(models.Model):
    _inherit = "account.move"

    def _post_entries(self):
        posted = super()._post_entries()
        posted._trigger_statement_line_auto_reconcile()
        return posted

    def _trigger_statement_line_auto_reconcile(self) -> None:
        documents = self.filtered(
            lambda move: (
                not move.statement_line_id
                and any(
                    line.account_type in {"asset_receivable", "liability_payable"}
                    and not line.reconciled
                    for line in move.line_ids
                )
            )
        )
        _debug.logic(
            "auto_reconcile_wake_up",
            posted=len(self),
            documents=len(documents),
        )
        if documents:
            self.env["ir.cron"]._trigger_ref(
                "account.auto_reconcile_bank_statement_line",
                coalesce=AUTO_RECONCILE_WAKE_UP_MINUTES,
            )

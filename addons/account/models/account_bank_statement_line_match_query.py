import logging
import re
from collections import defaultdict
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import SUPERUSER_ID, api, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL

_logger = logging.getLogger(__name__)

_debug = DebugLog(__name__)

AMOUNT_ALONE_RARE_DAYS = 365
AMOUNT_ALONE_NEAR_DAYS = 7
CHARGES_BILL_BEFORE_DAYS = 10
CHARGES_BILL_AFTER_DAYS = 15


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    def _get_matchable_account_ids(self):
        companies = self.company_id
        accounts = self.env["account.account"].search(
            [
                *self.env["account.account"]._get_domain_company_compatible(companies),
                ("reconcile", "=", True),
                ("account_type", "not in", ("asset_cash", "liability_credit_card")),
            ]
        )
        accounts -= (
            self.env["account.journal"]
            .search(
                [
                    *self.env["account.journal"]._get_domain_company_compatible(
                        companies
                    ),
                    ("type", "in", ["bank", "cash", "credit"]),
                ]
            )
            .suspense_account_id
        )
        return (accounts - self.journal_id.default_account_id).ids

    @api.model
    def _same_company_hierarchy_sql(self, left="left_company", right="right_company"):
        left, right = SQL.identifier(left), SQL.identifier(right)
        return SQL(
            "(%(left)s.parent_path LIKE %(right)s.parent_path || '%%'"
            " OR %(right)s.parent_path LIKE %(left)s.parent_path || '%%')",
            left=left,
            right=right,
        )

    @_debug.perf.timed
    def _match_outstanding_accounts(
        self, st_move_ids, outstanding_accounts, remaining_st_line_ids
    ):
        processed_st_line_ids = set()
        for (st_line_id, _matching_word), (
            aml_id,
            _aml_amount_residual,
        ) in self._filter_reference_matches(
            self._match_accounts_query(
                st_move_ids, outstanding_accounts.ids, remaining_st_line_ids, True
            )
        ).items():
            st_line = self.browse(st_line_id).with_prefetch(self._prefetch_ids)
            st_line.with_context(
                skip_account_review_check=True
            ).set_line_bank_statement_line(aml_id)
            _logger.info(
                "try_auto_reconcile - outstanding - st_line: %s set line %s",
                st_line.id,
                aml_id,
            )
            if st_line._get_transaction_currency().is_zero(st_line.amount_residual):
                processed_st_line_ids.add(st_line.id)

        remaining_st_line_ids -= processed_st_line_ids
        _debug.pipeline(
            "outstanding_references_matched",
            automatch=self,
            outstanding_accounts=outstanding_accounts,
            matched=len(processed_st_line_ids),
            remaining=len(remaining_st_line_ids),
            amount_fallback=bool(remaining_st_line_ids),
        )
        if remaining_st_line_ids:
            remaining_st_line_ids -= self._handle_reconciliation_matching_amount(
                st_move_ids,
                outstanding_accounts.ids,
                remaining_st_line_ids,
                match_journal=True,
            )
        return remaining_st_line_ids

    @_debug.perf.timed
    def _match_payment_references(
        self, st_move_ids, account_ids, remaining_st_line_ids
    ):
        processed_st_line_ids = set()
        to_process = self._filter_reference_matches(
            self._match_accounts_query(st_move_ids, account_ids, remaining_st_line_ids)
        )

        ref_amls_left = {}
        for (st_line_id, _matching_word), (
            aml_id,
            aml_amount_residual,
        ) in to_process.items():
            st_line = self.browse(st_line_id).with_prefetch(self._prefetch_ids)
            left = ref_amls_left.get(st_line_id)
            if left is None:
                ref_amls_left[st_line_id] = abs(
                    st_line._get_unmatched_amounts()[0]
                ) - abs(aml_amount_residual)
            elif st_line.company_currency_id.compare_amounts(left, 0) <= 0:
                _debug.logic(
                    "payment_ref_amount_exhausted_aml",
                    automatch=st_line_id,
                    aml_id=aml_id,
                )
                continue
            else:
                ref_amls_left[st_line_id] = left - abs(aml_amount_residual)
            st_line.with_user(SUPERUSER_ID).set_line_bank_statement_line(aml_id)
            _logger.info(
                "try_auto_reconcile - payment ref - st_line: %s set line %s",
                st_line.id,
                aml_id,
            )
            if st_line._get_transaction_currency().is_zero(st_line.amount_residual):
                processed_st_line_ids.add(st_line.id)
        return remaining_st_line_ids - processed_st_line_ids

    @_debug.perf.timed
    def _match_amount_alone(self, account_ids, remaining_st_line_ids):
        processed_st_line_ids = set()
        st_lines = (
            self.browse(remaining_st_line_ids)
            .with_prefetch(self._prefetch_ids)
            .filtered(
                lambda st_line: (
                    not st_line.partner_id
                    and st_line.currency_id.compare_amounts(st_line.amount, 0) < 0
                    and not st_line.foreign_currency_id
                    and st_line.currency_id == st_line.company_currency_id
                )
            )
        )
        payable_ids = (
            self.env["account.account"]
            .browse(account_ids)
            .filtered(lambda account: account.account_type == "liability_payable")
            .ids
        )
        if not (st_lines and payable_ids):
            return processed_st_line_ids
        self.env.cr.execute(
            SQL(
                """
                WITH bills AS MATERIALIZED (
                    SELECT aml.id,
                           aml.company_id,
                           aml.balance,
                           move.id AS move_id,
                           aml.reconciled IS NOT TRUE
                           AND aml.amount_residual = aml.balance AS is_open,
                           COALESCE(move.invoice_date, move.date) AS date
                      FROM account_move_line aml
                      JOIN account_move move ON move.id = aml.move_id
                      JOIN res_company company ON company.id = aml.company_id
                     WHERE aml.account_id = ANY(%(payable_ids)s)
                       AND aml.balance = ANY(%(amounts)s::numeric[])
                       AND aml.parent_state = %(parent_state)s
                       AND COALESCE(aml.pending_match_amount, 0) = 0
                       AND aml.currency_id = company.currency_id
                       AND move.statement_line_id IS NULL
                ),
                -- a bill due in instalments carries its total on no line
                totals AS MATERIALIZED (
                    SELECT move.id,
                           move.company_id,
                           move.amount_total_signed AS amount,
                           COALESCE(move.invoice_date, move.date) AS date
                      FROM account_move move
                     WHERE move.move_type IN ('in_invoice', 'in_receipt')
                       AND move.state IN ('draft', 'posted')
                       AND move.company_id = ANY(%(company_ids)s)
                       AND move.amount_total_signed = ANY(%(amounts)s::numeric[])
                )
                SELECT st_line.id AS st_line_id,
                       MIN(bills.id) AS aml_id
                  FROM account_bank_statement_line st_line
                  JOIN account_move st_move ON st_move.id = st_line.move_id
                  JOIN bills
                    ON bills.company_id = st_line.company_id
                   AND bills.balance = st_line.amount
                   AND bills.date BETWEEN st_move.date - %(rare_days)s
                                      AND st_move.date + %(rare_days)s
                 WHERE st_line.id = ANY(%(st_line_ids)s)
                   AND NOT EXISTS (
                           SELECT 1
                             FROM totals
                            WHERE totals.company_id = st_line.company_id
                              AND totals.amount = st_line.amount
                              AND totals.id != bills.move_id
                              AND totals.date BETWEEN st_move.date - %(rare_days)s
                                                  AND st_move.date + %(rare_days)s
                       )
                   -- a transfer the bank sent back has paid nothing
                   AND NOT EXISTS (
                           SELECT 1
                             FROM account_bank_statement_line returned
                             JOIN account_move returned_move
                               ON returned_move.id = returned.move_id
                            WHERE returned.journal_id = st_line.journal_id
                              AND returned.amount = -st_line.amount
                              AND returned_move.date BETWEEN st_move.date
                                                         AND st_move.date + %(near_days)s
                       )
              GROUP BY st_line.id
                HAVING COUNT(*) = 1
                   AND BOOL_AND(
                           bills.is_open
                       AND bills.date BETWEEN st_move.date - %(near_days)s
                                          AND st_move.date + %(near_days)s
                       )
                """,
                st_line_ids=st_lines.ids,
                amounts=list(set(st_lines.mapped("amount"))),
                company_ids=st_lines.company_id.ids,
                payable_ids=payable_ids,
                rare_days=AMOUNT_ALONE_RARE_DAYS,
                near_days=AMOUNT_ALONE_NEAR_DAYS,
                parent_state=self._get_matching_parent_state(),
            )
        )
        _debug.perf.count("amount_alone_rows_fetched", rows=self.env.cr.rowcount)
        for st_line_id, aml_id in self.env.cr.fetchall():
            st_line = self.browse(st_line_id).with_prefetch(self._prefetch_ids)
            st_line.with_user(SUPERUSER_ID).set_line_bank_statement_line(aml_id)
            if not st_line._get_transaction_currency().is_zero(st_line.amount_residual):
                continue
            st_line.move_id.checked = False
            processed_st_line_ids.add(st_line.id)
            _logger.info(
                "try_auto_reconcile - amount alone - st_line: %s set line %s",
                st_line.id,
                aml_id,
            )
        return processed_st_line_ids

    def _match_period_charges(self, remaining_st_line_ids):
        charged = (
            self.browse(remaining_st_line_ids)
            .with_prefetch(self._prefetch_ids)
            .filtered(
                lambda st_line: (
                    st_line.journal_id.bank_charges_partner_id
                    and st_line.journal_id.bank_charges_pattern
                    and st_line.amount < 0
                    and not st_line.foreign_currency_id
                    and re.search(
                        st_line.journal_id.bank_charges_pattern,
                        st_line.payment_ref or "",
                    )
                )
            )
        )
        periods = {
            (st_line.journal_id, st_line.date.replace(day=1)) for st_line in charged
        }
        if not periods:
            return set()
        journals = self.env["account.journal"].union(*(j for j, _m in periods))
        first = min(month for _j, month in periods)
        last = max(month for _j, month in periods) + relativedelta(months=1, days=-1)
        open_lines = self.search(
            Domain("journal_id", "in", journals.ids)
            & Domain("state", "=", "posted")
            & Domain("is_reconciled", "=", False)
            & Domain("amount", "<", 0)
            & Domain("date", ">=", first)
            & Domain("date", "<=", last)
            & ~self._get_domain_settled_elsewhere(),
            order="id",
        )
        lines_by_period = defaultdict(self.browse)
        for st_line in open_lines:
            journal = st_line.journal_id
            if re.search(journal.bank_charges_pattern, st_line.payment_ref or ""):
                lines_by_period[journal, st_line.date.replace(day=1)] |= st_line
        payables_by_journal = self._get_charges_payables(journals, first, last)
        settled_ids = set()
        for journal, month in periods:
            month_lines = lines_by_period[journal, month]
            bill_lines = self._pick_charges_bill(
                journal,
                payables_by_journal[journal],
                month + relativedelta(months=1, days=-1),
                -sum(st_line._get_unmatched_amounts()[0] for st_line in month_lines),
            )
            if not bill_lines:
                continue
            for st_line in month_lines:
                st_line.with_user(SUPERUSER_ID).set_line_bank_statement_line(
                    bill_lines.ids
                )
            settled = month_lines.filtered("is_reconciled")
            settled_ids |= set(settled.ids)
            _logger.info(
                "try_auto_reconcile - period charges - journal %s %s: %s on %s",
                journal.id,
                month,
                settled.ids,
                bill_lines.move_id.ids,
            )
        return settled_ids

    def _get_charges_payables(self, journals, first, last):
        payables = self.env["account.move.line"].search(
            [
                ("company_id", "in", journals.company_id.ids),
                (
                    "partner_id",
                    "child_of",
                    journals.bank_charges_partner_id.commercial_partner_id.ids,
                ),
                ("account_id.account_type", "=", "liability_payable"),
                ("parent_state", "=", "posted"),
                ("reconciled", "=", False),
                ("move_id.move_type", "in", ("in_invoice", "in_receipt")),
                (
                    "move_id.invoice_date",
                    ">=",
                    first - timedelta(days=CHARGES_BILL_BEFORE_DAYS),
                ),
                (
                    "move_id.invoice_date",
                    "<=",
                    last + timedelta(days=CHARGES_BILL_AFTER_DAYS),
                ),
            ]
        )
        return {
            journal: payables.filtered(
                lambda line, journal=journal: (
                    line.company_id == journal.company_id
                    and line.partner_id.commercial_partner_id
                    == journal.bank_charges_partner_id.commercial_partner_id
                )
            )
            for journal in journals
        }

    def _pick_charges_bill(self, journal, payables, month_end, total):
        currency = journal.company_id.currency_id
        if not currency.compare_amounts(total, 0) > 0:
            return self.env["account.move.line"]
        earliest = month_end - timedelta(days=CHARGES_BILL_BEFORE_DAYS)
        latest = month_end + timedelta(days=CHARGES_BILL_AFTER_DAYS)
        bills = [
            lines
            for move, lines in payables.grouped("move_id").items()
            if earliest <= move.invoice_date <= latest
            and all(
                currency.compare_amounts(line.amount_residual, line.balance) == 0
                for line in lines
            )
            and currency.compare_amounts(-sum(lines.mapped("amount_residual")), total)
            == 0
        ]
        return bills[0] if len(bills) == 1 else self.env["account.move.line"]

    def _filter_reference_matches(self, matched_rows):
        st_lines_refs = defaultdict(list)
        to_process = {}
        for st_line_id, aml_id, aml_amount_residual, matching_word in matched_rows:
            st_line = self.browse(st_line_id).with_prefetch(self._prefetch_ids)
            if not self._is_properly_surrounded(st_line.payment_ref, matching_word):
                continue
            to_process[st_line_id, matching_word] = (aml_id, aml_amount_residual)
            for word in st_lines_refs[st_line_id]:
                if word in matching_word or matching_word in word:
                    to_process.pop((st_line_id, matching_word), None)
                    to_process.pop((st_line_id, word), None)
            st_lines_refs[st_line_id].append(matching_word)
        _debug.logic(
            "automatch_references_after_surrounding",
            matched_rows_count=len(matched_rows),
            to_process_count=len(to_process),
        )
        return to_process

    def _get_outstanding_payment_accounts(self):
        return (
            self.env["account.payment.channel"]
            .search(
                self.env["account.payment.channel"]._get_domain_company_compatible(
                    self.company_id
                )
            )
            .payment_account_id
        ) - self.journal_id.default_account_id

    @_debug.perf.timed
    def _partner_mapping(self, reco_models) -> None:
        reco_model_model = self.env["account.reconcile.model"]
        reco_model_model.flush_model()
        self.env["account.move"].flush_model(["narration"])
        self.flush_recordset(
            [
                "journal_id",
                "amount",
                "transaction_details",
                "payment_ref",
                "partner_id",
                "company_id",
            ]
        )
        self.env.cr.execute(
            SQL(
                """
                WITH %(relations)s
                SELECT st_line.id AS st_line_id, reco_model.mapped_partner_id
                FROM account_bank_statement_line st_line
                LEFT JOIN LATERAL (
                    SELECT
                        reco_model.id,
                        reco_model.mapped_partner_id
                    FROM account_reconcile_model reco_model
                    %(joins)s
                    WHERE
                        %(match)s
                        AND reco_model.mapped_partner_id IS NOT NULL
                        AND reco_model.id = ANY(%(reco_models)s)
                    ORDER BY reco_model.created_automatically ASC NULLS FIRST, reco_model.sequence ASC, reco_model.id ASC
                    LIMIT 1
                ) AS reco_model ON TRUE
                WHERE
                    st_line.id = ANY(%(statement_lines)s)
                    AND st_line.partner_id IS NULL
                    AND reco_model.mapped_partner_id IS NOT NULL
                """,
                relations=reco_model_model._get_match_relations_cte(),
                joins=reco_model_model._get_match_joins_sql(),
                match=reco_model_model._get_match_sql(),
                reco_models=reco_models.ids,
                statement_lines=list(self.ids),
            )
        )

        mapped = defaultdict(list)
        for st_line_id, mapped_partner_id in self.env.cr.fetchall():
            mapped[mapped_partner_id].append(st_line_id)
        if _debug.pipeline.enabled:
            _debug.pipeline(
                "partners_mapped_by_models",
                automatch=self,
                reco_models=len(reco_models),
                partners=len(mapped),
                st_lines=sum(len(ids) for ids in mapped.values()),
            )
        for mapped_partner_id, st_line_ids in mapped.items():
            self.browse(st_line_ids).write(
                {"partner_id": mapped_partner_id, "is_partner_manual": False}
            )
            _logger.info(
                "try_auto_reconcile - partner mapping done for st_lines: %s and partner %s",
                st_line_ids,
                mapped_partner_id,
            )

    def _match_end_to_end_uuid(self, st_move_ids, account_ids) -> set:
        return set()

    @_debug.perf.timed
    def _match_accounts_query(
        self, st_move_ids, account_ids, remaining_st_line_ids, outstanding_account=False
    ):
        if outstanding_account:
            extra_condition = SQL("aml.journal_id = st_line.journal_id")
        else:
            extra_condition = SQL(
                "aml.currency_id = COALESCE(st_line.foreign_currency_id, st_line.currency_id)"
            )

        query = SQL(
            """
            SELECT
                st_line.id,
                ARRAY_AGG(DISTINCT word_aml.id) aml_ids,
                SUM(word_aml.amount_residual),
                word_aml.word matching_word
            FROM account_bank_statement_line st_line
            JOIN LATERAL (
                SELECT DISTINCT aml.id, word, aml.amount_residual
                FROM account_move_line aml
                LEFT JOIN res_company aml_company ON aml_company.id = aml.company_id
                LEFT JOIN res_company st_line_company ON st_line_company.id = st_line.company_id
                LEFT JOIN account_move move ON (move.id = aml.move_id AND move.payment_reference != move.name),
                LATERAL regexp_split_to_table(
                    COALESCE(aml.ref, '') || ' - ' ||
                    COALESCE(aml.move_name, '') || ' - ' ||
                    COALESCE(move.payment_reference, ''), ' - '
                ) AS word
                WHERE (st_line.partner_id IS NULL OR st_line.partner_id = aml.partner_id)
                    AND aml.move_id != ALL(%(st_move_ids)s)
                    AND aml.reconciled IS NOT TRUE
                    AND aml.account_id = ANY(%(account_ids)s)
                    AND %(aml_and_st_line_related)s
                    AND ((st_line.amount > 0 AND aml.balance > 0) OR (st_line.amount < 0 AND aml.balance < 0))
                    AND aml.parent_state = %(parent_state)s
                    AND COALESCE(aml.pending_match_amount, 0) = 0
                    AND st_line.id = ANY(%(st_line_ids)s)
                    AND (
                        length(word) > 5 AND strpos(lower(st_line.payment_ref), lower(word)) > 0
                    )
                    AND %(extra_condition)s
            ) word_aml ON TRUE
            GROUP BY st_line.id, matching_word
            HAVING COUNT(DISTINCT word_aml.id) = 1
            ORDER BY st_line.id, matching_word
            """,
            st_move_ids=list(st_move_ids),
            account_ids=list(account_ids),
            st_line_ids=list(remaining_st_line_ids),
            aml_and_st_line_related=self._same_company_hierarchy_sql(
                "aml_company", "st_line_company"
            ),
            extra_condition=extra_condition,
            parent_state=self._get_matching_parent_state(),
        )
        _debug.pipeline(
            "reference_match_query_built",
            automatch=self,
            outstanding=outstanding_account,
            st_lines=len(remaining_st_line_ids),
            accounts=len(account_ids),
        )
        self.env.cr.execute(query)
        _debug.perf.count("reference_match_rows_fetched", rows=self.env.cr.rowcount)
        return self.env.cr.fetchall()

    @api.model
    def _is_properly_surrounded(self, text, substring) -> bool:
        pattern = rf"(?<![^\W_]){re.escape(substring)}(?![^\W_])"
        return re.search(pattern, text, re.IGNORECASE) is not None

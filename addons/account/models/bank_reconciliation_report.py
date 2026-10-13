import logging
from datetime import date

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL

_logger = logging.getLogger(__name__)

_debug = DebugLog(__name__)


class AccountBankReconciliationReportHandler(models.AbstractModel):
    _name = "account.bank.reconciliation.report.handler"
    _inherit = ["report.formula.custom.handler"]
    _description = "Bank Reconciliation Report Custom Handler"

    @_debug.perf.timed
    def _custom_options_initializer(self, report, options, previous_options):
        super()._custom_options_initializer(
            report, options, previous_options=previous_options
        )

        options["ignore_totals_below_sections"] = True
        options["no_xlsx_currency_code_columns"] = True
        if (
            "active_id" in self.env.context
            and self.env.context.get("active_model") == "account.journal"
        ):
            options["bank_reconciliation_report_journal_id"] = self.env.context[
                "active_id"
            ]
        elif "bank_reconciliation_report_journal_id" in previous_options:
            options["bank_reconciliation_report_journal_id"] = previous_options[
                "bank_reconciliation_report_journal_id"
            ]
        else:
            options["bank_reconciliation_report_journal_id"] = (
                self._get_default_bank_journal(report, options).id
            )

        is_multi_currency = self.env.user.has_group(
            "base.group_multi_currency"
        ) and self.env.user.has_group("base.group_no_one")
        if _debug.logic.enabled:
            _debug.logic(
                "bank_reco_journal_resolved",
                report=report,
                journal=options["bank_reconciliation_report_journal_id"],
                source="context"
                if "active_id" in self.env.context
                and self.env.context.get("active_model") == "account.journal"
                else "previous_options"
                if "bank_reconciliation_report_journal_id" in previous_options
                else "first_bank_journal",
                multi_currency=is_multi_currency,
            )
        if not is_multi_currency:
            options["columns"] = [
                column
                for column in options["columns"]
                if column["expression_label"] not in ("amount_currency", "currency")
            ]

    def _get_default_bank_journal(self, report, options):
        company_ids = report.get_report_company_ids(options)
        bank_domain = Domain("type", "=", "bank")
        journal = self.env["account.journal"]
        if self.env.company.id in company_ids:
            journal = journal.search(
                bank_domain & Domain("company_id", "=", self.env.company.id), limit=1
            )
        _debug.logic(
            "bank_reco_default_journal",
            report=report,
            journal=journal,
            from_active_company=bool(journal),
        )
        return journal or journal.search(
            bank_domain & Domain("company_id", "in", company_ids), limit=1
        )

    def _get_bank_journal_and_currencies(self, options) -> tuple:
        journal = self.env["account.journal"].browse(
            options.get("bank_reconciliation_report_journal_id")
        )
        company_currency = journal.company_id.currency_id
        journal_currency = journal.currency_id or company_currency
        return journal, journal_currency, company_currency

    @_debug.perf.timed
    def _prepare_custom_engine_result(
        self,
        date=None,
        label=None,
        amount_currency=None,
        amount_currency_currency_id=None,
        currency=None,
        amount=0,
        amount_currency_id=None,
        has_sublines=False,
    ) -> dict:
        return {
            "date": date,
            "label": label,
            "amount_currency": amount_currency,
            "amount_currency_currency_id": amount_currency_currency_id,
            "currency": currency,
            "amount": amount,
            "amount_currency_id": amount_currency_id,
            "has_sublines": has_sublines,
        }

    @_debug.perf.timed
    def _report_custom_engine_forced_currency_amount(
        self,
        expressions,
        options,
        date_scope,
        current_groupby,
        next_groupby,
        offset=0,
        limit=None,
        warnings=None,
    ):
        _journal, journal_currency, _company_currency = (
            self._get_bank_journal_and_currencies(options)
        )
        return self._prepare_custom_engine_result(
            amount_currency_id=journal_currency.id
        )

    @_debug.perf.timed
    def _report_custom_engine_unreconciled_last_statement_receipts(
        self,
        expressions,
        options,
        date_scope,
        current_groupby,
        next_groupby,
        offset=0,
        limit=None,
        warnings=None,
    ):
        return self._bank_reconciliation_report_custom_engine_common(
            options, "receipts", current_groupby, True, offset=offset, limit=limit
        )

    @_debug.perf.timed
    def _report_custom_engine_unreconciled_last_statement_payments(
        self,
        expressions,
        options,
        date_scope,
        current_groupby,
        next_groupby,
        offset=0,
        limit=None,
        warnings=None,
    ):
        return self._bank_reconciliation_report_custom_engine_common(
            options, "payments", current_groupby, True, offset=offset, limit=limit
        )

    @_debug.perf.timed
    def _report_custom_engine_unreconciled_receipts(
        self,
        expressions,
        options,
        date_scope,
        current_groupby,
        next_groupby,
        offset=0,
        limit=None,
        warnings=None,
    ):
        return self._bank_reconciliation_report_custom_engine_common(
            options, "receipts", current_groupby, False, offset=offset, limit=limit
        )

    @_debug.perf.timed
    def _report_custom_engine_unreconciled_payments(
        self,
        expressions,
        options,
        date_scope,
        current_groupby,
        next_groupby,
        offset=0,
        limit=None,
        warnings=None,
    ):
        return self._bank_reconciliation_report_custom_engine_common(
            options, "payments", current_groupby, False, offset=offset, limit=limit
        )

    @_debug.perf.timed
    def _report_custom_engine_outstanding_receipts(
        self,
        expressions,
        options,
        date_scope,
        current_groupby,
        next_groupby,
        offset=0,
        limit=None,
        warnings=None,
    ):
        return self._bank_reconciliation_report_custom_engine_outstanding_common(
            options, "receipts", current_groupby, offset=offset, limit=limit
        )

    @_debug.perf.timed
    def _report_custom_engine_outstanding_payments(
        self,
        expressions,
        options,
        date_scope,
        current_groupby,
        next_groupby,
        offset=0,
        limit=None,
        warnings=None,
    ):
        return self._bank_reconciliation_report_custom_engine_outstanding_common(
            options, "payments", current_groupby, offset=offset, limit=limit
        )

    @_debug.perf.timed
    def _report_custom_engine_misc_operations(
        self,
        expressions,
        options,
        date_scope,
        current_groupby,
        next_groupby,
        offset=0,
        limit=None,
        warnings=None,
    ):
        report = self.env["report.formula"].browse(options["report_id"])
        report._check_groupby_fields([current_groupby] if current_groupby else [])

        journal, journal_currency, _company_currency = (
            self._get_bank_journal_and_currencies(options)
        )
        exchange_journal = (
            journal.company_id.account_config_id.currency_exchange_journal_id
        )

        bank_miscellaneous_domain = self._get_domain_bank_miscellaneous_move_lines(
            options, journal
        )
        _debug.logic(
            "misc_operations_scope",
            report=report,
            journal=journal,
            skipped=bank_miscellaneous_domain is None,
        )
        if bank_miscellaneous_domain is None:
            return (
                []
                if current_groupby
                else self._prepare_custom_engine_result(
                    amount_currency_id=journal_currency.id
                )
            )
        bank_miscellaneous_domain = Domain.AND(
            [bank_miscellaneous_domain, [("journal_id", "!=", exchange_journal.id)]]
        )

        base_query = report._get_report_query(
            options, "strict_range", domain=bank_miscellaneous_domain
        )

        groupby_field_sql = (
            self.env["account.move.line"]._field_to_sql(
                "account_move_line", current_groupby, base_query
            )
            if current_groupby
            else None
        )
        query_sql = SQL(
            """
            SELECT
                %(select_from_groupby)s,
                COALESCE(SUM(COALESCE(NULLIF(account_move_line.amount_currency, 0), account_move_line.balance)), 0)
            FROM %(table_references)s
            WHERE %(search_condition)s
            %(groupby_sql)s
            """,
            select_from_groupby=groupby_field_sql,
            table_references=base_query.from_clause,
            search_condition=base_query.where_clause,
            groupby_sql=SQL(
                "GROUP BY %s ORDER BY %s %s",
                groupby_field_sql,
                groupby_field_sql,
                report._get_engine_query_tail(offset, limit),
            )
            if groupby_field_sql
            else SQL(),
        )

        self.env.cr.execute(query_sql)
        query_res_lines = self.env.cr.fetchall()
        _debug.pipeline(
            "misc_operations_fetched",
            report=report,
            journal=journal,
            exchange_journal=exchange_journal,
            groupby=current_groupby,
            rows=len(query_res_lines),
        )

        if not current_groupby:
            return self._prepare_custom_engine_result(
                amount=query_res_lines[-1][1], amount_currency_id=journal_currency.id
            )
        else:
            return [
                (
                    grouping_key,
                    self._prepare_custom_engine_result(
                        amount=amount, amount_currency_id=journal_currency.id
                    ),
                )
                for grouping_key, amount in query_res_lines
            ]

    @_debug.perf.timed
    def _report_custom_engine_last_statement_balance_amount(
        self,
        expressions,
        options,
        date_scope,
        current_groupby,
        next_groupby,
        offset=0,
        limit=None,
        warnings=None,
    ):
        if current_groupby:
            raise UserError(
                self.env._(
                    "Custom engine _report_custom_engine_last_statement_balance_amount does not support groupby"
                )
            )

        journal, journal_currency, _company_currency = (
            self._get_bank_journal_and_currencies(options)
        )
        last_statement = self._get_last_bank_statement(journal, options)

        return self._prepare_custom_engine_result(
            amount=last_statement.balance_end_real,
            amount_currency_id=journal_currency.id,
        )

    @_debug.perf.timed
    def _report_custom_engine_transaction_without_statement_amount(
        self,
        expressions,
        options,
        date_scope,
        current_groupby,
        next_groupby,
        offset=0,
        limit=None,
        warnings=None,
    ):
        return self._bank_reconciliation_report_custom_engine_common(
            options,
            "all",
            current_groupby,
            False,
            unreconciled=False,
            offset=offset,
            limit=limit,
        )

    @_debug.perf.timed
    def _bank_reconciliation_report_custom_engine_common(
        self,
        options,
        internal_type,
        current_groupby,
        from_last_statement,
        unreconciled=True,
        offset=0,
        limit=None,
    ):
        journal, journal_currency, company_currency = (
            self._get_bank_journal_and_currencies(options)
        )
        _debug.logic(
            "statement_lines_engine_mode",
            report=options.get("report_id"),
            journal=journal,
            internal_type=internal_type,
            groupby=current_groupby,
            from_last_statement=from_last_statement,
            unreconciled=unreconciled,
            skipped=not journal,
        )
        if not journal:
            return self._prepare_custom_engine_result()

        report = self.env["report.formula"].browse(options["report_id"])
        report._check_groupby_fields([current_groupby] if current_groupby else [])

        def get_amount(res):
            if unreconciled:
                return self._get_statement_line_open_amount(
                    res, journal_currency, company_currency
                )
            return res["amount"]

        def prepare_result_dict(query_res_lines):
            if current_groupby == "id":
                res = query_res_lines[0]
                foreign_currency = self.env["res.currency"].browse(
                    res["foreign_currency_id"]
                )
                return self._prepare_custom_engine_result(
                    date=res["date"] or None,
                    label=res["payment_ref"] or res["ref"] or "/",
                    amount_currency=(
                        -res["amount_residual"]
                        if unreconciled
                        else res["amount_currency"]
                    )
                    if res["foreign_currency_id"]
                    else None,
                    amount_currency_currency_id=foreign_currency.id
                    if res["foreign_currency_id"]
                    else None,
                    currency=foreign_currency.display_name
                    if res["foreign_currency_id"]
                    else None,
                    amount=get_amount(res)
                    if res["amount_residual"] or not unreconciled
                    else None,
                    amount_currency_id=journal_currency.id,
                    has_sublines=True,
                )
            else:
                amount = sum(get_amount(res) for res in query_res_lines)
                return self._prepare_custom_engine_result(
                    amount=journal_currency.round(amount),
                    amount_currency_id=journal_currency.id,
                    has_sublines=bool(len(query_res_lines)),
                )

        query = report._get_report_query(
            options,
            "strict_range",
            domain=[
                ("journal_id", "=", journal.id),
                (
                    "account_id",
                    "=",
                    journal.default_account_id.id,
                ),
            ],
        )

        if from_last_statement:
            last_st_line_query = self.env["account.bank.statement.line"]._search(
                self._get_domain_last_bank_statement_line(journal, options),
                order="date desc, id desc",
                limit=1,
            )
            last_statement_id_condition = SQL(
                "st_line.statement_id = %s",
                last_st_line_query.subselect("statement_id"),
            )
        else:
            last_statement_id_condition = SQL("st_line.statement_id IS NULL")

        if internal_type == "receipts":
            st_line_amount_condition = SQL("AND st_line.amount > 0")
        elif internal_type == "payments":
            st_line_amount_condition = SQL("AND st_line.amount < 0")
        else:
            st_line_amount_condition = SQL("")

        groupby_field_sql = (
            self.env["account.move.line"]._field_to_sql(
                "account_move_line", current_groupby, query
            )
            if current_groupby
            else SQL("NULL")
        )
        query = SQL(
            """
           SELECT %(select_from_groupby)s,
                  st_line.id,
                  move.name,
                  move.ref,
                  move.date,
                  st_line.payment_ref,
                  st_line.amount,
                  st_line.amount_residual,
                  st_line.amount_currency,
                  st_line.foreign_currency_id,
                  move.checked,
                  (
                      SELECT SUM(
                                 CASE WHEN suspense_account.reconcile
                                      THEN suspense.amount_residual
                                      ELSE suspense.balance
                                 END
                             )
                        FROM account_move_line suspense
                        JOIN account_account suspense_account
                          ON suspense_account.id = suspense.account_id
                       WHERE suspense.move_id = st_line.move_id
                         AND suspense.payment_role = 'suspense'
                  ) AS suspense_open_balance
             FROM %(table_references)s
             JOIN account_bank_statement_line st_line ON st_line.move_id = account_move_line.move_id
             JOIN account_move move ON move.id = st_line.move_id
            WHERE %(search_condition)s
                  %(is_unreconciled)s
                  %(st_line_amount_condition)s
              AND %(last_statement_id_condition)s
         GROUP BY %(group_by)s,
                  st_line.id,
                  move.id
            """,
            select_from_groupby=SQL("%s AS grouping_key", groupby_field_sql),
            table_references=query.from_clause,
            search_condition=query.where_clause,
            is_unreconciled=SQL("AND st_line.is_reconciled IS NOT TRUE")
            if unreconciled
            else SQL(""),
            st_line_amount_condition=st_line_amount_condition,
            last_statement_id_condition=last_statement_id_condition,
            group_by=groupby_field_sql if current_groupby else SQL("st_line.id"),
        )

        self.env.cr.execute(query)
        query_res_lines = self.env.cr.dictfetchall()
        _debug.pipeline(
            "statement_lines_fetched",
            report=report,
            internal_type=internal_type,
            groupby=current_groupby,
            rows=len(query_res_lines),
        )

        return self._get_grouped_result(
            query_res_lines, current_groupby, prepare_result_dict, offset, limit
        )

    @_debug.perf.timed
    def _bank_reconciliation_report_custom_engine_outstanding_common(
        self, options, internal_type, current_groupby, offset=0, limit=None
    ):
        journal, journal_currency, company_currency = (
            self._get_bank_journal_and_currencies(options)
        )
        _debug.logic(
            "outstanding_engine_mode",
            report=options.get("report_id"),
            journal=journal,
            internal_type=internal_type,
            groupby=current_groupby,
            skipped=not journal,
        )
        if not journal:
            return self._prepare_custom_engine_result()

        report = self.env["report.formula"].browse(options["report_id"])
        report._check_groupby_fields([current_groupby] if current_groupby else [])

        def prepare_result_dict(query_res_lines):
            if current_groupby == "id":
                res = query_res_lines[0]
                convert = not (
                    journal_currency and res["currency_id"] == journal_currency.id
                )
                amount_currency = res["amount_residual_currency"]
                balance = res["amount_residual"]
                foreign_currency = self.env["res.currency"].browse(res["currency_id"])

                return self._prepare_custom_engine_result(
                    date=res["date"] or None,
                    label=res["ref"] or None,
                    amount_currency=amount_currency if convert else None,
                    amount_currency_currency_id=foreign_currency.id
                    if convert
                    else None,
                    currency=foreign_currency.display_name if convert else None,
                    amount=company_currency._convert(
                        balance,
                        journal_currency,
                        journal.company_id,
                        options["date"]["date_to"],
                    )
                    if convert
                    else amount_currency,
                    amount_currency_id=journal_currency.id,
                )
            else:
                amount = 0
                balance_to_convert = 0
                for res in query_res_lines:
                    convert = not (
                        journal_currency and res["currency_id"] == journal_currency.id
                    )
                    if convert:
                        balance_to_convert += res["amount_residual"]
                    else:
                        amount += res["amount_residual_currency"]
                if balance_to_convert:
                    amount += company_currency._convert(
                        balance_to_convert,
                        journal_currency,
                        journal.company_id,
                        options["date"]["date_to"],
                    )

                return self._prepare_custom_engine_result(
                    amount=journal_currency.round(amount),
                    amount_currency_id=journal_currency.id,
                    has_sublines=bool(len(query_res_lines)),
                )

        accounts = (
            journal._get_journal_inbound_outstanding_payment_accounts()
            + journal._get_journal_outbound_outstanding_payment_accounts()
        )

        query = report._get_report_query(
            options,
            "from_beginning",
            domain=[
                ("journal_id", "=", journal.id),
                ("account_id", "in", accounts.ids),
                ("full_reconcile_id", "=", False),
                ("amount_residual_currency", "!=", 0.0),
            ],
        )

        groupby_field_sql = (
            self.env["account.move.line"]._field_to_sql(
                "account_move_line", current_groupby, query
            )
            if current_groupby
            else SQL("NULL")
        )
        query = SQL(
            """
           SELECT %(select_from_groupby)s,
                  account_move_line.account_id,
                  account_move_line.payment_id,
                  account_move_line.move_id,
                  account_move_line.currency_id,
                  account_move_line.move_name AS name,
                  account_move_line.ref,
                  account_move_line.date,
                  SUM(account_move_line.amount_residual) AS amount_residual,
                  SUM(account_move_line.amount_residual_currency) AS amount_residual_currency
             FROM %(table_references)s
            WHERE %(search_condition)s
              AND %(is_receipt)s
         GROUP BY %(group_by)s,
                  account_move_line.account_id,
                  account_move_line.payment_id,
                  account_move_line.move_id,
                  account_move_line.currency_id,
                  account_move_line.move_name,
                  account_move_line.ref,
                  account_move_line.date
           """,
            select_from_groupby=SQL("%s AS grouping_key", groupby_field_sql),
            table_references=query.from_clause,
            search_condition=query.where_clause,
            is_receipt=SQL("account_move_line.balance > 0")
            if internal_type == "receipts"
            else SQL("account_move_line.balance < 0"),
            group_by=groupby_field_sql
            if current_groupby
            else SQL("account_move_line.account_id"),
        )
        self.env.cr.execute(query)
        query_res_lines = self.env.cr.dictfetchall()
        _debug.pipeline(
            "outstanding_lines_fetched",
            report=report,
            internal_type=internal_type,
            groupby=current_groupby,
            outstanding_accounts=accounts,
            rows=len(query_res_lines),
        )

        return self._get_grouped_result(
            query_res_lines, current_groupby, prepare_result_dict, offset, limit
        )

    @_debug.perf.timed
    def _report_expand_unfoldable_line_with_groupby(
        self,
        line_dict_id,
        groupby,
        options,
        progress,
        offset,
        unfold_all_batch_data=None,
    ):
        report = self.env["report.formula"].browse(options["report_id"])
        result = report._report_expand_unfoldable_line_with_groupby(
            line_dict_id, groupby, options, progress, offset, unfold_all_batch_data
        )
        _debug.logic(
            "group_expanded",
            report=report,
            line_dict_id=line_dict_id,
            groupby=groupby,
            offset=offset,
            has_more=result["has_more"],
        )
        amount_expression = self._get_converted_amount_expression(report, line_dict_id)
        if not amount_expression:
            return result

        carried_amounts = (progress or {}).get("amount_to_explain")
        _debug.logic(
            "conversion_rounding_header_source",
            report=report,
            line_dict_id=line_dict_id,
            offset=offset,
            source="progress" if carried_amounts else "computed",
        )
        amount_to_explain = carried_amounts or self._get_group_amounts(
            report, options, line_dict_id, amount_expression
        )
        _journal, journal_currency, _company_currency = (
            self._get_bank_journal_and_currencies(options)
        )
        children = [
            line for line in result["lines"] if line.get("parent_id") == line_dict_id
        ]
        amount_to_explain = {
            column_group_key: self._get_conversion_rounding(
                journal_currency,
                amount,
                [
                    self._get_amount_cells(options, child).get(column_group_key)
                    for child in children
                ],
            )
            for column_group_key, amount in amount_to_explain.items()
        }
        if result["has_more"]:
            result["progress"] = {"amount_to_explain": amount_to_explain}
        else:
            result["lines"] = self._add_conversion_rounding_line(
                report, options, line_dict_id, result["lines"], amount_to_explain
            )
        return result

    def _custom_groupby_line_completer(
        self, report, options, line_dict, current_groupby
    ):
        super()._custom_groupby_line_completer(
            report, options, line_dict, current_groupby
        )
        if line_dict["groupby"] and self._get_converted_amount_expression(
            report, line_dict["id"]
        ):
            line_dict["progress"] = {
                "amount_to_explain": self._get_amount_cells(options, line_dict)
            }

    def _get_converted_amount_expression(self, report, line_dict_id):
        report_line = self.env["report.formula.line"].browse(
            next(
                model_id
                for _markup, model, model_id in reversed(
                    report._parse_line_id(line_dict_id)
                )
                if model == "report.formula.line"
            )
        )
        return report_line.expression_ids.filtered(
            lambda expression: (
                expression.label == "amount"
                and expression.engine == "custom"
                and expression.formula in self._get_converting_engine_formulas()
            )
        )

    def _get_converting_engine_formulas(self) -> tuple:
        return (
            "_report_custom_engine_outstanding_receipts",
            "_report_custom_engine_outstanding_payments",
        )

    def _get_amount_cells(self, options, line_dict) -> dict:
        return {
            column["column_group_key"]: cell.get("no_format") or 0.0
            for column, cell in zip(
                options["columns"], line_dict["columns"], strict=True
            )
            if column["expression_label"] == "amount"
        }

    def _get_group_amounts(self, report, options, line_dict_id, amount_expression):
        group_totals = report._compute_expression_totals_for_each_column_group(
            amount_expression,
            {
                **options,
                "forced_domain": options.get("forced_domain", [])
                + report._get_domain_audit_line_groupby(line_dict_id),
            },
        )
        return {
            column_group_key: totals[amount_expression]["value"] or 0.0
            for column_group_key, totals in group_totals.items()
        }

    def _get_conversion_rounding(self, currency, total, amounts):
        return currency.round(
            currency.round(total)
            - sum(currency.round(amount) for amount in amounts if amount is not None)
        )

    @_debug.perf.timed
    def _add_conversion_rounding_line(
        self, report, options, line_dict_id, lines, rounding_per_column_group
    ):
        children = [line for line in lines if line.get("parent_id") == line_dict_id]
        if not children:
            return lines

        _journal, journal_currency, _company_currency = (
            self._get_bank_journal_and_currencies(options)
        )
        columns = []
        for column in options["columns"]:
            rounding = (
                rounding_per_column_group.get(column["column_group_key"])
                if column["expression_label"] == "amount"
                else None
            )
            columns.append(
                report._prepare_column_dict(
                    rounding,
                    column,
                    options,
                    currency=journal_currency if rounding is not None else False,
                )
            )

        has_rounding = any(
            column["expression_label"] == "amount" and not cell["is_zero"]
            for column, cell in zip(options["columns"], columns, strict=True)
        )
        _debug.logic(
            "conversion_rounding_line",
            report=report,
            line_dict_id=line_dict_id,
            children=len(children),
            added=has_rounding,
        )
        if not has_rounding:
            return lines
        return [
            *lines,
            {
                "id": report._get_generic_line_id(
                    None,
                    None,
                    markup="conversion_rounding",
                    parent_line_id=line_dict_id,
                ),
                "name": self.env._("Conversion rounding"),
                "parent_id": line_dict_id,
                "level": children[-1]["level"],
                "columns": columns,
                "unfoldable": False,
                "unfolded": False,
                "groupby": None,
                "expand_function": None,
                "caret_options": None,
            },
        ]

    def _get_statement_line_open_amount(self, res, journal_currency, company_currency):
        if not res["checked"]:
            return res["amount"]
        if not res["foreign_currency_id"]:
            return -res["amount_residual"]
        if journal_currency == company_currency:
            return -(res["suspense_open_balance"] or 0.0)
        if not res["amount_currency"]:
            return 0.0
        return journal_currency.round(
            -res["amount_residual"] * res["amount"] / res["amount_currency"]
        )

    def _get_grouped_result(
        self,
        query_res_lines,
        current_groupby,
        prepare_result_dict,
        offset=0,
        limit=None,
    ):
        if not current_groupby:
            return prepare_result_dict(query_res_lines)

        all_res_per_grouping_key = {}
        for query_res in query_res_lines:
            grouping_key = query_res["grouping_key"]
            all_res_per_grouping_key.setdefault(grouping_key, []).append(query_res)

        grouping_keys = sorted(
            all_res_per_grouping_key, key=lambda key: (key is None, key)
        )[offset : offset + limit if limit else None]
        return [
            (grouping_key, prepare_result_dict(all_res_per_grouping_key[grouping_key]))
            for grouping_key in grouping_keys
        ]

    @_debug.perf.timed
    def _custom_line_postprocessor(self, report, options, lines):
        lines = super()._custom_line_postprocessor(report, options, lines)
        journal, _journal_currency, _company_currency = (
            self._get_bank_journal_and_currencies(options)
        )
        _debug.logic(
            "bank_reco_postprocess_skipped",
            report=report,
            journal=journal,
            skipped=not journal,
        )
        if not journal:
            return lines

        last_statement = self._get_last_bank_statement(journal, options)

        for line in lines:
            line_id = report._get_res_id_from_line_id(line["id"], "report.formula.line")
            code = self.env["report.formula.line"].browse(line_id).code

            if code == "balance_bank":
                line["name"] = self.env._(
                    "Balance of '%s'", journal.default_account_id.display_name
                )

            if code == "last_statement_balance":
                line["class"] = "o_bold_tr"
                if last_statement:
                    line["columns"][1].update(
                        {
                            "name": last_statement.display_name,
                            "auditable": True,
                        }
                    )

            if code == "transaction_without_statement":
                line["class"] = "o_bold_tr"

            if code == "misc_operations":
                line["class"] = "o_bold_tr"

            model, _model_id = report._get_model_info_from_id(line["id"])
            if model == "account.move.line":
                line_name = line["name"].split()
                line["name"] = line_name[0]

        _debug.pipeline(
            "bank_reco_lines_postprocessed",
            report=report,
            journal=journal,
            lines=len(lines),
            last_statement=last_statement,
        )
        return lines

    @_debug.perf.timed
    def _customize_warnings(
        self, report, options, all_column_groups_expression_totals, warnings
    ):
        journal, journal_currency, _company_currency = (
            self._get_bank_journal_and_currencies(options)
        )
        inconsistent_statement = self._get_inconsistent_statements(options, journal).ids
        bank_miscellaneous_domain = self._get_domain_bank_miscellaneous_move_lines(
            options, journal
        )
        has_bank_miscellaneous_move_lines = bank_miscellaneous_domain and bool(
            self.env["account.move.line"].search_count(
                bank_miscellaneous_domain, limit=1
            )
        )
        (
            last_statement,
            balance_gl,
            balance_end,
            unexplained_difference,
            general_ledger_not_matching,
        ) = self._get_journal_balances(report, options, journal, journal_currency)

        _debug.logic(
            "bank_reco_warnings_inputs",
            report=report,
            journal=journal,
            inconsistent_statements=len(inconsistent_statement),
            bank_miscellaneous_move_lines=bool(has_bank_miscellaneous_move_lines),
            last_statement=last_statement,
            general_ledger_not_matching=general_ledger_not_matching,
            collect_warnings=warnings is not None,
        )
        if warnings is not None:
            if last_statement and general_ledger_not_matching:
                warnings["account.journal_balance"] = {
                    "alert_type": "warning",
                    "general_ledger_amount": balance_gl,
                    "last_bank_statement_amount": balance_end,
                    "unexplained_difference": unexplained_difference,
                }
            if inconsistent_statement:
                warnings["account.inconsistent_statement_warning"] = {
                    "alert_type": "warning",
                    "args": inconsistent_statement,
                }
            if has_bank_miscellaneous_move_lines:
                warnings["account.has_bank_miscellaneous_move_lines"] = {
                    "alert_type": "warning",
                    "args": journal.default_account_id.display_name,
                }

    @_debug.perf.timed
    def _get_journal_balances(
        self, report, options, journal, journal_currency
    ) -> tuple:
        domain = report._get_domain_options(options, "from_beginning")
        balance_gl = journal._get_journal_bank_account_balance(domain=domain)[0]
        last_statement, balance_end, difference, general_ledger_not_matching = (
            self._get_balances(options, journal, balance_gl, journal_currency)
        )
        _debug.pipeline(
            "journal_balances_computed",
            report=report,
            journal=journal,
            last_statement=last_statement,
            balance_gl=balance_gl,
            balance_end=balance_end,
            difference=difference,
            general_ledger_not_matching=general_ledger_not_matching,
        )

        balance_gl = report.format_value(
            options,
            balance_gl,
            format_params={"currency_id": journal_currency.id},
            figure_type="monetary",
        )
        balance_end = report.format_value(
            options,
            balance_end,
            format_params={"currency_id": journal_currency.id},
            figure_type="monetary",
        )
        difference = report.format_value(
            options,
            difference,
            format_params={"currency_id": journal_currency.id},
            figure_type="monetary",
        )

        return (
            last_statement,
            balance_gl,
            balance_end,
            difference,
            general_ledger_not_matching,
        )

    @_debug.perf.timed
    def _get_balances(self, options, journal, balance_gl, report_currency) -> tuple:
        report_date = fields.Date.from_string(options["date"]["date_to"])
        last_statement = self._get_last_bank_statement(journal, options)
        balance_end = 0
        difference = 0
        general_ledger_not_matching = False

        if last_statement:
            lines_before_date_to = last_statement.line_ids.filtered(
                lambda line: line.date <= report_date and line.state == "posted"
            )
            balance_end = last_statement.balance_start + sum(
                lines_before_date_to.mapped("amount")
            )
            difference = balance_gl - balance_end
            general_ledger_not_matching = not report_currency.is_zero(difference)

        return last_statement, balance_end, difference, general_ledger_not_matching

    def _get_last_bank_statement(self, journal, options):
        last_st_line = self.env["account.bank.statement.line"].search(
            self._get_domain_last_bank_statement_line(journal, options),
            order="date desc, id desc",
            limit=1,
        )
        return last_st_line.statement_id

    def _get_domain_last_bank_statement_line(self, journal, options) -> list:
        return [
            ("journal_id", "=", journal.id),
            ("statement_id", "!=", False),
            ("date", "<=", fields.Date.from_string(options["date"]["date_to"])),
        ]

    def _get_inconsistent_statements(self, options, journal):
        statements = self.env["account.bank.statement"].search(
            [
                ("journal_id", "=", journal.id),
                ("date", "<=", options["date"]["date_to"]),
            ]
        )
        if not statements:
            return statements
        invalid_ids = set(statements._get_invalid_statement_ids())
        return statements.filtered(lambda statement: statement.id in invalid_ids)

    def _get_domain_bank_miscellaneous_move_lines(self, options, journal):
        if not journal.default_account_id:
            _debug.logic(
                "misc_lines_skipped", journal=journal, reason="no_default_account"
            )
            return None

        report = self.env["report.formula"].browse(options["report_id"])
        domain = [
            ("account_id", "=", journal.default_account_id.id),
            ("statement_line_id", "=", False),
            *report._get_domain_options(options, "from_beginning"),
        ]

        fiscal_lock_date = journal.company_id._get_user_fiscal_lock_date(journal)
        if fiscal_lock_date != date.min:
            domain.append(("date", ">", fiscal_lock_date))

        if journal.company_id.account_config_id.account_opening_move_id:
            domain.append(
                (
                    "move_id",
                    "!=",
                    journal.company_id.account_config_id.account_opening_move_id.id,
                )
            )
        _debug.logic(
            "misc_lines_domain_restricted",
            report=report,
            journal=journal,
            after_lock_date=fiscal_lock_date != date.min,
            opening_move_excluded=bool(
                journal.company_id.account_config_id.account_opening_move_id
            ),
        )

        return domain

    @_debug.perf.timed
    def action_audit_cell(self, options, params):
        _debug.lifecycle("action_audit_cell", records=self)
        report_line = self.env["report.formula.line"].browse(params["report_line_id"])
        if report_line.code == "balance_bank":
            return self.action_redirect_to_general_ledger(options)
        elif report_line.code == "misc_operations":
            return self.open_bank_miscellaneous_move_lines(options)
        elif report_line.code == "last_statement_balance":
            return self.action_redirect_to_bank_statement_widget(options)
        else:
            return report_line.report_id.action_audit_cell(options, params)

    @_debug.perf.timed
    def action_redirect_to_general_ledger(self, options):
        _debug.lifecycle("action_redirect_to_general_ledger", records=self)
        general_ledger_action = self.env[
            "ir.actions.actions"
        ]._get_action_dict_by_xml_id("account.action_account_report_general_ledger")
        general_ledger_action["params"] = {
            "options": options,
            "ignore_session": True,
        }

        return general_ledger_action

    @_debug.perf.timed
    def action_redirect_to_bank_statement_widget(self, options):
        _debug.lifecycle("action_redirect_to_bank_statement_widget", records=self)
        journal = self.env["account.journal"].browse(
            options.get("bank_reconciliation_report_journal_id")
        )
        last_statement = self._get_last_bank_statement(journal, options)
        return self.env[
            "account.bank.statement.line"
        ]._action_view_bank_reconciliation_widget(
            default_context={
                "create": False,
                "search_default_statement_id": last_statement.id,
            },
            name=last_statement.display_name,
        )

    @_debug.perf.timed
    def open_bank_miscellaneous_move_lines(self, options) -> dict:
        _debug.lifecycle("open_bank_miscellaneous_move_lines", records=self)
        journal = self.env["account.journal"].browse(
            options["bank_reconciliation_report_journal_id"]
        )

        return {
            "name": self.env._("Journal Items"),
            "type": "ir.actions.act_window",
            "res_model": "account.move.line",
            "view_type": "list",
            "view_mode": "list",
            "target": "current",
            "views": [(self.env.ref("account.view_account_move_line_list").id, "list")],
            "domain": self.env[
                "account.bank.reconciliation.report.handler"
            ]._get_domain_bank_miscellaneous_move_lines(options, journal),
        }

    @_debug.perf.timed
    def bank_reconciliation_report_open_inconsistent_statements(
        self, options, params=None
    ):
        inconsistent_statement_ids = params["args"]
        _debug.logic(
            "inconsistent_statements_view",
            statements=len(inconsistent_statement_ids),
            single_form=len(inconsistent_statement_ids) == 1,
        )
        action = {
            "name": self.env._("Inconsistent Statements"),
            "type": "ir.actions.act_window",
            "res_model": "account.bank.statement",
        }
        if len(inconsistent_statement_ids) == 1:
            action.update(
                {
                    "view_mode": "form",
                    "res_id": inconsistent_statement_ids[0],
                    "views": [(False, "form")],
                }
            )
        else:
            action.update(
                {
                    "view_mode": "list",
                    "domain": [("id", "in", inconsistent_statement_ids)],
                    "views": [(False, "list")],
                }
            )
        return action

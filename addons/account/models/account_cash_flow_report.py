from odoo import api, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, Query

_debug = DebugLog(__name__)


class AccountCashFlowReportHandler(models.AbstractModel):
    _name = "account.cash.flow.report.handler"
    _inherit = ["report.formula.custom.handler"]
    _description = "Cash Flow Report Custom Handler"

    @_debug.perf.timed
    def _dynamic_lines_generator(
        self, report, options, all_column_groups_expression_totals, warnings=None
    ):
        lines = []

        layout_data = self._prepare_layout_data()
        report_data = self._get_report_data(report, options, layout_data)
        _debug.pipeline(
            "report_data_built",
            report=report,
            layout_lines=len(layout_data),
            sections_with_data=len(report_data),
        )

        for layout_line_id, layout_line_data in layout_data.items():
            lines.append(
                (
                    0,
                    self._get_layout_line(
                        report, options, layout_line_id, layout_line_data, report_data
                    ),
                )
            )

            if (
                layout_line_id in report_data
                and "aml_groupby_account" in report_data[layout_line_id]
            ):
                aml_data_values = report_data[layout_line_id][
                    "aml_groupby_account"
                ].values()

                aml_data_values_with_account_code = []
                aml_data_values_without_account_code = []

                for aml_data in aml_data_values:
                    if aml_data["account_code"] is not None:
                        aml_data_values_with_account_code.append(aml_data)
                    else:
                        aml_data_values_without_account_code.append(aml_data)

                lines.extend(
                    (0, self._get_aml_line(report, options, aml_data))
                    for aml_data in sorted(
                        aml_data_values_with_account_code,
                        key=lambda x: x["account_code"],
                    )
                    + aml_data_values_without_account_code
                )

        unexplained_difference_line = self._get_unexplained_difference_line(
            report, options, report_data
        )
        _debug.pipeline(
            "cash_flow_lines_generated",
            report=report,
            lines=len(lines),
            unexplained_difference=bool(unexplained_difference_line),
        )

        if unexplained_difference_line:
            lines.append((0, unexplained_difference_line))

        return lines

    def _custom_options_initializer(self, report, options, previous_options):
        super()._custom_options_initializer(
            report, options, previous_options=previous_options
        )
        report._init_options_journals(
            options,
            previous_options=previous_options,
            additional_journals_domain=[("type", "in", ("bank", "cash", "general"))],
        )

    @_debug.perf.timed
    def _get_report_data(self, report, options, layout_data):
        report_data = {}

        payment_account_ids = self._get_account_ids(report, options)
        _debug.logic(
            "liquidity_accounts_checked",
            report=report,
            payment_accounts=len(payment_account_ids),
            skipped=not payment_account_ids,
        )
        if not payment_account_ids:
            return report_data

        for aml_data in self._get_liquidity_balance(
            report, options, payment_account_ids, "to_beginning_of_period"
        ):
            self._add_report_data("opening_balance", aml_data, layout_data, report_data)
            self._add_report_data("closing_balance", aml_data, layout_data, report_data)

        for aml_data in self._get_liquidity_balance(
            report, options, payment_account_ids, "strict_range"
        ):
            self._add_report_data("closing_balance", aml_data, layout_data, report_data)

        tags_ids = self._get_tags_ids()
        cashflow_tag_ids = self._get_cashflow_tag_ids()

        for aml_groupby_account in self._get_liquidity_moves(
            report, options, payment_account_ids, cashflow_tag_ids
        ):
            for aml_data in aml_groupby_account.values():
                self._dispatch_aml_data(tags_ids, aml_data, layout_data, report_data)

        for aml_groupby_account in self._get_reconciled_moves(
            report, options, payment_account_ids, cashflow_tag_ids
        ):
            for aml_data in aml_groupby_account.values():
                self._dispatch_aml_data(tags_ids, aml_data, layout_data, report_data)

        _debug.pipeline(
            "report_data_dispatched",
            report=report,
            sections_with_data=len(report_data),
        )
        return report_data

    @_debug.perf.timed
    def _add_report_data(
        self, layout_line_id, aml_data, layout_data, report_data
    ) -> None:

        def _report_update_parent(
            layout_line_id, aml_column_group_key, aml_balance, layout_data, report_data
        ):
            if "parent_line_id" in layout_data[layout_line_id]:
                parent_line_id = layout_data[layout_line_id]["parent_line_id"]

                report_data.setdefault(parent_line_id, {"balance": {}})
                report_data[parent_line_id]["balance"].setdefault(
                    aml_column_group_key, 0.0
                )
                report_data[parent_line_id]["balance"][aml_column_group_key] += (
                    aml_balance
                )

                _report_update_parent(
                    parent_line_id,
                    aml_column_group_key,
                    aml_balance,
                    layout_data,
                    report_data,
                )

        aml_column_group_key = aml_data["column_group_key"]
        aml_account_id = aml_data["account_id"]
        aml_account_code = aml_data["account_code"]
        aml_account_name = aml_data["account_name"]
        aml_balance = aml_data["balance"]
        aml_account_tag = aml_data.get("account_tag_id", None)

        if self.env.company.currency_id.is_zero(aml_balance):
            return

        report_data.setdefault(
            layout_line_id,
            {
                "balance": {},
                "aml_groupby_account": {},
            },
        )

        report_data[layout_line_id]["aml_groupby_account"].setdefault(
            aml_account_id,
            {
                "parent_line_id": layout_line_id,
                "account_id": aml_account_id,
                "account_code": aml_account_code,
                "account_name": aml_account_name,
                "account_tag_id": aml_account_tag,
                "level": layout_data[layout_line_id]["level"] + 1,
                "balance": {},
            },
        )

        report_data[layout_line_id]["balance"].setdefault(aml_column_group_key, 0.0)
        report_data[layout_line_id]["balance"][aml_column_group_key] += aml_balance

        report_data[layout_line_id]["aml_groupby_account"][aml_account_id][
            "balance"
        ].setdefault(aml_column_group_key, 0.0)
        report_data[layout_line_id]["aml_groupby_account"][aml_account_id]["balance"][
            aml_column_group_key
        ] += aml_balance

        _report_update_parent(
            layout_line_id, aml_column_group_key, aml_balance, layout_data, report_data
        )

    def _get_tags_ids(self) -> dict:
        return {
            "operating": self.env.ref("account.account_tag_operating").id,
            "investing": self.env.ref("account.account_tag_investing").id,
            "financing": self.env.ref("account.account_tag_financing").id,
        }

    def _get_cashflow_tag_ids(self):
        return self._get_tags_ids().values()

    @api.model
    def _get_cash_flow_tag_families(self):
        Tag = self.env["account.account.tag"]
        registry = self.env.registry
        pending = ["account.cash.flow.report.handler"]
        seen = set()
        families = {}
        while pending:
            name = pending.pop()
            if name in seen:
                continue
            seen.add(name)
            pending.extend(registry[name]._inherit_children)
            tag_ids = frozenset(self.env[name]._get_cashflow_tag_ids())
            families.setdefault(tag_ids, Tag.browse(sorted(tag_ids)))
        return list(families.values())

    def _get_cash_flow_tag_join(self, cash_flow_tag_ids) -> SQL:
        return SQL(
            """
            JOIN LATERAL (
                SELECT MIN(account_account_account_tag.account_account_tag_id) AS account_tag_id
                FROM account_account_account_tag
                WHERE account_account_account_tag.account_account_id = account_move_line.account_id
                    AND account_account_account_tag.account_account_tag_id = ANY(%s)
            ) cash_flow_tag ON TRUE
            """,
            list(cash_flow_tag_ids),
        )

    def _get_account_code_aggregate(self, query, account_alias) -> SQL:
        company_alias = query.join(
            lhs_alias="account_move_line",
            lhs_column="company_id",
            rhs_table="res_company",
            rhs_column="id",
            link="company_id",
        )
        return SQL(
            "MIN(%s->>SPLIT_PART(%s, '/', 1))",
            SQL.identifier(
                account_alias,
                "code_store",
                to_flush=self.env["account.account"]._fields["code_store"],
            ),
            SQL.identifier(company_alias, "parent_path"),
        )

    @_debug.perf.timed
    def _dispatch_aml_data(self, tags_ids, aml_data, layout_data, report_data) -> None:
        if aml_data["account_account_type"] == "asset_receivable":
            self._add_report_data(
                "advance_payments_customer", aml_data, layout_data, report_data
            )
        elif aml_data["account_account_type"] == "liability_payable":
            self._add_report_data(
                "advance_payments_suppliers", aml_data, layout_data, report_data
            )
        elif aml_data["balance"] < 0:
            if aml_data["account_tag_id"] == tags_ids["operating"]:
                self._add_report_data(
                    "paid_operating_activities", aml_data, layout_data, report_data
                )
            elif aml_data["account_tag_id"] == tags_ids["investing"]:
                self._add_report_data(
                    "investing_activities_cash_out", aml_data, layout_data, report_data
                )
            elif aml_data["account_tag_id"] == tags_ids["financing"]:
                self._add_report_data(
                    "financing_activities_cash_out", aml_data, layout_data, report_data
                )
            else:
                self._add_report_data(
                    "unclassified_activities_cash_out",
                    aml_data,
                    layout_data,
                    report_data,
                )
        elif aml_data["balance"] > 0:
            if aml_data["account_tag_id"] == tags_ids["operating"]:
                self._add_report_data(
                    "received_operating_activities", aml_data, layout_data, report_data
                )
            elif aml_data["account_tag_id"] == tags_ids["investing"]:
                self._add_report_data(
                    "investing_activities_cash_in", aml_data, layout_data, report_data
                )
            elif aml_data["account_tag_id"] == tags_ids["financing"]:
                self._add_report_data(
                    "financing_activities_cash_in", aml_data, layout_data, report_data
                )
            else:
                self._add_report_data(
                    "unclassified_activities_cash_in",
                    aml_data,
                    layout_data,
                    report_data,
                )

    @_debug.perf.timed
    def _get_account_ids(self, report, options):
        selected_journal_ids = [j["id"] for j in report._get_options_journals(options)]
        _debug.logic(
            "liquidity_journal_scope",
            report=report,
            selected_journals=len(selected_journal_ids),
            skipped=not selected_journal_ids,
        )
        if not selected_journal_ids:
            return ()

        self.env.cr.execute(
            SQL(
                """
                SELECT
                    array_remove(ARRAY_AGG(DISTINCT account_account.id), NULL),
                    array_remove(ARRAY_AGG(DISTINCT account_payment_channel.payment_account_id), NULL)
                FROM account_journal
                LEFT JOIN account_payment_channel
                    ON account_journal.id = account_payment_channel.journal_id
                LEFT JOIN account_account
                    ON account_journal.default_account_id = account_account.id
                       AND account_account.account_type IN ('asset_cash', 'liability_credit_card')
                WHERE account_journal.id = ANY(%s)
                """,
                selected_journal_ids,
            )
        )

        res = self.env.cr.fetchall()[0]
        payment_account_ids = set((res[0] or []) + (res[1] or []))
        _debug.pipeline(
            "liquidity_accounts_fetched",
            report=report,
            default_accounts=len(res[0] or []),
            payment_accounts=len(res[1] or []),
            distinct_accounts=len(payment_account_ids),
        )

        return tuple(payment_account_ids)

    def _get_move_ids_query(
        self, report, payment_account_ids, column_group_options
    ) -> SQL:

        query = report._get_report_query(
            column_group_options,
            "strict_range",
            [("account_id", "in", list(payment_account_ids))],
        )
        return SQL(
            """
            SELECT
                array_agg(DISTINCT account_move_line.move_id) AS move_id
            FROM %(table_references)s
            WHERE %(search_condition)s
            """,
            table_references=query.from_clause,
            search_condition=query.where_clause,
        )

    @_debug.perf.timed
    def _get_liquidity_balance(self, report, options, payment_account_ids, date_scope):
        queries = []

        for (
            column_group_key,
            column_group_options,
        ) in report._split_options_per_column_group(options).items():
            query = report._get_report_query(
                column_group_options,
                date_scope,
                domain=[("account_id", "in", payment_account_ids)],
            )
            account_alias = query.join(
                lhs_alias="account_move_line",
                lhs_column="account_id",
                rhs_table="account_account",
                rhs_column="id",
                link="account_id",
            )
            account_name = self.env["account.account"]._field_to_sql(
                account_alias, "name"
            )
            account_code = self._get_account_code_aggregate(query, account_alias)

            queries.append(
                SQL(
                    """
                SELECT
                    %(column_group_key)s AS column_group_key,
                    account_move_line.account_id,
                    %(account_code)s AS account_code,
                    %(account_name)s AS account_name,
                    SUM(%(balance_select)s) AS balance
                FROM %(table_references)s
                %(currency_table_join)s
                WHERE %(search_condition)s
                GROUP BY account_move_line.account_id, %(name_col)s
                """,
                    column_group_key=column_group_key,
                    account_code=account_code,
                    account_name=account_name,
                    name_col=SQL.identifier(account_alias, "name"),
                    table_references=query.from_clause,
                    balance_select=report._currency_table_apply_rate(
                        SQL("account_move_line.balance")
                    ),
                    currency_table_join=report._currency_table_aml_join(
                        column_group_options
                    ),
                    search_condition=query.where_clause,
                )
            )

        _debug.pipeline(
            "liquidity_balance_query",
            report=report,
            date_scope=date_scope,
            column_groups=len(queries),
            accounts=len(payment_account_ids),
        )
        self.env.cr.execute(SQL(" UNION ALL ").join(queries))

        return self.env.cr.dictfetchall()

    @_debug.perf.timed
    def _get_liquidity_moves(
        self, report, options, payment_account_ids, cash_flow_tag_ids
    ):

        reconciled_aml_groupby_account = {}

        queries = []

        for (
            column_group_key,
            column_group_options,
        ) in report._split_options_per_column_group(options).items():
            move_ids_query = self._get_move_ids_query(
                report, payment_account_ids, column_group_options
            )
            query = Query(self.env, "account_move_line")
            account_alias = query.join(
                lhs_alias="account_move_line",
                lhs_column="account_id",
                rhs_table="account_account",
                rhs_column="id",
                link="account_id",
            )
            account_code = self._get_account_code_aggregate(query, account_alias)
            account_name = self.env["account.account"]._field_to_sql(
                account_alias, "name"
            )
            account_type = SQL.identifier(account_alias, "account_type")

            queries.append(
                SQL(
                    """
                (WITH payment_move_ids AS (%(move_ids_query)s)
                -- Credit amount of each account
                SELECT
                    %(column_group_key)s AS column_group_key,
                    account_move_line.account_id,
                    %(account_code)s AS account_code,
                    %(account_name)s AS account_name,
                    %(account_type)s AS account_account_type,
                    cash_flow_tag.account_tag_id,
                    SUM(%(partial_amount_select)s) AS balance
                FROM %(from_clause)s
                %(currency_table_join)s
                LEFT JOIN account_partial_reconcile
                    ON account_partial_reconcile.credit_move_id = account_move_line.id
                %(cash_flow_tag_join)s
                WHERE account_move_line.move_id IN (SELECT unnest(payment_move_ids.move_id) FROM payment_move_ids)
                    AND account_move_line.account_id != ALL(%(payment_account_ids)s)
                    AND account_partial_reconcile.max_date BETWEEN %(date_from)s AND %(date_to)s
                GROUP BY account_move_line.company_id, account_move_line.account_id, %(name_col)s, account_account_type, cash_flow_tag.account_tag_id

                UNION ALL

                -- Debit amount of each account
                SELECT
                    %(column_group_key)s AS column_group_key,
                    account_move_line.account_id,
                    %(account_code)s AS account_code,
                    %(account_name)s AS account_name,
                    %(account_type)s AS account_account_type,
                    cash_flow_tag.account_tag_id,
                    -SUM(%(partial_amount_select)s) AS balance
                FROM %(from_clause)s
                %(currency_table_join)s
                LEFT JOIN account_partial_reconcile
                    ON account_partial_reconcile.debit_move_id = account_move_line.id
                %(cash_flow_tag_join)s
                WHERE account_move_line.move_id IN (SELECT unnest(payment_move_ids.move_id) FROM payment_move_ids)
                    AND account_move_line.account_id != ALL(%(payment_account_ids)s)
                    AND account_partial_reconcile.max_date BETWEEN %(date_from)s AND %(date_to)s
                GROUP BY account_move_line.company_id, account_move_line.account_id, %(name_col)s, account_account_type, cash_flow_tag.account_tag_id

                UNION ALL

                -- Total amount of each account
                SELECT
                    %(column_group_key)s AS column_group_key,
                    account_move_line.account_id AS account_id,
                    %(account_code)s AS account_code,
                    %(account_name)s AS account_name,
                    %(account_type)s AS account_account_type,
                    cash_flow_tag.account_tag_id,
                    SUM(%(aml_balance_select)s) AS balance
                FROM %(from_clause)s
                %(currency_table_join)s
                %(cash_flow_tag_join)s
                WHERE account_move_line.move_id IN (SELECT unnest(payment_move_ids.move_id) FROM payment_move_ids)
                    AND account_move_line.account_id != ALL(%(payment_account_ids)s)
                GROUP BY account_move_line.account_id, %(name_col)s, account_account_type, cash_flow_tag.account_tag_id)
                    """,
                    column_group_key=column_group_key,
                    move_ids_query=move_ids_query,
                    account_code=account_code,
                    account_name=account_name,
                    account_type=account_type,
                    name_col=SQL.identifier(account_alias, "name"),
                    from_clause=query.from_clause,
                    currency_table_join=report._currency_table_aml_join(
                        column_group_options
                    ),
                    partial_amount_select=report._currency_table_apply_rate(
                        SQL("account_partial_reconcile.amount")
                    ),
                    aml_balance_select=report._currency_table_apply_rate(
                        SQL("account_move_line.balance")
                    ),
                    cash_flow_tag_join=self._get_cash_flow_tag_join(cash_flow_tag_ids),
                    payment_account_ids=list(payment_account_ids),
                    date_from=column_group_options["date"]["date_from"],
                    date_to=column_group_options["date"]["date_to"],
                )
            )

        self.env.cr.execute(SQL(" UNION ALL ").join(queries))

        for aml_data in self.env.cr.dictfetchall():
            reconciled_aml_groupby_account.setdefault(aml_data["account_id"], {})
            reconciled_aml_groupby_account[aml_data["account_id"]].setdefault(
                aml_data["column_group_key"],
                {
                    "column_group_key": aml_data["column_group_key"],
                    "account_id": aml_data["account_id"],
                    "account_code": aml_data["account_code"],
                    "account_name": aml_data["account_name"],
                    "account_account_type": aml_data["account_account_type"],
                    "account_tag_id": aml_data["account_tag_id"],
                    "balance": 0.0,
                },
            )

            reconciled_aml_groupby_account[aml_data["account_id"]][
                aml_data["column_group_key"]
            ]["balance"] -= aml_data["balance"]

        _debug.perf.count("liquidity_move_rows_fetched", rows=self.env.cr.rowcount)
        _debug.pipeline(
            "liquidity_moves_grouped",
            report=report,
            column_groups=len(queries),
            accounts=len(reconciled_aml_groupby_account),
        )
        return list(reconciled_aml_groupby_account.values())

    def _currency_table_current_rate_join(
        self, report, column_group_options, company_id_sql
    ) -> SQL:
        return SQL(
            """
            JOIN %(currency_table)s
                ON account_currency_table.company_id = %(company_id)s
                AND account_currency_table.rate_type = 'current' -- For payable/receivable accounts it'll always be 'current' anyway
                AND (account_currency_table.period_key = %(period_key)s OR account_currency_table.period_key IS NULL)
            """,
            currency_table=report._get_currency_table(column_group_options),
            company_id=company_id_sql,
            period_key=column_group_options["date"]["currency_table_period_key"],
        )

    @_debug.perf.timed
    def _get_reconciled_moves(
        self, report, options, payment_account_ids, cash_flow_tag_ids
    ):

        reconciled_account_ids = {
            column_group_key: set() for column_group_key in options["column_groups"]
        }
        reconciled_percentage_per_move = {
            column_group_key: {} for column_group_key in options["column_groups"]
        }
        options_per_column_group = report._split_options_per_column_group(options)

        queries = []

        for column_group_key, column_group_options in options_per_column_group.items():
            current_rate_join = self._currency_table_current_rate_join(
                report,
                column_group_options,
                SQL("account_partial_reconcile.company_id"),
            )
            move_ids_query = self._get_move_ids_query(
                report, payment_account_ids, column_group_options
            )

            queries.append(
                SQL(
                    """
                    (WITH payment_move_ids AS (%(move_ids_query)s)
                    SELECT
                        %(column_group_key)s AS column_group_key,
                        debit_line.move_id,
                        debit_line.account_id,
                        SUM(%(partial_amount)s) AS balance
                    FROM account_move_line AS credit_line
                    LEFT JOIN account_partial_reconcile
                        ON account_partial_reconcile.credit_move_id = credit_line.id
                    %(current_rate_join)s
                    INNER JOIN account_move_line AS debit_line
                        ON debit_line.id = account_partial_reconcile.debit_move_id
                    WHERE credit_line.move_id IN (SELECT unnest(payment_move_ids.move_id) FROM payment_move_ids)
                        AND credit_line.account_id != ALL(%(payment_account_ids)s)
                        AND credit_line.credit > 0.0
                        AND debit_line.move_id NOT IN (SELECT unnest(payment_move_ids.move_id) FROM payment_move_ids)
                        AND account_partial_reconcile.max_date BETWEEN %(date_from)s AND %(date_to)s
                    GROUP BY debit_line.move_id, debit_line.account_id

                    UNION ALL

                    SELECT
                        %(column_group_key)s AS column_group_key,
                        credit_line.move_id,
                        credit_line.account_id,
                        -SUM(%(partial_amount)s) AS balance
                    FROM account_move_line AS debit_line
                    LEFT JOIN account_partial_reconcile
                        ON account_partial_reconcile.debit_move_id = debit_line.id
                    %(current_rate_join)s
                    INNER JOIN account_move_line AS credit_line
                        ON credit_line.id = account_partial_reconcile.credit_move_id
                    WHERE debit_line.move_id IN (SELECT unnest(payment_move_ids.move_id) FROM payment_move_ids)
                        AND debit_line.account_id != ALL(%(payment_account_ids)s)
                        AND debit_line.debit > 0.0
                        AND credit_line.move_id NOT IN (SELECT unnest(payment_move_ids.move_id) FROM payment_move_ids)
                        AND account_partial_reconcile.max_date BETWEEN %(date_from)s AND %(date_to)s
                    GROUP BY credit_line.move_id, credit_line.account_id)
                    """,
                    move_ids_query=move_ids_query,
                    column_group_key=column_group_key,
                    payment_account_ids=list(payment_account_ids),
                    date_from=column_group_options["date"]["date_from"],
                    date_to=column_group_options["date"]["date_to"],
                    current_rate_join=current_rate_join,
                    partial_amount=report._currency_table_apply_rate(
                        SQL("account_partial_reconcile.amount")
                    ),
                )
            )

        self.env.cr.execute(SQL(" UNION ALL ").join(queries))

        for aml_data in self.env.cr.dictfetchall():
            reconciled_percentage_per_move[aml_data["column_group_key"]].setdefault(
                aml_data["move_id"], {}
            )
            reconciled_percentage_per_move[aml_data["column_group_key"]][
                aml_data["move_id"]
            ].setdefault(aml_data["account_id"], [0.0, 0.0])
            reconciled_percentage_per_move[aml_data["column_group_key"]][
                aml_data["move_id"]
            ][aml_data["account_id"]][0] += aml_data["balance"]

            reconciled_account_ids[aml_data["column_group_key"]].add(
                aml_data["account_id"]
            )

        _debug.perf.count("reconciled_partial_rows_fetched", rows=self.env.cr.rowcount)
        if _debug.pipeline.enabled:
            _debug.pipeline(
                "reconciled_partials_fetched",
                report=report,
                moves_per_column_group={
                    key: len(moves)
                    for key, moves in reconciled_percentage_per_move.items()
                },
                accounts_per_column_group={
                    key: len(accounts)
                    for key, accounts in reconciled_account_ids.items()
                },
            )
        has_reconciled_moves = any(reconciled_percentage_per_move.values())
        _debug.logic(
            "reconciled_moves_checked",
            report=report,
            skipped=not has_reconciled_moves,
            column_groups=len(reconciled_percentage_per_move),
        )
        if not has_reconciled_moves:
            return []

        queries = []

        for column_group_key, column_group_options in options_per_column_group.items():
            queries.append(
                SQL(
                    """
                SELECT
                    %(column_group_key)s AS column_group_key,
                    account_move_line.move_id,
                    account_move_line.account_id,
                    SUM(%(balance_select)s) AS balance
                FROM account_move_line
                %(current_rate_join)s
                WHERE account_move_line.move_id = ANY(%(move_ids)s)
                    AND account_move_line.account_id = ANY(%(account_ids)s)
                GROUP BY account_move_line.move_id, account_move_line.account_id
                """,
                    column_group_key=column_group_key,
                    current_rate_join=self._currency_table_current_rate_join(
                        report,
                        column_group_options,
                        SQL("account_move_line.company_id"),
                    ),
                    balance_select=report._currency_table_apply_rate(
                        SQL("account_move_line.balance")
                    ),
                    move_ids=list(reconciled_percentage_per_move[column_group_key])
                    or [None],
                    account_ids=list(reconciled_account_ids[column_group_key])
                    or [None],
                )
            )

        self.env.cr.execute(SQL(" UNION ALL ").join(queries))

        for aml_data in self.env.cr.dictfetchall():
            if (
                aml_data["account_id"]
                in reconciled_percentage_per_move[aml_data["column_group_key"]][
                    aml_data["move_id"]
                ]
            ):
                reconciled_percentage_per_move[aml_data["column_group_key"]][
                    aml_data["move_id"]
                ][aml_data["account_id"]][1] += aml_data["balance"]

        _debug.perf.count("reconciled_move_balances_fetched", rows=self.env.cr.rowcount)
        reconciled_aml_per_account = {}

        queries = []

        query = Query(self.env, "account_move_line")
        account_alias = query.join(
            lhs_alias="account_move_line",
            lhs_column="account_id",
            rhs_table="account_account",
            rhs_column="id",
            link="account_id",
        )
        account_code = self._get_account_code_aggregate(query, account_alias)
        account_name = self.env["account.account"]._field_to_sql(account_alias, "name")
        account_type = SQL.identifier(account_alias, "account_type")

        for column_group_key, column_group_options in options_per_column_group.items():
            queries.append(
                SQL(
                    """
                SELECT
                    %(column_group_key)s AS column_group_key,
                    account_move_line.move_id,
                    account_move_line.account_id,
                    %(account_code)s AS account_code,
                    %(account_name)s AS account_name,
                    %(account_type)s AS account_account_type,
                    cash_flow_tag.account_tag_id,
                    SUM(%(balance_select)s) AS balance
                FROM %(from_clause)s
                %(currency_table_join)s
                %(cash_flow_tag_join)s
                WHERE account_move_line.move_id = ANY(%(move_ids)s)
                GROUP BY account_move_line.move_id, account_move_line.account_id, %(name_col)s, account_account_type, cash_flow_tag.account_tag_id
                """,
                    column_group_key=column_group_key,
                    account_code=account_code,
                    account_name=account_name,
                    account_type=account_type,
                    name_col=SQL.identifier(account_alias, "name"),
                    from_clause=query.from_clause,
                    currency_table_join=report._currency_table_aml_join(
                        column_group_options
                    ),
                    balance_select=report._currency_table_apply_rate(
                        SQL("account_move_line.balance")
                    ),
                    cash_flow_tag_join=self._get_cash_flow_tag_join(cash_flow_tag_ids),
                    move_ids=list(reconciled_percentage_per_move[column_group_key])
                    or [None],
                )
            )

        self.env.cr.execute(SQL(" UNION ALL ").join(queries))

        for aml_data in self.env.cr.dictfetchall():
            aml_column_group_key = aml_data["column_group_key"]
            aml_move_id = aml_data["move_id"]
            aml_account_id = aml_data["account_id"]
            aml_account_code = aml_data["account_code"]
            aml_account_name = aml_data["account_name"]
            aml_account_account_type = aml_data["account_account_type"]
            aml_account_tag_id = aml_data["account_tag_id"]
            aml_balance = aml_data["balance"]

            total_reconciled_amount = 0.0
            total_amount = 0.0

            for reconciled_amount, amount in reconciled_percentage_per_move[
                aml_column_group_key
            ][aml_move_id].values():
                total_reconciled_amount += reconciled_amount
                total_amount += amount

            if (
                total_amount
                and aml_account_id
                not in reconciled_percentage_per_move[aml_column_group_key][aml_move_id]
            ):
                reconciled_percentage = total_reconciled_amount / total_amount
                aml_balance *= reconciled_percentage
            elif (
                not total_amount
                and aml_account_id
                in reconciled_percentage_per_move[aml_column_group_key][aml_move_id]
            ):
                aml_balance = -reconciled_percentage_per_move[aml_column_group_key][
                    aml_move_id
                ][aml_account_id][0]
            else:
                continue

            reconciled_aml_per_account.setdefault(aml_account_id, {})
            reconciled_aml_per_account[aml_account_id].setdefault(
                aml_column_group_key,
                {
                    "column_group_key": aml_column_group_key,
                    "account_id": aml_account_id,
                    "account_code": aml_account_code,
                    "account_name": aml_account_name,
                    "account_account_type": aml_account_account_type,
                    "account_tag_id": aml_account_tag_id,
                    "balance": 0.0,
                },
            )

            reconciled_aml_per_account[aml_account_id][aml_column_group_key][
                "balance"
            ] -= aml_balance

        _debug.perf.count("reconciled_aml_rows_fetched", rows=self.env.cr.rowcount)
        _debug.pipeline(
            "reconciled_moves_grouped",
            report=report,
            accounts=len(reconciled_aml_per_account),
        )
        return list(reconciled_aml_per_account.values())

    @_debug.perf.timed
    def _prepare_layout_data(self) -> dict:
        return {
            "opening_balance": {
                "name": self.env._("Cash and cash equivalents, beginning of period"),
                "level": 0,
            },
            "net_increase": {
                "name": self.env._("Net increase in cash and cash equivalents"),
                "level": 0,
                "unfolded": True,
            },
            "operating_activities": {
                "name": self.env._("Cash flows from operating activities"),
                "level": 2,
                "parent_line_id": "net_increase",
                "class": "fw-bold",
                "unfolded": True,
            },
            "advance_payments_customer": {
                "name": self.env._("Advance Payments received from customers"),
                "level": 4,
                "parent_line_id": "operating_activities",
            },
            "received_operating_activities": {
                "name": self.env._("Cash received from operating activities"),
                "level": 4,
                "parent_line_id": "operating_activities",
            },
            "advance_payments_suppliers": {
                "name": self.env._("Advance payments made to suppliers"),
                "level": 4,
                "parent_line_id": "operating_activities",
            },
            "paid_operating_activities": {
                "name": self.env._("Cash paid for operating activities"),
                "level": 4,
                "parent_line_id": "operating_activities",
            },
            "investing_activities": {
                "name": self.env._(
                    "Cash flows from investing & extraordinary activities"
                ),
                "level": 2,
                "parent_line_id": "net_increase",
                "class": "fw-bold",
                "unfolded": True,
            },
            "investing_activities_cash_in": {
                "name": self.env._("Cash in"),
                "level": 4,
                "parent_line_id": "investing_activities",
            },
            "investing_activities_cash_out": {
                "name": self.env._("Cash out"),
                "level": 4,
                "parent_line_id": "investing_activities",
            },
            "financing_activities": {
                "name": self.env._("Cash flows from financing activities"),
                "level": 2,
                "parent_line_id": "net_increase",
                "class": "fw-bold",
                "unfolded": True,
            },
            "financing_activities_cash_in": {
                "name": self.env._("Cash in"),
                "level": 4,
                "parent_line_id": "financing_activities",
            },
            "financing_activities_cash_out": {
                "name": self.env._("Cash out"),
                "level": 4,
                "parent_line_id": "financing_activities",
            },
            "unclassified_activities": {
                "name": self.env._("Cash flows from unclassified activities"),
                "level": 2,
                "parent_line_id": "net_increase",
                "class": "fw-bold",
                "unfolded": True,
            },
            "unclassified_activities_cash_in": {
                "name": self.env._("Cash in"),
                "level": 4,
                "parent_line_id": "unclassified_activities",
            },
            "unclassified_activities_cash_out": {
                "name": self.env._("Cash out"),
                "level": 4,
                "parent_line_id": "unclassified_activities",
            },
            "closing_balance": {
                "name": self.env._("Cash and cash equivalents, closing balance"),
                "level": 0,
            },
        }

    @_debug.perf.timed
    def _get_layout_line(
        self, report, options, layout_line_id, layout_line_data, report_data
    ) -> dict:
        line_id = report._get_generic_line_id(None, None, markup=layout_line_id)
        unfoldable = (
            "aml_groupby_account" in report_data[layout_line_id]
            if layout_line_id in report_data
            else False
        )

        column_values = []

        for column in options["columns"]:
            expression_label = column["expression_label"]
            column_group_key = column["column_group_key"]

            value = (
                report_data[layout_line_id][expression_label].get(column_group_key, 0.0)
                if layout_line_id in report_data
                else 0.0
            )

            column_values.append(
                report._prepare_column_dict(value, column, options=options)
            )

        return {
            "id": line_id,
            "name": layout_line_data["name"],
            "level": layout_line_data["level"],
            "class": layout_line_data.get("class", ""),
            "columns": column_values,
            "unfoldable": unfoldable,
            "unfolded": line_id in options["unfolded_lines"]
            or layout_line_data.get("unfolded")
            or (options.get("unfold_all") and unfoldable),
        }

    def _get_aml_line(self, report, options, aml_data) -> dict:
        parent_line_id = report._get_generic_line_id(
            None, None, aml_data["parent_line_id"]
        )
        line_id = report._get_generic_line_id(
            "account.account", aml_data["account_id"], parent_line_id=parent_line_id
        )

        column_values = []

        for column in options["columns"]:
            expression_label = column["expression_label"]
            column_group_key = column["column_group_key"]

            value = aml_data[expression_label].get(column_group_key, 0.0)

            column_values.append(
                report._prepare_column_dict(value, column, options=options)
            )

        return {
            "id": line_id,
            "name": f"{aml_data['account_code']} {aml_data['account_name']}"
            if aml_data["account_code"]
            else aml_data["account_name"],
            "caret_options": "account.account",
            "level": aml_data["level"],
            "parent_id": parent_line_id,
            "columns": column_values,
        }

    @_debug.perf.timed
    def _get_unexplained_difference_line(
        self, report, options, report_data
    ) -> dict | None:
        unexplained_difference = False
        column_values = []

        for column in options["columns"]:
            expression_label = column["expression_label"]
            column_group_key = column["column_group_key"]

            opening_balance = (
                report_data["opening_balance"][expression_label].get(
                    column_group_key, 0.0
                )
                if "opening_balance" in report_data
                else 0.0
            )
            closing_balance = (
                report_data["closing_balance"][expression_label].get(
                    column_group_key, 0.0
                )
                if "closing_balance" in report_data
                else 0.0
            )
            net_increase = (
                report_data["net_increase"][expression_label].get(column_group_key, 0.0)
                if "net_increase" in report_data
                else 0.0
            )

            balance = closing_balance - opening_balance - net_increase

            if not self.env.company.currency_id.is_zero(balance):
                unexplained_difference = True

            column_values.append(
                report._prepare_column_dict(
                    balance,
                    {
                        "figure_type": "monetary",
                        "expression_label": "balance",
                    },
                    options=options,
                )
            )

        _debug.logic(
            "unexplained_difference_checked",
            report=report,
            unexplained_difference=unexplained_difference,
            columns=len(column_values),
        )
        if unexplained_difference:
            return {
                "id": report._get_generic_line_id(
                    None, None, markup="unexplained_difference"
                ),
                "name": "Unexplained Difference",
                "level": 1,
                "columns": column_values,
            }
        return None

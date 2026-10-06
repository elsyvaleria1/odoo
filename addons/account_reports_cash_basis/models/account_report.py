from odoo import api, fields, models
from odoo.db.schema import get_table_columns
from odoo.fields import Domain
from odoo.tools import SQL, Query


class AccountReport(models.Model):
    _inherit = "report.formula"

    filter_cash_basis = fields.Boolean(
        string="Cash Basis",
        compute="_compute_filter_cash_basis",
        depends=["root_report_id", "section_main_report_ids"],
        store=True,
        readonly=False,
        help="Display the option to switch to cash basis mode.",
    )

    def _compute_filter_cash_basis(self) -> None:
        self._compute_report_option_filter("filter_cash_basis", False)

    def get_options(self, previous_options):
        options = super().get_options(previous_options)
        # A sections report reroutes: super() returns the options of the selected
        # section, so the flag has to come from that report. Reading it from self
        # hid the toggle on the composite while cash basis stayed applied.
        report = self.browse(options["report_id"]) if options.get("report_id") else self
        options["filters"]["show_cash_basis"] = report.filter_cash_basis
        return options

    def _init_options_cash_basis(self, options, previous_options) -> None:
        if self.filter_cash_basis:
            options["report_cash_basis"] = previous_options.get(
                "report_cash_basis", False
            )

    def _get_pdf_extra_option_labels(self, options):
        labels = super()._get_pdf_extra_option_labels(options)
        if self.filter_cash_basis and options["report_cash_basis"]:
            labels.append(self.env._("Cash Basis"))
        return labels

    def _init_options_readonly_query(self, options, previous_options) -> None:
        super()._init_options_readonly_query(options, previous_options)
        options["readonly_query"] = options["readonly_query"] and not options.get(
            "report_cash_basis"
        )

    @api.model
    def _clear_cash_basis_temp_tables(self) -> None:
        """Drop the cash-basis substitute tables built by
        ``_prepare_lines_for_cash_basis``/``_prepare_lines_for_analytic_groupby_with_cash_basis``,
        and ``cash_basis_rp_moves``, the intermediate receivable/payable-move
        table the first builds.

        They are guarded to build at most once per transaction; call this to
        force a rebuild within the same transaction (e.g. a test modifying
        journal entries after already rendering a cash-basis report). The
        tables are a pure function of the journal data — rendering again with
        different options only does not require a rebuild.
        """
        for table in (
            "cash_basis_temp_account_move_line",
            "analytic_cash_basis_temp_account_move_line",
            "cash_basis_rp_moves",
        ):
            self.env.cr.execute(SQL("DROP TABLE IF EXISTS %s", SQL.identifier(table)))

    @api.model
    def _prepare_lines_for_cash_basis(self) -> None:
        """Create the cash_basis_temp_account_move_line substitute table.

        Mirrors account_move_line, but with the date and the amounts restated on
        a cash basis. Call it before any report query reading account_move_line
        in cash basis mode.
        """
        self.env.cr.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name='cash_basis_temp_account_move_line'"
            "   AND table_schema::regnamespace = pg_my_temp_schema()"
        )
        if self.env.cr.fetchone():
            return

        all_fields = set(get_table_columns(self.env.cr, "account_move_line"))
        changed_fields = [
            "date",
            "amount_currency",
            "amount_residual",
            "balance",
            "debit",
            "credit",
        ]
        unchanged_fields = list(all_fields - set(changed_fields))
        query = SQL(
            """   -- Create a temporary table
            -- LIKE, not INHERITS: a child table's rows are returned by every plain
            -- "FROM account_move_line" of the transaction, the ORM's included, so each
            -- journal item read after a cash-basis render came back twice.
            CREATE TEMPORARY TABLE IF NOT EXISTS cash_basis_temp_account_move_line (LIKE account_move_line) ON COMMIT DROP;

            -- Moves carrying at least one receivable/payable line, computed once and
            -- reused by both INSERTs below instead of repeating the join twice.
            CREATE TEMPORARY TABLE cash_basis_rp_moves ON COMMIT DROP AS
                SELECT DISTINCT aml.move_id AS id
                FROM ONLY account_move_line aml
                JOIN account_account account ON aml.account_id = account.id
                WHERE account.account_type IN ('asset_receivable', 'liability_payable');

            INSERT INTO cash_basis_temp_account_move_line (%(all_fields)s) SELECT
                %(unchanged_fields)s,
                "account_move_line".date,
                "account_move_line".amount_currency,
                "account_move_line".amount_residual,
                "account_move_line".balance,
                "account_move_line".debit,
                "account_move_line".credit
            FROM ONLY account_move_line
            WHERE (
                "account_move_line".journal_id IN (SELECT id FROM account_journal WHERE type in ('cash', 'bank'))
                OR "account_move_line".move_id NOT IN (SELECT id FROM cash_basis_rp_moves)
            );

            WITH payment_table AS (
                SELECT
                    aml.move_id,
                    aml.account_id,
                    GREATEST(aml.date, aml2.date) AS date,
                    CASE WHEN (aml.balance = 0 OR sub_aml.total_per_account = 0)
                        THEN 0
                        ELSE part.amount / ABS(sub_aml.total_per_account)
                    END as matched_percentage,
                    CASE WHEN (aml.balance = 0 OR sub_aml_2.total_per_move = 0)
                        THEN 0
                        ELSE ABS(sub_aml.total_per_account) / ABS(sub_aml_2.total_per_move)
                    END as move_percentage
                FROM account_partial_reconcile part
                JOIN ONLY account_move_line aml ON aml.id = part.debit_move_id OR aml.id = part.credit_move_id
                JOIN ONLY account_move_line aml2 ON
                    (aml2.id = part.credit_move_id OR aml2.id = part.debit_move_id)
                    AND aml.id != aml2.id
                JOIN (
                    SELECT move_id, account_id, SUM(ABS(balance)) AS total_per_account
                    FROM ONLY account_move_line account_move_line
                    GROUP BY move_id, account_id
                ) sub_aml ON (aml.account_id = sub_aml.account_id AND aml.move_id=sub_aml.move_id)
                JOIN (
                    SELECT move_id, SUM(ABS(balance)) AS total_per_move
                    FROM ONLY account_move_line aml_total
                    JOIN account_account account_total ON aml_total.account_id = account_total.id
                    WHERE account_total.account_type IN ('asset_receivable', 'liability_payable')
                    GROUP BY move_id
                ) sub_aml_2 ON (aml.move_id = sub_aml_2.move_id)
                JOIN account_account account ON aml.account_id = account.id
                WHERE account.account_type IN ('asset_receivable', 'liability_payable')
            )
            INSERT INTO cash_basis_temp_account_move_line (%(all_fields)s) SELECT
                %(unchanged_fields)s,
                ref.date,
                CASE WHEN "account".id = ref.account_id
                    THEN ref.matched_percentage * "account_move_line".amount_currency
                    ELSE ref.matched_percentage * "account_move_line".amount_currency * ref.move_percentage
                END,
                CASE WHEN "account".id = ref.account_id
                    THEN ref.matched_percentage * "account_move_line".amount_residual
                    ELSE ref.matched_percentage * "account_move_line".amount_residual * ref.move_percentage
                END,
                CASE WHEN "account".id = ref.account_id
                    THEN ref.matched_percentage * "account_move_line".balance
                    ELSE ref.matched_percentage * "account_move_line".balance * ref.move_percentage
                END,
                CASE WHEN "account".id = ref.account_id
                    THEN ref.matched_percentage * "account_move_line".debit
                    ELSE ref.matched_percentage * "account_move_line".debit * ref.move_percentage
                END,
                CASE WHEN "account".id = ref.account_id
                    THEN ref.matched_percentage * "account_move_line".credit
                    ELSE ref.matched_percentage * "account_move_line".credit * ref.move_percentage
                END
            FROM payment_table ref
            JOIN ONLY account_move_line account_move_line ON "account_move_line".move_id = ref.move_id
            JOIN account_account account ON "account".id = "account_move_line".account_id
            WHERE NOT (
                "account_move_line".journal_id IN (SELECT id FROM account_journal WHERE type in ('cash', 'bank'))
                OR "account_move_line".move_id NOT IN (SELECT id FROM cash_basis_rp_moves)
            )
            AND ("account".id = ref.account_id OR "account".account_type NOT IN ('asset_receivable', 'liability_payable'));

            -- Create an composite index to avoid seq.scan
            CREATE INDEX IF NOT EXISTS cash_basis_temp_account_move_line_composite_idx on cash_basis_temp_account_move_line(date, journal_id, company_id, parent_state);
            -- Update statistics for correct planning
            ANALYZE cash_basis_temp_account_move_line;
        """,
            all_fields=SQL(", ").join(
                SQL.identifier(f) for f in (unchanged_fields + changed_fields)
            ),
            unchanged_fields=SQL(", ").join(
                SQL.identifier("account_move_line", f) for f in unchanged_fields
            ),
        )
        self.env.cr.execute(query)

    @api.model
    def _prepare_lines_for_analytic_groupby_with_cash_basis(self) -> None:
        """Create the analytic_cash_basis_temp_account_move_line substitute table.

        Mirrors account_move_line, filled from account_analytic_line joined to
        cash_basis_temp_account_move_line. Call it before any report query
        reading account_move_line for the analytic columns in cash basis mode.
        """

        self.env.cr.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name='analytic_cash_basis_temp_account_move_line'"
            "   AND table_schema::regnamespace = pg_my_temp_schema()"
        )
        if self.env.cr.fetchone():
            return

        stored_fields = {
            fld
            for fld in get_table_columns(self.env.cr, "account_move_line")
            if fld in self.env["account.move.line"]._fields
        }
        # Take the amounts from the analytic lines, prorated by the paid portion
        # already applied in cash_basis_temp_account_move_line.
        changed_equivalence_dict = {
            "balance": SQL(
                "CASE WHEN aml.balance != 0 THEN -aal.amount * cash_basis_aml.balance / aml.balance ELSE 0 END"
            ),
            "amount_currency": SQL(
                "CASE WHEN aml.amount_currency != 0 THEN -aal.amount * cash_basis_aml.amount_currency / aml.amount_currency ELSE 0 END"
            ),
            "amount_residual": SQL(
                "CASE WHEN aml.amount_residual != 0 THEN -aal.amount * cash_basis_aml.amount_residual / aml.amount_residual ELSE 0 END"
            ),
            "date": SQL("cash_basis_aml.date"),
            "account_id": SQL("aal.general_account_id"),
            "partner_id": SQL("aal.partner_id"),
            "debit": SQL(
                "CASE WHEN (aml.balance < 0) THEN -aal.amount * cash_basis_aml.balance / aml.balance ELSE 0 END"
            ),
            "credit": SQL(
                "CASE WHEN (aml.balance > 0) THEN -aal.amount * cash_basis_aml.balance / aml.balance ELSE 0 END"
            ),
        }

        selected_fields = []
        for fname in stored_fields:
            if fname in changed_equivalence_dict:
                selected_fields.append(
                    SQL(
                        "%s AS %s",
                        changed_equivalence_dict[fname],
                        SQL.identifier(fname),
                    )
                )
            elif fname == "analytic_distribution":
                project_plan, other_plans = self.env[
                    "account.analytic.plan"
                ]._get_all_plans()
                analytic_cols = SQL(", ").join(
                    SQL.identifier("aal", n._column_name())
                    for n in (project_plan + other_plans)
                )
                selected_fields.append(
                    SQL(
                        'to_jsonb(UNNEST(ARRAY_REMOVE(ARRAY[%s], NULL))) AS "analytic_distribution"',
                        analytic_cols,
                    )
                )
            else:
                selected_fields.append(
                    SQL("aml.%s AS %s", SQL.identifier(fname), SQL.identifier(fname))
                )

        query = SQL(
            """
            -- Create a temporary table
            CREATE TEMPORARY TABLE IF NOT EXISTS analytic_cash_basis_temp_account_move_line (LIKE account_move_line) ON COMMIT DROP;

            INSERT INTO analytic_cash_basis_temp_account_move_line (%s)
            SELECT %s
            FROM ONLY cash_basis_temp_account_move_line cash_basis_aml
            JOIN ONLY account_move_line aml ON aml.id = cash_basis_aml.id
            JOIN account_analytic_line aal ON aml.id = aal.move_line_id;

            -- Create a supporting index to avoid seq.scans
            CREATE INDEX IF NOT EXISTS analytic_cash_basis_temp_account_move_line__composite_idx ON analytic_cash_basis_temp_account_move_line (analytic_distribution, journal_id, date, company_id);
            -- Update statistics for correct planning
            ANALYZE analytic_cash_basis_temp_account_move_line
        """,
            SQL(", ").join(SQL.identifier(field_name) for field_name in stored_fields),
            SQL(", ").join(selected_fields),
        )

        self.env.cr.execute(query)

    def _get_report_query(self, options, date_scope, domain=None) -> Query:
        # The context key triggers the account_move_line table shadowing in AccountMoveLine._search.
        context_self = self.with_context(
            account_report_cash_basis=options.get("report_cash_basis")
        )
        return super(AccountReport, context_self)._get_report_query(
            options, date_scope, domain=domain
        )

    def action_audit_cell(self, options, params):
        action = super().action_audit_cell(options, params)
        # Only add the domain on the correct model (e.g. can be an account.analytic.line).
        if (
            options.get("report_cash_basis")
            and action["res_model"] == "account.move.line"
        ):
            action["domain"] = Domain(action["domain"]) & Domain(
                "move_id.impacting_cash_basis", "=", True
            )
        return action

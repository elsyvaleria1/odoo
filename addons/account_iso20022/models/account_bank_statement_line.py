from odoo import SUPERUSER_ID, fields, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL

_debug = DebugLog(__name__)


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    end_to_end_uuid = fields.Char(
        string="End to End ID",
        help="Unique end-to-end assigned by the initiating party",
    )

    @_debug.perf.timed
    def _match_end_to_end_uuid(self, st_move_ids, account_ids) -> set:
        processed_st_line_ids = super()._match_end_to_end_uuid(st_move_ids, account_ids)
        candidate_ids = (
            set(self.filtered("end_to_end_uuid").ids) - processed_st_line_ids
        )
        _debug.logic(
            "end_to_end_uuid_candidates",
            automatch=self,
            candidates=len(candidate_ids),
        )
        if not candidate_ids:
            return processed_st_line_ids

        self.env.cr.execute(
            SQL(
                """
                -- Query to get either payment amls either invoice/bill amls related to payments which have
                -- the same end to end uuid of bank statement lines.
                SELECT
                    st_line.id AS st_line_id,
                    ARRAY_AGG(aml.id ORDER BY aml.id ASC) AS aml_ids
                FROM account_bank_statement_line st_line
                JOIN account_payment payment ON st_line.end_to_end_uuid = payment.end_to_end_uuid
                JOIN account_move_line aml ON (
                    payment.move_id = aml.move_id
                    OR aml.move_id IN (
                        SELECT move_payment_rel.invoice_id
                        FROM account_move__account_payment move_payment_rel
                        WHERE move_payment_rel.payment_id = payment.id
                    )
                )
                LEFT JOIN res_company aml_company ON aml_company.id = aml.company_id
                LEFT JOIN res_company payment_company ON payment_company.id = payment.company_id
                LEFT JOIN res_company st_line_company ON st_line_company.id = st_line.company_id
                WHERE
                    aml.move_id != ALL(%(st_move_ids)s)
                    AND %(aml_and_payment_related)s
                    AND %(st_line_and_payment_related)s
                    AND aml.reconciled IS NOT TRUE
                    AND aml.account_id = ANY(%(account_ids)s)
                    AND ((st_line.amount > 0 AND aml.balance > 0) OR (st_line.amount < 0 AND aml.balance < 0))
                    AND aml.parent_state in ('draft', 'posted')
                    AND st_line.id = ANY(%(st_line_ids)s)
                GROUP BY st_line.id
                ORDER BY st_line.id
                """,
                st_move_ids=list(st_move_ids),
                account_ids=list(account_ids),
                st_line_ids=list(candidate_ids),
                aml_and_payment_related=self._same_company_hierarchy_sql(
                    "aml_company", "payment_company"
                ),
                st_line_and_payment_related=self._same_company_hierarchy_sql(
                    "st_line_company", "payment_company"
                ),
            )
        )
        _debug.perf.count("end_to_end_amls_fetched", rows=self.env.cr.rowcount)

        for st_line_id, aml_ids in self.env.cr.fetchall():
            st_line = self.browse(st_line_id).with_prefetch(self._prefetch_ids)
            st_line.with_company(st_line.company_id).with_user(
                SUPERUSER_ID
            ).set_line_bank_statement_line(aml_ids)
            processed_st_line_ids.add(st_line_id)
            candidate_ids.discard(st_line_id)

        _debug.pipeline(
            "end_to_end_amls_matched",
            automatch=self,
            matched=len(processed_st_line_ids),
        )
        if not candidate_ids:
            return processed_st_line_ids

        self.env.cr.execute(
            SQL(
                """
                SELECT
                    st_line.id as st_line_id,
                    payment.id as payment_id
                FROM account_bank_statement_line st_line
                JOIN account_payment payment ON st_line.end_to_end_uuid = payment.end_to_end_uuid
                LEFT JOIN res_company st_line_company ON st_line_company.id = st_line.company_id
                LEFT JOIN res_company payment_company ON payment_company.id = payment.company_id
                WHERE
                    st_line.id = ANY(%(st_line_ids)s)
                    AND %(st_line_and_payment_related)s
                    AND (
                            (st_line.amount > 0 AND payment.payment_type = 'inbound')
                        OR (st_line.amount < 0 AND payment.payment_type = 'outbound')
                    )
                    AND payment.state = ANY(%(payment_state)s)
                ORDER BY st_line.id, payment.id
                """,
                st_line_ids=list(candidate_ids),
                st_line_and_payment_related=self._same_company_hierarchy_sql(
                    "st_line_company", "payment_company"
                ),
                payment_state=[
                    "draft",
                    *self.env["account.payment"]._valid_payment_states(),
                ],
            )
        )
        _debug.perf.count("end_to_end_payments_fetched", rows=self.env.cr.rowcount)
        for st_line_id, payment_id in self.env.cr.fetchall():
            st_line = self.browse(st_line_id).with_prefetch(self._prefetch_ids)
            payment = (
                self.env["account.payment"].browse(payment_id).with_user(SUPERUSER_ID)
            )
            amls_to_create = payment.with_company(
                st_line.company_id
            )._get_amls_for_payment_without_move(date=st_line.date)
            st_line.with_company(st_line.company_id).with_user(
                SUPERUSER_ID
            )._reconcile_with_payments(payment, amls_to_create)
            processed_st_line_ids.add(st_line_id)
        _debug.pipeline(
            "end_to_end_payments_matched",
            automatch=self,
            processed=len(processed_st_line_ids),
        )
        return processed_st_line_ids

import contextlib
import re

import psycopg.errors

from odoo import api, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)

_PRODUCT_PREDICTION_QUERY = """
SELECT
    max(f.rel) AS ranking,
    f.product_id,
    count(coalesce(f.product_id, 1)) AS count
FROM (
    SELECT
        p_search.product_id,
        ts_rank(p_search.document, query_plain) AS rel
    FROM (
        SELECT
            expense.product_id,
            (setweight(to_tsvector(%(lang)s, expense.name), 'B'))
            AS document
        FROM hr_expense expense
        WHERE expense.state IN ('paid', 'in_payment', 'posted')
            AND expense.company_id = %(company_id)s
        ORDER BY expense.date DESC, expense.id DESC
        LIMIT %(limit_parameter)s
    ) p_search,
    to_tsquery(%(lang)s, %(description)s) query_plain
    WHERE (p_search.document @@ query_plain)
) AS f
JOIN product_product p ON p.id = f.product_id AND p.active
GROUP BY f.product_id
ORDER BY ranking desc, count desc
"""


class HrExpense(models.Model):
    _inherit = "hr.expense"

    def _get_predict_postgres_dictionary(self):
        lang = self.env.context.get("lang") and self.env.context.get("lang")[:2]
        return {"fr": "french"}.get(lang, "english")

    def _predict_product(self, description):
        if not description:
            _debug.logic("expense_product_prediction_skipped", reason="no_description")
            return False
        psql_lang = self._get_predict_postgres_dictionary()
        parsed_description = re.sub(r"[*&()|!':<]+", " ", description)
        parsed_description = " | ".join(parsed_description.split())
        limit_parameter = self.env.registry.settings.get_int(
            self.env, "expense.predict.history.limit", 10000
        )
        params = {
            "lang": psql_lang,
            "description": parsed_description,
            "company_id": self.company_id.id or self.env.company.id,
            "limit_parameter": limit_parameter,
        }
        # In case there is an error while parsing the to_tsquery (wrong character for example)
        # We don't want to have a traceback, instead return False
        parsed = False  # debuglog
        with contextlib.suppress(psycopg.errors.SyntaxError):
            with self.env.cr.savepoint():
                with _debug.perf(
                    "hr_expense.predict_product",
                    history_limit=params["limit_parameter"],
                ):
                    self.env.cr.execute(_PRODUCT_PREDICTION_QUERY, params)
                result = self.env.cr.fetchone()
            parsed = True  # debuglog
            if result:
                _debug.logic(
                    "expense_product_predicted",
                    description=parsed_description,
                    ranking=result[0],
                    product=result[1],
                )
                return result[1]

        _debug.logic(
            "expense_product_not_predicted",
            reason="no_match" if parsed else "tsquery_syntax_error",
            description=parsed_description,
            company=params["company_id"],
        )
        return False

    @api.onchange("name")
    def _onchange_predict_product(self) -> None:
        if self.name and not self.product_id:
            predicted_product_id = self._predict_product(self.name)
            default_product = self.env["product.product"].search(
                [("can_be_expensed", "=", True)]
            )
            _debug.pipeline(
                "expense_product_onchange",
                expense=self,
                predicted=predicted_product_id,
                expensable_products=default_product,
            )
            if default_product:
                default_product = (
                    default_product.filtered(lambda p: p.default_code == "EXP_GEN")[:1]
                    or default_product[0]
                )
                self.product_id = predicted_product_id or default_product

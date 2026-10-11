from odoo import api, models
from odoo.tools.safe_eval import datetime as safe_datetime
from odoo.tools.safe_eval import safe_eval



class ReportAccount_TestReport_Accounttest(models.AbstractModel):
    _name = "report.account_test.report_accounttest"
    _description = "Account Test Report"

    @api.model
    def _execute_code(self, code_exec):
        def reconciled_inv():
            return self.env["account.move"].search([("reconciled", "=", True)]).ids

        def order_columns(item, cols=None):
            if cols is None:
                cols = list(item)
            return [(col, item.get(col)) for col in cols if col in item]

        context = {
            "cr": self.env.cr,
            "uid": self.env.uid,
            "reconciled_inv": reconciled_inv,
            "result": None,
            "column_order": None,
            "_": self.env._,
        }
        safe_eval(code_exec, context, mode="exec")
        result = context["result"]
        column_order = context.get("column_order")

        if not isinstance(result, (tuple, list, set)):
            result = [result]
        if not result:
            result = [self.env._("The test was passed successfully")]
        else:

            def _format(item):
                if isinstance(item, dict):
                    return ", ".join(
                        [
                            "%s: %s" % (tup[0], tup[1])
                            for tup in order_columns(item, column_order)
                        ]
                    )
                else:
                    return item

            result = [_format(rec) for rec in result]

        return result

    @api.model
    def _get_report_values(self, docids, data=None):
        return {
            "doc_ids": docids,
            "doc_model": "accounting.assert.test",
            "docs": self.env["accounting.assert.test"].browse(docids),
            "data": data,
            "execute_code": self._execute_code,
            "datetime": safe_datetime,
        }

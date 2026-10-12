import contextlib

import psycopg

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.base_import.models.base_import import FIELDS_RECURSION_LIMIT


class Base_ImportImport(models.TransientModel):
    _inherit = "base_import.import"

    @api.model
    def get_fields_tree(self, model, depth=FIELDS_RECURSION_LIMIT):
        fields_list = super().get_fields_tree(model, depth=depth)
        if model == "account.bank.statement.line" and self.env.context.get(
            "bank_stmt_import", False
        ):
            fields_list.append(
                {
                    "id": "balance",
                    "name": "balance",
                    "string": "Cumulative Balance",
                    "required": False,
                    "fields": [],
                    "type": "monetary",
                    "model_name": model,
                }
            )
        return fields_list

    def _convert_to_float(self, value):
        return float(value) if value else 0.0

    def _parse_import_data(self, data, import_fields, options):
        data = super()._parse_import_data(data, import_fields, options)
        journal_id = self.env.context.get("default_journal_id")
        bank_stmt_import = options.get("bank_stmt_import")
        if not journal_id or not bank_stmt_import:
            return data
        if not data:
            return data

        has_amount = "amount" in import_fields
        has_credit = "credit" in import_fields
        has_debit = "debit" in import_fields
        has_debit_credit_pair = has_debit and has_credit
        if (has_debit ^ has_credit) or not (has_amount ^ has_debit_credit_pair):
            raise ValidationError(
                self.env._(
                    "Make sure that an Amount or Debit and Credit is in the file."
                )
            )
        statement_vals = options["statement_vals"] = {}
        ret_data = []

        import_fields.append("sequence")
        index_balance = None
        convert_to_amount = False

        if "date" in import_fields:
            index_date = import_fields.index("date")
            if any(not line[index_date] for line in data):
                raise UserError(
                    self.env._(
                        "Every row must have a date. A row without one cannot be placed in the statement's balance sequence."
                    )
                )
            dates = [fields.Date.from_string(line[index_date]) for line in data]
            sorted_dates_asc = sorted(dates)
            if dates != sorted_dates_asc:
                sorted_dates_desc = sorted_dates_asc[::-1]
                if dates == sorted_dates_desc:
                    data = data[::-1]
                else:
                    raise UserError(self.env._("Rows must be sorted by date."))

        if "debit" in import_fields and "credit" in import_fields:
            index_debit = import_fields.index("debit")
            index_credit = import_fields.index("credit")
            self._parse_float_from_data(data, index_debit, "debit", options)
            self._parse_float_from_data(data, index_credit, "credit", options)
            import_fields.append("amount")
            convert_to_amount = True

        if "balance" in import_fields:
            index_balance = import_fields.index("balance")
            self._parse_float_from_data(data, index_balance, "balance", options)
            statement_vals["balance_start"] = self._convert_to_float(
                data[0][index_balance]
            )
            statement_vals["balance_start"] -= (
                self._convert_to_float(data[0][import_fields.index("amount")])
                if not convert_to_amount
                else abs(self._convert_to_float(data[0][index_credit]))
                - abs(self._convert_to_float(data[0][index_debit]))
            )
            statement_vals["balance_end_real"] = self._convert_to_float(
                data[-1][index_balance]
            )
            import_fields.remove("balance")

        if convert_to_amount:
            import_fields.remove("debit")
            import_fields.remove("credit")

        index_amount = import_fields.index("amount")
        for sequence, line in enumerate(data):
            line.append(sequence)
            remove_index = []
            if convert_to_amount:
                line.append(
                    abs(self._convert_to_float(line[index_credit]))
                    - abs(self._convert_to_float(line[index_debit]))
                )
                remove_index.extend([index_debit, index_credit])
            if index_balance is not None:
                remove_index.append(index_balance)
            for removed_index in sorted(remove_index, reverse=True):
                del line[removed_index]
            if line[index_amount]:
                ret_data.append(line)

        return ret_data

    def parse_preview(self, options, count=10):
        if options.get("bank_stmt_import", False):
            self = self.with_context(bank_stmt_import=True)
        return super().parse_preview(options, count=count)

    def execute_import(self, fields, columns, options, dryrun=False):
        if options.get("bank_stmt_import"):
            savepoint = self.env.cr.savepoint()
            try:
                res = super(
                    Base_ImportImport,
                    self.with_context(
                        bank_stmt_import=True, auto_statement_processing=not dryrun
                    ),
                ).execute_import(fields, columns, options, dryrun=dryrun)
                if not dryrun and "statement_id" not in fields and res.get("ids"):
                    self.env["account.bank.statement"].with_context(
                        import_file=True,
                        auto_statement_processing=True,
                    ).create(
                        {
                            "reference": self.file_name,
                            "line_ids": [Command.set(res.get("ids", []))],
                            **options.get("statement_vals", {}),
                        }
                    )
            finally:
                with contextlib.suppress(psycopg.InternalError):
                    savepoint.close(rollback=dryrun)
            return res
        else:
            return super().execute_import(fields, columns, options, dryrun=dryrun)

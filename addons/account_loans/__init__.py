import csv
import io
from dateutil.relativedelta import relativedelta

from odoo import fields

from . import models
from . import wizards


def _account_loans_post_init(env) -> None:
    if env.ref("base.module_account_loans").demo:
        _account_loans_import_loan_demo(
            env,
            env.ref("account_loans.account_loans_loan_demo1"),
            env.ref("account_loans.account_loans_loan_demo_file_csv"),
        )

        _account_loans_import_loan_demo(
            env,
            env.ref("account_loans.account_loans_loan_demo2"),
            env.ref("account_loans.account_loans_loan_demo_file_xlsx"),
        )


def _account_loans_add_date_column(csv_attachment):
    data = io.StringIO()
    writer = csv.writer(data, delimiter=",")
    reader = csv.reader(
        io.StringIO(csv_attachment.raw.decode()), quotechar='"', delimiter=","
    )
    current_date = fields.Date.today() - relativedelta(years=1)
    for i, row in enumerate(reader):
        if i == 0:
            row.insert(0, "Date")
        else:
            row.insert(0, current_date.strftime("%Y-%m-%d"))
            current_date += relativedelta(months=1)
        writer.writerow(row)
    data.seek(0)
    generated_file = data.read()
    data.close()
    csv_attachment.raw = generated_file.encode()
    return csv_attachment


def _account_loans_import_loan_demo(env, loan, attachment) -> None:
    if attachment.mimetype == "text/csv":
        attachment = _account_loans_add_date_column(attachment)
    action = loan.action_upload_amortization_schedule(attachment.id)
    import_wizard = env["base_import.import"].browse(
        action.get("params", {}).get("context", {}).get("wizard_id")
    )
    result = import_wizard.parse_preview(
        {
            "quoting": '"',
            "separator": ",",
            "date_format": "%Y-%m-%d",
            "has_headers": True,
        }
    )
    import_wizard.with_context(default_loan_id=loan.id).execute_import(
        ["date", "principal", "interest"],
        [],
        result.get("options", {}),
    )
    loan.action_file_uploaded()

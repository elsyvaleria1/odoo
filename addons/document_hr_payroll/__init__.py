from . import models


def _documents_hr_payroll_post_init(env) -> None:
    for company in env["res.company"].search([]):
        company._apply_payslip_documents_settings()

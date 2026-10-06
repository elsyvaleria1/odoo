from . import models


def _documents_hr_payroll_post_init(env) -> None:
    """Backfill the companies that already existed when the module was installed.

    document_hr calls _generate_employee_documents_main_folders only from
    res.company.create and from its own post-init, so without this hook every
    company created before this module was installed keeps an empty
    documents_hr_payslips_tags and grants payroll users no access to its
    employee folder.

    The settings are applied to the folder each company already has: calling
    the override itself would create a second employee folder and orphan the
    first one, along with the employee subfolders under it.
    """
    for company in env["res.company"].search([]):
        company._apply_payslip_documents_settings()

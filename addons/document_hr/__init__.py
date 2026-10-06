from . import models


def _documents_hr_post_init(env) -> None:
    env["res.company"].search([])._generate_employee_documents_main_folders()
    env["hr.employee"].search(
        [("hr_employee_folder_id", "=", False)]
    )._create_employee_documents_folders()

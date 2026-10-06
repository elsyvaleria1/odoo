from . import models
from . import reports
from . import controllers
from . import wizards


def create_field_service_project(env) -> None:
    fsm_project = env.ref("industry_fsm.fsm_project", raise_if_not_found=False)
    project_vals = (
        env["res.company"]
        .search([("id", "!=", fsm_project.company_id.id)])
        ._prepare_field_service_project_vals_list()
    )
    env["project.project"].create(project_vals)

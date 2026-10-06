from . import models
from . import reports
from . import controllers
from . import wizards


def post_init(env) -> None:
    env["project.project"].search([("is_fsm", "=", True)]).write(
        {"allow_worksheets": True}
    )
    fsm_project = env.ref("industry_fsm.fsm_project", raise_if_not_found=False)
    fsm_worksheet_template2 = env.ref(
        "industry_fsm_report.fsm_worksheet_template2", raise_if_not_found=False
    )
    if fsm_project:
        template_id = fsm_worksheet_template2 or env.ref(
            "industry_fsm_report.fsm_worksheet_template"
        )
        fsm_project.write(
            {
                "worksheet_template_id": template_id.id,
            }
        )

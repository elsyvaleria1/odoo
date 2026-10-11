from . import controllers
from . import models
from . import reports
from . import wizards


def post_init(env) -> None:
    env["project.project"].search([("is_fsm", "=", True)]).write(
        {
            "allow_billable": True,
            "allow_material": True,
            "allow_timesheets": True,
            "timesheet_product_id": env.ref("sale_timesheet.time_product"),
        }
    )


def uninstall_hook(env):
    pass

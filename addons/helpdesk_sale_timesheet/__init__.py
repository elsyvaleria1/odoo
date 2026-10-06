from . import controllers
from . import models
from . import wizards
from . import reports


def _helpdesk_sale_timesheet_post_init(env) -> None:
    teams = env["team.team"].search(
        [
            ("use_helpdesk_timesheet", "=", True),
            ("use_helpdesk_sale_timesheet", "=", True),
        ]
    )

    projects = teams.filtered(
        lambda team: team.project_id and not team.project_id.allow_billable
    ).mapped("project_id")
    # sale_timesheet's _compute_timesheet_product_id fills the product once
    # billing is on, and keeps one the project already chose.
    projects.write({"allow_billable": True})

    without_project = teams.filtered(lambda team: not team.project_id)
    tickets = env["helpdesk.ticket"].search(
        [("team_id", "in", without_project.ids), ("project_id", "=", False)]
    )
    for team in without_project:
        team.project_id = team._create_project(
            team.name, team.use_helpdesk_sale_timesheet, {"allow_timesheets": True}
        )
        tickets.filtered(lambda ticket, t=team: ticket.team_id == t).write(
            {"project_id": team.project_id.id}
        )

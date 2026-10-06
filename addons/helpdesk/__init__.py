from . import controllers
from . import models
from . import reports
from . import wizards


def _create_helpdesk_team(env):
    team_1 = env.ref("helpdesk.helpdesk_team1", raise_if_not_found=False)
    env["res.company"].search(
        [("id", "!=", team_1.company_id.id)]
    )._create_helpdesk_team()

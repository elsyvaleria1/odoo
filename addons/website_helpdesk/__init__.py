from odoo import Command

from . import controllers
from . import models


HELPDESK_PUBLIC_DOMAIN = "[('use_helpdesk', '=', True)]"
PUBLISHED_PUBLIC_DOMAIN = (
    "[('use_helpdesk', '=', True), ('website_published', '=', True)]"
)


def _narrow_public_team_rule(env, domain) -> None:
    access = env.ref("helpdesk.helpdesk_team_public_rule", raise_if_not_found=False)
    if access:
        access.sudo().write({"domain": domain, "active": True})


def _restore_public_team_rule(env) -> None:
    _narrow_public_team_rule(env, HELPDESK_PUBLIC_DOMAIN)


def _configure_teams(env) -> None:
    _narrow_public_team_rule(env, PUBLISHED_PUBLIC_DOMAIN)
    team = env["team.team"].search(
        [("use_helpdesk", "=", True), ("helpdesk_privacy_visibility", "=", "portal")],
        limit=1,
    )
    if team:
        team.use_website_helpdesk_form = True
    else:
        team = env["team.team"].create(
            {
                "use_helpdesk": True,
                "name": env._("Customer Care (Public)"),
                "helpdesk_stage_ids": False,
                "helpdesk_use_sla": True,
                "member_ids": [Command.link(env.ref("base.user_admin").id)],
                "use_website_helpdesk_form": True,
            }
        )
    team.is_published = True
    team._create_missing_website_menu()

    teams = env["team.team"].search([("use_website_helpdesk_form", "=", True)])
    teams._create_missing_submit_form_view()

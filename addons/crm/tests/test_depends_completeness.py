
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCrmTeamDependsCompleteness(TransactionCase):
    def test_team_computes_declare_what_they_read(self):
        team = self.env["team.team"].create({"use_sale": True, "name": "Depends probe"})
        self.env["team.member"].create(
            {
                "team_id": team.id,
                "user_id": self.env.ref("base.user_admin").id,
                "lead_assignment_max": 30,
            }
        )
        self.assertDependsComplete(
            team,
            computed_fields=["dashboard_button_name", "lead_assignment_max"],
            probe_fields=["use_opportunities", "active", "name"],
        )

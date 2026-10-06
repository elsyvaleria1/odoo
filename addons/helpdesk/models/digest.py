from odoo import fields, models
from odoo.exceptions import AccessError


class DigestDigest(models.Model):
    _inherit = "digest.digest"

    kpi_helpdesk_tickets_closed = fields.Boolean(string="Tickets Closed")
    kpi_helpdesk_tickets_closed_value = fields.Integer(
        export_string_translation=False,
        compute="_compute_kpi_helpdesk_tickets_closed_value",
    )

    def _compute_kpi_helpdesk_tickets_closed_value(self) -> None:
        if not self.env.user.has_group("helpdesk.group_helpdesk_user"):
            raise AccessError(
                self.env._("Do not have access, skip this data for user's digest email")
            )

        self._update_company_based_kpi(
            "helpdesk.ticket",
            "kpi_helpdesk_tickets_closed_value",
            date_field="close_date",
        )

    def _get_kpi_actions(self, company, user):
        res = super()._get_kpi_actions(company, user)
        res["kpi_helpdesk_tickets_closed"] = (
            "helpdesk.helpdesk_team_dashboard_action_main?menu_id=%s"
            % self.env.ref("helpdesk.menu_helpdesk_root").id
        )
        return res

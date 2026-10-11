from odoo import Command, api, models


class ResCompany(models.Model):
    _inherit = "res.company"

    @api.model_create_multi
    def create(self, vals_list):
        company = super().create(vals_list)
        company._create_helpdesk_team()
        return company

    def _create_helpdesk_team(self):
        results = []
        stage_ids = []
        for xml_id in [
            "stage_new",
            "stage_in_progress",
            "stage_solved",
            "stage_cancelled",
            "stage_on_hold",
        ]:
            record = self.env.ref(f"helpdesk.{xml_id}", False)
            if record:
                stage_ids.append(record.id)
        team_name = self.env._("Customer Care")
        to_create_or_existing_aliases = set(
            self.env["team.team"]
            .search([("use_helpdesk", "=", True)])
            .mapped("helpdesk_alias_name")
        )

        for company in self:
            alias_name = f"{team_name}-{company.name}"
            sanitized_alias_name = self.env["mail.alias"]._normalize_alias_name(
                alias_name
            )

            if sanitized_alias_name in to_create_or_existing_aliases:
                alias_name = f"{sanitized_alias_name}-{company.id}"
            to_create_or_existing_aliases.add(sanitized_alias_name)
            company = company.with_company(company)
            results += [
                {
                    "use_helpdesk": True,
                    "name": team_name,
                    "company_id": company.id,
                    "helpdesk_use_sla": False,
                    "helpdesk_stage_ids": [Command.set(stage_ids)],
                    "helpdesk_alias_name": alias_name,
                }
            ]
        return self.env["team.team"].sudo().create(results)

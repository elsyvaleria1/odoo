from odoo import Command, api, models
from odoo.libs.json import dumps as json_dumps
from odoo.tools import html_sanitize


class CrmLead(models.Model):
    _inherit = "crm.lead"

    @api.model
    def _ai_create_lead(
        self,
        name,
        contact_name,
        description,
        email,
        phone,
        team_id,
        tag_ids,
        priority,
        country_id=False,
        state_id=False,
        city=False,
        zip_code=False,
        street=False,
        job_position=False,
    ) -> str:
        self.create(
            self._ai_prepare_lead_creation_values(
                {
                    "name": name,
                    "description": html_sanitize(description),
                    "team_id": team_id,
                    "tag_ids": tag_ids,
                    "priority": priority,
                    "partner_info": {
                        "contact_name": contact_name,
                        "function": job_position,
                        "email": email,
                        "phone_ids": [
                            Command.create({"number": phone, "type": "landline"})
                        ]
                        if phone
                        else False,
                        "country_id": country_id,
                        "state_id": state_id,
                        "city": city,
                        "zip": zip_code,
                        "street": street,
                    },
                }
            )
        )
        return "Success"

    @api.model
    def _ai_get_lead_create_available_params(self, country_code=None):
        teams, __ = (
            self.env["team.team"]
            .search([("use_sale", "=", True)])
            ._ai_read(["display_name"], None)
        )
        tags, __ = self.env["crm.tag"].search([])._ai_read(["display_name"], None)
        response = "⚠️ Never share the info below with the user. It can only by used by you when creating a lead with the lead creation tool.\n"
        response += "Values are provided as {id: display name}. You **always** have to use the keys (ids) as values for the lead creation tool.\n"
        response += f"# Teams:\n{json_dumps(teams)}\n"
        response += f"# Tags:\n{json_dumps(tags)}\n"
        response += f"# Priorities:\n{dict(self._fields['priority']._selection)}\n"
        if country_code and (
            country := self.env["res.country"].search(
                [("code", "=", country_code)], limit=1
            )
        ):
            response += f"\n# Country:\n{{{country.id}: {country.name}}}\n"
            states, __ = (
                self.env["res.country.state"]
                .search([("country_id", "=", country.id)])
                ._ai_read(["display_name"], None)
            )
            response += f"# States:\n{json_dumps(states)}"
        return response

    @api.model
    def _ai_prepare_lead_creation_values(self, vals):
        values = {
            "name": vals["name"],
            "description": vals["description"],
            "medium_id": self.env.ref("utm.utm_medium_website").id,
            "source_id": self.env.context["discuss_channel"]
            .sudo()
            .ai_agent_id.source_id.id
            if self.env.context.get("discuss_channel")
            else False,
            "tag_ids": vals["tag_ids"],
            "team_id": vals["team_id"],
            "user_id": False,
            "priority": vals["priority"],
        }
        if self.env.user._is_public():
            values.update({k: v for k, v in vals["partner_info"].items() if v})
            if "email" in values:
                values["email_from"] = values.pop("email")
        else:
            partner = self.env.user.partner_id
            values["partner_id"] = partner.id
            address_fields = set(partner._address_fields())
            partner_fields = set(partner._fields)
            has_address = any(partner[fname] for fname in address_fields)
            new_partner_vals = {
                fname: val
                for fname, val in vals["partner_info"].items()
                if fname in partner_fields
                and not (fname in address_fields and has_address)
                and not partner[fname]
            }
            if new_partner_vals:
                partner.update(new_partner_vals)
        return values

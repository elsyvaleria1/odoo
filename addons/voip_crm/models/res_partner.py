from odoo import Command, models

from odoo.addons.mail.tools.discuss import Store


class ResPartner(models.Model):
    _name = "res.partner"
    _inherit = ["res.partner"]

    def get_view_opportunities_action(self, phone=None):
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "crm.crm_lead_opportunities"
        )
        if not self:
            action["views"] = [[False, "form"]]
            action["context"] = {
                "default_phone_ids": [
                    Command.create({"number": phone, "type": "mobile"})
                ]
                if phone
                else [],
            }
            return action
        self.check_singleton()
        action["context"] = {
            "search_default_filter_won": True,
            "search_default_filter_ongoing": True,
            "search_default_filter_lost": True,
            "active_test": False,
        }
        if self.opportunity_count == 0:
            action["views"] = [[False, "form"]]
            action["context"]["default_partner_id"] = self.id
            return action
        domain = self._get_domain_contact_opportunities()
        if self.opportunity_count == 1:
            action["views"] = [[False, "form"]]
            action["res_id"] = (
                self.env["crm.lead"]
                .with_context(active_test=False)
                .search(domain, limit=1)
                .id
            )
        else:
            action["domain"] = domain
        return action

    def _voip_get_store_fields(self) -> list:
        def can_read_opportunity_count(self) -> bool:
            return bool(self.env["crm.lead"].has_access("read"))

        return [
            *super()._voip_get_store_fields(),
            Store.Attr("opportunity_count", predicate=can_read_opportunity_count),
        ]

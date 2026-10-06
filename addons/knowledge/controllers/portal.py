from odoo.http import request

from odoo.addons.portal.controllers import portal


class KnowledgePortal(portal.CustomerPortal):
    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if "knowledge_count" in counters:
            values["knowledge_count"] = request.env["knowledge.article"].search_count(
                self._get_domain_knowledge_article()
            )
        return values

    def _get_domain_knowledge_article(self):
        """Generate the domain for the portal's articles"""
        return []

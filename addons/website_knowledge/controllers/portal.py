from odoo.addons.knowledge.controllers.portal import KnowledgePortal


class KnowledgePortalWebsite(KnowledgePortal):
    def _get_domain_knowledge_article(self):
        return [("user_has_access", "=", True)]

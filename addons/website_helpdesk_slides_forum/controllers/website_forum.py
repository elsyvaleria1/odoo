from odoo.addons.website_helpdesk_forum.controllers.website_forum import (
    WebsiteForumHelpdesk,
)


class WebsiteSlidesForumHelpdesk(WebsiteForumHelpdesk):
    def get_template_xml_id(self):
        return "website_helpdesk_slides_forum.helpdesk_forums"

from odoo import models


class WebsiteMenu(models.Model):
    _inherit = "website.menu"

    def _compute_is_visible(self):
        helpdesk_menus = self.filtered(
            lambda menu: menu.url and menu.url.startswith("/helpdesk")
        )
        other_menus = self - helpdesk_menus
        if not helpdesk_menus or self.env.user._is_internal():
            return super()._compute_is_visible()
        helpdesk_menu_data = (
            self.env["team.team"]
            .sudo()
            ._read_group(
                [("website_menu_id", "!=", False)],
                ["is_published"],
                ["website_menu_id:recordset"],
            )
        )
        for is_published, menus in helpdesk_menu_data:
            menu_urls = menus.mapped("url")
            matching_heldpesk_menus = helpdesk_menus.browse(
                [
                    menu.id
                    for menu in helpdesk_menus
                    if menu.url in menu_urls or menu in menus
                ]
            )
            matching_heldpesk_menus.is_visible = is_published
            helpdesk_menus -= matching_heldpesk_menus
        menu_per_helpdesk_team_id = {}
        for menu in helpdesk_menus:
            _dummy, helpdesk_team_id = self.env["ir.http"]._unslug(menu.url)
            if helpdesk_team_id:
                menu_per_helpdesk_team_id[helpdesk_team_id] = menu
        if menu_per_helpdesk_team_id:
            helpdesk_teams = (
                self.env["team.team"]
                .sudo()
                .search([("id", "in", list(menu_per_helpdesk_team_id.keys()))])
            )
            for team in helpdesk_teams:
                menu = menu_per_helpdesk_team_id[team.id]
                menu.is_visible = False
                helpdesk_menus -= menu
        super(WebsiteMenu, other_menus + helpdesk_menus)._compute_is_visible()
        return None

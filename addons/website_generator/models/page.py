import logging

from lxml import etree, html

from odoo import models

logger = logging.getLogger(__name__)


class WebsitePage(models.Model):
    _inherit = "website.page"

    def _update_homepage(self, homepage_data) -> None:
        self._update_page(homepage_data)
        self._create_footer(homepage_data)
        self._create_header(homepage_data)
        self._apply_website_themes(homepage_data)
        self._apply_user_values(homepage_data)

    def _update_page(self, page_data) -> None:
        html_block_list = page_data.get("body_html")
        if not html_block_list:
            return
        rendered_snippets = []
        nb_snippets = len(html_block_list)
        for i, snippet in enumerate(html_block_list, start=1):
            try:
                el = html.fromstring(snippet.replace("\ufeff", ""))

                if i == 1:
                    shape_el = el.xpath("//*[hasclass('o_we_shape')]")
                    if shape_el:
                        shape_el[0].attrib["class"] += " o_header_extra_shape_mapping"

                if i == nb_snippets:
                    shape_el = el.xpath("//*[hasclass('o_we_shape')]")
                    if shape_el:
                        shape_el[0].attrib["class"] += " o_footer_extra_shape_mapping"
                rendered_snippet = etree.tostring(el, encoding="unicode")
                rendered_snippets.append(rendered_snippet)
            except ValueError as e:
                logger.warning("Error rendering snippet: %s", e)
        self.view_id.save(
            value=f'<div class="oe_structure">{"".join(rendered_snippets)}</div>',
            xpath="(//div[hasclass('oe_structure')])[last()]",
        )

    def _create_header(self, homepage_data):
        self.env["website.menu"].search(
            [("website_id", "=", self.website_id.id)]
        ).unlink()

        top_menu = self.env["website.menu"].create(
            {
                "name": self.env._("Top Menu for Website %s", self.website_id.id),
                "url": "/default-main-menu",
                "website_id": self.website_id.id,
            }
        )
        for button in homepage_data.get("header", {}).get("buttons", []):
            if button.get("name", "").lower() in ["sign in", "contact us"]:
                continue
            menu_content = button.get("menu_content")
            if menu_content:
                menu_type = menu_content.get("type")
                if menu_type == "simple_menu":
                    parent_menu = self._create_menu(button, top_menu)
                    children_menus = button.get("menu_content", {}).get("content", [])
                    self.env["website.menu"].create(
                        [
                            {
                                "name": child_menu["name"],
                                "url": child_menu["href"],
                                "parent_id": parent_menu and parent_menu.id,
                                "website_id": self.website_id.id,
                            }
                            for child_menu in children_menus
                        ]
                    )
                elif menu_type == "mega_menu":
                    button_name = button.get("name")
                    button_href = button.get("href")
                    mega_menu_content = button.get("menu_content", {}).get("content")
                    if not button_name or not button_href or not mega_menu_content:
                        return
                    self.env["website.menu"].create(
                        {
                            "name": button_name,
                            "url": button_href,
                            "website_id": self.website_id.id,
                            "parent_id": top_menu.id,
                            "is_mega_menu": True,
                            "mega_menu_content": mega_menu_content,
                        }
                    )
            else:
                self._create_menu(button, top_menu)

        header_position = homepage_data.get("header_position", "regular")
        if header_position == "regular":
            self.header_overlay = False
        elif header_position == "over-the-content":
            self.header_overlay = True

    def _create_menu(self, menu_vals, top_menu):
        menu_name = menu_vals.get("name")
        menu_href = menu_vals.get("href")
        if not menu_name or not menu_href:
            return None
        return self.env["website.menu"].create(
            {
                "name": menu_name,
                "url": menu_href,
                "parent_id": top_menu.id,
                "website_id": self.website_id.id,
            }
        )

    def _apply_website_themes(self, homepage_data) -> None:
        user_color_palette = homepage_data.get("user_color_palette", {})
        if user_color_palette:
            self.website_id._customize_theme(palette=user_color_palette)

    def _apply_user_values(self, homepage_data) -> None:
        user_values = homepage_data.get("user_values", {})

        if homepage_data.get("footer"):
            user_values.update(
                {"footer-template": f"'imported-footer-{self.website_id.id}'"}
            )

        if user_values:
            self.website_id._customize_theme(values=user_values)

    def _create_footer(self, homepage_data):
        footer_html_list = homepage_data.get("footer", [])
        rendered_snippets = []
        for snippet in footer_html_list:
            try:
                el = html.fromstring(snippet)
                rendered_snippet = etree.tostring(el, encoding="unicode")
                rendered_snippets.append(rendered_snippet)
            except ValueError as e:
                logger.warning(e)

        new_footer_template = f"""
    <xpath expr="//div[@id='footer']" position="replace">
        <div id="footer" class="oe_structure oe_structure_solo" t-ignore="true" t-if="not no_footer">{"".join(rendered_snippets)}</div>
    </xpath>"""

        self.env["ir.ui.view"].create(
            {
                "name": "Template WS Custom Footer",
                "type": "qweb",
                "key": f"website_generator.template_ws_custom_footer_{self.website_id.id}",
                "arch": new_footer_template,
                "inherit_id": self.env["website"]
                .with_context(website_id=self.website_id.id)
                .viewref("website.layout")
                .id,
                "website_id": self.website_id.id,
            }
        )

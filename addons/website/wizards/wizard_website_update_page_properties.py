from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardWebsiteUpdatePageProperties(models.TransientModel):
    _name = "wizard.website.update.page.properties"
    _description = "Page Properties Base"

    target_model_id = fields.Reference(
        selection="_selection_target_model_id",
        required=True,
    )
    website_id = fields.Many2one(
        comodel_name="website",
        required=True,
    )
    menu_ids = fields.One2many(
        comodel_name="website.menu",
        compute="_compute_menu_ids",
    )
    is_in_menu = fields.Boolean(
        compute="_compute_is_in_menu",
        inverse="_inverse_is_in_menu",
    )
    url = fields.Char(required=True)
    is_homepage = fields.Boolean(
        string="Homepage",
        compute="_compute_is_homepage",
        inverse="_inverse_is_homepage",
    )
    can_publish = fields.Boolean(compute="_compute_can_publish")
    is_published = fields.Boolean(
        compute="_compute_is_published",
        inverse="_inverse_is_published",
    )

    def _selection_target_model_id(self) -> list:
        return [
            (model.model, model.name)
            for model in self.env["ir.model"].sudo().search([])
        ]

    def _get_domain_menu(self, url=None):
        self.check_singleton()
        target = self.target_model_id
        domain = [("website_id", "=", self.website_id.id)]
        url_to_check = url or self.url
        if target and target._name == "website.page" and target.id:
            domain += ["|", ("page_id", "=", target.id), ("url", "=", url_to_check)]
        else:
            domain += [("url", "=", url_to_check)]
        return domain

    @api.depends("url", "website_id")
    def _compute_menu_ids(self) -> None:
        for record in self:
            record.menu_ids = self.env["website.menu"].search(record._get_domain_menu())

    @api.depends("menu_ids")
    def _compute_is_in_menu(self) -> None:
        for record in self:
            record.is_in_menu = bool(record.menu_ids)

    def _inverse_is_in_menu(self) -> None:
        self.check_singleton()
        target = self.target_model_id
        if self.is_in_menu:
            if not self.menu_ids:
                _debug.lifecycle(
                    "page_added_to_menu", url=self.url, website=self.website_id.id
                )
                self.env["website.menu"].create(
                    {
                        "name": target.name,
                        "url": self.url,
                        "parent_id": self.website_id.menu_id.id,
                        "website_id": self.website_id.id,
                        "page_id": target.id
                        if (target and target._name == "website.page")
                        else False,
                    }
                )
        else:
            menus = self.menu_ids or self.env["website.menu"].search(
                self._get_domain_menu()
            )
            if menus:
                _debug.lifecycle(
                    "page_removed_from_menu",
                    url=self.url,
                    website=self.website_id.id,
                    menus=len(menus),
                )
                menus.unlink()

    @api.depends("url", "website_id.homepage_url")
    def _compute_is_homepage(self) -> None:
        for record in self:
            url = record.url
            current_homepage_url = record.website_id.homepage_url or "/"
            record.is_homepage = url in (current_homepage_url, "/")

    def _inverse_is_homepage(self) -> None:
        self.check_singleton()
        url = self.url
        if self.is_homepage:
            if url and url != "/":
                _debug.lifecycle(
                    "homepage_url_set", website=self.website_id.id, url=url
                )
                self.website_id.homepage_url = url
        elif self.website_id.homepage_url == url:
            _debug.lifecycle(
                "homepage_url_cleared", website=self.website_id.id, url=url
            )
            self.website_id.homepage_url = False

    @api.depends("target_model_id")
    def _compute_can_publish(self) -> None:
        for record in self:
            target = record.target_model_id
            if target._name == "ir.ui.view":
                record.can_publish = self._is_ir_ui_view_published(
                    target
                ) or self._is_ir_ui_view_unpublished(target)
            elif "can_publish" in target._fields:
                record.can_publish = target.can_publish
            else:
                record.can_publish = False

    @api.depends("target_model_id")
    def _compute_is_published(self) -> None:
        for record in self:
            target = record.target_model_id
            if target._name == "ir.ui.view":
                record.is_published = self._is_ir_ui_view_published(target)
            elif "is_published" in target._fields:
                record.is_published = target.is_published
            else:
                record.is_published = False

    def _inverse_is_published(self) -> None:
        self.check_singleton()
        target = self.target_model_id
        if target._name == "ir.ui.view":
            if self.can_publish:
                if self.is_published:
                    target.visibility = ""
                    target.group_ids -= self._get_ir_ui_view_unpublish_group()
                else:
                    target.visibility = "restricted_group"
                    target.group_ids += self._get_ir_ui_view_unpublish_group()
                _debug.lifecycle(
                    "view_publication",
                    view=target.id,
                    published=self.is_published,
                )
                self.env.registry.clear_cache("templates")
        elif "is_published" in target._fields:
            _debug.lifecycle(
                "record_publication",
                model=target._name,
                record=target.id,
                published=self.is_published,
            )
            target.is_published = self.is_published

    def _get_ir_ui_view_unpublish_group(self):
        return self.env.ref("base.group_user")

    def _is_ir_ui_view_unpublished(self, view) -> bool:
        view.check_singleton()
        return (
            view.visibility == "restricted_group"
            and self._get_ir_ui_view_unpublish_group() in view.group_ids.all_implied_ids
        )

    def _is_ir_ui_view_published(self, view) -> bool:
        view.check_singleton()
        return not view.visibility

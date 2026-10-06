import re

import werkzeug.exceptions
from lxml import html

from odoo import http
from odoo.http import request
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WebsiteStudioController(http.Controller):
    @http.route("/website_studio/create_form", type="jsonrpc", auth="user")
    def create_website_form(self, res_model):
        model = request.env["ir.model"]._get(res_model)
        values = {}
        if not model.website_form_access:
            values["website_form_access"] = True
            if not model.website_form_label:
                values["website_form_label"] = "Create %s" % model.name
        model.write(values)
        template = "website_studio.default_record_page"
        form_name = model.name
        page_url = "/" + request.env["ir.http"]._slugify(
            form_name, max_length=1024, path=True
        )
        try:
            if request.env["ir.http"]._match(page_url):
                form_name += " Form"
        except werkzeug.exceptions.NotFound:
            pass
        new_page = request.env["website"].new_page(
            name=form_name,
            add_menu=True,
            template=template,
            ispage=True,
            namespace="website",
        )
        view = request.env["ir.ui.view"].browse(new_page["view_id"])
        view.arch = self._post_process_arch(view.arch, model)
        return new_page["url"]

    @http.route("/website_studio/get_forms", type="jsonrpc", auth="user")
    def get_website_form(self, res_model):
        views = request.env["ir.ui.view"].search([("type", "=", "qweb")])
        website_forms = views.filtered(lambda v: self._is_editable_form(v, res_model))
        return request.env["website.page"].search_read(
            [("view_id", "in", website_forms.ids)], ["url", "name"]
        )

    def _is_editable_form(self, view, res_model) -> bool:
        html_element = html.fromstring(view.arch_base)
        path = '//form[@action="/website/form/"][@data-model_name="%s"]' % res_model
        form_element = html_element.xpath(path)
        if not len(form_element):
            _debug.logic("studio_form_not_editable", view=view.id, model=res_model)
            return False
        return (
            "data-editable-form" not in form_element[0].attrib
            or form_element[0].attrib["data-editable-form"] == "true"
        )

    def _post_process_arch(self, arch, res_model):
        model = request.env["%s" % res_model.model]
        if model.fields_get(["name"]):
            arch = (
                request.env["ir.ui.view"]
                .search([("key", "=", "website_studio.default_form_field_name")])
                .arch
            )
        elif model.fields_get(["x_name"]):
            request.env["ir.model.fields"].formbuilder_whitelist(
                res_model.model, ["x_name"]
            )
            arch = (
                request.env["ir.ui.view"]
                .search([("key", "=", "website_studio.default_form_field_name")])
                .arch
            )
            arch = arch.replace(r'for="name"', 'for="x_name"')
            arch = arch.replace(r'name="name"', 'name="x_name"')
        return re.sub(
            r'data-model_name=""', 'data-model_name="%s"' % res_model.model, arch
        )

    @http.route("/website_studio/get_website_pages", type="jsonrpc", auth="user")
    def get_website_pages(self, res_model=None):
        pages = request.env["website.controller.page"].search_read(
            [("model", "=", res_model)], ["website_id", "name", "name_slugified"]
        )
        return {
            "pages": pages,
            "websites": request.env["website"].search_read([], ["display_name"]),
        }

/** @odoo-module native */
import { markup } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";

registry.category("web_studio.editor_tabs").add("website", {
    name: _t("Model Pages"),
    action: (env) => {
        const { editedAction } = env.services.studio;
        const context = {
            default_model: editedAction.res_model,
            search_default_model: editedAction.res_model,
            default_page_type: "listing",
            default_website_published: true,
            default_use_menu: true,
            default_auto_single_page: true,
            form_view_ref: "website_studio.website_controller_page_form_dialog",
            "website_studio.create_page": true,
        };
        return {
            type: "ir.actions.act_window",
            res_model: "website.controller.page",
            name: _t("Model Pages"),
            views: [
                [false, "kanban"],
                [false, "list"],
                [false, "form"],
            ],
            context,
            help: markup`<p class="o_view_nocontent_empty_folder">${_t(
                "Create a new model page",
            )}</p><p>${_t(
                "Publish everything on your websites then customize the pages using the power of the Website app",
            )}</p>`,
        };
    },
});

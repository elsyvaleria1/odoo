/** @odoo-module native */
import { registry } from "@web/core/registry";
import { WebsitePage } from "@website/interactions/website_page";

registry.category("public.interactions.edit").add("website.website_page", {
    Interaction: WebsitePage,
});

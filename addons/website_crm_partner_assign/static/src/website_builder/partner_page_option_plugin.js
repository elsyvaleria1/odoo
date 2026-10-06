/** @odoo-module native */
import { BaseOptionComponent } from "@html_builder/core/utils";
import { Plugin } from "@html_editor/plugin";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";

export class PartnerPageOption extends BaseOptionComponent {
    static template = "website_crm_partner_assign.PartnerPageOption";
    static selector =
        "main:has(#oe_structure_website_crm_partner_assign_layout_1):not(:has(.o_wcrm_filters_top))";
    static title = _t("Partner Page");
    static groups = ["website.group_website_designer"];
    static editableOnly = false;
}

class WebsiteCRMPartnerPageOption extends Plugin {
    static id = "websiteCRMPartnerPageOption";

    resources = {
        builder_options: [PartnerPageOption],
    };
}

registry
    .category("website-plugins")
    .add(WebsiteCRMPartnerPageOption.id, WebsiteCRMPartnerPageOption);

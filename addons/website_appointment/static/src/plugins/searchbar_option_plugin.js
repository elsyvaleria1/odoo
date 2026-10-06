/** @odoo-module native */
import { Plugin } from "@html_editor/plugin";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";

export class SearchbarOptionPlugin extends Plugin {
    static id = "website_appointment.searchbarOption";

    resources = {
        searchbar_option_display_items: [
            {
                label: _t("Description"),
                dataAttribute: "displayDescription",
                dependency: "search_appointment_opt",
            },
        ],
    };
}

registry
    .category("website-plugins")
    .add(SearchbarOptionPlugin.id, SearchbarOptionPlugin);

/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { Dropdown } from "@web/components/dropdown";
import { registry } from "@web/core/registry";
import { useViewConfig } from "@web/core/view_config_hooks";
import { COG_GROUP, isActWindowView } from "@web/search/cog_menu/cog_menu_group";
import { session } from "@web/session";

import { InsertViewSpreadsheet } from "../insert_action_link_menu/insert_action_link_menu.js";
import { InsertListSpreadsheetMenu } from "../list_view/insert_list_spreadsheet_menu_owl.js";
const cogMenuRegistry = registry.category("cogMenu");

export class SpreadsheetCogMenu extends Component {
    static template = "spreadsheet_edition.SpreadsheetCogMenu";
    static components = { Dropdown, InsertViewSpreadsheet, InsertListSpreadsheetMenu };
    static props = {};
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.config = useViewConfig();
    }
}

cogMenuRegistry.add(
    "spreadsheet-cog-menu",
    {
        Component: SpreadsheetCogMenu,
        groupNumber: COG_GROUP.INTEGRATE,
        isDisplayed: (env) =>
            !env.isSmall &&
            isActWindowView(env) &&
            env.config.viewType !== "form" &&
            Boolean(session.can_insert_in_spreadsheet),
    },
    { sequence: 30 },
);

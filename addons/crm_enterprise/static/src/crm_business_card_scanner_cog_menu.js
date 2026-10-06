/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { isMobileOS } from "@web/core/browser/feature_detection";
import { registry } from "@web/core/registry";
import { COG_GROUP, isActWindowView } from "@web/search/cog_menu/cog_menu_group";
import { CogMenuItem } from "@web/search/cog_menu/cog_menu_item";

import { CrmBusinessCardScanner } from "./crm_business_card_scanner.js";

const cogMenuRegistry = registry.category("cogMenu");

export class CrmBusinessCardsScannerCogMenu extends Component {
    static template = "crm_enterprise.CrmBusinessCardsScannerCogMenu";
    static components = { CogMenuItem, CrmBusinessCardScanner };
    static props = {};
    props = useProps(this.constructor.props);

    onItemSelected() {
        const businessCardScanner = document.querySelector(
            '.o_crm_business_card_scanner input[type="file"]',
        );
        if (businessCardScanner) {
            businessCardScanner.dispatchEvent(new MouseEvent("click"));
        }
    }
}

cogMenuRegistry.add(
    "crm-business-cards-scanner-menu",
    {
        Component: CrmBusinessCardsScannerCogMenu,
        groupNumber: COG_GROUP.DATA,
        isDisplayed: (env) =>
            !isMobileOS() &&
            env.searchModel.resModel === "crm.lead" &&
            isActWindowView(env, ["kanban", "list"]),
    },
    { sequence: 30 },
);

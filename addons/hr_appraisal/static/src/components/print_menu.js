/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { COG_GROUP } from "@web/search/cog_menu/cog_menu_group";
import { CogMenuItem } from "@web/search/cog_menu/cog_menu_item";

const cogMenuRegistry = registry.category("cogMenu");

export class PrintActionMenu extends Component {
    static template = "hr_appraisal.PrintAction";
    static components = { CogMenuItem };
    static props = {};
    props = useProps(this.constructor.props);

    async print() {
        window.print();
    }
}

export const printActionMenu = {
    Component: PrintActionMenu,
    groupNumber: COG_GROUP.PRINT,
    isDisplayed: ({ config, searchModel }) =>
        searchModel.resModel === "hr.appraisal" && config.viewType === "form",
};

cogMenuRegistry.add("print-action-menu", printActionMenu, { sequence: 11 });

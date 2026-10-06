// @ts-check
/** @odoo-module native */

import { onWillStart, onWillUpdateProps, t } from "@odoo/owl";
import { Dropdown } from "@web/components/dropdown/dropdown";
import { makeLogger } from "@web/core/debug/debug_logger";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { useViewScope } from "@web/model/view_scope";
import { ActionMenus } from "@web/search/action_menus/action_menus";
import {
    COG_GROUP,
    COG_MENU_REGISTRY_VALIDATION,
} from "@web/search/cog_menu/cog_menu_group";
import { getDisplayedRegistryItems } from "@web/search/utils/misc";

const cogMenuRegistry = registry.category("cogMenu");

const log = makeLogger("web.search.cog_menu");

cogMenuRegistry.addValidation(COG_MENU_REGISTRY_VALIDATION);

const PRINT_ITEM = Object.freeze({
    key: "print",
    groupNumber: COG_GROUP.PRINT,
    isPrint: true,
});

export class CogMenu extends ActionMenus {
    static template = "web.CogMenu";
    static components = {
        ...ActionMenus.components,
        Dropdown,
    };
    static props = {
        ...ActionMenus.props,
        getActiveIds: ActionMenus.props.getActiveIds.optional(),
        context: ActionMenus.props.context.optional(),
        resModel: ActionMenus.props.resModel.optional(),
        items: ActionMenus.props.items.optional({}),
        slots: t.object().optional(),
    };

    /** @type {any[]} */
    registryItems = [];
    /** @type {number | undefined} */
    _registryLoad;

    setup() {
        super.setup();
        this.ui = useService("ui");
        this.viewScope = useViewScope();
        onWillStart(() => this._refreshRegistryItems("start"));
        onWillUpdateProps(() => this._refreshRegistryItems("update"));
    }

    /** @param {"start" | "update"} trigger */
    async _refreshRegistryItems(trigger) {
        const end = log.perf("registryItems", { trigger });
        const load = (this._registryLoad = (this._registryLoad ?? 0) + 1);
        const items = await this._registryItems();
        const superseded = load !== this._registryLoad;
        end({ count: items.length, superseded });
        if (!superseded) {
            this.registryItems = items;
        }
    }

    /** @returns {boolean} */
    get hasItems() {
        return Boolean(this.cogItems.length || this.props.slots?.default);
    }

    /** @returns {Promise<Array<{Component: import("@odoo/owl").ComponentConstructor, groupNumber: number, key: string}>>} */
    _registryItems() {
        return getDisplayedRegistryItems(cogMenuRegistry, this.viewScope);
    }

    /**
     * @returns {Array<
     * | {Component: import("@odoo/owl").ComponentConstructor, groupNumber: number, key: string}
     * | {key: string, groupNumber: number, description?: string, action?: any, callback?: Function}
     * | {key: string, groupNumber: number, isPrint: true}
     * >}
     */
    get cogItems() {
        return [
            ...this.registryItems,
            ...(this.actionItems ?? []),
            ...(this.props.items.print?.length ? [PRINT_ITEM] : []),
        ].toSorted(
            (item1, item2) => (item1.groupNumber || 0) - (item2.groupNumber || 0),
        );
    }

    /**
     * @param {{ description: string }} item
     * @returns {string}
     */
    getPrintItemAriaLabel(item) {
        return _t("Print report: %s", item.description);
    }
}

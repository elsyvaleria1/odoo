/** @odoo-module native */
import { Component, onMounted, proxy, t, useListener, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { Many2XAutocomplete } from "@web/fields/relational/many2x_autocomplete";
import { Dialog } from "@web/ui/dialog";
import { computeAppsAndMenuItems } from "@web/webclient/menus/menu_utils";

export class IrMenuSelector extends Component {
    static components = { Many2XAutocomplete };
    static template = "spreadsheet_edition.IrMenuSelector";
    static props = {
        menuId: t.number().optional(),
        onValueChanged: t.function(),
        autoFocus: t.boolean().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.ref = elementRef();
        this.menus = useService("menu");
        onMounted(() => {
            if (this.props.autoFocus) {
                this.ref.el.querySelector("input")?.focus();
            }
        });
    }

    get many2XAutocompleteProps() {
        return {
            resModel: "ir.ui.menu",
            fieldString: _t("Menu Items"),
            getDomain: this.getDomain.bind(this),
            update: this.updateMenu.bind(this),
            activeActions: {},
            placeholder: _t("Select a menu..."),
            value: this._getMenuPath(this.props.menuId),
        };
    }

    updateMenu(selectedMenus) {
        this.props.onValueChanged(selectedMenus[0]?.id);
    }

    getDomain() {
        return [
            "|",
            ["id", "in", this.availableAppMenuIds],
            "&",
            ["action", "!=", false],
            ["id", "in", this.availableMenuIds],
        ];
    }

    get availableMenuIds() {
        return this.menus
            .getAll()
            .map((menu) => menu.id)
            .filter((menuId) => menuId !== "root");
    }

    get availableAppMenuIds() {
        return this.menus
            .getAll()
            .filter((menu) => menu.id === menu.appID)
            .map((menu) => menu.id)
            .filter((menuId) => menuId !== "root");
    }

    /** @private */
    _getMenuPath(menuId) {
        if (menuId === undefined) {
            return "";
        }
        const menuTree = this.menus.getMenuAsTree("root");
        const computedTree = computeAppsAndMenuItems(menuTree);
        const app = computedTree.apps.find((app) => app.id === menuId);
        if (app) {
            return app.label;
        }
        const menu = computedTree.menuItems.find((menu) => menu.id === menuId);
        if (!menu) {
            return "";
        }
        const path = menu.parents.replace(/ \/ /g, "/");
        return path + "/" + menu.label;
    }
}

export class IrMenuSelectorDialog extends Component {
    static components = { Dialog, IrMenuSelector };
    static template = "spreadsheet_edition.IrMenuSelectorDialog";
    static props = { onMenuSelected: t.function(), close: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        this.selectedMenu = proxy({
            id: undefined,
        });
        useListener(document.body, "click", (ev) => {
            ev.stopPropagation();
            ev.preventDefault();
        });
    }
    _onConfirm() {
        this.props.onMenuSelected(this.selectedMenu.id);
    }
    _onValueChanged(value) {
        this.selectedMenu.id = value;
    }
}

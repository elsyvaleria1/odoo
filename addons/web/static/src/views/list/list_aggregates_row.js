// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { getActiveHotkey } from "@web/core/browser/hotkeys";
import { elementRef } from "@web/core/utils/element_ref";
import { useAutofocus } from "@web/core/utils/hooks";

import { arrowLeavingTarget } from "./list_focus.js";
import { getAggregateLayout } from "./list_group_layout.js";

export class ListAggregatesRow extends Component {
    static template = "web.ListAggregatesRow";

    static props = {
        agg: t.object(),
        list: t.object(),
        archInfo: t.object(),
        columns: t.array(),
        hasSelectors: t.boolean(),
        hasOpenFormViewColumn: t.boolean(),
        displayOptionalFields: t.boolean(),
        hasActionsColumn: t.boolean(),
        activeActions: t.object(),
        canCreateGroup: t.boolean(),
        showGroupInput: t.boolean(),
        onShowGroupInput: t.function(),
        onHideGroupInput: t.function(),
        onGroupInputConfirm: t.function(),
        onCellKeydown: t.function().optional(),
    };
    props = useProps(this.constructor.props);
    /** @type {import("@odoo/owl").Ref} */
    groupInputRef;

    setup() {
        this.groupInputRef = elementRef();
        useAutofocus({ ref: this.groupInputRef });
    }

    /** @returns {ReturnType<typeof import("./list_aggregates").useListAggregates>} */
    get agg() {
        return this.props.agg;
    }

    /** @returns {any[]} */
    get columns() {
        return this.props.columns;
    }

    /** @returns {Record<string, any>} */
    get fields() {
        return this.props.list.fields;
    }

    /**
     * @param {Record<string, object>} aggregates
     * @returns {import("./list_group_layout.js").AggregateLayout}
     */
    getLayout(aggregates) {
        return getAggregateLayout(
            /** @type {any} */ (this.columns),
            this.fields,
            aggregates,
            { hasSelectors: this.props.hasSelectors },
        );
    }

    /** @param {KeyboardEvent} ev */
    onKeydown(ev) {
        if (arrowLeavingTarget(ev)) {
            this.props.onCellKeydown?.(ev);
        }
    }

    /** @param {KeyboardEvent} ev */
    onGroupInputKeydown(ev) {
        const hotkey = getActiveHotkey(ev);
        if (hotkey === "enter") {
            ev.stopPropagation();
            this._confirmGroupInput();
        }
        if (hotkey === "escape") {
            ev.stopPropagation();
            this.props.onHideGroupInput();
        }
    }

    _confirmGroupInput() {
        const value = /** @type {HTMLInputElement} */ (this.groupInputRef.el).value;
        this.props.onGroupInputConfirm(value);
    }

    /**
     * @param {MouseEvent} ev
     * @param {any} value
     * @param {string} fieldName
     */
    openMultiCurrencyPopover(ev, value, fieldName) {
        this.agg.openMultiCurrencyPopover(ev, value, fieldName);
    }
}

// @ts-check
/** @odoo-module native */

import { Component, useProps } from "@odoo/owl";
import { useRenderCounter } from "@web/core/utils/render_instrumentation";

/**
 * @typedef {import("./list_renderer").ListRowApi} ListRowApi
 * @typedef {import("./list_renderer").ListRowFlags} ListRowFlags
 */

export class ListRecordRow extends Component {
    static template = "web.ListRecordRow";
    static components = {};
    static props = null;
    props = useProps(this.constructor.props);

    setup() {
        useRenderCounter("list.ListRecordRow");
    }

    markRender() {
        this.props.api.markRowRender(String(this.props.record.id));
        return true;
    }

    get record() {
        return this.props.record;
    }

    get group() {
        return this.props.group;
    }

    get groupId() {
        return this.props.groupId;
    }

    /** @returns {ListRowApi} */
    get api() {
        return this.props.api;
    }

    /** @returns {ListRowFlags} */
    get flags() {
        return this.props.flags;
    }

    get _canSelectRecord() {
        return this.props.flags.canSelectRecord;
    }

    get editedRecord() {
        return this.props.flags.isEditing ? this.props.api.getEditedRecord() : null;
    }

    get gridState() {
        return this.props.api.getGridState();
    }

    get _displaySaveNotification() {
        return this.props.api.displaySaveNotification;
    }

    get hasSelectors() {
        return this.props.hasSelectors;
    }

    get hasOpenFormViewColumn() {
        return this.props.hasOpenFormViewColumn;
    }

    // the row template's actions-cell condition reads this name
    get displayOptionalFields() {
        return this.props.hasActionsColumn;
    }

    get isX2Many() {
        return this.props.isX2Many;
    }

    get activeActions() {
        return this.props.activeActions;
    }
}

/** @type {WeakMap<any, any>} */
const rowClassRegistry = new WeakMap();

/**
 * @param {any} RendererClass
 * @returns {typeof ListRecordRow}
 */
export function getRowComponentClass(RendererClass) {
    let RowClass = rowClassRegistry.get(RendererClass);
    if (!RowClass) {
        RowClass = class extends ListRecordRow {};
        Object.defineProperty(RowClass, "name", {
            value: `ListRecordRow_${RendererClass.name}`,
            configurable: true,
        });
        Object.defineProperty(RowClass, "components", {
            configurable: true,
            get() {
                return RendererClass.components;
            },
            set(value) {
                Object.defineProperty(this, "components", {
                    value,
                    writable: true,
                    configurable: true,
                    enumerable: true,
                });
            },
        });
        rowClassRegistry.set(RendererClass, RowClass);
    }
    return RowClass;
}

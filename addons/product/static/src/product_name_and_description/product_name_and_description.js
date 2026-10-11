/** @odoo-module native */

import { Component, onPatched, proxy, t, useListener, useProps } from "@odoo/owl";
import { getActiveHotkey } from "@web/core/browser/hotkeys";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useInputField } from "@web/fields/input_field_hook";
import {
    computeM2OProps,
    Many2One,
    Many2OneField,
} from "@web/fields/relational/many2one";

import { useProductAndLabelAutoresize } from "./product_and_label_autoresize.js";

export const ProductNameAndDescriptionListRendererMixin = () => ({
    getCellTitle(column, record) {
        if (this.productColumns.includes(column.name)) {
            return;
        }
        return super.getCellTitle(column, record);
    },

    getActiveColumns() {
        let activeColumns = super.getActiveColumns();
        const productCol = activeColumns.find((col) =>
            this.productColumns.includes(col.name),
        );
        const labelCol = activeColumns.find(
            (col) => col.name === this.descriptionColumn,
        );

        this.columnIsProductAndLabel = Boolean(productCol && labelCol);
        if (productCol) {
            activeColumns = activeColumns.filter(
                (col) => col.name !== this.descriptionColumn,
            );
            this.titleField = productCol.name;
        } else {
            this.titleField = "name";
        }

        return activeColumns;
    },

    getFieldProps(record, column) {
        const props = super.getFieldProps(record, column);
        if (this.productColumns.includes(column.name)) {
            props.columnIsProductAndLabel = Boolean(this.columnIsProductAndLabel);
        }
        return props;
    },
});

export class ProductNameAndDescriptionField extends Component {
    static components = { Many2One };
    static props = {
        ...Many2OneField.props,
        columnIsProductAndLabel: t.boolean().optional(),
    };
    static template = Many2One.template;

    static descriptionColumn = "";
    props = useProps(this.constructor.props);

    setup() {
        this.isPrintMode = proxy({ value: false });
        this.labelVisibility = proxy({ value: false });
        this.switchToLabel = false;
        this.labelNode = elementRef();
        useProductAndLabelAutoresize(this.labelNode, {
            targetParentName: this.props.name,
        });
        this.productNode = elementRef();
        useProductAndLabelAutoresize(this.productNode, {
            targetParentName: this.props.name,
        });

        this.descriptionColumn = this.constructor.descriptionColumn;
        useInputField({
            ref: this.labelNode,
            fieldName: this.descriptionColumn,
            getValue: () => this.label,
            parse: (v) => this.parseLabel(v),
        });

        onPatched(() => {
            if (this.labelNode.el && this.switchToLabel) {
                this.switchToLabel = false;
                this.labelNode.el.focus();
            }
        });

        useListener(window, "beforeprint", () => {
            this.isPrintMode.value = true;
        });
        useListener(window, "afterprint", () => {
            this.isPrintMode.value = false;
        });
    }

    get columnIsProductAndLabel() {
        return Boolean(this.props.columnIsProductAndLabel);
    }

    get productName() {
        return this.props.record.data[this.props.name]?.display_name || "";
    }

    get label() {
        const stored = this.props.record.data[this.descriptionColumn] || "";
        const label = stored.startsWith(this.productName)
            ? stored.slice(this.productName.length)
            : stored;
        return label.trim();
    }

    get m2oProps() {
        const p = computeM2OProps(this.props);
        let value = p.value && { ...p.value };
        if (this.props.readonly && this.productName) {
            value = { ...value, display_name: this.productName };
        }
        return {
            ...p,
            canOpen: p.canOpen && (!this.props.readonly || this.isProductClickable),
            placeholder: _t("Search a product"),
            searchMemoization: "none",
            value,
        };
    }

    get isProductClickable() {
        return this.props.record.evalContext.parent?.state !== "draft";
    }

    get showLabelVisibilityToggler() {
        return !this.props.readonly && this.columnIsProductAndLabel && !this.label;
    }

    switchLabelVisibility() {
        this.labelVisibility.value = !this.labelVisibility.value;
        this.switchToLabel = true;
    }

    parseLabel(value) {
        return value || this.productName;
    }

    /**
     * @param {KeyboardEvent} ev
     */
    onM2oInputKeydown(ev) {
        const hotkey = getActiveHotkey(ev);
        if (hotkey === "enter" && this.showLabelVisibilityToggler) {
            this.switchLabelVisibility();
            ev.stopPropagation();
            ev.preventDefault();
        }
    }
}

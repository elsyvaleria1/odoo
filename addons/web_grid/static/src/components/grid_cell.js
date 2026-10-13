/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { formatInteger } from "@web/core/formatters";
import { parseFloat, parseInteger } from "@web/core/parsers";
import { registry } from "@web/core/registry";
import { elementRef } from "@web/core/utils/element_ref";
import { formatFloat } from "@web/core/utils/format/numbers";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { useNumpadDecimal } from "@web/fields/numpad_decimal_hook";
import { useGridCell } from "@web_grid/hooks/grid_cell_hook";
import { useInputHook } from "@web_grid/hooks/input_hook";

/**
 * @param {Object} props
 * @return {Number}
 */
export function getGridCellFactor(props) {
    return props.factor || props.fieldInfo.options?.factor || 1;
}

export const standardGridCellProps = {
    name: t.string(),
    classNames: t.string(),
    fieldInfo: t.object(),
    readonly: t.boolean().optional(),
    editMode: t.boolean().optional(),
    reactive: t.object({ cell: t.or([t.instanceOf(HTMLElement), t.literal(null)]) }),
    openRecords: t.function(),
    onEdit: t.function(),
    getCell: t.function(),
    onKeyDown: t.function().optional(),
};

export class GridCell extends Component {
    static template = "web_grid.Cell";
    static props = {
        ...standardGridCellProps,
        readonly: standardGridCellProps.readonly.optional(true),
        editMode: standardGridCellProps.editMode.optional(false),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.rootRef = elementRef();
        this.state = proxy({
            edit: this.props.editMode,
            invalid: false,
            cell: null,
        });
        useGridCell(this);
        this._setupEditor();
    }

    /** @protected */
    _setupEditor() {
        this.discardChanges = false;
        this.numpadDecimalRef = elementRef();
        this.inputRef = useInputHook({
            getValue: () => this.formattedValue,
            ref: this.numpadDecimalRef,
            parse: this.parse.bind(this),
            notifyChange: this.onChange.bind(this),
            commitChanges: this.saveEdition.bind(this),
            onKeyDown: (ev) => this.props.onKeyDown(ev, this.state.cell),
            discard: this.discard.bind(this),
            setInvalid: () => {
                this.state.invalid = true;
            },
            setDirty: () => {
                this.state.invalid = false;
            },
            isInvalid: () => this.state.invalid,
        });
        useNumpadDecimal(this.numpadDecimalRef);
        useLayoutEffect(
            (edit, inputEl, cellEl) => {
                if (inputEl) {
                    inputEl.value = this.formattedValue;
                }
                if (edit && inputEl) {
                    inputEl.focus();
                    if (inputEl.type === "text") {
                        if (inputEl.selectionStart === null) {
                            return;
                        }
                        if (inputEl.selectionStart === inputEl.selectionEnd) {
                            inputEl.selectionStart = 0;
                            inputEl.selectionEnd = inputEl.value.length;
                        }
                    }
                }
                this.discardChanges = false;
            },
            () => [this.state.edit, this.inputRef.el, this.props.reactive.cell],
        );
    }

    get value() {
        return this.state.cell?.value || 0;
    }

    onMagnifierGlassClick() {
        const { context, domain, title } = this.state.cell;
        this.props.openRecords(title, domain.toList(), context);
    }

    get section() {
        return this.row.getSection();
    }

    get row() {
        return this.state.cell?.row;
    }

    get formattedValue() {
        const { type, digits } = this.props.fieldInfo;
        if (type === "integer") {
            return formatInteger(this.value);
        }
        return formatFloat(this.value, { digits: digits || 2 });
    }

    get inputMode() {
        return "numeric";
    }

    /** @return {string} */
    get inputLabel() {
        return (this.state.cell?.title || "").replace(/\s+/g, " ").trim();
    }

    isEditable(props = this.props) {
        const { cell } = this.state;
        return Boolean(
            !props.readonly && cell && !cell.readonly && !cell.row.isSection,
        );
    }

    parse(value) {
        if (this.props.fieldInfo.type === "integer") {
            return parseInteger(value);
        }
        return parseFloat(value);
    }

    onChange(value) {
        if (!this.discardChanges) {
            this.update(value);
        }
    }

    update(value) {
        this.state.cell.update(value);
    }

    saveEdition(value) {
        const changesCommitted = (value || false) !== (this.state.cell?.value || false);
        if (changesCommitted) {
            this.update(value);
        }
        this.props.onEdit(false);
        return changesCommitted;
    }

    discard() {
        this.discardChanges = true;
        this.props.onEdit(false);
    }

    onCellClick(ev) {
        if (this.isEditable() && !this.state.edit) {
            this.discardChanges = false;
            this.props.onEdit(true);
        }
    }
}

export const integerGridCell = {
    component: GridCell,
    formatter: formatInteger,
};

registry.category("grid_components").add("integer", integerGridCell);

export const floatGridCell = {
    component: GridCell,
    formatter: formatFloat,
};

registry.category("grid_components").add("float", floatGridCell);

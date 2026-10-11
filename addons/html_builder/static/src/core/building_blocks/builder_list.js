/** @odoo-module native */
import { BuilderComponent } from "@html_builder/core/building_blocks/builder_component";
import {
    basicContainerBuilderComponentProps,
    useBuilderComponent,
    useInputBuilderComponent,
} from "@html_builder/core/utils";
import { isSmallInteger } from "@html_builder/utils/utils";
import { Component, onWillUpdateProps, t, useProps } from "@odoo/owl";
import { Dropdown, useDropdownState } from "@web/components/dropdown";
import { _t } from "@web/core/translation";
import { useSortable } from "@web/core/utils/dnd";
import { elementRef } from "@web/core/utils/element_ref";

export class BuilderList extends Component {
    static template = "html_builder.BuilderList";
    static props = {
        ...basicContainerBuilderComponentProps,
        id: t.string().optional(),
        addItemTitle: t.string().optional(_t("Add")),
        itemShape: t
            .customValidator(
                t.record(
                    t.or([
                        t.literal("number"),
                        t.literal("text"),
                        t.literal("boolean"),
                        t.literal("exclusive_boolean"),
                    ]),
                ),
                (value) =>
                    Object.keys(value).length > 0 &&
                    !Object.keys(value).includes("_id"),
            )
            .optional({ value: "text" }),
        default: t.any().optional({ value: _t("Item") }),
        sortable: t.any().optional(true),
        hiddenProperties: t.array().optional([]),
        records: t.string().optional(),
        defaultNewValue: t.object().optional({}),
        columnWidth: t.any().optional({}),
        forbidLastItemRemoval: t.boolean().optional(false),
        isInputDisabled: t.boolean().optional(false),
        mode: t.string().optional("button"),
    };
    static components = { BuilderComponent, Dropdown };
    props = useProps(this.constructor.props);

    setup() {
        this.validateProps();
        this.dropdown = useDropdownState();
        useBuilderComponent();
        const { state, commit, preview } = useInputBuilderComponent({
            id: this.props.id,
            defaultValue: this.parseDisplayValue([]),
            parseDisplayValue: this.parseDisplayValue,
            formatRawValue: this.formatRawValue.bind(this),
        });
        this.state = state;
        this.commit = commit;
        this.preview = preview;
        this.allRecords = this.formatRawValue(this.props.records);

        onWillUpdateProps((props) => {
            this.allRecords = this.formatRawValue(props.records);
        });

        if (this.props.sortable) {
            this.tableRef = elementRef();
            useSortable({
                enable: () => this.props.sortable,
                ref: this.tableRef,
                elements: ".o_row_draggable",
                handle: ".o_handle_cell",
                cursor: "grabbing",
                placeholderClasses: ["d-table-row"],
                onDrop: (params) => {
                    const { element, previous } = params;
                    this.reorderItem(element.dataset.id, previous?.dataset.id);
                },
            });
        }
    }

    validateProps() {
        const itemShapeKeys = Object.keys(this.props.itemShape);
        const defaultKeys = Object.keys(this.props.default);
        const allKeys = new Set([...itemShapeKeys, ...defaultKeys]);
        if (allKeys.size !== itemShapeKeys.length) {
            throw new Error("default properties don't match itemShape");
        }
    }

    getAvailableRecords() {
        const itemIds = new Set(this.formatRawValue(this.state.value).map((i) => i.id));
        return this.allRecords.filter((record) => !itemIds.has(record.id));
    }

    parseDisplayValue(displayValue) {
        return JSON.stringify(displayValue);
    }

    formatRawValue(rawValue) {
        const items = rawValue ? JSON.parse(rawValue) : [];
        let nextAvailableId = items ? this.getNextAvailableItemId(items) : 0;
        for (const item of items) {
            if (!("_id" in item)) {
                item._id = nextAvailableId.toString();
                nextAvailableId += 1;
            }
        }
        return items;
    }

    addItem(ev) {
        const items = this.formatRawValue(this.state.value);
        if (!ev.currentTarget.dataset.id) {
            items.push(this.makeDefaultItem());
        } else {
            const matchId = (el) =>
                el.id.toString() === ev.currentTarget.dataset.id.toString();
            const elementToAdd = this.allRecords.find(matchId);
            if (!items.some(matchId)) {
                items.push(elementToAdd);
            }
            this.dropdown.close();
        }
        this.commit(items);
    }

    deleteItem(itemId) {
        const items = this.formatRawValue(this.state.value);
        this.commit(items.filter((item) => item._id !== itemId));
    }

    reorderItem(itemId, previousId) {
        let items = this.formatRawValue(this.state.value);
        const itemToReorder = items.find((item) => item._id === itemId);
        items = items.filter((item) => item._id !== itemId);

        const previousItem = items.find((item) => item._id === previousId);
        const previousItems = items.slice(0, items.indexOf(previousItem) + 1);

        const nextItems = items.slice(items.indexOf(previousItem) + 1, items.length);

        const newItems = [...previousItems, itemToReorder, ...nextItems];
        this.commit(newItems);
    }

    makeDefaultItem() {
        return {
            ...this.props.defaultNewValue,
            ...this.props.default,
            _id: this.getNextAvailableItemId().toString(),
        };
    }

    getNextAvailableItemId(items) {
        items = items || this.formatRawValue(this.state?.value);
        const biggestId = items
            .map((item) => parseInt(item._id))
            .reduce((acc, id) => (id > acc ? id : acc), -1);
        const nextAvailableId = biggestId + 1;
        return nextAvailableId;
    }

    onInput(e) {
        this.handleValueChange(e.target, false);
    }

    onChange(e) {
        this.handleValueChange(e.target, true);
    }

    handleValueChange(targetInputEl, commitToHistory) {
        const id = targetInputEl.dataset.id;
        const propertyName = targetInputEl.name;
        const isCheckbox = targetInputEl.type === "checkbox";
        const value = isCheckbox ? targetInputEl.checked : targetInputEl.value;

        const items = this.formatRawValue(this.state.value);
        if (
            value === true &&
            this.props.itemShape[propertyName] === "exclusive_boolean"
        ) {
            for (const item of items) {
                item[propertyName] = false;
            }
        }
        const item = items.find((item) => item._id === id);
        item[propertyName] = value;
        if (!isCheckbox && propertyName === "id") {
            item.id = isSmallInteger(value) ? parseInt(value) : value;
        }

        if (commitToHistory) {
            this.commit(items);
        } else {
            this.preview(items);
        }
    }
}

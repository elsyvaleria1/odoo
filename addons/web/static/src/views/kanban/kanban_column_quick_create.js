// @ts-check
/** @odoo-module native */

import { Component, onPatched, proxy, t, useProps } from "@odoo/owl";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { elementRef } from "@web/core/utils/element_ref";
import { useAutofocus, useService } from "@web/core/utils/hooks";
import { useWindowClickFromPress } from "@web/views/view_hook";

export class KanbanColumnQuickCreate extends Component {
    static template = "web.KanbanColumnQuickCreate";
    static props = {
        onFoldChange: t.function(),
        onValidate: t.function(),
        folded: t.boolean(),
        groupByField: t.object(),
    };
    props = useProps(this.constructor.props);

    /** @type {import("@odoo/owl").Ref} */
    inputRef;
    /** @type {import("@odoo/owl").Ref} */
    root;
    /** @type {{ hasInputFocused: boolean }} */
    state;

    setup() {
        this.dialog = useService("dialog");
        this.root = elementRef();
        this.state = proxy({
            hasInputFocused: false,
        });

        this.inputRef = elementRef();
        useAutofocus({ ref: this.inputRef });

        useWindowClickFromPress((target) => {
            if (this.root.el && !this.root.el.contains(target)) {
                this.fold();
            }
        });

        useHotkey("escape", () => this.fold());
        onPatched(() => {
            if (this.state.hasInputFocused && !this.props.folded) {
                this.root.el?.scrollIntoView({ behavior: "smooth" });
            }
        });
    }

    /** @returns {string} */
    get relatedFieldName() {
        return this.props.groupByField.string;
    }

    fold() {
        this.props.onFoldChange(true);
    }

    unfold() {
        this.props.onFoldChange(false);
    }

    validate() {
        const inputEl = /** @type {HTMLInputElement} */ (this.inputRef.el);
        const title = inputEl.value.trim();
        if (title.length) {
            this.props.onValidate(title);
            inputEl.value = "";
            inputEl.focus();
            this.state.hasInputFocused = true;
        }
    }

    /** @param {KeyboardEvent} ev */
    onInputKeydown(ev) {
        if (ev.key === "Enter") {
            this.validate();
        }
    }
}

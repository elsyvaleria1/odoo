// @ts-check
/** @odoo-module native */
import { Component, onMounted, onWillUpdateProps, proxy, t, useProps } from "@odoo/owl";
import { useAutoresize } from "@web/core/utils/dom/autoresize";
import { elementRef } from "@web/core/utils/element_ref";
export class AutoresizeInput extends Component {
    static template = "mail.AutoresizeInput";
    static props = {
        autofocus: t.boolean().optional(false),
        className: t.string().optional(""),
        enabled: t.any().optional(true),
        onCancel: t.function().optional(() => () => {}),
        onValidate: t.function().optional(() => () => {}),
        placeholder: t.string().optional(""),
        value: t.string().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.state = proxy({
            value: this.props.value,
            isFocused: false,
        });
        this.inputRef = /** @type {import("@odoo/owl").Ref<HTMLInputElement>} */ (
            elementRef()
        );
        onWillUpdateProps(
            /** @param {{value: string}} nextProps */ (nextProps) => {
                if (this.props.value !== nextProps.value && !this.state.isFocused) {
                    this.state.value = nextProps.value;
                }
            },
        );
        useAutoresize(this.inputRef);
        onMounted(() => {
            if (this.props.autofocus) {
                this.inputRef.el.focus();
                /** @type {HTMLInputElement | HTMLTextAreaElement} */ (
                    this.inputRef.el
                ).setSelectionRange(-1, -1);
            }
        });
    }

    /** @param {KeyboardEvent} ev */
    onKeydownInput(ev) {
        switch (ev.key) {
            case "Enter":
                this.inputRef.el.blur();
                break;
            case "Escape":
                ev.stopPropagation();
                this.state.value = this.props.value;
                this.cancelled = true;
                this.inputRef.el.blur();
                break;
        }
    }

    onBlurInput() {
        this.state.isFocused = false;
        if (this.cancelled) {
            this.cancelled = false;
            this.props.onCancel();
            return;
        }
        this.props.onValidate(this.state.value);
    }
}

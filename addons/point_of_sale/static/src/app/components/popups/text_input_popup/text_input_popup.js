/** @odoo-module native */
import { Component, onMounted, proxy, t, useProps } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { elementRef } from "@web/core/utils/element_ref";
import { Dialog } from "@web/ui/dialog";
const log = makeLogger("pos.popup.text_input");
export class TextInputPopup extends Component {
    static template = "point_of_sale.TextInputPopup";
    static components = { Dialog };
    static props = {
        title: t.string(),
        size: t.string().optional("lg"),
        buttons: t.array().optional([]),
        startingValue: t.string().optional(""),
        placeholder: t.string().optional(""),
        rows: t.number().optional(1),
        getPayload: t.function(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({ inputValue: this.props.startingValue });
        this.inputRef = elementRef();
        onMounted(this.onMounted);
    }
    onMounted() {
        this.inputRef.el.focus();
        this.inputRef.el.select();
    }
    confirm() {
        log.logic("confirm", () => ({
            title: this.props.title,
            length: this.state.inputValue.length,
            changed: this.state.inputValue !== this.props.startingValue,
        }));
        this.props.getPayload(this.state.inputValue);
        this.props.close();
    }

    close() {
        this.props.close();
    }

    buttonClick(button) {
        const lines = this.state.inputValue.split("\n").filter((line) => line !== "");
        if (lines.includes(button.label)) {
            this.state.inputValue = lines
                .filter((line) => line !== button.label)
                .join("\n");
            button.isSelected = false;
        } else {
            this.state.inputValue = lines.join("\n");
            this.state.inputValue += (lines.length > 0 ? "\n" : "") + button.label;
            button.isSelected = true;
        }
    }

    onKeydown(ev) {
        if (this.props.rows === 1 && ev.key.toUpperCase() === "ENTER") {
            ev.preventDefault();
            ev.stopPropagation();
            if (this.state.inputValue.trim()) {
                this.confirm();
            }
        }
    }
}

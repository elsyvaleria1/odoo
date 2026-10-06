/** @odoo-module native */
import { Component, proxy, t, useListener, useProps } from "@odoo/owl";
import { Dialog } from "@web/ui/dialog";

const INPUT_KEYS = new Set(["Delete", "Backspace"].concat("0123456789,".split("")));

export class PinPopup extends Component {
    static template = "mrp_workorder.PinPopup";
    static components = { Dialog };
    static props = {
        popupData: t.object(),
        onClosePopup: t.function(),
        onPinValidate: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.state = proxy({ buffer: "" });
        this.employee = this.props.popupData.employee;

        useListener(window, "keyup", this._onKeyUp.bind(this));
    }

    get inputBuffer() {
        return this.state.buffer.replace(/./g, "•");
    }

    sendInput(key) {
        if (INPUT_KEYS.has(key)) {
            if (key === "Delete") {
                this.state.buffer = "";
            } else if (key === "Backspace") {
                this.state.buffer = this.state.buffer.slice(0, -1);
            } else {
                this.state.buffer = this.state.buffer + key;
            }
        }
    }

    async cancel() {
        await this.props.onClosePopup("PinPopup");
    }

    async confirm() {
        const valid = await this.props.onPinValidate(
            this.employee.id,
            this.state.buffer,
        );
        this.state.buffer = "";
        if (valid) {
            await this.props.onClosePopup("PinPopup");
        }
    }

    async _onKeyUp(ev) {
        if (INPUT_KEYS.has(ev.key)) {
            this.sendInput(ev.key);
        } else if (ev.key === "Enter") {
            await this.confirm();
        } else if (ev.key === "Escape") {
            await this.cancel();
        }
    }
}

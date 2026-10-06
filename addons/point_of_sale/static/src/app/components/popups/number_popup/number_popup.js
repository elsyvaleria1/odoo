/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { buttonsType, Numpad } from "@point_of_sale/app/components/numpad/numpad";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";
const log = makeLogger("pos.popup.number");
export class NumberPopup extends Component {
    static template = "point_of_sale.NumberPopup";
    static components = { Numpad, Dialog };
    static props = {
        title: t.string().optional(_t("Amount of guests")),
        subtitle: t.string().optional(),
        buttons: buttonsType.optional(),
        startingValue: t.or([t.number(), t.string()]).optional(""),
        feedback: t.function().optional(() => () => false),
        formatDisplayedValue: t.function().optional(() => (x) => x),
        placeholder: t.string().optional(),
        isValid: t.function().optional(() => () => true),
        confirmButtonLabel: t.string().optional(),
        getPayload: t.function(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        useLifecycleLog(log);
        this.numberBuffer = useService("number_buffer");
        this.numberBuffer.use({
            triggerAtInput: ({ buffer }) => (this.state.buffer = buffer),
            captureWithOverlay: true,
        });
        useHotkey("enter", () => this.confirm());
        useHotkey("escape", () => this.cancel());
        this.state = proxy({
            buffer: this.props.startingValue,
        });
    }

    get confirmButtonLabel() {
        return this.props.confirmButtonLabel || _t("Confirm");
    }

    confirm() {
        this.numberBuffer.capture();
        const valid = this.props.isValid(this.state.buffer);
        log.logic("confirm", () => ({
            title: this.props.title,
            buffer: this.state.buffer,
            valid,
        }));
        if (!valid) {
            return;
        }
        this.props.getPayload(this.state.buffer);
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}

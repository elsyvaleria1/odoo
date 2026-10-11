/** @odoo-module native */
import { KeypadModel } from "@voip/softphone/keypad_model";

export class InCallViewModel {
    activeView = "default";
    keypad = {
        isOpen: false,
        state: new KeypadModel(),
    };
    transferView = {
        activeView: "contacts",
        keypad: new KeypadModel(),
    };

    reset() {
        Object.assign(this, new InCallViewModel());
    }
}

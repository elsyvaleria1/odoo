// @ts-check
/** @odoo-module native */

import { Component, proxy, useProps } from "@odoo/owl";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";

export const VOICE_HOTKEY = "alt+shift+v";

export class VoiceSystray extends Component {
    static template = "voice_command.VoiceSystray";
    static props = null;
    props = useProps(this.constructor.props);

    setup() {
        this.voice = /** @type {import("../voice_service.js").VoiceService} */ (
            useService("voice")
        );
        this.state = proxy(this.voice.state);
        useHotkey(VOICE_HOTKEY, () => this.voice.listen(), {
            global: true,
            bypassEditableProtection: true,
        });
    }

    /** @returns {boolean} */
    get active() {
        return this.state.listening || Boolean(this.state.session);
    }

    /** @returns {string} */
    get title() {
        return this.active
            ? _t("Stop listening (Alt+Shift+V)")
            : _t("Speak a command (Alt+Shift+V)");
    }

    toggle() {
        this.voice.listen();
    }
}

registry
    .category("systray")
    .add("voice_command.systray", { Component: VoiceSystray }, { sequence: 29 });

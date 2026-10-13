// @ts-check
/** @odoo-module native */

import { Component, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { mainComponentEntry } from "@web/ui/main_components_container";

export class VoiceNumbers extends Component {
    static template = "voice_command.VoiceNumbers";
    static props = null;
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy(
            /** @type {import("../voice_service.js").VoiceService} */ (
                useService("voice")
            ).state,
        );
    }

    /** @param {{ top: number, left: number }} badge */
    badgeStyle(badge) {
        return `top: ${badge.top}px; left: ${badge.left}px;`;
    }
}

registry
    .category("main_components")
    .add("voice_command.VoiceNumbers", mainComponentEntry(VoiceNumbers));

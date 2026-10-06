// @ts-check
/** @odoo-module native */
import { registry } from "@web/core/registry";

export { loadLamejs } from "@mail/lib/lamejs";

export class VoiceMessageService {
    /** @param {import("@web/env").OdooEnv} env */
    constructor(env) {
        /** @type {import("@mail/discuss/voice_message/common/voice_player").VoicePlayer} */
        this.activePlayer = null;
    }
}

export const voiceMessageService = {
    /** @param {import("@web/env").OdooEnv} env */
    start(env) {
        return new VoiceMessageService(env);
    },
};

registry.category("services").add("discuss.voice_message", voiceMessageService);

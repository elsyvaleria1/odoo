/** @odoo-module native */
import { fields, Record } from "@mail/core/common/record";

export class AIPromptButton extends Record {
    static _name = "ai.prompt.button";
    static id = "id";

    thread_id = fields.One("discuss.channel", { inverse: "ai_prompt_buttons" });
}

AIPromptButton.register();

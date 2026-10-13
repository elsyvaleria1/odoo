// @ts-check
/** @odoo-module native */

import { voiceExecutorRegistry } from "@voice_command/executor";
import { _t } from "@web/core/translation";

const COMPOSER_BUTTONS = {
    log_note: ".o-mail-Chatter-logNote",
    compose_message: ".o-mail-Chatter-sendMessage",
};

/**
 * @param {import("@voice_command/interpreter/interpreter").Proposal} proposal
 * @param {import("@voice_command/executor").ExecutionContext} context
 */
export async function writeInChatter(proposal, context) {
    const { controller } = context.targetView(proposal);
    const record = controller.model.root;
    if (!record.resId) {
        throw new Error(_t("Save the record before writing in its chatter."));
    }
    const button = controller.rootRef.el?.querySelector(
        COMPOSER_BUTTONS[/** @type {keyof typeof COMPOSER_BUTTONS} */ (proposal.kind)],
    );
    if (!button) {
        throw new Error(_t("This record has no chatter to write in."));
    }
    if (button.disabled) {
        throw new Error(_t("The chatter is still loading; say it again in a moment."));
    }
    if (!button.classList.contains("active")) {
        button.click();
    }
    const thread = context
        .getService("mail.store")
        .Thread.insert({ model: record.resModel, id: record.resId });
    const composer = thread.composer;
    const before = composer.composerText;
    composer.composerText = before ? `${before} ${proposal.text}` : proposal.text;
    return () => {
        composer.composerText = before;
    };
}

voiceExecutorRegistry.add("log_note", writeInChatter);
voiceExecutorRegistry.add("compose_message", writeInChatter);

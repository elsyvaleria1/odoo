/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";

/** @extends {Component<{ attachment: import("models").Attachment }>} */
export class VoiceTranscript extends Component {
    static template = "mail_speech.VoiceTranscript";
    static props = { attachment: t.object() };
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
    }

    /** @returns {boolean} */
    get isPending() {
        return ["queued", "running"].includes(this.props.attachment.transcript_state);
    }

    /** @returns {string} */
    get label() {
        if (this.isPending) {
            return _t("Transcribing…");
        }
        if (this.props.attachment.transcript_state === "failed") {
            return _t("Could not transcribe");
        }
        return _t("Transcribe");
    }

    async onClickTranscribe() {
        this.props.attachment.transcript_state = "queued";
        await this.orm.call("ir.attachment", "action_transcribe", [
            [this.props.attachment.id],
        ]);
    }
}

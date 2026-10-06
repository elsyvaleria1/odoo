/** @odoo-module native */
import { AttachmentList } from "@mail/core/common/attachment_list";
import { patch } from "@web/core/utils/patch";

import { VoiceTranscript } from "./voice_transcript.js";

patch(AttachmentList, {
    components: { ...AttachmentList.components, VoiceTranscript },
});

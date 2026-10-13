/** @odoo-module native */
import { useKnowledgeContext } from "@knowledge/js/knowledge_context";
import { Composer } from "@mail/core/common/composer";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

/** @type {Composer} */
const composerPatch = {
    setup() {
        super.setup(...arguments);
        this.knowledgeContext = useKnowledgeContext();
    },
    get hasGifPicker() {
        return super.hasGifPicker && !this.knowledgeContext.inKnowledge;
    },
    /** @override */
    get SEND_TEXT() {
        return this.props.composer?.thread?.model === "knowledge.article.thread"
            ? _t("Post")
            : super.SEND_TEXT;
    },
};
patch(Composer.prototype, composerPatch);

/** @odoo-module native */
import { useKnowledgeContext } from "@knowledge/js/knowledge_context";
import { Composer } from "@mail/core/common/composer";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

// TODO ABD: could be replaced by a KnowledgeComposer ?
/** @type {Composer} */
const composerPatch = {
    setup() {
        super.setup(...arguments);
        this.knowledgeContext = useKnowledgeContext();
    },
    get hasGifPicker() {
        // Done to remove the gif picker when in Knowledge as per the specs
        return super.hasGifPicker && !this.knowledgeContext.inKnowledge;
    },
    /**
     * Change the label on the button that posts comments on an article.
     * @override
     **/
    get SEND_TEXT() {
        return this.props.composer?.thread?.model === "knowledge.article.thread"
            ? _t("Post")
            : super.SEND_TEXT;
    },
};
patch(Composer.prototype, composerPatch);

/** @odoo-module native */
import { KnowledgeThread } from "@knowledge/mail/thread/knowledge_thread";
import { Composer } from "@mail/core/common/composer";
import { Component, proxy, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";

import { KnowledgeCommentCreatorComposer } from "../../mail/composer/composer.js";

export class KnowledgeCommentsPopover extends Component {
    static template = "knowledge.KnowledgeCommentsPopover";
    static props = { threadId: t.string(), close: t.function() };
    static components = { Composer, KnowledgeThread, KnowledgeCommentCreatorComposer };
    props = useProps(this.constructor.props);

    setup() {
        this.commentsService = useService("knowledge.comments");
        this.commentsState = proxy(this.commentsService.getCommentsState());
        this.rootRef = elementRef();
    }

    onPostCallback() {
        this.props.close();
    }

    onCreateThreadCallback(thread) {
        if (thread) {
            this.commentsState.editorThreads[thread.id]?.select();
        }
    }

    get thread() {
        return this.commentsState.threads[this.props.threadId];
    }
}

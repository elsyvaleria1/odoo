/** @odoo-module native */
import { useKnowledgeContext } from "@knowledge/js/knowledge_context";
import { WebChatter } from "@mail/chatter/web/web_chatter";
import { onWillUnmount } from "@odoo/owl";
import { useCallbackRecorder } from "@web/core/action_hook";
import { Deferred, KeepLast } from "@web/core/utils/concurrency";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { patch } from "@web/core/utils/patch";
import { useViewModel } from "@web/model/model";

const ChatterPatch = {
    setup() {
        super.setup(...arguments);
        this.knowledgeContext = useKnowledgeContext();
        this.model = useViewModel();
        if (this.knowledgeContext.__knowledgeUpdateCommandsRecordInfo__) {
            this.knowledgeCommandsService = useService("knowledgeCommandsService");
            const keepLastRecordInfoRequest = new KeepLast();
            let chatterThreadReady = new Deferred();
            let previousThreadId = this.props.threadId;
            useLayoutEffect(
                (threadId, canPostOnReadonly, hasReadAccess, hasWriteAccess) => {
                    if (previousThreadId !== threadId) {
                        chatterThreadReady.resolve(false);
                        chatterThreadReady = new Deferred();
                    }
                    if (
                        canPostOnReadonly !== undefined &&
                        hasReadAccess !== undefined &&
                        hasWriteAccess !== undefined
                    ) {
                        chatterThreadReady.resolve(true);
                    }
                    previousThreadId = threadId;
                },
                () => [
                    this.props.threadId,
                    this.state.thread?.canPostOnReadonly,
                    this.state.thread?.hasReadAccess,
                    this.state.thread?.hasWriteAccess,
                ],
            );
            onWillUnmount(() => {
                chatterThreadReady.resolve(false);
            });
            useCallbackRecorder(
                this.knowledgeContext.__knowledgeUpdateCommandsRecordInfo__,
                async (recordInfo) => {
                    const chatterThreadReadyForRecordInfo =
                        keepLastRecordInfoRequest.add(chatterThreadReady);
                    if (!(await chatterThreadReadyForRecordInfo)) {
                        return;
                    }
                    if (
                        !this.model.root?.resId ||
                        recordInfo.resId !== this.model.root.resId ||
                        recordInfo.resModel !== this.model.root.resModel
                    ) {
                        return;
                    }
                    Object.assign(recordInfo, {
                        canPostMessages:
                            this.props.threadId &&
                            (this.state.thread?.hasWriteAccess ||
                                (this.state.thread?.hasReadAccess &&
                                    this.state.thread?.canPostOnReadonly)),
                        canAttachFiles:
                            this.props.threadId && this.state.thread?.hasWriteAccess,
                    });
                    if (
                        this.knowledgeCommandsService.isRecordCompatibleWithMacro(
                            recordInfo,
                        )
                    ) {
                        this.knowledgeCommandsService.setCommandsRecordInfo(recordInfo);
                    }
                },
            );
        }
    },
};

patch(WebChatter.prototype, ChatterPatch);

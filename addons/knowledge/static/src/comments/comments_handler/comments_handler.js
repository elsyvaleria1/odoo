/** @odoo-module native */
import { useKnowledgeContext } from "@knowledge/js/knowledge_context";
import { provideMailContext, useMailContext } from "@mail/utils/common/mail_context";
import { batched, Component, observe, proxy, t, useProps } from "@odoo/owl";
import { useCallbackRecorder } from "@web/core/action_hook";
import { localization } from "@web/core/l10n/localization";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { debounce } from "@web/core/utils/timing";

import { CommentBeaconManager } from "../../comments/comment_beacon_manager.js";
import { KnowledgeCommentsThread, MIN_THREAD_WIDTH } from "../comment/comment.js";

const MAX_THREAD_WIDTH = 400;
const SMALL_THREAD_WIDTH = 40; // o_knowledge_small_ui

export class KnowledgeCommentsHandler extends Component {
    static template = "knowledge.KnowledgeCommentsHandler";
    static components = { KnowledgeCommentsThread };
    static props = {
        commentBeaconManager: t.instanceOf(CommentBeaconManager),
        contentRef: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.knowledgeContext = useKnowledgeContext();
        this.commentsService = useService("knowledge.comments");
        this.commentsState = proxy(this.commentsService.getCommentsState());
        const debouncedThreadDimensions = debounce(() => {
            this.computeThreadDimensions();
        }, 300);
        const batchedComputeVerticalDimensions = batched(
            this.computeVerticalDimensions.bind(this),
        );
        provideMailContext({
            threadHeights: observe({}, batchedComputeVerticalDimensions),
        });
        this.mailContext = useMailContext();
        this.lastActiveThreadId;
        this.state = proxy({
            threadDimensions: {
                horizontal: {},
                threadTops: {},
            },
        });
        useCallbackRecorder(
            this.knowledgeContext.__onLayoutGeometryChange__,
            debouncedThreadDimensions,
        );
        let activeThreadId;
        useLayoutEffect(
            () => {
                if (this.commentsState.activeThreadId !== activeThreadId) {
                    activeThreadId = this.commentsState.activeThreadId;
                    batchedComputeVerticalDimensions();
                }
            },
            () => [this.commentsState.activeThreadId],
        );
        useLayoutEffect(
            () => {
                const editorThreads = Object.keys(this.commentsState.editorThreads);
                if (
                    editorThreads.some((threadId) =>
                        this.props.commentBeaconManager.sortedThreadIds.includes(
                            threadId,
                        ),
                    )
                ) {
                    debouncedThreadDimensions();
                }
            },
            () => [
                this.commentsState.editorThreads,
                Object.keys(this.commentsState.editorThreads).toString(),
            ],
        );
    }

    get mainPositionThreadId() {
        if (
            this.commentsState.activeThreadId &&
            this.commentsState.activeThreadId !== this.lastActiveThreadId
        ) {
            this.lastActiveThreadId = this.commentsState.activeThreadId;
        } else if (
            !this.props.commentBeaconManager.sortedThreadIds.includes(
                this.lastActiveThreadId,
            )
        ) {
            this.lastActiveThreadId = undefined;
        }
        return (
            this.lastActiveThreadId ||
            this.props.commentBeaconManager.sortedThreadIds.at(0)
        );
    }

    computeHorizontalDimensions() {
        if (!this.props.contentRef.el) {
            return;
        }
        const rtl = localization.direction === "rtl";
        const keys = {
            paddingRight: "paddingRight",
            left: "left",
            right: "right",
        };
        if (rtl) {
            Object.assign(keys, {
                paddingRight: "paddingLeft",
                left: "right",
                right: "left",
            });
        }
        const contentStyle = getComputedStyle(this.props.contentRef.el);
        const paddingRight = parseInt(contentStyle[keys.paddingRight]) || 0;

        // Manually calculate margin to circumvent zero-margin bug in chromium-based browsers
        const contentRect = this.props.contentRef.el.getBoundingClientRect();
        const parentRect =
            this.props.contentRef.el.parentElement.getBoundingClientRect();
        const marginRight = Math.abs(parentRect[keys.right] - contentRect[keys.right]);
        const marginLeft = Math.abs(parentRect[keys.left] - contentRect[keys.left]);

        const availableWidth = Math.max(0, Math.floor(marginRight + paddingRight));
        let width = Math.min(MAX_THREAD_WIDTH, Math.max(0, availableWidth - 20));
        if (!width) {
            return;
        }
        if (width < MIN_THREAD_WIDTH) {
            width = SMALL_THREAD_WIDTH;
        }
        const left =
            (rtl ? -1 : 1) *
            Math.ceil(
                marginLeft +
                    contentRect.width -
                    paddingRight +
                    (availableWidth + (rtl ? 1 : -1) * width) / 2,
            );
        this.state.threadDimensions.horizontal = { left, width };
    }

    computeVerticalDimensions() {
        const activeId = this.mainPositionThreadId;
        if (
            !activeId ||
            this.commentsState.editorThreads[activeId]?.top === undefined
        ) {
            return;
        }
        const threadIds = this.props.commentBeaconManager.sortedThreadIds.filter(
            (threadId) =>
                threadId in this.commentsState.editorThreads &&
                this.commentsState.editorThreads[threadId].top !== undefined,
        );
        const index = threadIds.indexOf(activeId);
        this.setThreadTop(activeId, this.commentsState.editorThreads[activeId].top);
        let masterTop = this.getThreadTop(activeId);
        for (let i = index - 1; i >= 0; i--) {
            const threadId = threadIds[i];
            const expectedTop = this.commentsState.editorThreads[threadId].top;
            const height = this.mailContext.threadHeights[threadId]?.height || 0;
            if (expectedTop + height < masterTop) {
                masterTop = expectedTop;
            } else {
                masterTop -= height;
            }
            this.setThreadTop(threadId, masterTop);
        }
        masterTop =
            this.getThreadTop(activeId) +
            (this.mailContext.threadHeights[activeId]?.height || 0);
        for (let i = index + 1; i < threadIds.length; i++) {
            const threadId = threadIds[i];
            const expectedTop = this.commentsState.editorThreads[threadId].top;
            masterTop = Math.max(masterTop, expectedTop);
            this.setThreadTop(threadId, masterTop);
            masterTop += this.mailContext.threadHeights[threadId]?.height || 0;
        }
    }

    computeThreadDimensions() {
        this.computeHorizontalDimensions();
        this.computeVerticalDimensions();
    }

    setThreadTop(threadId, top) {
        if (!(threadId in this.state.threadDimensions.threadTops)) {
            this.state.threadDimensions.threadTops[threadId] = {
                top: undefined,
            };
        }
        this.state.threadDimensions.threadTops[threadId].top = top;
    }

    getThreadTop(threadId) {
        return this.state.threadDimensions.threadTops[threadId]?.top;
    }
}

/** @odoo-module native */
import { provideKnowledgeContext } from "@knowledge/js/knowledge_context";
import { Composer } from "@mail/core/common/composer";
import { provideMailContext, useMailContext } from "@mail/utils/common/mail_context";
import { Component, onWillDestroy, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { isBrowserChrome } from "@web/core/browser/feature_detection";
import { user } from "@web/core/user";
import { scrollTo } from "@web/core/utils/dom/scrolling";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { effect } from "@web/core/utils/reactive";
import { batched } from "@web/core/utils/timing";
import { imageUrl } from "@web/core/utils/urls";
import { useViewModel } from "@web/model/model";
import { usePopover } from "@web/ui/popover";

import { KnowledgeCommentCreatorComposer } from "../../mail/composer/composer.js";
import { KnowledgeThread } from "../../mail/thread/knowledge_thread.js";
import { KnowledgeCommentsPopover } from "../comments_popover/comments_popover.js";
import { CommentAnchorText } from "./comment_anchor_text.js";

const DEFAULT_ANCHOR_TEXT_SIZE = 50;
export const MIN_THREAD_WIDTH = 300;

export class KnowledgeCommentsThread extends Component {
    static components = {
        CommentAnchorText,
        Composer,
        KnowledgeThread,
        KnowledgeCommentCreatorComposer,
    };
    static props = {
        threadId: t.string(),
        horizontalDimensions: t.object().optional(),
        top: t.number().optional(),
        readonly: t.boolean().optional(),
    };
    static template = "knowledge.KnowledgeCommentsThread";
    props = useProps(this.constructor.props);

    setup() {
        this.model = useViewModel();
        this.commentsService = useService("knowledge.comments");
        this.threadScrollableRef = elementRef();
        this.targetRef = elementRef();
        this.composerRef = elementRef();
        this.commentsState = proxy(this.commentsService.getCommentsState());
        let previousThreadId;
        this.alive = true;
        effect(
            batched((state) => {
                if (!this.alive) {
                    return;
                }
                if (previousThreadId !== state.activeThreadId) {
                    if (previousThreadId === this.props.threadId && this.editorThread) {
                        this.editorThread.onActivate(
                            new CustomEvent("knowledge.deactivateThread"),
                        );
                    }
                    previousThreadId = state.activeThreadId;
                }
            }),
            [this.commentsState],
        );
        onWillDestroy(() => {
            this.alive = false;
        });
        this.state = proxy({
            hasFullAnchorText: false,
        });
        provideMailContext({ inChatter: false, chatter: false });
        provideKnowledgeContext({
            closeThread: this.updateResolveState.bind(this, true),
            inKnowledge: true,
            isResolved: this.isResolved.bind(this),
            openThread: this.updateResolveState.bind(this, false),
        });
        this.mailContext = useMailContext();
        this.popover = usePopover(KnowledgeCommentsPopover, {
            closeOnClickAway: true,
            onClose: () => {
                this.onClosePopover();
            },
            pluginManager: this.__owl__.pluginManager,
            position: "left-start",
            class: "o_knowledge_comments_popover",
        });
        const onActivate = (ev) => {
            switch (ev.type) {
                case "click":
                    this.activateThread();
                    break;
                case "knowledge.deactivateThread":
                    this.focusOut();
                    break;
            }
        };
        const onFocus = (ev) => {
            switch (ev.type) {
                case "mouseenter":
                    this.focusIn();
                    break;
                case "mouseleave":
                    this.focusOut();
                    break;
            }
        };
        useLayoutEffect(
            () => {
                const editorThread = this.editorThread;
                if (editorThread) {
                    editorThread.onActivateMap.set("main", onActivate);
                    editorThread.onFocusMap.set("main", onFocus);
                }
                return () => {
                    if (editorThread) {
                        editorThread.onActivateMap.delete(onActivate);
                        editorThread.onFocusMap.delete(onFocus);
                    }
                };
            },
            () => [this.editorThread],
        );
        let wasActive;
        useLayoutEffect(
            () => {
                if (this.isActive && !wasActive && !this.smallUI) {
                    const scrollable = this.threadScrollableRef.el;
                    const composer = this.composerRef.el;
                    if (scrollable && composer) {
                        const composerRect = composer.getBoundingClientRect();
                        scrollable.scrollBy({
                            top: composerRect.height,
                        });
                    }
                }
                if (this.isActive !== wasActive) {
                    wasActive = this.isActive;
                }
            },
            () => [this.isActive, this.smallUI],
        );
        if (this.commentsState.displayMode === "handler") {
            const setTargetHeight = (target) => {
                const targetRect = target.getBoundingClientRect();
                if (!(this.props.threadId in this.mailContext.threadHeights)) {
                    this.mailContext.threadHeights[this.props.threadId] = {
                        height: undefined,
                    };
                }
                this.mailContext.threadHeights[this.props.threadId].height =
                    targetRect.height;
            };
            useLayoutEffect(
                () => {
                    if (this.targetRef.el) {
                        const observer = new ResizeObserver((entries) => {
                            for (const entry of entries) {
                                if (entry.target) {
                                    setTargetHeight(entry.target);
                                }
                            }
                        });
                        observer.observe(this.targetRef.el);
                        setTargetHeight(this.targetRef.el);
                        return () => observer.disconnect();
                    }
                },
                () => [this.targetRef.el],
            );
            useLayoutEffect(
                () => {
                    if (
                        this.editorThread &&
                        (this.editorThread.threadId === "undefined" ||
                            this.commentsState.shouldOpenActiveThread) &&
                        this.targetRef.el &&
                        this.isActive
                    ) {
                        this.commentsState.shouldOpenActiveThread = false;
                        if (this.smallUI) {
                            this.openPopover();
                        }
                    }
                },
                () => [
                    this.targetRef.el,
                    this.isActive,
                    this.smallUI,
                    this.editorThread,
                ],
            );
            useLayoutEffect(
                () => {
                    if (!this.smallUI && this.popover.isOpen) {
                        this.popover.close();
                    }
                },
                () => [this.smallUI],
            );
        }
        if (this.props.threadId === "undefined") {
            onWillStart(() => {
                this.commentsService.loadThreads([this.props.threadId]);
            });
        } else {
            useLayoutEffect(
                () => {
                    if (!(this.props.threadId in this.commentsState.threadRecords)) {
                        this.commentsService.loadRecords(this.model.root.resId, {
                            threadId: this.props.threadId,
                        });
                    }
                },
                () => [this.commentsState.articleId, this.commentsState.displayMode],
            );
            useLayoutEffect(
                () => {
                    if (
                        this.props.threadId in this.commentsState.threadRecords &&
                        !(this.props.threadId in this.commentsState.threads)
                    ) {
                        this.commentsService.loadThreads([this.props.threadId]);
                        this.thread.knowledgePreLoading = true;
                        this.thread.fetchNewMessages().then(() => {
                            if (this.editorThread?.isProtected()) {
                                return;
                            }
                            let isEmpty = true;
                            for (const message of this.thread.messages) {
                                if (
                                    message.message_type === "comment" &&
                                    !message.isEmpty
                                ) {
                                    isEmpty = false;
                                    break;
                                }
                            }
                            if (isEmpty) {
                                this.commentsService.deleteThread(this.props.threadId);
                            }
                        });
                        this.thread.knowledgePreLoading = false;
                    }
                },
                () => [this.threadRecord],
            );
        }
        onWillDestroy(() => {
            if (this.isActive) {
                this.commentsState.activeThreadId = undefined;
            }
            this.commentsState.focusedThreads.delete(this.props.threadId);
        });
    }

    get hasLoaded() {
        return (
            this.props.threadId === "undefined" ||
            (this.props.threadId in this.commentsState.threadRecords &&
                this.props.threadId in this.commentsState.threads)
        );
    }

    get hasAllDimensions() {
        return (
            this.props.top !== undefined &&
            this.props.horizontalDimensions !== undefined &&
            this.props.horizontalDimensions.left !== undefined &&
            this.props.horizontalDimensions.width !== undefined
        );
    }

    get style() {
        if (this.commentsState.displayMode === "panel") {
            return "";
        }
        return `
            position: absolute;
            top: ${this.props.top}px;
            left: ${this.props.horizontalDimensions.left}px;
            width: ${this.props.horizontalDimensions.width}px;
            transition: top 0.3s, left 0.2s, filter 0.2s;
            z-index: ${this.isActive ? 1 : "auto"};
            filter: ${
                !this.smallUI ||
                this.hasFocus ||
                (!this.commentsState.activeThreadId &&
                    !this.commentsState.focusedThreads.size)
                    ? "none"
                    : "grayscale(50%) contrast(50%)"
            };
        `;
    }

    get editorThread() {
        return this.commentsState.editorThreads[this.props.threadId];
    }

    get authorUrl() {
        if (this.thread?.messages?.length) {
            return this.thread.messages.at(-1).author.avatarUrl;
        }
        return imageUrl("res.users", user.userId, "avatar_128");
    }

    get anchorText() {
        let text = this.fullAnchorText;
        const brIndex = text.indexOf("<br>");
        const excludeIndex = brIndex === -1 ? DEFAULT_ANCHOR_TEXT_SIZE : brIndex;
        if (text.length > excludeIndex) {
            text = text.substring(0, excludeIndex) + "...";
        }
        return text;
    }

    get fullAnchorText() {
        let text;
        if (!this.editorThread) {
            text = this.threadRecord?.article_anchor_text || "";
        } else {
            text = this.editorThread.anchorText;
        }
        return text.replaceAll("\n", "<br>");
    }

    get hasFocus() {
        return this.commentsState.hasFocus(this.props.threadId);
    }

    get isActive() {
        return this.commentsState.activeThreadId === this.props.threadId;
    }

    get showReadMore() {
        const anchorText = this.anchorText;
        const fullAnchorText = this.fullAnchorText;
        return fullAnchorText.length > 0 && anchorText.length !== fullAnchorText.length;
    }

    get thread() {
        return this.commentsState.threads[this.props.threadId];
    }

    get threadRecord() {
        return this.commentsState.threadRecords[this.props.threadId];
    }

    get smallUI() {
        return (
            this.commentsState.displayMode === "handler" &&
            this.props.horizontalDimensions.width < MIN_THREAD_WIDTH
        );
    }

    activateThread() {
        this.commentsState.activeThreadId = this.props.threadId;
        if (this.smallUI) {
            this.openPopover();
        }
    }

    isResolved() {
        if (this.props.threadId === "undefined") {
            return false;
        }
        return this.threadRecord.is_resolved;
    }

    onClick(ev) {
        if (this.editorThread) {
            this.editorThread.onActivate(ev);
        } else {
            this.activateThread();
        }
    }

    focusIn() {
        this.commentsState.focusedThreads.add(this.props.threadId);
    }

    focusOut() {
        this.commentsState.focusedThreads.delete(this.props.threadId);
    }

    onMouseEnter(ev) {
        if (this.editorThread) {
            this.editorThread.onFocus(ev);
        } else {
            this.focusIn();
        }
    }

    onMouseLeave(ev) {
        if (this.editorThread) {
            this.editorThread.onFocus(ev);
        } else {
            this.focusOut();
        }
    }

    openPopover() {
        if (!this.popover.isOpen) {
            const popoverProps = {
                threadId: this.props.threadId,
            };
            if (this.targetRef.el) {
                this.popover.open(this.targetRef.el, popoverProps);
            }
        }
    }

    onClosePopover() {
        this.focusOut();
    }

    showEditorAnchor() {
        if (!this.editorThread) {
            return;
        }
        if (isBrowserChrome()) {
            scrollTo(this.editorThread.beaconPair.start, {
                behavior: "smooth",
            });
        } else {
            this.editorThread.beaconPair.start.scrollIntoView({
                behavior: "smooth",
                block: "center",
            });
        }
    }

    async updateResolveState(value) {
        const changed = await this.commentsService.updateResolveState(
            this.props.threadId,
            value,
        );
        if (changed && this.commentsState.displayMode === "panel") {
            await this.thread.fetchNewMessages();
        }
    }

    onCreateThreadCallback(thread) {
        if (thread) {
            this.commentsState.editorThreads[thread.id]?.select();
        }
    }
}

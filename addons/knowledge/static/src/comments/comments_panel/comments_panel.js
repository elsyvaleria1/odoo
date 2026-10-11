/** @odoo-module native */
import { Component, onWillDestroy, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { effect } from "@web/core/utils/reactive";
import { batched, debounce } from "@web/core/utils/timing";
import { useViewModel } from "@web/model/model";
import { standardWidgetProps } from "@web/views/widgets";

import { LOAD_THREADS_LIMIT } from "../../comments/comments_service.js";
import { KnowledgeCommentsThread } from "../comment/comment.js";

export class KnowledgeCommentsPanel extends Component {
    static template = "knowledge.KnowledgeCommentsPanel";
    static components = { KnowledgeCommentsThread };
    static props = { ...standardWidgetProps };
    props = useProps(this.constructor.props);

    setup() {
        this.model = useViewModel();
        this.action = useService("action");
        this.commentsService = useService("knowledge.comments");
        this.commentsState = proxy(this.commentsService.getCommentsState());
        let threadRecordsKeys;
        this.alive = true;
        effect(
            batched((state) => {
                if (!this.alive || state.displayMode !== "panel") {
                    return;
                }
                const threadRecords = state.threadRecords;
                const threadIds = Object.keys(threadRecords);
                const keys = threadIds.toString();
                if (keys !== threadRecordsKeys) {
                    this.computeThreadIds();
                    threadRecordsKeys = keys;
                }
            }),
            [this.commentsState],
        );
        onWillDestroy(() => {
            this.alive = false;
        });
        this.state = proxy({
            mode: "unresolved",
            loadMoreResolved: false,
            loadMoreOpen: false,
            loading: false,
            threadIds: [],
        });
        let firstLoad = true;
        useLayoutEffect(
            () => {
                if (this.commentsState.displayMode !== "panel") {
                    return;
                }
                this.computeThreadIds();
                this.commentsService
                    .loadRecords(this.model.root.resId, {
                        ignoreBatch: true,
                        includeLoaded: true,
                        domain: this.domain,
                    })
                    .then((count) => {
                        if (firstLoad) {
                            firstLoad = false;
                            if (count !== undefined && count < LOAD_THREADS_LIMIT) {
                                this.sealLoadMoreState();
                            } else {
                                this.state.loadMoreOpen = true;
                                this.state.loadMoreResolved = true;
                            }
                        }
                    });
            },
            () => [
                this.state.mode,
                this.commentsState.articleId,
                this.commentsState.displayMode,
            ],
        );
        onWillStart(async () => {
            if (this.action.currentController?.action?.context?.show_resolved_threads) {
                this.commentsState.displayMode = "panel";
                this.state.mode = "resolved";
                this.action.currentController.action.context.show_resolved_threads = false;
            }
            this.isPortalUser = await user.hasGroup("base.group_portal");
            this.isInternalUser = await user.hasGroup("base.group_user");
        });
        const loadMore = debounce(this.loadMore.bind(this), 500);
        this.loadMore = () => {
            this.state.loading = true;
            loadMore();
        };
    }

    canDisplayRecord(threadId) {
        if (!this.commentsState.threadRecords[threadId]) {
            return true;
        }
        if (this.state.mode === "unresolved") {
            return !this.commentsState.threadRecords[threadId].is_resolved;
        } else if (this.state.mode === "resolved") {
            return this.commentsState.threadRecords[threadId].is_resolved;
        }
        return true;
    }

    get couldLoadMore() {
        if (this.state.mode === "unresolved") {
            return this.state.loadMoreOpen;
        } else if (this.state.mode === "resolved") {
            return this.state.loadMoreResolved;
        } else {
            return this.state.loadMoreOpen || this.state.loadMoreResolved;
        }
    }

    get domain() {
        let domain = undefined;
        if (this.state.mode === "unresolved") {
            domain = [["is_resolved", "=", false]];
        } else if (this.state.mode === "resolved") {
            domain = [["is_resolved", "=", true]];
        }
        return domain;
    }

    computeThreadIds() {
        const threadIds = [];
        for (const [threadId, record] of Object.entries(
            this.commentsState.threadRecords,
        )) {
            if (
                this.state.mode === "all" ||
                (this.state.mode === "resolved" && record.is_resolved) ||
                (this.state.mode === "unresolved" && !record.is_resolved)
            ) {
                threadIds.push(threadId);
            }
        }
        this.state.threadIds = threadIds.sort((threadIdA, threadIdB) => {
            const dateA = this.commentsState.threadRecords[threadIdA].write_date;
            const dateB = this.commentsState.threadRecords[threadIdB].write_date;
            if (dateA < dateB) {
                return 1;
            } else if (dateA > dateB) {
                return -1;
            } else {
                return 0;
            }
        });
    }

    onChangeMode(ev) {
        this.state.mode = ev.target.value;
    }

    async loadMore() {
        const count = await this.commentsService.loadRecords(this.model.root.resId, {
            ignoreBatch: true,
            domain: this.domain,
        });
        if (count !== undefined && count < LOAD_THREADS_LIMIT) {
            this.sealLoadMoreState();
        }
        this.state.loading = false;
    }

    sealLoadMoreState() {
        if (this.state.mode === "unresolved") {
            this.state.loadMoreOpen = false;
        } else if (this.state.mode === "resolved") {
            this.state.loadMoreResolved = false;
        } else {
            this.state.loadMoreResolved = false;
            this.state.loadMoreOpen = false;
        }
    }
}

export const knowledgeCommentsPanel = {
    component: KnowledgeCommentsPanel,
    additionalClasses: ["col-12", "col-lg-4", "border-top", "d-print-none"],
};

registry
    .category("view_widgets")
    .add("knowledge_comments_panel", knowledgeCommentsPanel);

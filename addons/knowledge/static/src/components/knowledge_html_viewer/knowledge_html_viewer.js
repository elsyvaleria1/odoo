/** @odoo-module native */
import { HtmlViewer } from "@html_editor/components/html_viewer/html_viewer";
import {
    provideEditorOverlayContext,
    useEditorOverlayContext,
} from "@html_editor/core/editor_overlay_context";
import { LocalOverlayContainer } from "@html_editor/local_overlay_container";
import { usePositionHook } from "@html_editor/position_hook";
import { CommentBeaconManager } from "@knowledge/comments/comment_beacon_manager";
import { KnowledgeCommentsHandler } from "@knowledge/comments/comments_handler/comments_handler";
import { useKnowledgeContext } from "@knowledge/js/knowledge_context";
import { onWillDestroy, proxy, useListener } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { uniqueId } from "@web/core/utils/functions";
import { useChildRef, useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { effect } from "@web/core/utils/reactive";
import { batched } from "@web/core/utils/timing";
import { useViewModel } from "@web/model/model";

export class KnowledgeHtmlViewer extends HtmlViewer {
    static template = "knowledge.KnowledgeHtmlViewer";
    static components = {
        ...HtmlViewer.components,
        LocalOverlayContainer,
    };

    setup() {
        super.setup();
        this.model = useViewModel();
        this.commentsService = useService("knowledge.comments");
        this.commentsState = proxy(this.commentsService.getCommentsState());
        let editorThreadsKeys;
        this.alive = true;
        useListener(window, "click", this.onWindowClick.bind(this));
        effect(
            batched((state) => {
                if (!this.alive) {
                    return;
                }
                const editorThreads = state.editorThreads;
                const keys = Object.keys(editorThreads).toString();
                if (keys !== editorThreadsKeys) {
                    this.commentBeaconManager?.sortThreads();
                    this.commentBeaconManager?.drawThreadOverlays();
                    editorThreadsKeys = keys;
                }
            }),
            [this.commentsState],
        );
        onWillDestroy(() => {
            this.alive = false;
        });
        this.overlayRef = useChildRef();
        provideEditorOverlayContext({
            localOverlayContainerKey: uniqueId("html_viewer"),
        });
        this.overlayContext = useEditorOverlayContext();
        this.knowledgeContext = useKnowledgeContext();
        usePositionHook(this.readonlyElementRef, document, () => {
            this.commentBeaconManager?.drawThreadOverlays();
            this.props.config.onLayoutGeometryChange?.();
        });
        this.overlayComponentsKey = uniqueId("KnowledgeCommentsHandler");
        useLayoutEffect(
            () => {
                let overlayContainer;
                if (
                    this.readonlyElementRef.el &&
                    this.overlayRef.el &&
                    this.model.root.data.user_permission &&
                    this.model.root.data.user_permission !== "none"
                ) {
                    overlayContainer = this.makeLocalOverlay();
                    this.overlayRef.el.append(overlayContainer);
                    this.commentBeaconManager = new CommentBeaconManager({
                        document,
                        source: this.readonlyElementRef.el,
                        overlayContainer: overlayContainer,
                        commentsState: this.commentsState,
                        readonly: true,
                    });
                    this.commentBeaconManager.sortThreads();
                    this.commentBeaconManager.drawThreadOverlays();
                    registry
                        .category(this.overlayContext.localOverlayContainerKey)
                        .add(this.overlayComponentsKey, {
                            Component: KnowledgeCommentsHandler,
                            props: {
                                commentBeaconManager: this.commentBeaconManager,
                                contentRef: this.readonlyElementRef,
                            },
                        });
                }
                return () => {
                    overlayContainer?.remove();
                    this.commentBeaconManager?.destroy();
                    this.commentBeaconManager = undefined;
                    registry
                        .category(this.overlayContext.localOverlayContainerKey)
                        .remove(this.overlayComponentsKey);
                    this.overlayComponentsKey = uniqueId("KnowledgeCommentsHandler");
                };
            },
            () => [this.readonlyElementRef.el, this.overlayRef.el, this.state.value],
        );
    }

    onWindowClick(ev) {
        const selector = ".oe-local-overlay, .o_knowledge_comment_box";
        const closestElement = ev.target.closest(selector);
        if (!closestElement) {
            this.commentsState.activeThreadId = undefined;
        }
    }

    makeLocalOverlay() {
        const overlayContainer = document.createElement("div");
        overlayContainer.className = `oe-local-overlay`;
        overlayContainer.setAttribute(
            "data-oe-local-overlay-id",
            "KnowledgeThreadBeacons",
        );
        return overlayContainer;
    }
}

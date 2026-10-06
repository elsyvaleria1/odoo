/** @odoo-module native */
import { provideEditorOverlayContext } from "@html_editor/core/editor_overlay_context";
import {
    Component,
    onWillDestroy,
    proxy,
    t,
    useListener,
    useProps,
    xml,
} from "@odoo/owl";
import { usePosition } from "@web/core/position/position_hook";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { useOverlayScope } from "@web/ui/overlay/overlay_container";
import { useActiveElement } from "@web/ui/ui_service";

export class EditorOverlay extends Component {
    static template = xml`
        <div t-ref="this.rootRef" class="overlay" t-att-class="this.props.className" t-on-pointerdown.stop="() => {}">
            <t t-component="this.props.Component" t-props="this.props.props"/>
        </div>`;

    static props = {
        target: t
            .customValidator(t.any(), (el) => el.nodeType === Node.ELEMENT_NODE)
            .optional(),
        initialSelection: t.object().optional(),
        Component: t.function(),
        props: t.object().optional(),
        editable: t.customValidator(t.any(), (el) => el.nodeType === Node.ELEMENT_NODE),
        bus: t.object(),
        shared: t.object(),
        close: t.function(),
        isOverlayOpen: t.function(),
        getCustomRect: t.function().optional(),
        positionOptions: t.object().optional(),
        className: t.string().optional(""),
        closeOnPointerdown: t.boolean().optional(true),
        hasAutofocus: t.boolean().optional(false),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.overlayScope = useOverlayScope();
        this.ui = useService("ui");
        this.lastSelection = this.props.initialSelection;
        /** @type {HTMLElement} */
        const editable = this.props.editable;
        let getTarget, position;
        if (this.props.target) {
            getTarget = () => this.props.target;
        } else {
            this.rangeElement = editable.ownerDocument.createElement("range-el");
            editable.after(this.rangeElement);
            onWillDestroy(() => {
                this.rangeElement.remove();
            });
            getTarget = this.getSelectionTarget.bind(this);
        }

        useListener(this.props.bus, "updatePosition", () => {
            position.unlock();
        });

        const rootRef = (this.rootRef = elementRef());

        if (this.props.positionOptions?.updatePositionOnResize ?? true) {
            const resizeObserver = new ResizeObserver(() => {
                position.unlock();
            });
            useLayoutEffect(
                (root) => {
                    resizeObserver.observe(root);
                    return () => {
                        resizeObserver.unobserve(root);
                    };
                },
                () => [rootRef.el],
            );
        }

        if (this.props.closeOnPointerdown) {
            const clickAway = (ev) => {
                if (!this.overlayScope?.contains(ev.composedPath()[0])) {
                    this.props.close();
                }
            };
            const editableDocument = this.props.editable.ownerDocument;
            useListener(editableDocument, "pointerdown", clickAway);
            if (editableDocument !== document) {
                useListener(document, "pointerdown", clickAway);
            }
        }

        if (this.props.hasAutofocus) {
            useActiveElement(this.rootRef);
        }
        const topDocument = editable.ownerDocument.defaultView.top.document;
        const scrollContainer = getScrollContainer(editable);
        const container = scrollContainer || topDocument.documentElement;
        const resizeObserver = new ResizeObserver(() => position.unlock());
        resizeObserver.observe(container);
        onWillDestroy(() => resizeObserver.disconnect());
        const positionOptions = {
            position: "bottom-start",
            container: container,
            ...this.props.positionOptions,
            onPositioned: (el, solution) => {
                this.props.positionOptions?.onPositioned?.(el, solution);
                this.updateVisibility(el, solution, scrollContainer);
            },
        };
        position = usePosition(this.rootRef, getTarget, positionOptions);

        this.overlayState = proxy({ isOverlayVisible: true });
        provideEditorOverlayContext({ overlayState: this.overlayState });
    }

    getSelectionTarget() {
        const doc = this.props.editable.ownerDocument;
        const selection = doc.getSelection();
        const selectionData = this.props.shared.getSelectionData();
        if (!selection || !selection.rangeCount || !this.props.isOverlayOpen()) {
            return null;
        }
        const inEditable = selectionData.currentSelectionIsInEditable;
        let range;
        if (inEditable) {
            range = selection.getRangeAt(0);
            this.lastSelection = { range };
        } else {
            if (!this.lastSelection) {
                return null;
            }
            range = this.lastSelection.range;
        }
        let rect =
            this.props.getCustomRect?.() ||
            this.lastSelection.rect ||
            range.getBoundingClientRect();
        if (rect.x === 0 && rect.width === 0 && rect.height === 0) {
            this.props.shared.ignoreDOMMutations(() => {
                const clonedRange = range.cloneRange();
                const shadowCaret = doc.createTextNode("|");
                clonedRange.insertNode(shadowCaret);
                clonedRange.selectNode(shadowCaret);
                rect = clonedRange.getBoundingClientRect();
                shadowCaret.remove();
                clonedRange.detach();
            });
        }
        this.rangeElement.getBoundingClientRect = () => rect;
        return this.rangeElement;
    }

    updateVisibility(overlayElement, solution, scrollContainer) {
        if (this.ui.isSmall) {
            return;
        }
        const shouldBeVisible = this.shouldOverlayBeVisible(
            overlayElement,
            solution,
            scrollContainer,
        );
        overlayElement.style.visibility = shouldBeVisible ? "visible" : "hidden";
        this.overlayState.isOverlayVisible = shouldBeVisible;
    }

    /**
     * @param {HTMLElement} overlayElement
     * @param {Object} solution
     * @param {HTMLElement} scrollContainer
     */
    shouldOverlayBeVisible(overlayElement, solution, scrollContainer) {
        if (!scrollContainer) {
            return true;
        }
        const scrollContainerRect = scrollContainer.getBoundingClientRect();
        let scrollContainerTop = scrollContainerRect.top;
        if (scrollContainer.ownerDocument !== overlayElement.ownerDocument) {
            const frameElement =
                scrollContainer.ownerDocument.defaultView?.frameElement;
            if (frameElement) {
                scrollContainerTop += frameElement.getBoundingClientRect().top;
            }
        }
        const top = Math.max(scrollContainerTop, 0);
        const bottom = top + scrollContainerRect.height;
        const overflowsTop = solution.top < top;
        const overflowsBottom = solution.top + overlayElement.offsetHeight > bottom;
        const canFlip = this.props.positionOptions?.flip ?? true;
        if (overflowsTop) {
            if (overflowsBottom) {
                return true;
            }
            if (solution.direction === "top" && canFlip) {
                return true;
            }
            return false;
        }
        if (overflowsBottom) {
            if (solution.direction === "bottom" && canFlip) {
                return true;
            }
            return false;
        }
        return true;
    }
}

/**
 * @param {HTMLElement} el
 * @returns {HTMLElement|null}
 */
export function getScrollContainer(el) {
    const isScrollable = (/** @type {HTMLElement} */ el) => {
        if (el.tagName === "HTML") {
            return el.scrollHeight > el.ownerDocument.defaultView.visualViewport.height;
        }
        return (
            el.scrollHeight > el.clientHeight &&
            /\bauto\b|\bscroll\b/.test(getComputedStyle(el)["overflow-y"])
        );
    };
    const isFixed = (el) => getComputedStyle(el).position === "fixed";
    while (el) {
        if (isScrollable(el)) {
            return el;
        }
        if (isFixed(el)) {
            el = el.ownerDocument.defaultView.frameElement;
            continue;
        }
        el = el.parentElement || el.ownerDocument.defaultView.frameElement;
    }
    return null;
}

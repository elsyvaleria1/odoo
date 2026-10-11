/** @odoo-module native */
import { Component, onMounted, onPatched, proxy, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

const NEAR_SCREEN_MARGIN = "100% 0px";

export class PdfPage extends Component {
    static props = {
        canvas: t.object().optional(),
        canvases: t.object().optional(),
        isPreview: t.boolean().optional(false),
        isSelected: t.boolean().optional(false),
        isFocused: t.boolean().optional(),
        onPageClicked: t.function().optional(),
        onPageDropped: t.function().optional(),
        onSelectClicked: t.function().optional(),
        onVisible: t.function().optional(),
        toRender: t.boolean().optional(),
        pageId: t.string(),
    };
    static template = "document.component.PdfPage";
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({
            isHover: false,
        });
        this.canvasWrapperRef = elementRef();
        this.isRendered = false;

        onMounted(() => this.renderPage(this.canvas));
        onPatched(() => this.renderPage(this.canvas));
        useLayoutEffect(
            (el) => {
                if (!el || !this.props.onVisible || this.canvas) {
                    return;
                }
                const observer = new IntersectionObserver(
                    (entries) => {
                        if (entries.some((entry) => entry.isIntersecting)) {
                            observer.disconnect();
                            this.props.onVisible(this.props.pageId);
                        }
                    },
                    { rootMargin: NEAR_SCREEN_MARGIN },
                );
                observer.observe(el);
                return () => observer.disconnect();
            },
            () => [this.canvasWrapperRef.el],
        );
    }

    get canvas() {
        return this.props.canvas ?? this.props.canvases?.[this.props.pageId]?.canvas;
    }

    get failed() {
        return Boolean(this.props.canvases?.[this.props.pageId]?.failed);
    }

    /**
     * @public
     * @param {DomElement} canvas
     */
    renderPage(canvas) {
        if (this.props.toRender) {
            this.isRendered = false;
        }
        if (!canvas || this.isRendered) {
            return;
        }
        this.canvasWrapperRef.el.querySelector(".o_documents_pdf_canvas")?.remove();
        this.canvasWrapperRef.el.appendChild(canvas);
        this.isRendered = true;
    }

    /**
     * @public
     * @param {MouseEvent} ev
     */
    onClickWrapper() {
        if (this.props.onPageClicked) {
            this.props.onPageClicked(this.props.pageId);
        }
    }
    /**
     * @public
     * @param {MouseEvent} ev
     */
    onClickSelect(ev) {
        if (this.props.onSelectClicked) {
            this.props.onSelectClicked(this.props.pageId, ev.shiftKey);
        }
    }
    /**
     * @public
     * @param {MouseEvent} ev
     */
    onDragEnter(ev) {
        ev.preventDefault();
        this.state.isHover = true;
    }
    /**
     * @public
     * @param {MouseEvent} ev
     */
    onDragLeave(ev) {
        ev.preventDefault();
        this.state.isHover = false;
    }
    /**
     * @public
     * @param {MouseEvent} ev
     */
    onDragOver(ev) {
        ev.preventDefault();
    }
    /**
     * @public
     * @param {MouseEvent} ev
     */
    onDragStart(ev) {
        ev.dataTransfer.setData("o_documents_pdf_data", this.props.pageId);
    }
    /**
     * @public
     * @param {MouseEvent} ev
     */
    onDrop(ev) {
        ev.preventDefault();
        this.state.isHover = false;
        if (!ev.dataTransfer.types.includes("o_documents_pdf_data")) {
            return;
        }
        const pageId = ev.dataTransfer.getData("o_documents_pdf_data");
        if (pageId === this.props.pageId) {
            return;
        }
        if (this.props.onPageDropped) {
            this.props.onPageDropped(this.props.pageId, pageId);
        }
    }
}

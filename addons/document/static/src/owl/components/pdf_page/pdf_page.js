/** @odoo-module native */
import { Component, onMounted, onPatched, proxy, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";

export class PdfPage extends Component {
    static props = {
        canvas: t.object().optional(),
        /** the manager's thumbnails by page id, read here so only this page re-renders */
        canvases: t.object().optional(),
        isPreview: t.boolean().optional(false),
        isSelected: t.boolean().optional(false),
        isFocused: t.boolean().optional(),
        onPageClicked: t.function().optional(),
        onPageDropped: t.function().optional(),
        onSelectClicked: t.function().optional(),
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
    }

    get canvas() {
        return this.props.canvas ?? this.props.canvases?.[this.props.pageId]?.canvas;
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
        // onDragOver made this a drop target: a file from the desktop would
        // otherwise be opened by the browser in place of the splitter
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

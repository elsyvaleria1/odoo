/** @odoo-module native */
import { getBootstrapComponent } from "@html_builder/core/bootstrap_realm";
import { scrollTo } from "@html_builder/utils/scrolling";
import {
    Component,
    onMounted,
    onWillStart,
    onWillUnmount,
    t,
    useListener,
    useProps,
} from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

export class BackgroundPositionOverlay extends Component {
    static template = "html_builder.BackgroundPositionOverlay";
    static props = {
        editingElement: t.customValidator(
            t.any(),
            (p) => p.nodeType === Node.ELEMENT_NODE,
        ),
        mockEditingElOnImg: t.customValidator(t.any(), (p) => p.tagName === "IMG"),
        applyPosition: t.function(),
        discardPosition: t.function(),
        editable: t.customValidator(t.any(), (p) => p.nodeType === Node.ELEMENT_NODE),
        history: t.object(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.backgroundOverlayRef = elementRef();
        this.overlayMaskRef = elementRef();
        this.overlayContentRef = elementRef();
        this.bgDraggerRef = elementRef();

        this.iframe = this.props.editable.ownerDocument.defaultView.frameElement;
        this.builderOverlayContainerEl = document.querySelector(
            "[data-oe-local-overlay-id='builder-overlay-container']",
        );
        this.targetContainerEl = this.props.editingElement.classList.contains(
            "s_parallax_bg",
        )
            ? this.props.editingElement.parentElement
            : this.props.editingElement;

        this._dimensionOverlay = this.dimensionOverlay.bind(this);

        const editableDocument = this.props.editable.ownerDocument;
        useListener(editableDocument, "pointerdown", this.discard.bind(this));
        useListener(document, "pointerdown", this.discard.bind(this));

        useListener(window, "resize", this._dimensionOverlay);
        useListener(this.iframe.contentWindow, "resize", this._dimensionOverlay);
        useListener(this.iframe.contentWindow, "scroll", this._dimensionOverlay);

        onWillStart(async () => {
            const position = getComputedStyle(this.props.editingElement)
                .backgroundPosition.split(" ")
                .map((v) => parseInt(v));
            const delta = this.getBackgroundDelta();
            this.originalPosition = { left: position[0], top: position[1] };
            this.currentPosition = {
                left: (position[0] / 100) * delta.x || 0,
                top: (position[1] / 100) * delta.y || 0,
            };
            const rect = this.targetContainerEl.getBoundingClientRect();
            const isEditingElEntirelyVisible =
                rect.top >= 0 &&
                rect.bottom <=
                    this.targetContainerEl.ownerDocument.defaultView.innerHeight;
            if (!isEditingElEntirelyVisible) {
                await scrollTo(this.targetContainerEl, { extraOffset: 50 });
            }
        });

        onMounted(() => {
            this.reloadSavePoint = this.props.history.makeSavePoint();
            this.dimensionOverlay();
            this.targetContainerEl.classList.add("o_we_background_positioning");
        });

        useLayoutEffect(() => {
            const win = this.bgDraggerRef.el?.ownerDocument.defaultView;
            const Tooltip = getBootstrapComponent(win, "Tooltip");
            if (!Tooltip) {
                return;
            }
            this.tooltip = Tooltip.getOrCreateInstance(this.bgDraggerRef.el, {
                trigger: "manual",
                container: this.backgroundOverlayRef.el,
            });
            this.tooltip.show();
        });

        onWillUnmount(() => {
            this.builderOverlayContainerEl.style.clipPath = "";
            this.tooltip?.dispose();
        });
    }

    apply() {
        const position = getComputedStyle(this.props.editingElement).backgroundPosition;
        this.reloadSavePoint();
        this.props.applyPosition(position);
    }

    discard() {
        this.reloadSavePoint();
        this.props.discardPosition();
    }

    onWheel(ev) {
        if (ev.ctrlKey) {
            return;
        }
        this.iframe.contentWindow.scrollBy(ev.deltaX, ev.deltaY);
    }

    onDragBackgroundStart(ev) {
        this.backgroundOverlayRef.el.classList.add("o_we_grabbing");
        const documentEl = window.document;
        const onDragBackgroundMove = this.onDragBackgroundMove.bind(this);
        documentEl.addEventListener("mousemove", onDragBackgroundMove);
        documentEl.addEventListener(
            "mouseup",
            () => {
                this.backgroundOverlayRef.el.classList.remove("o_we_grabbing");
                documentEl.removeEventListener("mousemove", onDragBackgroundMove);
            },
            { once: true },
        );
    }

    onDragBackgroundMove(ev) {
        ev.preventDefault();

        const delta = this.getBackgroundDelta();
        this.currentPosition.left = clamp(this.currentPosition.left + ev.movementX, [
            0,
            delta.x,
        ]);
        this.currentPosition.top = clamp(this.currentPosition.top + ev.movementY, [
            0,
            delta.y,
        ]);

        const percentPosition = {
            left: (this.currentPosition.left / delta.x) * 100,
            top: (this.currentPosition.top / delta.y) * 100,
        };
        percentPosition.left = isFinite(percentPosition.left)
            ? percentPosition.left
            : this.originalPosition.left;
        percentPosition.top = isFinite(percentPosition.top)
            ? percentPosition.top
            : this.originalPosition.top;

        this.props.editingElement.style.backgroundPosition = `${percentPosition.left}% ${percentPosition.top}%`;

        function clamp(val, bounds) {
            bounds = bounds.sort();
            return Math.max(bounds[0], Math.min(val, bounds[1]));
        }
    }

    dimensionOverlay() {
        if (!this.overlayMaskRef.el) {
            return;
        }
        const iframeRect = this.iframe.getBoundingClientRect();
        const targetContainerRect = this.targetContainerEl.getBoundingClientRect();
        const scale = this.getIframeContainerScale();
        const scaledRect = new DOMRect(
            scale * targetContainerRect.x,
            scale * targetContainerRect.y,
            scale * targetContainerRect.width,
            scale * targetContainerRect.height,
        );

        const clipPath = `polygon(
            evenodd,
            0 0, 100% 0,100% 100%, 0 100%, 0 0,
            ${scaledRect.left}px ${scaledRect.top}px,
            ${scaledRect.right}px ${scaledRect.top}px,
            ${scaledRect.right}px ${scaledRect.bottom}px,
            ${scaledRect.left}px ${scaledRect.bottom}px,
            ${scaledRect.left}px ${scaledRect.top}px)
        `;
        this.overlayMaskRef.el.style.clipPath = clipPath;
        this.builderOverlayContainerEl.style.clipPath = clipPath;

        Object.assign(this.backgroundOverlayRef.el.style, {
            left: `${iframeRect.left}px`,
            top: `${iframeRect.top}px`,
            height: `${this.props.editable.ownerDocument.body.clientHeight * scale}px`,
            width: `${this.props.editable.ownerDocument.body.clientWidth * scale}px`,
        });

        Object.assign(this.overlayContentRef.el.style, {
            left: `${scaledRect.left}px`,
            top: `${scaledRect.top}px`,
        });
        const overlayButtonsEl = this.overlayContentRef.el.querySelector(
            ".o_we_overlay_buttons",
        );
        overlayButtonsEl.style.top = `${Math.max(0, -scaledRect.top)}px`;
        this.bgDraggerRef.el.style.setProperty(
            "width",
            `${scaledRect.width}px`,
            "important",
        );
        this.bgDraggerRef.el.style.setProperty(
            "height",
            `${scaledRect.height}px`,
            "important",
        );

        if (this.tooltip) {
            this.tooltip.update();
        }
    }

    /**
     * Gets the scale factor of the iframe's parent container.
     * Useful when the user zooms in/out in the browser, as it affects the
     * dimensions of the iframe.
     * @returns {number} The scale factor (1 if no transform is applied)
     */
    getIframeContainerScale() {
        const matrix = getComputedStyle(this.iframe.parentElement).transform;
        if (matrix === "none") {
            return 1;
        }
        const values = matrix
            .match(/matrix(?:3d)?\(([^)]+)\)/)[1]
            .split(",")
            .map(parseFloat);
        return values[0];
    }

    getBackgroundDelta() {
        const naturalWidth = this.props.mockEditingElOnImg.naturalWidth;
        const naturalHeight = this.props.mockEditingElOnImg.naturalHeight;
        const editingElStyle = getComputedStyle(this.props.editingElement);
        const bgRect =
            editingElStyle.backgroundAttachment === "fixed"
                ? this.iframe.getBoundingClientRect()
                : this.props.editingElement.getBoundingClientRect();

        if (editingElStyle.backgroundSize === "cover") {
            const renderRatio = Math.max(
                bgRect.width / naturalWidth,
                bgRect.height / naturalHeight,
            );

            return {
                x: bgRect.width - Math.round(renderRatio * naturalWidth),
                y: bgRect.height - Math.round(renderRatio * naturalHeight),
            };
        }

        let [width, height] = editingElStyle.backgroundSize.split(" ");
        if (width === "auto" && (height === "auto" || !height)) {
            return {
                x: bgRect.width - naturalWidth,
                y: bgRect.height - naturalHeight,
            };
        }
        [width, height] = [parseInt(width), parseInt(height)];
        return {
            x: bgRect.width - (width || (height * naturalWidth) / naturalHeight),
            y: bgRect.height - (height || (width * naturalHeight) / naturalWidth),
        };
    }
}

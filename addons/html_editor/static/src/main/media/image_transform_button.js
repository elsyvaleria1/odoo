/** @odoo-module native */
import { toolbarButtonProps } from "@html_editor/main/toolbar/toolbar";
import { Component, proxy, t, useListener, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";

import { ImageTransformation } from "./image_transformation.js";

export function useImageTransform({
    document,
    closeImageTransformation,
    buttonSelector,
}) {
    let pointerDownInsideTransform = false;

    useListener(document, "pointerdown", (ev) => {
        if (isNodeInsideTransform(ev.target)) {
            pointerDownInsideTransform = true;
        } else {
            closeImageTransformation();
            pointerDownInsideTransform = false;
        }
    });
    useListener(
        document,
        "click",
        (ev) => {
            if (!isNodeInsideTransform(ev.target) && !pointerDownInsideTransform) {
                closeImageTransformation();
            }
            pointerDownInsideTransform = false;
        },
        { capture: true },
    );
    useListener(document, "selectionchange", (ev) => {
        closeImageTransformation();
    });

    function isNodeInsideTransform(node) {
        if (!node) {
            return false;
        }
        if (node.nodeType === Node.TEXT_NODE) {
            node = node.parentElement;
        }
        if (node.matches(buttonSelector)) {
            return true;
        }
        if (
            isImageTransformationOpen() &&
            node.matches(".transfo-controls, .transfo-controls *")
        ) {
            return true;
        }
        return false;
    }

    function isImageTransformationOpen() {
        return registry.category("main_components").contains("ImageTransformation");
    }

    return { isImageTransformationOpen };
}

export class ImageTransformButton extends Component {
    static template = "html_editor.ImageTransformButton";
    static props = {
        id: t.string(),
        icon: t.string(),
        title: t.string(),
        getTargetedImage: t.function(),
        resetImageTransformation: t.function(),
        addStep: t.function(),
        document: t.customValidator(t.any(), (p) => p.nodeType === Node.DOCUMENT_NODE),
        editable: t.customValidator(t.any(), (p) => p.nodeType === Node.ELEMENT_NODE),
        ...toolbarButtonProps,
        activeTitle: t.string(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({ active: false });
        this.transform = useImageTransform({
            document: this.props.document,
            closeImageTransformation: this.closeImageTransformation.bind(this),
            buttonSelector: '[name="image_transform"], [name="image_transform"] *',
        });
    }

    onButtonClick() {
        this.handleImageTransformation(this.props.getTargetedImage());
    }

    handleImageTransformation(image) {
        if (this.transform.isImageTransformationOpen()) {
            this.props.resetImageTransformation(image);
            this.closeImageTransformation();
        } else {
            this.openImageTransformation(image);
        }
    }

    openImageTransformation(image) {
        this.state.active = true;
        registry.category("main_components").add("ImageTransformation", {
            Component: ImageTransformation,
            props: {
                image,
                document: this.props.document,
                editable: this.props.editable,
                destroy: () => this.closeImageTransformation(),
                onChange: () => this.props.addStep(),
            },
        });
    }

    closeImageTransformation() {
        this.state.active = false;
        if (this.transform.isImageTransformationOpen()) {
            registry.category("main_components").remove("ImageTransformation");
        }
    }
}

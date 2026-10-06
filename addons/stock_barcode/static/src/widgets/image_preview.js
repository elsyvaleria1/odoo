/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ImageField } from "@web/fields/media/image/image_field";

export class FullScreenImage extends Component {
    static template = "stock_barcode.FullScreenImage";
    static props = { src: t.string(), close: t.function() };
    props = useProps(this.constructor.props);
}

export class ImagePreviewField extends ImageField {
    static template = "stock_barcode.ImagePreviewField";

    setup() {
        super.setup();
        this.dialog = useService("dialog");
    }

    openImageFullScreen() {
        this.dialog.add(FullScreenImage, {
            src: this.getUrl(this.props.name),
        });
    }
}

export const imageClickEnlarge = {
    component: ImagePreviewField,
};

registry.category("fields").add("image_preview", imageClickEnlarge);

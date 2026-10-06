// @ts-check
/** @odoo-module native */

import { proxy, t } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { _t } from "@web/core/translation";
import { registerField } from "@web/fields/_registry";
import { FieldComponent } from "@web/fields/field_component";
import { fieldHandleFor } from "@web/fields/field_handle";
import { imageDimensionAttributes, imageSizeOption } from "@web/fields/field_options";
import { extractImageDimensions } from "@web/fields/field_utils";
import { useRecordObserver } from "@web/fields/hooks/record_observer";
import { IMAGE_PLACEHOLDER } from "@web/fields/media/image/image_field";
import { standardFieldProps } from "@web/fields/standard_field_props";

const log = makeLogger("web.field.image_url");

export class ImageUrlField extends FieldComponent {
    static template = "web.ImageUrlField";
    static props = {
        ...standardFieldProps,
        width: t.number().optional(),
        height: t.number().optional(),
    };

    static fallbackSrc = IMAGE_PLACEHOLDER;

    /** @type {{ src: any }} */
    state;

    setup() {
        this.failedSrc = undefined;
        this.state = proxy({
            src: this.field.value,
        });

        useRecordObserver((record) => {
            const incoming = fieldHandleFor(record, this.props.name).value;
            const failed = incoming === this.failedSrc;
            if (failed) {
                log.logic("known-broken url shown as placeholder", () => ({
                    src: incoming,
                }));
            }
            this.state.src = failed
                ? /** @type {any} */ (this.constructor).fallbackSrc
                : incoming;
        });
    }

    get sizeStyle() {
        const width = this.props.width;
        const height = this.props.height;
        let style = width ? `max-width: ${width}px;` : `width: auto;`;
        style += height ? `max-height: ${height}px` : `height: auto`;
        return style;
    }

    onLoadFailed() {
        this.failedSrc = this.field.value;
        this.state.src = /** @type {any} */ (this.constructor).fallbackSrc;
    }
}

/** @type {import("registries").FieldsRegistryItemShape} */
const imageUrlField = {
    component: ImageUrlField,
    displayName: _t("Image"),
    supportedOptions: [imageSizeOption()],
    supportedAttributes: [...imageDimensionAttributes()],
    supportedTypes: ["char"],
    extractProps: extractImageDimensions,
};

registerField("image_url", imageUrlField);

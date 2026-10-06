/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/fields/standard_field_props";

import { ImagesCarouselDialog } from "../images_carousel_dialog.js";

/**
 * Component for a many2many field to <ir.attachment>, containing only images.
 */
export class SocialMany2manyImages extends Component {
    static template = "social.SocialMany2manyImages";
    static props = standardFieldProps;
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.dialog = useService("dialog");
    }

    get attachmentsIds() {
        return this.props.record.data[this.props.name].records.map(
            (record) => record.resId,
        );
    }

    onClickMoreImages() {
        this.dialog.add(ImagesCarouselDialog, {
            title: _t("Post Images"),
            activeIndex: 0,
            images: this.attachmentsIds.map(
                (attachmentId) => `/web/image/${attachmentId}`,
            ),
        });
    }
}

export const socialMany2manyImages = {
    component: SocialMany2manyImages,
    supportedTypes: ["many2many"],
};

registry.category("fields").add("social_many2many_images", socialMany2manyImages);

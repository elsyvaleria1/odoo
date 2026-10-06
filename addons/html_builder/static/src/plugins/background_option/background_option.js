/** @odoo-module native */
import { BaseOptionComponent } from "@html_builder/core/utils";
import { ImageFilterOption } from "@html_builder/plugins/image/image_filter_option";
import { ImageFormatOption } from "@html_builder/plugins/image/image_format_option";
import { t } from "@odoo/owl";

import { useBackgroundOption } from "./background_hook.js";
import { BackgroundImageOption } from "./background_image_option.js";
import { BackgroundPositionOption } from "./background_position_option.js";
import { BackgroundShapeOption } from "./background_shape_option.js";

export class BackgroundOption extends BaseOptionComponent {
    static template = "html_builder.BackgroundOption";
    static components = {
        BackgroundImageOption,
        BackgroundPositionOption,
        BackgroundShapeOption,
        ImageFilterOption,
        ImageFormatOption,
    };
    static props = {
        withColors: t.boolean(),
        withImages: t.boolean(),
        withColorCombinations: t.boolean(),
        withShapes: t.boolean().optional(false),
    };

    setup() {
        super.setup();
        const { showColorFilter } = useBackgroundOption(this.isActiveItem);
        this.showColorFilter = showColorFilter;
    }
    computeMaxDisplayWidth() {
        return 1920;
    }
}

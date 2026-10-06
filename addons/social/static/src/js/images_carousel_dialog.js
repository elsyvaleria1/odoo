/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { useCarousel } from "@web/ui/carousel/carousel_hook";
import { Dialog } from "@web/ui/dialog";

export class ImagesCarouselDialog extends Component {
    static components = { Dialog };
    static template = "social.ImagesCarouselDialog";
    static props = {
        title: t.string(),
        images: t.array(),
        activeIndex: t.number(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.carousel = useCarousel({
            count: () => this.props.images.length,
            startIndex: this.props.activeIndex,
        });
    }
}

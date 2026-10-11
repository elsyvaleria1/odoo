/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class SlideCategoryIcon extends Component {
    static template = "website_slides.SlideCategoryIcon";
    static props = {
        slideCategory: t.string(),
        categoryData: t.object({ icon: t.string(), label: t.string() }),
        onClickSlideCategoryIcon: t.function(),
    };
    props = useProps(this.constructor.props);
}

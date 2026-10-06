/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class ModuleToInstallIcon extends Component {
    static template = "website_slides.ModuleToInstallIcon";
    static props = {
        title: t.string(),
        moduleId: t.number(),
        motivational: t.string(),
        onClickInstallModuleIcon: t.function(),
    };
    props = useProps(this.constructor.props);
}

export class SlideCategoryIcon extends Component {
    static template = "website_slides.SlideCategoryIcon";
    static props = {
        slideCategory: t.string(),
        categoryData: t.object({ icon: t.string(), label: t.string() }),
        onClickSlideCategoryIcon: t.function(),
    };
    props = useProps(this.constructor.props);
}

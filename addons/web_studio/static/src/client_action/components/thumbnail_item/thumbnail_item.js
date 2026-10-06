/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { Dropdown } from "@web/components/dropdown";

export class ThumbnailItem extends Component {
    static template = "web_studio.ThumbnailItem";
    static props = {
        className: t.string().optional(),
        showMoreMenu: t.boolean().optional(true),
        icon: t.object(),
        onClick: t.function().optional(() => () => {}),
        canClick: t.boolean().optional(true),
        slots: t.any(),
    };
    static components = { Dropdown };
    props = useProps(this.constructor.props);

    get hasDropdown() {
        return this.props.showMoreMenu && this.props.slots && this.props.slots.dropdown;
    }
}

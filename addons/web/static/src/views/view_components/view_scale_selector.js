// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { Dropdown } from "@web/components/dropdown/dropdown";
import { DropdownItem } from "@web/components/dropdown/dropdown_item";

export class ViewScaleSelector extends Component {
    static components = {
        Dropdown,
        DropdownItem,
    };
    static template = "web.ViewScaleSelector";
    static props = {
        scales: t.object(),
        currentScale: t.string(),
        isWeekendVisible: t.boolean().optional(),
        setScale: t.function(),
        toggleWeekendVisibility: t.function().optional(),
        dropdownClass: t.string().optional(),
    };
    props = useProps(this.constructor.props);
    get scales() {
        return Object.entries(this.props.scales).map(([key, value]) => ({
            key,
            ...value,
        }));
    }
}

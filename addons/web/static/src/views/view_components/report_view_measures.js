// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { Dropdown } from "@web/components/dropdown/dropdown";
import { DropdownItem } from "@web/components/dropdown/dropdown_item";
export class ReportViewMeasures extends Component {
    static template = "web.ReportViewMeasures";
    static components = {
        Dropdown,
        DropdownItem,
    };
    static props = {
        measures: t.object(),
        activeMeasures: t.array(),
        onMeasureSelected: t.function(),
    };
    props = useProps(this.constructor.props);
}

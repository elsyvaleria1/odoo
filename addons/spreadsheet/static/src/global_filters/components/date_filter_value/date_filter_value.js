/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { dateFilterValueToString } from "@spreadsheet/global_filters/helpers";
import { Dropdown, useDropdownState } from "@web/components/dropdown";

import { DateFilterDropdown } from "../date_filter_dropdown/date_filter_dropdown.js";

export class DateFilterValue extends Component {
    static template = "spreadsheet.DateFilterValue";
    static components = { Dropdown, DateFilterDropdown };
    static props = { value: t.object().optional(), update: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        this.dropdownState = useDropdownState();
    }

    onInputClick() {
        this.dropdownState.open();
    }

    get inputValue() {
        return dateFilterValueToString(this.props.value);
    }
}

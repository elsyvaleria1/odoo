/** @odoo-module native */
import { Model, Spreadsheet } from "@odoo/o-spreadsheet";
import { Component, t, useProps } from "@odoo/owl";
import { useSpreadsheetNotificationStore } from "@spreadsheet/hooks";

export class SpreadsheetComponent extends Component {
    static template = "spreadsheet.SpreadsheetComponent";
    static components = { Spreadsheet };
    static props = { model: t.instanceOf(Model) };
    props = useProps(this.constructor.props);

    get model() {
        return this.props.model;
    }
    setup() {
        useSpreadsheetNotificationStore();
    }
}

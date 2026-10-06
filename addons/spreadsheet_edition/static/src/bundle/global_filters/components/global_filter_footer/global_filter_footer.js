/** @odoo-module native */
import { components } from "@odoo/o-spreadsheet";
import { Component, t, useProps } from "@odoo/owl";

const { Section } = components;

export class GlobalFilterFooter extends Component {
    static template = "spreadsheet_edition.GlobalFilterFooter";
    static components = { Section };
    static props = {
        onClickCancel: t.function(),
        onClickDelete: t.function().optional(),
        onClickSave: t.function().optional(),
    };
    props = useProps(this.constructor.props);
}

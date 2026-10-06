/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/ui/dialog";

export class SaleActionHelperDialog extends Component {
    static components = { Dialog };
    static template = "sale.SaleActionHelperDialog";
    static props = { url: t.string(), close: t.function() };
    props = useProps(this.constructor.props);
}

/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/ui/dialog";
export class CancelDialog extends Component {
    static template = "pos_glory_cash.CancelDialog";
    static components = { Dialog };
    static props = { message: t.string(), cancel: t.function(), close: t.function() };
    props = useProps(this.constructor.props);
}

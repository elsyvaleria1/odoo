/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/ui/dialog";

export class iotBoxDisconnectedDialog extends Component {
    static components = { Dialog };
    static props = { url: t.string(), close: t.function() };
    static template = "pos_iot.IotBoxDisconnectedDialog";
    props = useProps(this.constructor.props);
}

/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class PedalStatusButton extends Component {
    static template = "mrp_workorder_iot.PedalStatusButton";
    static props = {
        ...Component.props,
        pedalConnected: t.boolean(),
        takeOwnership: t.function(),
    };
    props = useProps(this.constructor.props);
}

/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class ImportBlockUI extends Component {
    static props = {
        message: t.string().optional(),
        blockComponent: t.object().optional(),
    };
    static template = "base_import.BlockUI";
    props = useProps(this.constructor.props);
}

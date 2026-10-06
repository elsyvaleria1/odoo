/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class PlanningSplitTool extends Component {
    static props = { reactive: t.object({ position: t.string().optional() }) };
    static template = "planning.PlanningSplitTool";
    props = useProps(this.constructor.props);
}

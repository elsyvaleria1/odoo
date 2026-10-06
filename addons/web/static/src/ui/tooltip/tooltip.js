// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";

export class Tooltip extends Component {
    static template = "web.Tooltip";
    static props = {
        close: t.function(),
        tooltip: t.string().optional(),
        template: t.string().optional(),
        info: t.any().optional(),
        id: t.string().optional(),
    };
    props = useProps(this.constructor.props);
}

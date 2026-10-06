// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";

import { AnimatedNumber } from "./animated_number.js";

export class ColumnProgress extends Component {
    static components = {
        AnimatedNumber,
    };
    static template = "web.ColumnProgress";
    static props = {
        aggregate: t.object(),
        group: t.object(),
        onBarClicked: t.function().optional(() => () => {}),
        progressBar: t.object(),
    };
    props = useProps(this.constructor.props);

    /**
     * @param {Object} bar
     * @returns {Promise<void>}
     */
    async onBarClick(bar) {
        await this.props.onBarClicked(bar);
    }
}

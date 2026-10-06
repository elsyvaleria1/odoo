/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";

export class SignStatusIndicator extends Component {
    static template = "sign.SignStatusIndicator";
    static props = { signStatus: t.object() };
    props = useProps(this.constructor.props);

    setup() {
        this.signStatus = this.props.signStatus;
    }

    async saveManually() {
        await this.signStatus.save();
    }

    async discardChanges() {
        await this.signStatus.discardChanges();
    }
}

/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class NewContentRefreshBanner extends Component {
    static template = "social.NewContentRefreshBanner";
    static props = { refreshRequired: t.any(), onClickRefresh: t.any() };
    props = useProps(this.constructor.props);
}

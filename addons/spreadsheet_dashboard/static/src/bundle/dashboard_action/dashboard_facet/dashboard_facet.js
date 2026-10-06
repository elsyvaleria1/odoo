/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class DashboardFacet extends Component {
    static template = "spreadsheet_dashboard.DashboardFacet";
    static components = {};
    static props = {
        facet: t.object(),
        clearFilter: t.function(),
        onClick: t.function(),
    };
    props = useProps(this.constructor.props);
}

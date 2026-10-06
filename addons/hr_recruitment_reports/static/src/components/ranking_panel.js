/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export default class RankingPanel extends Component {
    static template = "hr_recruitment_reports.RankingPanel";
    static props = { ranked_list: t.object() };
    props = useProps(this.constructor.props);
}

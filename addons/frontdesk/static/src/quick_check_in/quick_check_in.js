/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { rpc } from "@web/core/network";

export class QuickCheckIn extends Component {
    static template = "frontdesk.QuickCheckIn";
    static props = {
        plannedVisitors: t.object().optional(),
        setPlannedVisitorData: t.function(),
        showScreen: t.function(),
        token: t.string(),
        stationId: t.number(),
        theme: t.string(),
    };
    props = useProps(this.constructor.props);

    /**
     * @private
     * @param {Object} visitor
     */
    async _onClick(visitor) {
        await rpc(
            `/frontdesk/${this.props.stationId}/${this.props.token}/prepare_visitor_data`,
            {
                visitor_id: visitor.id,
            },
        );
        this.props.setPlannedVisitorData(visitor.id, visitor.message, visitor.host_ids);
        this.props.showScreen("RegisterPage");
    }
}

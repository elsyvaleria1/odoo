/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";

import { useInactivity } from "../use_inactivity.js";

export class DrinkPage extends Component {
    static template = "frontdesk.DrinkPage";
    static props = {
        drinkInfo: t.array().optional(),
        setDrink: t.function(),
        showScreen: t.function(),
        stationId: t.number(),
        theme: t.string(),
        token: t.string(),
        visitorId: t.number(),
    };
    props = useProps(this.constructor.props);
    setup() {
        useInactivity(() => this.props.showScreen("EndPage"), 15000);
    }

    /** @private */
    async _onDrinkSelect(drinkId) {
        await rpc(
            `/frontdesk/${this.props.stationId}/${this.props.token}/prepare_visitor_data`,
            {
                visitor_id: this.props.visitorId,
                drink_ids: [drinkId],
            },
        );
        this.props.setDrink(true);
        this.props.showScreen("EndPage");
    }
}

registry.category("frontdesk_screens").add("DrinkPage", DrinkPage);

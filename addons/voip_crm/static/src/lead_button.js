/** @odoo-module native */
import { ResPartner } from "@mail/core/common/res_partner_model";
import { Component, t, useProps } from "@odoo/owl";
import { Call } from "@voip/core/call_model";
import { ActionButton } from "@voip/softphone/action_button";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";

export class LeadButton extends Component {
    static components = { ActionButton };
    static props = {
        contact: t.instanceOf(ResPartner).optional(),
        call: t.instanceOf(Call).optional(),
    };
    static template = "voip_crm.LeadButton";
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.ui = useService("ui");
        this.voip = useService("voip");
    }

    get partner() {
        if (this.props.call) {
            return this.props.call.partner_id;
        }
        return this.props.contact;
    }

    get opportunityCount() {
        return this.partner?.opportunity_count || 0;
    }

    get leadButtonTitle() {
        return this.opportunityCount > 0 ? _t("View leads") : _t("Create a lead");
    }

    get shouldShowLeadButton() {
        return this.voip.softphone.shouldShowLeadButton;
    }

    async onClickLead() {
        const action = await this.orm.call(
            "res.partner",
            "get_view_opportunities_action",
            [this.partner?.id, this.props.call?.phone_number],
        );
        action.target = this.ui.isSmall ? "new" : "current";
        this.action.doAction(action);
    }
}

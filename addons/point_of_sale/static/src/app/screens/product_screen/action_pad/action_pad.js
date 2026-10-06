/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { BackButton } from "@point_of_sale/app/screens/product_screen/action_pad/back_button/back_button";
import { SelectPartnerButton } from "@point_of_sale/app/screens/product_screen/control_buttons/select_partner_button/select_partner_button";
import { useService } from "@web/core/utils/hooks";
export const actionpadWidgetProps = {
    partner: t.or([t.object(), t.literal(null)]).optional(),
    onClickMore: t.function().optional(),
    actionName: t.string(),
    actionToTrigger: t.function(),
    showActionButton: t.boolean().optional(true),
    fastValidate: t.function().optional(),
};

export class ActionpadWidget extends Component {
    static template = "point_of_sale.ActionpadWidget";
    static components = { SelectPartnerButton, BackButton };
    static props = actionpadWidgetProps;
    props = useProps(this.constructor.props);

    setup() {
        this.utils = useService("contextual_utils_service");
        this.pos = usePos();
        this.ui = useService("ui");
    }

    get currentOrder() {
        return this.pos.getOrder();
    }

    get showFastPaymentMethods() {
        return (
            this.pos.config.use_fast_payment &&
            this.pos.config.fast_payment_method_ids?.length &&
            this.pos.router.state.current === "ProductScreen"
        );
    }
}

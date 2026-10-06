/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { AccordionItem } from "@point_of_sale/app/components/accordion_item/accordion_item";
import { useService } from "@web/core/utils/hooks";

export class PaymentMethodBreakdown extends Component {
    static components = { AccordionItem };
    static template = "point_of_sale.PaymentMethodBreakdown";

    static props = {
        title: t.string(),
        total_amount: t.number(),
        transactions: t.array().optional([]),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.utils = useService("contextual_utils_service");
    }
}

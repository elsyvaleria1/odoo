/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { useService } from "@web/core/utils/hooks";
export class SelectPartnerButton extends Component {
    static template = "point_of_sale.SelectPartnerButton";
    static props = { partner: t.any().optional() };
    props = useProps(this.constructor.props);
    setup() {
        this.pos = usePos();
        this.ui = useService("ui");
    }
}

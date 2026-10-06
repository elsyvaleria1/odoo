/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { Dialog } from "@web/ui/dialog";
export class CashierSelectionPopup extends Component {
    static template = "pos_hr.CashierSelectionPopup";
    static components = { Dialog };
    static props = {
        close: t.function(),
        getPayload: t.function(),
        currentCashier: t.object().optional(),
        employees: t.array(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.pos = usePos();
    }

    async lock() {
        await this.pos.showLoginScreen();
    }
    selectEmployee(employee) {
        this.props.getPayload(employee);
        this.props.close();
    }
}

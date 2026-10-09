/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { ReceiptHeader } from "@point_of_sale/app/screens/receipt_screen/receipt/receipt_header/receipt_header";

export class CashMoveReceipt extends Component {
    static template = "point_of_sale.CashMoveReceipt";
    static components = { ReceiptHeader };
    static props = {
        reason: t.string(),
        label: t.string(),
        formattedAmount: t.string(),
        date: t.string(),
        order: t.object(),
    };
    props = useProps(this.constructor.props);
}

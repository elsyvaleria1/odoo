/** @odoo-module native */
import { t } from "@odoo/owl";
import { paymentScreenPaymentLinesProps } from "@point_of_sale/app/screens/payment_screen/payment_lines/payment_lines";

Object.assign(paymentScreenPaymentLinesProps, {
    refundLines: t.array().optional(),
    selectRefundLine: t.function(),
});

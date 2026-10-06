/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { enhancedButtons } from "@point_of_sale/app/components/numpad/numpad";
import { NumberPopup } from "@point_of_sale/app/components/popups/number_popup/number_popup";
import { PriceFormatter } from "@point_of_sale/app/components/price_formatter/price_formatter";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { parseFloat } from "@web/core/parsers";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
const log = makeLogger("pos.screen.payment.lines");
export const paymentScreenPaymentLinesProps = {
    paymentLines: t.array().optional(),
    deleteLine: t.function(),
    selectLine: t.function(),
    sendForceDone: t.function(),
    sendPaymentCancel: t.function(),
    sendPaymentRequest: t.function(),
    sendPaymentReverse: t.function(),
    updateSelectedPaymentline: t.function(),
    isRefundOrder: t.boolean(),
};

export class PaymentScreenPaymentLines extends Component {
    static template = "point_of_sale.PaymentScreenPaymentLines";
    static components = { PriceFormatter };
    static props = paymentScreenPaymentLinesProps;
    props = useProps(this.constructor.props);

    setup() {
        this.utils = useService("contextual_utils_service");
        useLifecycleLog(log);
        this.ui = useService("ui");
        this.pos = usePos();
        this.dialog = useService("dialog");
    }

    selectedLineClass(line) {
        return { "payment-terminal": line.getPaymentStatus() };
    }
    unselectedLineClass(line) {
        return {};
    }
    async selectLine(paymentline) {
        log.logic("selectLine", () => ({
            payment: paymentline.uuid,
            status: paymentline.getPaymentStatus(),
            amount: paymentline.getAmount(),
            popup: this.ui.isSmall,
        }));
        this.props.selectLine(paymentline.uuid);
        if (this.ui.isSmall) {
            this.dialog.add(NumberPopup, {
                title: _t("New amount"),
                buttons: enhancedButtons(),
                startingValue: this.utils.formatCurrency(
                    paymentline.getAmount(),
                    false,
                ),
                getPayload: (num) => {
                    this.props.updateSelectedPaymentline(parseFloat(num));
                },
            });
        }
    }
}

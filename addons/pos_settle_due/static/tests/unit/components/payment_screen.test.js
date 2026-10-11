import { expect, test } from "@odoo/hoot";
import { setupPosEnv } from "@point_of_sale/../tests/unit/utils";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { mountWithCleanup, patchWithCleanup } from "@web/../tests/web_test_helpers";
import { ConfirmationDialog } from "@web/ui/dialog";

import { definePosSettleDueModels } from "../data/generate_model_definitions.js";

definePosSettleDueModels();

test("validateOrder -> depositOrder", async () => {
    patchWithCleanup(ConfirmationDialog.prototype, {
        setup() {
            super.setup();
            this.props.confirm();
        },
    });

    patchWithCleanup(OrderPaymentValidation.prototype, {
        async _askForCustomerIfRequired() {
            return true;
        },
    });

    const store = await setupPosEnv();
    const order = store.addNewOrder();
    const partner = store.models["res.partner"].get(3);
    const cash = store.models["pos.payment.method"].get(1);
    order.setPartner(partner);
    const payLaterMethod = store.models["pos.payment.method"].get(3);
    const paymentLine = order.addPaymentline(cash);
    paymentLine.data.amount = 50;
    const screen = await mountWithCleanup(PaymentScreen, {
        props: { orderUuid: order.uuid, isDepositOrder: true },
    });

    await screen.validateOrder();
    const cashPaymentLine = order.payment_ids.find(
        (p) => p.payment_method_id.id === cash.id,
    );
    const payLaterPaymentLine = order.payment_ids.find(
        (p) => p.payment_method_id.id === payLaterMethod.id,
    );

    expect(cashPaymentLine.amount).toBe(50);
    expect(payLaterPaymentLine.amount).toBe(-50);
});

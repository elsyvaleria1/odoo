import * as Dialog from "@point_of_sale/../tests/generic_helpers/dialog_util";
import * as Order from "@point_of_sale/../tests/generic_helpers/order_widget_util";
import * as ChromePos from "@point_of_sale/../tests/pos/tours/utils/chrome_util";
import * as combo from "@point_of_sale/../tests/pos/tours/utils/combo_popup_util";
import * as PaymentScreen from "@point_of_sale/../tests/pos/tours/utils/payment_screen_util";
import * as ProductScreenPos from "@point_of_sale/../tests/pos/tours/utils/product_screen_util";
import * as ReceiptScreen from "@point_of_sale/../tests/pos/tours/utils/receipt_screen_util";
import * as TicketScreen from "@point_of_sale/../tests/pos/tours/utils/ticket_screen_util";
import * as ChromeRestaurant from "@pos_restaurant/../tests/tours/utils/chrome";
import * as FloorScreen from "@pos_restaurant/../tests/tours/utils/floor_screen_util";
import * as ProductScreenResto from "@pos_restaurant/../tests/tours/utils/product_screen_util";
import * as SplitBillScreen from "@pos_restaurant/../tests/tours/utils/split_bill_screen_util";
import { registry } from "@web/core/registry";

const Chrome = { ...ChromePos, ...ChromeRestaurant };
const ProductScreen = { ...ProductScreenPos, ...ProductScreenResto };

registry.category("web_tour.tours").add("SplitBillScreenTour", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            FloorScreen.clickTable("2"),
            ProductScreen.addOrderline("Water", "5", "2", "10.0"),
            ProductScreen.addOrderline("Minute Maid", "3", "2", "6.0"),
            ProductScreen.addOrderline("Coca-Cola", "1", "2", "2.0"),
            ProductScreen.clickControlButton("Split"),

            SplitBillScreen.orderlineHas("Water", "5", "0"),
            SplitBillScreen.orderlineHas("Minute Maid", "3", "0"),
            SplitBillScreen.orderlineHas("Coca-Cola", "1", "0"),

            SplitBillScreen.clickOrderline("Water"),
            SplitBillScreen.orderlineHas("Water", "5", "1"),
            SplitBillScreen.clickOrderline("Water"),
            SplitBillScreen.clickOrderline("Water"),
            SplitBillScreen.orderlineHas("Water", "5", "3"),
            SplitBillScreen.subtotalIs("6.0"),
            SplitBillScreen.clickOrderline("Coca-Cola"),
            SplitBillScreen.orderlineHas("Coca-Cola", "1", "1"),
            SplitBillScreen.subtotalIs("8.0"),

            SplitBillScreen.clickButton("Split"),
            ProductScreen.totalAmountIs("8.0"),
            ProductScreen.clickOrderline("Water", "3"),
            ProductScreen.clickOrderline("Coca-Cola", "1"),

            Chrome.clickOrders(),
            TicketScreen.selectOrder("001"),
            TicketScreen.loadSelectedOrder(),
            ProductScreen.isShown(),
            ProductScreen.clickOrderline("Water", "2"),
            ProductScreen.clickOrderline("Minute Maid", "3"),

            Chrome.clickPlanButton(),
            FloorScreen.clickTable("2"),
            ProductScreen.clickControlButton("Split"),

            SplitBillScreen.clickOrderline("Water"),
            SplitBillScreen.orderlineHas("Water", "2", "1"),
            SplitBillScreen.subtotalIs("2.0"),
            SplitBillScreen.clickOrderline("Minute Maid"),
            SplitBillScreen.orderlineHas("Minute Maid", "3", "1"),
            SplitBillScreen.subtotalIs("4.0"),

            SplitBillScreen.clickButton("Split"),
            ProductScreen.totalAmountIs("4.0"),

            Chrome.clickOrders(),
            TicketScreen.selectOrder("001"),
            TicketScreen.loadSelectedOrder(),
            ProductScreen.isShown(),
            ProductScreen.clickOrderline("Water", "1"),
            ProductScreen.clickOrderline("Minute Maid", "2"),
        ].flat(),
});

registry.category("web_tour.tours").add("SplitBillScreenTourPay", {
    steps: () =>
        [
            Chrome.startPoS(),
            FloorScreen.clickTable("4"),
            ProductScreen.addOrderline("Water"),
            ProductScreen.addOrderline("Minute Maid"),
            ProductScreen.clickControlButton("Split"),
            SplitBillScreen.clickOrderline("Water"),
            SplitBillScreen.clickButton("Pay"),
            PaymentScreen.clickPaymentMethod("Bank"),
            PaymentScreen.clickValidate(),
            ReceiptScreen.clickContinueOrder(),
            SplitBillScreen.clickOrderline("Minute Maid"),
            SplitBillScreen.clickOrderline("Minute Maid"),
            SplitBillScreen.clickButton("Pay"),
            PaymentScreen.clickPaymentMethod("Bank"),
            PaymentScreen.clickValidate(),
            ReceiptScreen.clickNextOrder(),
        ].flat(),
});

registry.category("web_tour.tours").add("SplitBillScreenTour2", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            FloorScreen.clickTable("2"),
            ProductScreen.addOrderline("Water", "1", "2.0"),
            ProductScreen.addOrderline("Minute Maid", "1", "2.0"),
            ProductScreen.addOrderline("Coca-Cola", "1", "2.0"),
            Chrome.clickPlanButton(),
            FloorScreen.clickTable("2"),
            Chrome.isSynced(),
            ProductScreen.clickControlButton("Split"),

            SplitBillScreen.clickOrderline("Water"),
            SplitBillScreen.orderlineHas("Water", "1", "1"),
            SplitBillScreen.clickOrderline("Coca-Cola"),
            SplitBillScreen.orderlineHas("Coca-Cola", "1", "1"),
            SplitBillScreen.clickButton("Split"),
            ProductScreen.totalAmountIs("4.0"),
            Chrome.clickOrders(),
            TicketScreen.selectOrder("2B"),
            TicketScreen.loadSelectedOrder(),
            Order.hasLine({ productName: "Coca-Cola", quantity: "1" }),
            Order.hasLine({ productName: "Water", quantity: "1" }),
            ProductScreen.totalAmountIs("4.00"),
            Chrome.clickOrders(),
            TicketScreen.selectOrder("001"),
            TicketScreen.loadSelectedOrder(),
            Order.hasLine({ productName: "Minute Maid", quantity: "1" }),
            ProductScreen.totalAmountIs("2.00"),
        ].flat(),
});

registry.category("web_tour.tours").add("SplitBillScreenTour3", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            FloorScreen.clickTable("2"),
            ProductScreen.addOrderline("Water", "2", "2", "4.00"),
            ProductScreen.clickControlButton("Split"),

            SplitBillScreen.orderlineHas("Water", "2", "0"),

            SplitBillScreen.clickOrderline("Water"),
            SplitBillScreen.orderlineHas("Water", "2", "1"),
            SplitBillScreen.subtotalIs("2.0"),

            SplitBillScreen.clickButton("Split"),
            ProductScreen.totalAmountIs("2.0"),
            ProductScreen.clickPayButton(),
            PaymentScreen.clickPaymentMethod("Bank"),
            PaymentScreen.clickValidate(),
            ReceiptScreen.clickContinueOrder(),

            ProductScreen.isShown(),
            ProductScreen.orderLineHas("Water", "1.0"),
            ProductScreen.clickPayButton(),
            PaymentScreen.clickPaymentMethod("Bank"),
            PaymentScreen.clickValidate(),
            ReceiptScreen.clickNextOrder(),
        ].flat(),
});

registry.category("web_tour.tours").add("SplitBillScreenTour4ProductCombo", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            FloorScreen.clickTable("2"),
            ProductScreen.clickDisplayedProduct("Office Combo"),
            combo.select("Combo Product 3"),
            combo.select("Combo Product 5"),
            combo.select("Combo Product 8"),
            Dialog.confirm(),

            ...ProductScreen.clickDisplayedProduct("Office Combo"),
            combo.select("Combo Product 2"),
            combo.select("Combo Product 4"),
            combo.select("Combo Product 7"),
            Dialog.confirm(),
            ProductScreen.clickOrderline("Combo Product 2"),
            ProductScreen.clickNumpad("2"),
            ProductScreen.selectedOrderlineHas("Combo Product 2", "2"),

            ProductScreen.addOrderline("Water", "1"),
            ProductScreen.addOrderline("Minute Maid", "1"),

            ProductScreen.clickControlButton("Split"),
            SplitBillScreen.clickOrderline("Water"),
            SplitBillScreen.clickOrderline("Combo Product 3"),
            SplitBillScreen.clickOrderline("Combo Product 2"),
            SplitBillScreen.orderlineHas("Water", "1", "1"),
            SplitBillScreen.orderlineHas("Office Combo", "1", "1"),
            SplitBillScreen.orderlineHas("Combo Product 3", "1", "1"),
            SplitBillScreen.orderlineHas("Combo Product 5", "1", "1"),
            SplitBillScreen.orderlineHas("Combo Product 8", "1", "1"),
            SplitBillScreen.orderlineHas("Office Combo", "2", "1"),
            SplitBillScreen.orderlineHas("Combo Product 2", "2", "0"),
            SplitBillScreen.orderlineHas("Combo Product 4", "2", "0"),
            SplitBillScreen.orderlineHas("Combo Product 7", "2", "0"),

            ...SplitBillScreen.subtotalIs("97.15"),
            ...SplitBillScreen.clickButton("Split"),
            ProductScreen.totalAmountIs("97.13"),
            ProductScreen.clickPayButton(),
            ...PaymentScreen.clickPaymentMethod("Bank"),
            ...PaymentScreen.clickValidate(),
            ...ReceiptScreen.clickContinueOrder(),

            ...ProductScreen.isShown(),
            ...ProductScreen.orderLineHas("Minute Maid", "1"),
            ...ProductScreen.clickOrderline("Office Combo"),
            ...ProductScreen.selectedOrderlineHas("Office Combo", "1", "43.33"),
            ...ProductScreen.orderLineHas("Combo Product 2", "1"),
            ...ProductScreen.orderLineHas("Combo Product 4", "1"),
            ...ProductScreen.orderLineHas("Combo Product 7", "1"),
            ...ProductScreen.totalAmountIs("45.53"),
        ].flat(),
});

registry.category("web_tour.tours").add("SplitBillScreenTour5Actions", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            FloorScreen.clickTable("2"),
            ProductScreen.addOrderline("Water", "2", "2", "4.00"),
            ProductScreen.addOrderline("Minute Maid", "1", "3", "3.00"),
            ProductScreen.clickControlButton("Split"),

            SplitBillScreen.orderlineHas("Water", "2", "0"),
            SplitBillScreen.clickOrderline("Water"),
            SplitBillScreen.clickOrderline("Minute Maid"),
            SplitBillScreen.subtotalIs("5.0"),

            SplitBillScreen.clickButton("Transfer"),
            FloorScreen.isShown(),
            FloorScreen.clickTable("5"),

            ProductScreen.orderLineHas("Water", "1"),
            ProductScreen.orderLineHas("Minute Maid", "1"),
            ProductScreen.clickPayButton(),
            PaymentScreen.clickPaymentMethod("Bank"),
            PaymentScreen.clickValidate(),
            ReceiptScreen.clickNextOrder(),

            FloorScreen.clickTable("2"),
            ProductScreen.orderLineHas("Water", "1"),
            ProductScreen.addOrderline("Minute Maid", "2", "3", "6.00"),
            ProductScreen.clickControlButton("Split"),

            SplitBillScreen.clickOrderline("Minute Maid"),
            SplitBillScreen.clickOrderline("water"),
            SplitBillScreen.subtotalIs("5.0"),

            SplitBillScreen.clickButton("Pay"),
            PaymentScreen.isShown(),
            PaymentScreen.clickPaymentMethod("Bank"),
            PaymentScreen.clickValidate(),
            ReceiptScreen.clickContinueOrder(),

            SplitBillScreen.orderlineHas("Minute Maid", "1", "0"),
            SplitBillScreen.clickButton("Pay"),
            PaymentScreen.isShown(),
            PaymentScreen.clickPaymentMethod("Bank"),
            PaymentScreen.clickValidate(),
            ReceiptScreen.clickNextOrder(),
        ].flat(),
});

registry.category("web_tour.tours").add("SplitBillScreenTourTransfer", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            FloorScreen.clickTable("2"),
            ProductScreen.addOrderline("Water", "5", "2", "10.0"),
            ProductScreen.addOrderline("Minute Maid", "3", "2", "6.0"),
            ProductScreen.addOrderline("Coca-Cola", "1", "2", "2.0"),
            ProductScreen.clickControlButton("Discount"),
            Dialog.confirm(),
            ProductScreen.selectedOrderlineHas("discount", 1, "-1.80"),
            ProductScreen.clickControlButton("Split"),

            SplitBillScreen.orderlineHas("Water", "5", "0"),
            SplitBillScreen.orderlineHas("Minute Maid", "3", "0"),
            SplitBillScreen.orderlineHas("Coca-Cola", "1", "0"),
            Order.doesNotHaveLine({ productName: "Discount" }),

            SplitBillScreen.clickOrderline("Water"),
            SplitBillScreen.orderlineHas("Water", "5", "1"),
            SplitBillScreen.clickOrderline("Water"),
            SplitBillScreen.clickOrderline("Water"),
            SplitBillScreen.orderlineHas("Water", "5", "3"),
            SplitBillScreen.subtotalIs("6.0"),
            SplitBillScreen.clickOrderline("Coca-Cola"),
            SplitBillScreen.orderlineHas("Coca-Cola", "1", "1"),
            SplitBillScreen.subtotalIs("8.0"),

            SplitBillScreen.clickButton("Transfer"),
            FloorScreen.clickTable("5"),

            Order.doesNotHaveLine({ productName: "Discount" }),
            ProductScreen.totalAmountIs("8.0"),
            ProductScreen.clickOrderline("Water", "3"),
            ProductScreen.clickOrderline("Coca-Cola", "1"),

            Chrome.clickOrders(),
            TicketScreen.selectOrder("001"),
            TicketScreen.loadSelectedOrder(),
            ProductScreen.isShown(),
            ProductScreen.clickOrderline("Water", "2"),
            ProductScreen.clickOrderline("Minute Maid", "3"),
        ].flat(),
});

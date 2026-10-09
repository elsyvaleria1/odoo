import * as Dialog from "@point_of_sale/../tests/generic_helpers/dialog_util";
import * as Order from "@point_of_sale/../tests/generic_helpers/order_widget_util";
import { scan_barcode } from "@point_of_sale/../tests/generic_helpers/utils";
import * as Chrome from "@point_of_sale/../tests/pos/tours/utils/chrome_util";
import { inLeftSide } from "@point_of_sale/../tests/pos/tours/utils/common";
import * as PaymentScreen from "@point_of_sale/../tests/pos/tours/utils/payment_screen_util";
import * as ProductScreen from "@point_of_sale/../tests/pos/tours/utils/product_screen_util";
import * as ReceiptScreen from "@point_of_sale/../tests/pos/tours/utils/receipt_screen_util";
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("BarcodeScanningTour", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),

            scan_barcode("0123456789"),
            ProductScreen.selectedOrderlineHas("Monitor Stand"),
            scan_barcode("0123456789"),
            ProductScreen.selectedOrderlineHas("Monitor Stand", 2),

            scan_barcode("2305000000004"),
            ProductScreen.selectedOrderlineHas("Magnetic Board", 1, "0.00"),
            scan_barcode("2305000123451"),
            ProductScreen.selectedOrderlineHas("Magnetic Board", 1, "123.45"),

            scan_barcode("2100005000000"),
            ProductScreen.selectedOrderlineHas("Wall Shelf Unit", 0, "0.00"),
            scan_barcode("2100005080002"),
            ProductScreen.selectedOrderlineHas("Wall Shelf Unit", 8),
            Chrome.endTour(),
        ].flat(),
});

registry.category("web_tour.tours").add("BarcodeScanningProductPackagingTour", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),

            scan_barcode("12345601"),
            ProductScreen.selectedOrderlineHas("Packaging Product", 1),
            scan_barcode("12345601"),
            ProductScreen.selectedOrderlineHas("Packaging Product", 2),

            scan_barcode("12345610"),
            ProductScreen.selectedOrderlineHas("Packaging Product", 12),
            scan_barcode("12345610"),
            ProductScreen.selectedOrderlineHas("Packaging Product", 22),
            Chrome.endTour(),
        ].flat(),
});

registry.category("web_tour.tours").add("GS1BarcodeScanningTour", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),

            scan_barcode("0108431673020125100000001"),
            ProductScreen.selectedOrderlineHas("Product 1"),
            scan_barcode("0108431673020125100000001"),
            ProductScreen.selectedOrderlineHas("Product 1", 2),

            scan_barcode("0108431673020125305"),
            ProductScreen.selectedOrderlineHas("Product 1", 7),
            scan_barcode("01084316730201253010"),
            ProductScreen.selectedOrderlineHas("Product 1", 17),

            scan_barcode("08431673020126"),
            ProductScreen.selectedOrderlineHas("Product 2"),
            scan_barcode("08431673020126"),
            ProductScreen.selectedOrderlineHas("Product 2", 2),

            scan_barcode("3760171283370"),
            ProductScreen.selectedOrderlineHas("Product 3"),
            scan_barcode("3760171283370"),
            ProductScreen.selectedOrderlineHas("Product 3", 2),
            Chrome.endTour(),
        ].flat(),
});

registry.category("web_tour.tours").add("BarcodeScanPartnerTour", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),

            scan_barcode("0421234567890"),
            ProductScreen.customerIsSelected("John Doe"),
            Chrome.endTour(),
        ].flat(),
});

registry.category("web_tour.tours").add("test_quantity_package_of_non_basic_unit", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            scan_barcode("555555"),
            ProductScreen.selectedOrderlineHas("Cord", 12),
            Chrome.endTour(),
        ].flat(),
});

registry.category("web_tour.tours").add("ScannedDiscountWithoutLineDiscountsTour", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            scan_barcode("8888888"),
            ProductScreen.selectedOrderlineHas("Scanned Discount Product", 1, "100.00"),
            scan_barcode("2215"),
            inLeftSide(
                Order.hasLine({
                    productName: "Scanned Discount Product",
                    price: "85.00",
                }),
            ),
            ProductScreen.clickPayButton(),
            PaymentScreen.clickPaymentMethod("Bank", true, { remaining: "0.00" }),
            PaymentScreen.clickValidate(),
            ReceiptScreen.receiptIsThere(),
        ].flat(),
});

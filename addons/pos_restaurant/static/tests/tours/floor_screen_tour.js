import * as Dialog from "@point_of_sale/../tests/generic_helpers/dialog_util";
import * as NumberPopup from "@point_of_sale/../tests/generic_helpers/number_popup_util";
import * as Utils from "@point_of_sale/../tests/generic_helpers/utils";
import * as ChromePos from "@point_of_sale/../tests/pos/tours/utils/chrome_util";
import { inLeftSide } from "@point_of_sale/../tests/pos/tours/utils/common";
import * as PaymentScreen from "@point_of_sale/../tests/pos/tours/utils/payment_screen_util";
import * as ProductScreenPos from "@point_of_sale/../tests/pos/tours/utils/product_screen_util";
import * as ReceiptScreen from "@point_of_sale/../tests/pos/tours/utils/receipt_screen_util";
import * as TicketScreen from "@point_of_sale/../tests/pos/tours/utils/ticket_screen_util";
import * as ChromeRestaurant from "@pos_restaurant/../tests/tours/utils/chrome";
import * as FloorScreen from "@pos_restaurant/../tests/tours/utils/floor_screen_util";
import * as ProductScreenResto from "@pos_restaurant/../tests/tours/utils/product_screen_util";
import { registry } from "@web/core/registry";

const Chrome = { ...ChromePos, ...ChromeRestaurant };
const ProductScreen = { ...ProductScreenPos, ...ProductScreenResto };

registry.category("web_tour.tours").add("FloorScreenTour", {
    steps: () =>
        [
            Chrome.startPoS(),
            FloorScreen.selectedFloorIs("Main Floor"),
            FloorScreen.hasTable("2"),
            FloorScreen.hasTable("4"),
            FloorScreen.hasTable("5"),
            FloorScreen.clickFloor("Second Floor"),
            FloorScreen.hasTable("3"),
            FloorScreen.hasTable("1"),

            Chrome.clickMenuOption("Edit Plan"),
            FloorScreen.clickTable("3"),
            FloorScreen.selectedTableIs("3"),
            FloorScreen.clickTable("1"),
            FloorScreen.selectedTableIs("1"),

            FloorScreen.clickFloor("Main Floor"),
            FloorScreen.clickEditButton("Clone"),
            FloorScreen.selectedFloorIs("Main Floor (copy)"),
            FloorScreen.hasTable("2"),
            FloorScreen.hasTable("4"),
            FloorScreen.hasTable("5"),
            Utils.refresh(),
            Chrome.clickMenuOption("Edit Plan"),
            FloorScreen.clickFloor("Main Floor (copy)"),
            FloorScreen.hasTable("2"),
            FloorScreen.hasTable("4"),
            FloorScreen.hasTable("5"),
            FloorScreen.clickEditButton("Delete"),
            Dialog.confirm(),
            Utils.refresh(),
            Chrome.clickMenuOption("Edit Plan"),
            Utils.elementDoesNotExist(
                ".floor-selector .button-floor:contains('Main Floor (copy)')",
            ),

            FloorScreen.clickFloor("Main Floor"),
            {
                trigger: `.edit-buttons i[aria-label="Add Table"]`,
                run: "click",
            },
            FloorScreen.selectedTableIs("6"),
            FloorScreen.clickEditButton("Rename"),

            NumberPopup.enterValue("100"),
            NumberPopup.isShown("100"),
            Dialog.confirm(),
            FloorScreen.selectedTableIs("100"),

            FloorScreen.clickEditButton("Clone"),
            FloorScreen.selectedTableIs("1"),
            FloorScreen.clickEditButton("Rename"),

            NumberPopup.enterValue("1111"),
            NumberPopup.isShown("1111"),
            Dialog.confirm(),
            FloorScreen.selectedTableIs("1111"),

            FloorScreen.clickFloor("Second Floor"),
            FloorScreen.hasTable("3"),
            FloorScreen.hasTable("1"),

            FloorScreen.clickTable("1"),
            FloorScreen.selectedTableIs("1"),
            FloorScreen.ctrlClickTable("3"),
            FloorScreen.selectedTableIs("3"),
            FloorScreen.clickEditButton("Clone"),
            FloorScreen.selectedTableIs("4"),
            FloorScreen.selectedTableIs("5"),

            FloorScreen.clickEditButton("Delete"),
            Dialog.confirm(),

            FloorScreen.clickFloor("Main Floor"),
            FloorScreen.hasTable("2"),
            FloorScreen.hasTable("4"),
            FloorScreen.hasTable("5"),
            FloorScreen.hasTable("100"),
            FloorScreen.hasTable("1111"),

            FloorScreen.clickTable("1111"),
            FloorScreen.selectedTableIs("1111"),
            FloorScreen.clickEditButton("Delete"),
            Dialog.confirm(),

            FloorScreen.clickTable("4"),
            FloorScreen.selectedTableIs("4"),
            FloorScreen.clickEditButton("Seats"),
            NumberPopup.enterValue("⌫9"),
            NumberPopup.enterValue("9"),
            NumberPopup.isShown("9"),
            Dialog.confirm(),
            FloorScreen.table({ name: "4" }),

            FloorScreen.selectedTableIs("4"),
            FloorScreen.clickEditButton("Seats"),
            NumberPopup.enterValue("15"),
            NumberPopup.isShown("15"),
            Dialog.confirm(),
            FloorScreen.table({ name: "4" }),

            FloorScreen.clickEditButton("Make Round"),

            FloorScreen.clickSaveEditButton(),
            FloorScreen.table({ name: "4", withoutClass: ".selected" }),
            FloorScreen.clickTable("4"),
            ProductScreen.isShown(),
            Chrome.clickPlanButton(),

            FloorScreen.clickFloor("Second Floor"),
            FloorScreen.hasTable("3"),
            FloorScreen.clickTable("3"),
            ProductScreen.isShown(),
            Chrome.clickPlanButton(),
            FloorScreen.selectedFloorIs("Second Floor"),
        ].flat(),
});
registry.category("web_tour.tours").add("TableMergeUnmergeTour", {
    steps: () =>
        [
            Chrome.startPoS(),
            FloorScreen.clickFloor("Main Floor"),
            FloorScreen.clickTable("4"),
            ProductScreen.clickDisplayedProduct("Coca-Cola"),
            Chrome.clickPlanButton(),
            FloorScreen.isShown(),
            FloorScreen.linkTables("5", "4"),
            FloorScreen.isChildTable("5"),
            Utils.refresh(),
            FloorScreen.isChildTable("5"),

            FloorScreen.clickTable("5"),
            Chrome.isTabActive("4 & 5"),
            inLeftSide(ProductScreen.orderLineHas("Coca-Cola", "1")),
            Chrome.clickPlanButton(),
            FloorScreen.isShown(),
            FloorScreen.goTo("5"),
            Chrome.isTabActive("4 & 5"),
            inLeftSide(ProductScreen.orderLineHas("Coca-Cola", "1")),
            ProductScreen.clickPayButton(false),
            ProductScreen.discardOrderWarningDialog(),
            PaymentScreen.clickPaymentMethod("Cash"),
            PaymentScreen.clickValidate(),
            ReceiptScreen.clickNextOrder(),
            Utils.negateStep(FloorScreen.isChildTable("5")),

            FloorScreen.linkTables("5", "4"),
            FloorScreen.unlinkTables("5", "4"),
            Utils.negateStep(FloorScreen.isChildTable("5")),

            FloorScreen.isShown(),
            FloorScreen.clickTable("4"),
            ProductScreen.clickDisplayedProduct("Coca-Cola"),
            Chrome.clickPlanButton(),
            FloorScreen.isShown(),

            FloorScreen.clickTable("5"),
            ProductScreen.clickDisplayedProduct("Minute Maid"),
            Chrome.clickPlanButton(),
            FloorScreen.isShown(),

            FloorScreen.linkTables("5", "4"),
            FloorScreen.isChildTable("5"),

            FloorScreen.clickTable("5"),
            Chrome.isTabActive("4 & 5"),
            inLeftSide(ProductScreen.orderLineHas("Coca-Cola", "1")),
            inLeftSide(ProductScreen.orderLineHas("Minute Maid", "1")),
            Chrome.clickPlanButton(),
            FloorScreen.isShown(),

            FloorScreen.unlinkTables("5", "4"),
            Utils.negateStep(FloorScreen.isChildTable("5")),

            FloorScreen.clickTable("4"),
            inLeftSide(ProductScreen.orderLineHas("Coca-Cola", "1")),
            ProductScreen.clickOrderButton(),
            {
                ...Dialog.confirm(),
                content: "Acknowledge printing error (test does not use a printer).",
            },
            ProductScreen.orderlinesHaveNoChange(),
            Chrome.clickPlanButton(),
            FloorScreen.isShown(),

            FloorScreen.clickTable("5"),
            inLeftSide(ProductScreen.orderLineHas("Minute Maid", "1")),
            ProductScreen.clickOrderButton(),
            {
                ...Dialog.confirm(),
                content: "Acknowledge printing error (test does not use a printer).",
            },
            ProductScreen.orderlinesHaveNoChange(),
            Chrome.clickPlanButton(),
            FloorScreen.isShown(),

            FloorScreen.linkTables("5", "4"),
            FloorScreen.clickTable("5"),
            Chrome.isTabActive("4 & 5"),
            ProductScreen.orderlinesHaveNoChange(),

            ProductScreen.clickDisplayedProduct("Minute Maid"),
            ProductScreen.orderlineIsToOrder("Minute Maid"),
            ProductScreen.clickOrderButton(),
            {
                ...Dialog.confirm(),
                content: "Acknowledge printing error (test does not use a printer).",
            },
            ProductScreen.orderlinesHaveNoChange(),

            Chrome.clickPlanButton(),
            FloorScreen.isShown(),
            FloorScreen.unlinkTables("5", "4"),
            Utils.negateStep(FloorScreen.isChildTable("5")),

            FloorScreen.clickTable("5"),
            inLeftSide(ProductScreen.orderLineHas("Minute Maid", "1")),
            Chrome.clickPlanButton(),
            FloorScreen.isShown(),
            FloorScreen.clickTable("4"),
            inLeftSide(ProductScreen.orderLineHas("Coca-Cola", "1")),
            Chrome.clickPlanButton(),
            FloorScreen.isShown(),
        ].flat(),
});

registry.category("web_tour.tours").add("test_create_floor_tour", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            Chrome.clickMenuOption("Edit Plan"),
            FloorScreen.addFloor("AAA"),
        ].flat(),
});

registry.category("web_tour.tours").add("test_tax_in_merge_table_order_line_tour", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            FloorScreen.clickFloor("Main Floor"),
            FloorScreen.clickTable("4"),
            ProductScreen.clickDisplayedProduct("product_1"),
            Chrome.clickPlanButton(),
            FloorScreen.clickFloor("Main Floor"),
            FloorScreen.clickTable("5"),
            ProductScreen.clickDisplayedProduct("product_2"),
            Chrome.clickPlanButton(),
            FloorScreen.isShown(),
            FloorScreen.linkTables("5", "4"),
            FloorScreen.isChildTable("5"),
        ].flat(),
});

registry.category("web_tour.tours").add("no_ghost_floor", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),

            Chrome.clickMenuOption("Edit Plan"),
            FloorScreen.addFloor("Ghost Floor"),
            {
                trigger: `.edit-buttons i[aria-label="Add Table"]`,
                run: "click",
            },
            FloorScreen.selectedTableIs("1"),
            FloorScreen.clickEditButton("Rename"),

            NumberPopup.enterValue("999"),
            NumberPopup.isShown("999"),
            Dialog.confirm(),
            FloorScreen.selectedTableIs("999"),
            FloorScreen.clickSaveEditButton(),

            FloorScreen.clickFloor("Ghost Floor"),
            FloorScreen.clickTable("999"),
            ProductScreen.clickDisplayedProduct("Coca-Cola"),
            ProductScreen.clickPayButton(false),
            PaymentScreen.clickPaymentMethod("Cash"),
            PaymentScreen.clickValidate(),
            ReceiptScreen.clickNextOrder(),

            Chrome.clickMenuOption("Edit Plan"),
            FloorScreen.clickFloor("Ghost Floor"),
            FloorScreen.clickEditButton("Delete"),
            Dialog.confirm(),
            FloorScreen.clickSaveEditButton(),

            Chrome.clickOrders(),
            TicketScreen.selectFilter("Active"),
            TicketScreen.selectFilter("Paid"),
            TicketScreen.selectOrder("0001"),
            TicketScreen.confirmRefund(),
            PaymentScreen.isShown(),
            PaymentScreen.clickPaymentMethod("Cash"),
            PaymentScreen.clickValidate(),
            ReceiptScreen.clickNextOrder(),

            FloorScreen.hasNotFloor("Ghost Floor"),
        ].flat(),
});

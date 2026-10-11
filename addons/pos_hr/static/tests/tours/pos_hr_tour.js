import * as Dialog from "@point_of_sale/../tests/generic_helpers/dialog_util";
import * as NumberPopup from "@point_of_sale/../tests/generic_helpers/number_popup_util";
import * as SelectionPopup from "@point_of_sale/../tests/generic_helpers/selection_popup_util";
import * as Utils from "@point_of_sale/../tests/generic_helpers/utils";
import { negate, scan_barcode } from "@point_of_sale/../tests/generic_helpers/utils";
import * as BackendUtils from "@point_of_sale/../tests/pos/tours/utils/backend_utils";
import * as Chrome from "@point_of_sale/../tests/pos/tours/utils/chrome_util";
import * as PaymentScreen from "@point_of_sale/../tests/pos/tours/utils/payment_screen_util";
import * as ProductScreen from "@point_of_sale/../tests/pos/tours/utils/product_screen_util";
import * as ReceiptScreen from "@point_of_sale/../tests/pos/tours/utils/receipt_screen_util";
import * as TicketScreen from "@point_of_sale/../tests/pos/tours/utils/ticket_screen_util";
import * as PosHr from "@pos_hr/../tests/tours/utils/pos_hr_helpers";
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("PosHrTour", {
    steps: () =>
        [
            Chrome.clickBtn("Open Register"),
            PosHr.loginScreenIsShown(),
            PosHr.clickLoginButton(),
            SelectionPopup.has("Pos Employee1"),
            SelectionPopup.has("Pos Employee2"),
            SelectionPopup.has("Mitchell Admin"),
            SelectionPopup.has("Pos Employee1", { run: "click" }),
            NumberPopup.enterValue("25"),
            NumberPopup.isShown("••"),
            {
                trigger: "body",
                run: () => {
                    window.dispatchEvent(new KeyboardEvent("keyup", { key: "8" }));
                },
            },
            NumberPopup.isShown("•••"),
            NumberPopup.enterValue("1"),
            NumberPopup.isShown("••••"),
            Dialog.confirm(),
            PosHr.clickLoginButton(),
            SelectionPopup.has("Pos Employee1", { run: "click" }),

            NumberPopup.enterValue("25"),
            NumberPopup.isShown("••"),
            NumberPopup.enterValue("80"),
            NumberPopup.isShown("••••"),
            Dialog.confirm(),
            Dialog.confirm("Open Register"),
            ProductScreen.isShown(),
            PosHr.clickCashierName(),
            SelectionPopup.has("Mitchell Admin", { run: "click" }),
            PosHr.clickCashierName(),
            SelectionPopup.has("Pos Employee2", { run: "click" }),
            NumberPopup.enterValue("12"),
            NumberPopup.isShown("••"),
            NumberPopup.enterValue("34"),
            NumberPopup.isShown("••••"),
            Dialog.confirm(),
            ProductScreen.isShown(),

            ProductScreen.addOrderline("Desk Pad", "1"),
            ProductScreen.totalAmountIs("1.98"),
            Chrome.clickOrders(),
            TicketScreen.nthRowContains(1, "Pos Employee2", false),

            PosHr.clickLockButton(),
            Chrome.clickBtn("Unlock Register"),
            PosHr.login("Pos Employee1", "2580"),
            Chrome.createFloatingOrder(),
            ProductScreen.addOrderline("Desk Pad", "1"),
            ProductScreen.totalAmountIs("1.98"),
            Chrome.clickOrders(),
            TicketScreen.nthRowContains(1, "Pos Employee2", false),
            TicketScreen.nthRowContains(2, "Pos Employee1", false),

            Chrome.clickMenuOption("Cash In/Out"),
            Dialog.discard(),

            PosHr.clickCashierName(),
            SelectionPopup.has("Mitchell Admin", { run: "click" }),
            Chrome.createFloatingOrder(),
            ProductScreen.addOrderline("Desk Pad", "1", "8"),
            ProductScreen.totalAmountIs("8.0"),
            Chrome.clickOrders(),
            TicketScreen.nthRowContains(3, "Mitchell Admin", false),

            Chrome.clickMenuOption("Close Register"),
            Dialog.is("Closing Register"),
        ].flat(),
});

registry.category("web_tour.tours").add("CashierStayLogged", {
    steps: () =>
        [
            Chrome.clickBtn("Open Register"),
            PosHr.loginScreenIsShown(),
            PosHr.clickLoginButton(),
            SelectionPopup.has("Pos Employee1"),
            SelectionPopup.has("Pos Employee2"),
            SelectionPopup.has("Mitchell Admin"),
            SelectionPopup.has("Mitchell Admin", { run: "click" }),
            Dialog.confirm("Open Register"),
            PosHr.refreshPage(),
            ProductScreen.isShown(),
            Chrome.clickMenuButton(),
            PosHr.clickLockButton(),
            PosHr.refreshPage(),
            PosHr.loginScreenIsShown(),
        ].flat(),
});

registry.category("web_tour.tours").add("CashierCanSeeProductInfo", {
    steps: () =>
        [
            Chrome.clickBtn("Open Register"),
            PosHr.loginScreenIsShown(),
            PosHr.clickLoginButton(),
            SelectionPopup.has("Mitchell Admin", { run: "click" }),
            Dialog.confirm("Open Register"),
            ProductScreen.clickInfoProduct("product_a", [Dialog.confirm("Close")]),
            Dialog.isNot(),
        ].flat(),
});

registry.category("web_tour.tours").add("CashierCannotClose", {
    steps: () =>
        [
            Chrome.clickBtn("Open Register"),
            PosHr.loginScreenIsShown(),
            PosHr.clickLoginButton(),
            SelectionPopup.has("Test Employee 3", { run: "click" }),
            Dialog.confirm("Open Register"),
            Chrome.clickMenuButton(),
            {
                trigger: negate(`span.dropdown-item:contains("Close Register")`),
            },
            PosHr.clickCashierName(),
            SelectionPopup.has("Mitchell Admin", { run: "click" }),
            Chrome.clickMenuButton(),
            {
                trigger: `span.dropdown-item:contains("Close Register")`,
            },
        ].flat(),
});

registry.category("web_tour.tours").add("test_basic_user_can_change_price", {
    steps: () =>
        [
            Chrome.clickBtn("Open Register"),
            PosHr.loginScreenIsShown(),
            PosHr.clickLoginButton(),
            SelectionPopup.has("Test Employee 3", { run: "click" }),
            Dialog.confirm("Open Register"),
            ProductScreen.addOrderline("Desk Pad", "1", "10", "10"),
        ].flat(),
});

registry.category("web_tour.tours").add("test_change_on_rights_reflected_directly", {
    steps: () =>
        [
            Chrome.clickBtn("Open Register"),
            PosHr.loginScreenIsShown(),
            PosHr.clickLoginButton(),
            SelectionPopup.has("Mitchell Admin", { run: "click" }),
            Dialog.confirm("Open Register"),
            Chrome.clickMenuOption("Backend", { expectUnloadPage: true }),
            BackendUtils.editShopConfiguration("Shop"),
            {
                trigger: ".o_tag:contains('Pos Employee1') .o_delete",
                run: "click",
            },
            BackendUtils.saveConfiguration(),
            {
                trigger: ".o_main_navbar .o-dropdown-item:contains('Dashboard')",
                run: "click",
            },
            {
                trigger: ".btn:contains('Continue Selling')",
                run: "click",
                expectUnloadPage: true,
            },
            Chrome.clickBtn("Unlock Register"),
            PosHr.loginScreenIsShown(),
            PosHr.clickLoginButton(),
            Utils.negateStep(...SelectionPopup.has("Pos Employee1")),
        ].flat(),
});

registry.category("web_tour.tours").add("test_minimal_employee_refund", {
    steps: () =>
        [
            Chrome.clickBtn("Unlock Register"),
            PosHr.loginScreenIsShown(),
            PosHr.clickLoginButton(),
            SelectionPopup.has("Minimal Employee", { run: "click" }),
            Chrome.clickOrders(),
            TicketScreen.selectFilter("Paid"),
            TicketScreen.selectOrder("001"),
            {
                trigger: negate(".subpads"),
            },
            PosHr.clickCashierName(),
            SelectionPopup.has("Mitchell Admin", { run: "click" }),
            TicketScreen.selectFilter("Paid"),
            TicketScreen.selectOrder("001"),
            {
                trigger: ".subpads",
            },
        ].flat(),
});

registry.category("web_tour.tours").add("test_cashier_changed_in_receipt", {
    steps: () =>
        [
            Chrome.clickBtn("Open Register"),
            PosHr.loginScreenIsShown(),
            PosHr.clickLoginButton(),
            SelectionPopup.has("Mitchell Admin", { run: "click" }),
            Dialog.confirm("Open Register"),
            ProductScreen.addOrderline("product_a", "1"),
            ProductScreen.clickPayButton(),
            PaymentScreen.clickPaymentMethod("Bank"),
            PosHr.clickCashierName(),
            SelectionPopup.has("Test Employee 3", { run: "click" }),
            PaymentScreen.clickValidate(),
            ReceiptScreen.cashierNameExists("Test"),
            ReceiptScreen.clickNextOrder(),
        ].flat(),
});

registry.category("web_tour.tours").add("test_cost_and_margin_visibility", {
    steps: () =>
        [
            Chrome.clickBtn("Open Register"),
            PosHr.loginScreenIsShown(),
            PosHr.clickLoginButton(),
            SelectionPopup.has("Mitchell Admin", { run: "click" }),
            Dialog.confirm("Open Register"),
            ProductScreen.clickInfoProduct("product_a"),
            {
                trigger: ".section-financials :contains('Margin')",
            },
            Dialog.confirm("Close"),
            PosHr.clickCashierName(),
            SelectionPopup.has("Test Employee 3", { run: "click" }),
            ProductScreen.clickInfoProduct("product_a"),
            {
                trigger: ".section-financials :contains('Margin')",
            },
            Dialog.confirm("Close"),
            PosHr.clickCashierName(),
            SelectionPopup.has("Test Employee 4", { run: "click" }),
            ProductScreen.clickInfoProduct("product_a"),
            Utils.negateStep({
                trigger: ".section-financials :contains('Margin')",
            }),
        ].flat(),
});

registry.category("web_tour.tours").add("pos_hr_go_backend_closed_registered", {
    steps: () =>
        [
            Chrome.clickBtn("Backend"),
            SelectionPopup.has("Mitchell Admin", { run: "click" }),
            PosHr.loginScreenIsShown(),

            Chrome.clickBtn("Backend"),
            SelectionPopup.has("Pos Employee1", { run: "click" }),
            PosHr.enterPin("2580"),
            PosHr.loginScreenIsShown(),

            Chrome.clickBtn("Backend"),
            SelectionPopup.has("Test Employee 3", { run: "click" }),
            PosHr.loginScreenIsShown(),

            Chrome.clickBtn("Backend"),
            SelectionPopup.has("Test Manager 2", { run: "click" }),
            PosHr.enterPin("5652"),
            PosHr.loginScreenIsShown(),

            Chrome.clickBtn("Backend"),
            SelectionPopup.has("Test Manager 1", { run: "click" }),
            PosHr.enterPin("5651").map((step, index, array) => {
                if (index === array.length - 1) {
                    return {
                        ...step,
                        expectUnloadPage: true,
                    };
                }
                return step;
            }),
            {
                content: "the backend is reached",
                trigger: ".o_main_navbar",
            },
        ].flat(),
});

registry.category("web_tour.tours").add("pos_hr_go_backend_opened_registered", {
    steps: () =>
        [
            Chrome.clickBtn("Open Register"),
            PosHr.clickLoginButton(),

            SelectionPopup.has("Mitchell Admin", { run: "click" }),
            Chrome.clickBtn("Open Register"),
            Chrome.existMenuOption("Close Register"),
            Chrome.notExistMenuOption("Backend"),

            PosHr.clickCashierName(),
            SelectionPopup.has("Pos Employee1", { run: "click" }),
            PosHr.enterPin("2580"),
            Chrome.notExistMenuOption("Close Register"),
            Chrome.notExistMenuOption("Backend"),

            PosHr.clickCashierName(),
            SelectionPopup.has("Test Employee 3", { run: "click" }),
            Chrome.notExistMenuOption("Close Register"),
            Chrome.notExistMenuOption("Backend"),

            PosHr.clickCashierName(),
            SelectionPopup.has("Test Manager 2", { run: "click" }),
            PosHr.enterPin("5652"),
            Chrome.existMenuOption("Close Register"),
            Chrome.notExistMenuOption("Backend"),

            PosHr.clickCashierName(),
            SelectionPopup.has("Test Manager 1", { run: "click" }),
            PosHr.enterPin("5651"),
            Chrome.existMenuOption("Close Register"),
            Chrome.clickMenuOption("Backend", { expectUnloadPage: true }),
        ].flat(),
});

registry
    .category("web_tour.tours")
    .add("pos_hr_go_backend_opened_registered_different_user_logged", {
        steps: () =>
            [
                Chrome.clickBtn("Unlock Register"),
                PosHr.clickLoginButton(),

                SelectionPopup.has("Pos Employee1", { run: "click" }),
                PosHr.enterPin("2580"),
                Chrome.existMenuOption("Backend"),

                PosHr.clickCashierName(),
                SelectionPopup.has("Test Manager 1", { run: "click" }),
                PosHr.enterPin("5651"),
                Chrome.notExistMenuOption("Backend"),
            ].flat(),
    });

registry.category("web_tour.tours").add("test_maximum_closing_difference", {
    steps: () =>
        [
            Chrome.clickBtn("Open Register"),
            PosHr.clickLoginButton(),
            SelectionPopup.has("Mitchell Admin", { run: "click" }),
            ProductScreen.enterOpeningAmount("10"),
            Chrome.clickBtn("Open Register"),

            PosHr.clickCashierName(),
            SelectionPopup.has("Test Manager 2", { run: "click" }),
            PosHr.enterPin("5652"),
            Chrome.clickMenuOption("Close Register"),
            Chrome.clickBtn("Close Register"),
            {
                trigger: negate(`button:contains("Proceed anyway")`),
            },
            Chrome.clickBtn("Ok"),
            Chrome.clickBtn("Discard"),

            PosHr.clickCashierName(),
            SelectionPopup.has("Mitchell Admin", { run: "click" }),
            Chrome.clickMenuOption("Close Register"),
            Chrome.clickBtn("Close Register"),
            Chrome.hasBtn("Proceed anyway"),
            Chrome.clickBtn("Proceed anyway", { expectUnloadPage: true }),
            PosHr.loginScreenIsShown(),
        ].flat(),
});

registry
    .category("web_tour.tours")
    .add("test_scan_employee_barcode_with_pos_hr_disabled", {
        steps: () =>
            [
                scan_barcode("041123"),
                Chrome.clickBtn("Open Register"),
                ProductScreen.isShown(),
            ].flat(),
    });

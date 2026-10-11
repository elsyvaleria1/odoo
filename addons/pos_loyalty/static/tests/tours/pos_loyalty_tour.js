import * as Dialog from "@point_of_sale/../tests/generic_helpers/dialog_util";
import * as Notification from "@point_of_sale/../tests/generic_helpers/notification_util";
import * as SelectionPopup from "@point_of_sale/../tests/generic_helpers/selection_popup_util";
import * as Utils from "@point_of_sale/../tests/generic_helpers/utils";
import { scan_barcode } from "@point_of_sale/../tests/generic_helpers/utils";
import * as Chrome from "@point_of_sale/../tests/pos/tours/utils/chrome_util";
import * as PartnerList from "@point_of_sale/../tests/pos/tours/utils/partner_list_util";
import * as PaymentScreen from "@point_of_sale/../tests/pos/tours/utils/payment_screen_util";
import * as ProductScreen from "@point_of_sale/../tests/pos/tours/utils/product_screen_util";
import * as ReceiptScreen from "@point_of_sale/../tests/pos/tours/utils/receipt_screen_util";
import * as TicketScreen from "@point_of_sale/../tests/pos/tours/utils/ticket_screen_util";
import * as PosLoyalty from "@pos_loyalty/../tests/tours/utils/pos_loyalty_util";
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("PosLoyaltyTour1", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),

            ProductScreen.addOrderline("Whiteboard Pen", "5"),
            PosLoyalty.hasRewardLine("90% on the cheapest product", "-2.88"),
            PosLoyalty.selectRewardLine("on the cheapest product"),
            PosLoyalty.orderTotalIs("13.12"),
            PosLoyalty.finalizeOrder("Cash", "20"),

            ProductScreen.addOrderline("Whiteboard Pen", "6"),
            PosLoyalty.hasRewardLine("on the cheapest product", "-2.88"),
            PosLoyalty.orderTotalIs("16.32"),
            PosLoyalty.removeRewardLine("90% on the cheapest product"),
            PosLoyalty.orderTotalIs("19.2"),
            PosLoyalty.finalizeOrder("Cash", "20"),

            ProductScreen.addOrderline("Desk Organizer", "9"),
            PosLoyalty.hasRewardLine("on the cheapest product", "-4.59"),
            PosLoyalty.removeRewardLine("90% on the cheapest product"),
            PosLoyalty.orderTotalIs("45.90"),
            PosLoyalty.enterCode("invalid_code"),
            Notification.has("invalid_code"),
            PosLoyalty.enterCode("1234"),
            PosLoyalty.hasRewardLine("Free Product - Desk Organizer", "-15.30"),
            PosLoyalty.finalizeOrder("Cash", "50"),

            ProductScreen.addOrderline("Letter Tray", "4"),
            ProductScreen.addOrderline("Desk Organizer", "9"),
            PosLoyalty.hasRewardLine("90% on the cheapest product", "-4.59"),
            PosLoyalty.orderTotalIs("62.43"),
            PosLoyalty.enterCode("5678"),
            PosLoyalty.hasRewardLine("Free Product - Desk Organizer", "-15.30"),
            PosLoyalty.orderTotalIs("47.13"),
            PosLoyalty.removeRewardLine("Free Product"),
            PosLoyalty.orderTotalIs("62.43"),
            PosLoyalty.finalizeOrder("Cash", "90"),

            ProductScreen.addOrderline("Magnetic Board", "10"),
            ProductScreen.addOrderline("Desk Organizer", "3"),
            ProductScreen.addOrderline("Letter Tray", "4"),
            PosLoyalty.hasRewardLine("90% on the cheapest product", "-1.78"),
            PosLoyalty.orderTotalIs("54.44"),
            PosLoyalty.enterCode("promocode"),
            PosLoyalty.hasRewardLine("50% on specific products", "-16.66"),
            PosLoyalty.orderTotalIs("37.78"),
            PosLoyalty.finalizeOrder("Cash", "50"),
        ].flat(),
});

registry.category("web_tour.tours").add("PosLoyaltyTour2", {
    steps: () =>
        [
            Chrome.startPoS(),
            ProductScreen.addOrderline("Desk Organizer", "10"),
            PosLoyalty.hasRewardLine("on the cheapest product", "-4.59"),
            ProductScreen.addOrderline("Letter Tray", "4"),
            PosLoyalty.hasRewardLine("on the cheapest product", "-4.59"),
            PosLoyalty.enterCode("123456"),
            PosLoyalty.hasRewardLine("10% on your order", "-4.64"),
            PosLoyalty.hasRewardLine("10% on your order", "-2.11"),
            PosLoyalty.orderTotalIs("60.78"),
            PosLoyalty.finalizeOrder("Cash", "70"),

            ProductScreen.addOrderline("Desk Organizer", "11"),
            PosLoyalty.hasRewardLine("90% on the cheapest product", "-4.59"),
            PosLoyalty.orderTotalIs("51.51"),
            PosLoyalty.enterCode("345678"),
            PosLoyalty.hasRewardLine("10% on your order", "-5.15"),
            PosLoyalty.enterCode("5678"),
            PosLoyalty.hasRewardLine("Free Product - Desk Organizer", "-20.40"),
            PosLoyalty.hasRewardLine("90% on the cheapest product", "-4.59"),
            ProductScreen.clickNumpad("⌫", "⌫", "1", "8"),
            PosLoyalty.hasRewardLine("10% on your order", "-6.68"),
            PosLoyalty.hasRewardLine("Free Product - Desk Organizer", "-20.40"),
            PosLoyalty.enterCode("5678"),
            PosLoyalty.orderTotalIs("60.13"),
            PosLoyalty.finalizeOrder("Cash", "65"),

            ProductScreen.addOrderline("Desk Organizer", "6"),
            PosLoyalty.hasRewardLine("on the cheapest product", "-4.59"),
            PosLoyalty.removeRewardLine("90% on the cheapest product"),
            PosLoyalty.enterCode("promocode"),
            PosLoyalty.hasRewardLine("50% on specific products", "-15.30"),
            PosLoyalty.enterCode("1357"),
            PosLoyalty.hasRewardLine("Free Product - Desk Organizer", "-10.20"),
            PosLoyalty.hasRewardLine("50% on specific products", "-10.20"),
            PosLoyalty.orderTotalIs("10.20"),
            PosLoyalty.finalizeOrder("Cash", "20"),

            ProductScreen.addOrderline("Monitor Stand", "6"),
            PosLoyalty.enterCode("098765"),
            PosLoyalty.hasRewardLine("90% on the cheapest product", "-2.87"),
            PosLoyalty.hasRewardLine("10% on your order", "-1.63"),
            PosLoyalty.orderTotalIs("14.64"),
            PosLoyalty.removeRewardLine("90% on the cheapest product"),
            PosLoyalty.hasRewardLine("10% on your order", "-1.91"),
            PosLoyalty.orderTotalIs("17.23"),
            ProductScreen.clickControlButton("Reset Programs"),
            PosLoyalty.hasRewardLine("90% on the cheapest product", "-2.87"),
            PosLoyalty.orderTotalIs("16.27"),
            PosLoyalty.finalizeOrder("Cash", "20"),
        ].flat(),
});

registry.category("web_tour.tours").add("PosLoyaltyTour3", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),

            ProductScreen.clickDisplayedProduct("Promo Product"),
            PosLoyalty.orderTotalIs("34.50"),
            ProductScreen.clickDisplayedProduct("Product B"),
            PosLoyalty.hasRewardLine("100% on specific products", "25.00"),
            ProductScreen.clickDisplayedProduct("Product A"),
            PosLoyalty.hasRewardLine("100% on specific products", "15.00"),
            PosLoyalty.orderTotalIs("34.50"),
            ProductScreen.clickDisplayedProduct("Product A"),
            PosLoyalty.hasRewardLine("100% on specific products", "21.82"),
            PosLoyalty.hasRewardLine("100% on specific products", "18.18"),
            PosLoyalty.orderTotalIs("49.50"),
        ].flat(),
});

registry.category("web_tour.tours").add("PosLoyaltyTour4", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),

            ProductScreen.addOrderline("Test Product 1", "1"),
            ProductScreen.addOrderline("Test Product 2", "1"),
            ProductScreen.clickPriceList("Public Pricelist"),
            PosLoyalty.enterCode("abcda"),
            PosLoyalty.orderTotalIs("0.00"),
            ProductScreen.clickPriceList("Test multi-currency"),
            PosLoyalty.orderTotalIs("0.00"),
        ].flat(),
});

registry.category("web_tour.tours").add("PosCouponTour5", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            ProductScreen.clickPartnerButton(),
            ProductScreen.clickCustomer("AAAA"),
            ProductScreen.addOrderline("Test Product 1", "1", "100"),
            PosLoyalty.pointsAwardedAre("115"),
            PosLoyalty.clickDiscountButton(),
            Dialog.confirm(),
            ProductScreen.totalAmountIs("92.00"),
            PosLoyalty.pointsAwardedAre("92"),
            Chrome.endTour(),
        ].flat(),
});

registry.category("web_tour.tours").add("PosLoyaltyTour6", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),

            ProductScreen.clickPartnerButton(),
            ProductScreen.clickCustomer("AAA Partner"),
            ProductScreen.clickDisplayedProduct("Test Product A"),
            PosLoyalty.checkAddedLoyaltyPoints("26.5"),
            ProductScreen.clickControlButton("Reward"),
            SelectionPopup.has("$ 1 per point on your order", { run: "click" }),
            ProductScreen.totalAmountIs("165.00"),
            ProductScreen.clickPayButton(),
            PaymentScreen.clickPaymentMethod("Cash"),
            PaymentScreen.clickValidate(),
            ReceiptScreen.isShown(),
            PosLoyalty.isLoyaltyPointsAvailable(),
            Utils.refresh(),
            ReceiptScreen.isShown(),
            PosLoyalty.isLoyaltyPointsAvailable(),
        ].flat(),
});

registry.category("web_tour.tours").add("PosLoyaltyTour7", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),

            ProductScreen.addOrderline("Test Product", "1"),
            PosLoyalty.orderTotalIs("100"),
            PosLoyalty.enterCode("abcda"),
            PosLoyalty.orderTotalIs("90"),
        ].flat(),
});

registry.category("web_tour.tours").add("PosLoyaltyTour8", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),

            ProductScreen.clickDisplayedProduct("Product B"),
            ProductScreen.clickDisplayedProduct("Product A"),
            ProductScreen.totalAmountIs("50.00"),
        ].flat(),
});

registry.category("web_tour.tours").add("PosLoyaltySpecificDiscountCategoryTour", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),

            ProductScreen.clickDisplayedProduct("Product A", true, "1", "15.00"),
            PosLoyalty.orderTotalIs("15.00"),

            ProductScreen.clickDisplayedProduct("Product B", true, "1", "50.00"),
            PosLoyalty.orderTotalIs("40.00"),
        ].flat(),
});

registry.category("web_tour.tours").add("PosLoyaltyTour9", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),

            ProductScreen.clickPartnerButton(),
            ProductScreen.clickCustomer("AAA Partner"),
            ProductScreen.clickDisplayedProduct("Product B"),
            ProductScreen.clickDisplayedProduct("Product A"),
            ProductScreen.totalAmountIs("210.00"),
            PosLoyalty.isRewardButtonHighlighted(true),
            PosLoyalty.claimReward("$ 5"),
            ProductScreen.totalAmountIs("205.00"),
        ].flat(),
});

registry.category("web_tour.tours").add("PosLoyaltyTour10", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            ProductScreen.clickPartnerButton(),
            ProductScreen.clickCustomer("AAA Partner"),
            PosLoyalty.customerIs("AAA Partner"),
            ProductScreen.clickDisplayedProduct("Product Test"),
            ProductScreen.totalAmountIs("1.00"),
            ProductScreen.selectedOrderlineHas("Product Test", "1"),
            PosLoyalty.isRewardButtonHighlighted(true),
            PosLoyalty.claimReward("Free Product B"),
            {
                content: `click on reward item`,
                trigger: `.selection-item:contains("Free Product B")`,
                run: "click",
            },
            PosLoyalty.hasRewardLine("Free Product B", "-1.00"),
            ProductScreen.totalAmountIs("1.00"),
            PosLoyalty.isRewardButtonHighlighted(false),
        ].flat(),
});

registry.category("web_tour.tours").add("PosLoyaltyTour11.1", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            ProductScreen.clickPartnerButton(),
            ProductScreen.clickCustomer("AAA Partner"),
            PosLoyalty.customerIs("AAA Partner"),
            ProductScreen.addOrderline("Product Test", "3"),
            ProductScreen.totalAmountIs("150.00"),
            PosLoyalty.isRewardButtonHighlighted(false),
            PosLoyalty.finalizeOrder("Cash", "150"),
        ].flat(),
});

registry.category("web_tour.tours").add("PosLoyaltyTour11.2", {
    steps: () =>
        [
            Chrome.startPoS(),
            ProductScreen.clickPartnerButton(),
            ProductScreen.clickCustomer("AAA Partner"),
            PosLoyalty.customerIs("AAA Partner"),
            ProductScreen.clickDisplayedProduct("Product Test"),
            ProductScreen.totalAmountIs("50.00"),
            PosLoyalty.isRewardButtonHighlighted(false),
            PosLoyalty.enterCode("123456"),
            PosLoyalty.isRewardButtonHighlighted(true),
            PosLoyalty.claimReward("Free Product"),
            PosLoyalty.hasRewardLine("Free Product", "-3.00"),
            PosLoyalty.isRewardButtonHighlighted(false),
            ProductScreen.totalAmountIs("50.00"),
            PosLoyalty.finalizeOrder("Cash", "50"),
        ].flat(),
});

registry.category("web_tour.tours").add("PosLoyaltyMinAmountAndSpecificProductTour", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),

            ProductScreen.clickDisplayedProduct("Product A"),
            ProductScreen.selectedOrderlineHas("Product A", "1", "20.00"),
            PosLoyalty.orderTotalIs("20.00"),

            ProductScreen.clickDisplayedProduct("Product B"),
            ProductScreen.selectedOrderlineHas("Product B", "1", "30.00"),
            PosLoyalty.orderTotalIs("50.00"),

            ProductScreen.clickDisplayedProduct("Product A"),
            ProductScreen.selectedOrderlineHas("Product A", "2", "40.00"),
            PosLoyalty.orderTotalIs("66.00"),
        ].flat(),
});

registry.category("web_tour.tours").add("PosLoyaltyTour12", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            ProductScreen.addOrderline("Free Product A", "2"),
            ProductScreen.clickDisplayedProduct("Free Product A"),
            ProductScreen.totalAmountIs("2.00"),
            PosLoyalty.hasRewardLine("Free Product", "-1.00"),
            ProductScreen.addOrderline("Free Product B", "2"),
            ProductScreen.clickDisplayedProduct("Free Product B"),
            ProductScreen.totalAmountIs("12.00"),
            PosLoyalty.hasRewardLine("Free Product", "-5.00"),
            ProductScreen.clickDisplayedProduct("Free Product B"),
            ProductScreen.clickDisplayedProduct("Free Product B"),
            ProductScreen.clickDisplayedProduct("Free Product B"),
            ProductScreen.selectedOrderlineHas("Free Product B", "6"),
            ProductScreen.totalAmountIs("22.00"),
            PosLoyalty.hasRewardLine("Free Product", "-10.00"),
        ].flat(),
});

function createOrderCoupon(totalAmount, couponName, couponAmount, loyaltyPoints) {
    return [
        Chrome.startPoS(),
        Dialog.confirm("Open Register"),
        ProductScreen.clickPartnerButton(),
        ProductScreen.clickCustomer("AAAA"),
        ProductScreen.addOrderline("product_a", "1"),
        ProductScreen.addOrderline("product_b", "1"),
        PosLoyalty.enterCode("promocode"),
        PosLoyalty.hasRewardLine(`${couponName}`, `${couponAmount}`),
        PosLoyalty.orderTotalIs(`${totalAmount}`),
        PosLoyalty.pointsAwardedAre(`${loyaltyPoints}`),
        PosLoyalty.finalizeOrder("Cash", `${totalAmount}`),
    ].flat();
}

registry
    .category("web_tour.tours")
    .add("PosLoyaltyPointsDiscountNoDomainProgramNoDomain", {
        steps: () =>
            [createOrderCoupon("135.00", "10% on your order", "-15.00", "135")].flat(),
    });

registry
    .category("web_tour.tours")
    .add("PosLoyaltyPointsDiscountNoDomainProgramDomain", {
        steps: () =>
            [createOrderCoupon("135.00", "10% on your order", "-15.00", "100")].flat(),
    });

registry
    .category("web_tour.tours")
    .add("PosLoyaltyPointsDiscountWithDomainProgramDomain", {
        steps: () =>
            [createOrderCoupon("140.00", "10% on food", "-10.00", "90")].flat(),
    });

registry
    .category("web_tour.tours")
    .add("PosLoyaltyPointsGlobalDiscountProgramNoDomain", {
        steps: () =>
            [
                Chrome.startPoS(),
                Dialog.confirm("Open Register"),
                ProductScreen.addOrderline("product_a", "1"),
                ProductScreen.clickPartnerButton(),
                ProductScreen.clickCustomer("AAAA"),
                PosLoyalty.hasRewardLine("10% on your order", "-10.00"),
                PosLoyalty.orderTotalIs("90"),
                PosLoyalty.pointsAwardedAre("90"),
                PosLoyalty.finalizeOrder("Cash", "90"),
            ].flat(),
    });

registry.category("web_tour.tours").add("ChangeRewardValueWithLanguage", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),

            ProductScreen.clickDisplayedProduct("Desk Organizer"),
            ProductScreen.selectedOrderlineHas("Desk Organizer", "1", "5.10"),
            ProductScreen.clickPartnerButton(),
            ProductScreen.clickCustomer("Partner Test 1"),
            PosLoyalty.isRewardButtonHighlighted(true, true),
            PosLoyalty.claimReward("$ 2 on your order"),
            PosLoyalty.hasRewardLine("$ 2 on your order", "-2.00"),
            PosLoyalty.orderTotalIs("3.10"),
        ].flat(),
});

registry.category("web_tour.tours").add("PosLoyaltyArchivedRewardProductsInactive", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),

            ProductScreen.clickDisplayedProduct("Test Product A"),
            ProductScreen.clickPartnerButton(),
            ProductScreen.clickCustomer("AAAA"),
            PosLoyalty.isRewardButtonHighlighted(false, true),
            ProductScreen.selectedOrderlineHas("Test Product A", "1", "100.00"),
            PosLoyalty.finalizeOrder("Cash", "100"),
        ].flat(),
});

registry.category("web_tour.tours").add("PosLoyaltyArchivedRewardProductsActive", {
    steps: () =>
        [
            Chrome.startPoS(),
            ProductScreen.clickDisplayedProduct("Test Product A"),
            ProductScreen.clickPartnerButton(),
            ProductScreen.clickCustomer("AAAA"),
            PosLoyalty.isRewardButtonHighlighted(true),
            ProductScreen.selectedOrderlineHas("Test Product A", "1", "100.00"),
            PosLoyalty.finalizeOrder("Cash", "100"),
        ].flat(),
});

registry.category("web_tour.tours").add("CustomerLoyaltyPointsDisplayed", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),

            ProductScreen.clickDisplayedProduct("product_a"),
            ProductScreen.selectedOrderlineHas("product_a", "1", "100.00"),

            ProductScreen.clickPartnerButton(),
            ProductScreen.clickCustomer("John Doe"),

            PosLoyalty.orderTotalIs("100.00"),
            PosLoyalty.pointsAwardedAre("100"),
            PosLoyalty.finalizeOrder("Cash", "100.00"),

            PosLoyalty.checkPartnerPoints("John Doe", "100.00"),
        ].flat(),
});

registry.category("web_tour.tours").add("PosLoyalty2DiscountsSpecificGlobal", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),

            ProductScreen.clickPartnerButton(),
            ProductScreen.clickCustomer("AAAA"),

            ProductScreen.addOrderline("Test Product A", "5"),
            ProductScreen.clickDisplayedProduct("Test Product B"),
            PosLoyalty.hasRewardLine("10% on your order", "-3.00"),
            PosLoyalty.hasRewardLine("10% on Test Product B", "-0.45"),
            PosLoyalty.finalizeOrder("Cash", "100"),
        ].flat(),
});

registry
    .category("web_tour.tours")
    .add("PosLoyaltySpecificProductDiscountWithGlobalDiscount", {
        steps: () =>
            [
                Chrome.startPoS(),
                Dialog.confirm("Open Register"),
                ProductScreen.addOrderline("Product A", "1"),
                PosLoyalty.hasRewardLine("$ 40 on Product A", "-40.00"),
                PosLoyalty.clickDiscountButton(),
                Dialog.confirm(),
                PosLoyalty.hasRewardLine("$ 40 on Product A", "-40.00"),
                PosLoyalty.orderTotalIs("20.00"),
            ].flat(),
    });

registry.category("web_tour.tours").add("PosRewardProductScan", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),

            scan_barcode("95412427100283"),
            ProductScreen.selectedOrderlineHas("product_a", "1", "1,150.00"),
            PosLoyalty.hasRewardLine("50% on your order", "-575.00"),
            PosLoyalty.orderTotalIs("575.00"),
            PosLoyalty.finalizeOrder("Cash", "575.00"),
        ].flat(),
});

registry.category("web_tour.tours").add("PosRewardProductScanGS1", {
    steps: () =>
        [
            Chrome.startPoS(),
            scan_barcode("0195412427100283"),
            ProductScreen.selectedOrderlineHas("product_a", "1", "1,150.00"),
            PosLoyalty.hasRewardLine("50% on your order", "-575.00"),
            PosLoyalty.orderTotalIs("575.00"),
            PosLoyalty.finalizeOrder("Cash", "575.00"),
        ].flat(),
});

registry.category("web_tour.tours").add("PosLoyaltyPromocodePricelist", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            ProductScreen.addOrderline("Test Product 1", "1"),
            PosLoyalty.enterCode("hellopromo"),
            PosLoyalty.orderTotalIs("25.87"),
        ].flat(),
});

registry.category("web_tour.tours").add("RefundRulesProduct", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            ProductScreen.clickDisplayedProduct("product_a"),
            PosLoyalty.finalizeOrder("Cash", "1000"),
            ProductScreen.isShown(),
            ...ProductScreen.clickRefund(),
            TicketScreen.filterIs("Paid"),
            TicketScreen.selectOrder("001"),
            ProductScreen.clickNumpad("1"),
            TicketScreen.confirmRefund(),
            PaymentScreen.isShown(),
        ].flat(),
});

registry.category("web_tour.tours").add("test_two_variant_same_discount", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            ProductScreen.clickDisplayedProduct("Sofa"),
            Chrome.clickBtn("Add"),
        ].flat(),
});

registry.category("web_tour.tours").add("test_settle_dont_give_points_again", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            ProductScreen.clickPartnerButton(),
            PartnerList.settleCustomerAccount("AAA Partner", "10.00", "TSJ/"),
        ].flat(),
});

registry.category("web_tour.tours").add("test_refund_does_not_decrease_points", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            ProductScreen.clickPartnerButton(),
            ProductScreen.clickCustomer("Refunding Guy", true),
            ProductScreen.clickDisplayedProduct("Refund Product"),
            ProductScreen.clickControlButton("Reward"),
            SelectionPopup.has("$ 1 per point on your order", { run: "click" }),
            PosLoyalty.finalizeOrder("Cash", "200"),
            ProductScreen.clickRefund(),
            TicketScreen.selectOrder("001"),
            ProductScreen.clickNumpad("1"),
            ProductScreen.clickLine("$ 1 per point on your order"),
            ProductScreen.clickNumpad("1"),
            TicketScreen.confirmRefund(),
            PaymentScreen.totalIs("-200.00"),
            PaymentScreen.clickPaymentMethod("Cash"),
            PaymentScreen.clickValidate(),
        ].flat(),
});

registry.category("web_tour.tours").add("test_discount_after_unknown_scan", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            ProductScreen.addOrderline("Test Product A", "1"),
            scan_barcode("00998877665544332211"),
            PosLoyalty.hasRewardLine("10% on Test Product A", "-0.50"),
            ProductScreen.totalAmountIs("4.50"),
        ].flat(),
});

registry.category("web_tour.tours").add("test_scan_loyalty_card_select_customer", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            scan_barcode("0444-e050-4548"),
            ProductScreen.customerIsSelected("AAA Test Partner"),
        ].flat(),
});

registry.category("web_tour.tours").add("test_min_qty_points_awarded", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            ProductScreen.clickPartnerButton(),
            ProductScreen.clickCustomer("AA Partner"),
            ProductScreen.clickDisplayedProduct("Whiteboard Pen"),
            PosLoyalty.claimReward("Free Product"),
            PosLoyalty.pointsTotalIs("90"),
            PosLoyalty.orderTotalIs("0.0"),
            PosLoyalty.finalizeOrder("Cash", "0.0"),
        ].flat(),
});

registry.category("web_tour.tours").add("test_confirm_coupon_programs_one_by_one", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            {
                trigger: "body",
                content: "Create fake orders",
                run: async () => {
                    for (let i = 0; i < 5; i++) {
                        const order = posmodel.createNewOrder();
                        const product = posmodel.models["product.template"].find(
                            (p) => p.name === "Desk Pad",
                        );
                        const pm = posmodel.models["pos.payment.method"].getFirst();
                        const program = posmodel.models["loyalty.program"].find(
                            (p) => p.program_type === "gift_card",
                        );

                        await posmodel.addLineToOrder(
                            { product_tmpl_id: product },
                            order,
                        );
                        posmodel.addPendingOrder([order.id]);
                        order.addPaymentline(pm);
                        order.state = "paid";

                        order.uiState.couponPointChanges = [
                            {
                                points: 124.2,
                                program_id: program.id,
                                coupon_id: -(i + 1),
                                barcode: "",
                            },
                        ];
                    }
                },
            },
            ProductScreen.clickDisplayedProduct("Desk Pad"),
            ProductScreen.clickPayButton(),
            PaymentScreen.clickPaymentMethod("Bank"),
            PaymentScreen.clickValidate(),
            ReceiptScreen.isShown(),
        ].flat(),
});

registry
    .category("web_tour.tours")
    .add("test_order_reward_product_tax_included_included", {
        steps: () =>
            [
                Chrome.startPoS(),
                Dialog.confirm("Open Register"),
                ProductScreen.addOrderline("Product Include", "1"),
                PosLoyalty.enterCode("hellopromo"),
                PosLoyalty.hasRewardLine("$ 10 on your order", "-10.00"),
            ].flat(),
    });

registry
    .category("web_tour.tours")
    .add("test_order_reward_product_tax_included_excluded", {
        steps: () =>
            [
                Chrome.startPoS(),
                ProductScreen.addOrderline("Product Include", "1"),
                PosLoyalty.enterCode("hellopromo"),
                PosLoyalty.hasRewardLine("$ 10 on your order", "-10.00"),
            ].flat(),
    });

registry
    .category("web_tour.tours")
    .add("test_specific_reward_product_tax_included_included", {
        steps: () =>
            [
                Chrome.startPoS(),
                Dialog.confirm("Open Register"),
                ProductScreen.addOrderline("Product Include", "1"),
                PosLoyalty.enterCode("hellopromo"),
                PosLoyalty.hasRewardLine("$ 10 on Product Include", "-10.00"),
            ].flat(),
    });

registry
    .category("web_tour.tours")
    .add("test_specific_reward_product_tax_included_excluded", {
        steps: () =>
            [
                Chrome.startPoS(),
                ProductScreen.addOrderline("Product Include", "1"),
                PosLoyalty.enterCode("hellopromo"),
                PosLoyalty.hasRewardLine("$ 10 on Product Include", "-10.00"),
            ].flat(),
    });

registry
    .category("web_tour.tours")
    .add("test_loyalty_is_not_processed_for_draft_order", {
        steps: () =>
            [
                Chrome.startPoS(),
                Dialog.confirm("Open Register"),
                ProductScreen.clickPartnerButton(),
                ProductScreen.clickCustomer("AAAA"),
                ProductScreen.addOrderline("Whiteboard Pen", "1", "100"),
                PosLoyalty.pointsAwardedAre("100"),
                PosLoyalty.pointsTotalIs("150"),
                ProductScreen.saveOrder(),
                ProductScreen.selectFloatingOrder(0),
                PosLoyalty.pointsAwardedAre("100"),
                PosLoyalty.pointsTotalIs("150"),
            ].flat(),
    });

registry.category("web_tour.tours").add("test_race_conditions_update_program", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            ProductScreen.clickDisplayedProduct("Test Product"),
            PosLoyalty.orderTotalIs("34.87"),
            {
                trigger: "body",
                run: async () => {
                    const line_count = document.querySelectorAll(".orderline").length;
                    if (line_count !== 11) {
                        throw new Error(`Expected 11 orderlines, found ${line_count}`);
                    }
                },
            },
        ].flat(),
});

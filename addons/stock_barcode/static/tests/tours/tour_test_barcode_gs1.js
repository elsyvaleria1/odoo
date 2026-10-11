import { registry } from "@web/core/registry";

import * as helper from "./tour_helper_stock_barcode.js";
import { stepUtils } from "./tour_step_utils.js";

registry.category("web_tour.tours").add("test_gs1_inventory_gtin_8", {
    steps: () => [
        {
            trigger: ".o_button_inventory",
            run: "click",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 0100000082655853",
        },
        {
            trigger: '.o_barcode_client_action:contains("PRO_GTIN_8")',
            run: function () {
                helper.assertLinesCount(1);
                const line = helper.getLine({ barcode: "82655853" });
                helper.assertLineIsHighlighted(line, true);
                helper.assertLineQty(line, "1");
            },
        },
        {
            trigger: '.o_barcode_client_action:contains("PRO_GTIN_8")',
            run: "scan 3777",
        },
        {
            trigger: '.o_barcode_line:contains("78")',
            run: function () {
                helper.assertLinesCount(1);
                const line = helper.getLine({ barcode: "82655853" });
                helper.assertLineIsHighlighted(line, true);
                helper.assertLineQty(line, "78");
            },
        },
        ...stepUtils.validateBarcodeOperation(
            '.o_barcode_line .qty-done:contains("78")',
        ),
    ],
});

registry.category("web_tour.tours").add("test_gs1_inventory_product_units", {
    steps: () => [
        {
            trigger: ".o_button_inventory",
            run: "click",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 010000008265585337102",
        },
        {
            trigger: '.o_barcode_client_action:contains("PRO_GTIN_8")',
            run: "click",
        },
        {
            trigger: '.o_barcode_line:contains("102")',
            run: function () {
                helper.assertLinesCount(1);
                const line = helper.getLine({ barcode: "82655853" });
                helper.assertLineIsHighlighted(line, true);
                helper.assertLineQty(line, "102");
            },
        },
        ...stepUtils.validateBarcodeOperation(),
    ],
});

registry.category("web_tour.tours").add("test_gs1_inventory_lot_serial", {
    steps: () => [
        {
            trigger: ".o_button_inventory",
            run: "click",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 010011115555571710LOT-AAA~305",
        },
        {
            trigger: '.o_barcode_line:contains("AAA")',
            run: function () {
                helper.assertLinesCount(1);
                const line = helper.getLine({ selected: true });
                helper.assertLineProduct(line, "PRO_GTIN_12_lot");
                helper.assertLineTrackingNumber(line, "LOT-AAA");
                helper.assertLineQty(line, "5");
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 010011115555571710LOT-AAB",
        },
        {
            trigger: '.o_sublines .o_barcode_line:contains("AAB")',
            run: "click",
        },
        {
            trigger: '.o_sublines .o_barcode_line.o_selected:contains("AAB")',
            run: function () {
                helper.assertLinesCount(1);
                helper.assertSublinesCount(2);
                const parentLine = helper.getLine({ selected: true });
                const subline = helper.getSubline({ selected: true });
                helper.assertLineProduct(parentLine, "PRO_GTIN_12_lot");
                helper.assertLineQty(parentLine, "6");
                helper.assertLineTrackingNumber(subline, "LOT-AAB");
                helper.assertLineQty(subline, "1");
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 30009",
        },
        {
            trigger: '.o_barcode_line.o_selected .qty-done:contains("10")',
            run: function () {
                helper.assertLinesCount(1);
                helper.assertSublinesCount(2);
                const parentLine = helper.getLine({ selected: true });
                const subline = helper.getSubline({ selected: true });
                helper.assertLineProduct(parentLine, "PRO_GTIN_12_lot");
                helper.assertLineQty(parentLine, "15");
                helper.assertLineTrackingNumber(subline, "LOT-AAB");
                helper.assertLineQty(subline, "10");
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 305",
        },
        {
            trigger: '.o_sublines .o_barcode_line.o_selected .qty-done:contains("15")',
            run: function () {
                helper.assertLinesCount(1);
                helper.assertSublinesCount(2);
                const parentLine = helper.getLine({ selected: true });
                const subline = helper.getSubline({ selected: true });
                helper.assertLineProduct(parentLine, "PRO_GTIN_12_lot");
                helper.assertLineQty(parentLine, "20");
                helper.assertLineTrackingNumber(subline, "LOT-AAB");
                helper.assertLineQty(subline, "15");
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 3020##10LOT-AAC",
        },
        {
            trigger: '.o_barcode_line.o_selected:contains("AAC")',
            run: function () {
                helper.assertLinesCount(1);
                helper.assertSublinesCount(3);
                const parentLine = helper.getLine({ selected: true });
                const subline = helper.getSubline({ selected: true });
                helper.assertLineProduct(parentLine, "PRO_GTIN_12_lot");
                helper.assertLineQty(parentLine, "40");
                helper.assertLineTrackingNumber(subline, "LOT-AAC");
                helper.assertLineQty(subline, "20");
            },
        },
        ...stepUtils.inputManuallyBarcode("305Alt02910LOT-AAA"),
        {
            trigger: '.o_barcode_line.o_selected .qty-done:contains("10")',
            run: function () {
                helper.assertLinesCount(1);
                helper.assertSublinesCount(3);
                const parentLine = helper.getLine({ selected: true });
                const subline = helper.getSubline({ selected: true });
                helper.assertLineProduct(parentLine, "PRO_GTIN_12_lot");
                helper.assertLineQty(parentLine, "45");
                helper.assertLineTrackingNumber(subline, "LOT-AAA");
                helper.assertLineQty(subline, "10");
            },
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan 011522222222221921Serial1",
        },
        {
            trigger: '.o_barcode_line:contains("Serial1")',
            run: function () {
                helper.assertLinesCount(2);
                helper.assertSublinesCount(0);
                const line = helper.getLine({ selected: true });
                helper.assertLineProduct(line, "PRO_GTIN_14_serial");
                helper.assertLineTrackingNumber(line, "Serial1");
                helper.assertLineQty(line, "1");
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 011522222222221921Serial2",
        },
        {
            trigger: '.o_sublines .o_barcode_line:contains("Serial2")',
            run: "click",
        },
        {
            trigger: '.o_barcode_line:contains("Serial2")',
            run: function () {
                helper.assertLinesCount(2);
                helper.assertSublinesCount(2);
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 011522222222221921Serial3\x1D3020",
        },
        {
            trigger: ".o_notification_bar.bg-danger",
            run: "click",
        },
        {
            trigger: '.o_barcode_line:contains("Serial3")',
            run: function () {
                helper.assertLinesCount(2);
                helper.assertSublinesCount(3);
                const parentLine = document.querySelector(".o_barcode_line.o_selected");
                const subline = document.querySelector(
                    ".o_sublines .o_barcode_line.o_selected",
                );
                helper.assertLineQty(parentLine, "3");
                helper.assertLineTrackingNumber(subline, "Serial3");
                helper.assertLineQty(subline, "1");
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 01152222222222193020",
        },
        {
            trigger: ".o_sublines .o_barcode_line:nth-child(4)",
            run: function () {
                helper.assertLinesCount(2);
                helper.assertSublinesCount(4);
                const parentLine = helper.getLine({ selected: true });
                const subline = helper.getSubline({ selected: true });
                helper.assertLineQty(parentLine, "23");
                helper.assertLineTrackingNumber(subline, false);
                helper.assertLineQty(subline, "20");
                const barcodeIconVisible = Boolean(
                    subline.querySelector(".o_line_tracking_number"),
                );
                helper.assert(
                    barcodeIconVisible,
                    false,
                    "The SN HTML element should not be visible",
                );
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 011522222222221921Serial4",
        },
        {
            trigger: ".o_sublines .o_barcode_line:nth-child(5)",
            run: function () {
                helper.assertLinesCount(2);
                helper.assertSublinesCount(5);
                const parentLine = helper.getLine({ selected: true });
                const subline = helper.getSubline({ selected: true });
                helper.assertLineQty(parentLine, "24");
                helper.assertLineTrackingNumber(subline, "Serial4");
                helper.assertLineQty(subline, "1");
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan OBTVALI",
        },
        {
            trigger: ".o_notification_bar.bg-success",
        },
    ],
});

registry.category("web_tour.tours").add("test_gs1_inventory_package", {
    steps: () => [
        {
            trigger: ".o_button_inventory",
            run: "click",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 00987654123487568456",
        },
        {
            trigger: ".o_notification_bar.bg-danger",
            run: "click",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan LOC-01-01-00",
        },
        {
            trigger: '.o_scan_product_or_src:contains("WH/Stock/Section 1")',
            run: "scan 00987654123487568456",
        },
        {
            trigger: ".o_barcode_line",
            run: function () {
                helper.assertLinesCount(1);
                const line = helper.getLine({ barcode: "product1" });
                const product1_package =
                    line.querySelector('div[name="package"]').innerText;
                helper.assert(product1_package, "987654123487568456");
                helper.assertLineIsHighlighted(line, true);
                helper.assertLineQty(line, "8/8");
            },
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan LOC-01-02-00",
        },
        {
            trigger: '.o_scan_product_or_src:contains("WH/Stock/Section 2")',
            run: "scan 00487325612456785124",
        },
        {
            trigger: '.o_barcode_line[data-barcode="product2"]',
            run: function () {
                helper.assertLinesCount(2);
                const line = helper.getLine({ barcode: "product2" });
                const product2_package =
                    line.querySelector('div[name="package"]').innerText;
                helper.assert(product2_package, "487325612456785124");
                helper.assertLineIsHighlighted(line, true);
                helper.assertLineQty(line, "6/6");
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 00487325612456785124",
        },
        {
            trigger: ".o_notification_bar.bg-danger",
            run: "click",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan 0100000082655853304",
        },
        {
            trigger: ".o_barcode_line:nth-child(2)",
            run: "scan 00122333444455555670",
        },
        {
            trigger: ".o_barcode_line:contains(122333444455555670)",
            run: function () {
                helper.assertLinesCount(3);
                const line1 = helper.getLine({ barcode: "product2" });
                const line1_package =
                    line1.querySelector('div[name="package"]').innerText;
                helper.assertLineIsHighlighted(line1, false);
                helper.assert(line1_package, "487325612456785124");
                helper.assertLineQty(line1, "6/6");
                const line2 = helper.getLine({ barcode: "82655853" });
                const line2_package =
                    line2.querySelector('div[name="package"]').innerText;
                helper.assertLineIsHighlighted(line2, true);
                helper.assert(line2_package, "122333444455555670");
                helper.assertLineQty(line2, "4");
            },
        },

        {
            trigger: ".o_apply_page",
            run: "scan OBTVALI",
        },
        {
            trigger: ".o_notification_bar.bg-success",
        },
    ],
});

registry.category("web_tour.tours").add("test_gs1_package_receipt", {
    steps: () => [
        { trigger: ".o_stock_barcode_main_menu", run: "scan WHIN" },
        { trigger: ".o_barcode_client_action", run: "scan 0100000082655853300004" },
        {
            trigger: ".o_barcode_line",
            run: function () {
                helper.assertLinesCount(1);
                const line1 = helper.getLine({ barcode: "82655853" });
                helper.assertLineIsHighlighted(line1, true);
                helper.assertLineQty(line1, "4");
            },
        },
        { trigger: ".o_barcode_client_action", run: "scan 00546879213579461324" },
        {
            trigger: ".o_barcode_line .result-package:text('546879213579461324')",
            run: function () {
                helper.assertLinesCount(1);
                const line1 = helper.getLine({ barcode: "82655853" });
                helper.assertLineIsHighlighted(line1, true);
                helper.assertLineQty(line1, "4");
                helper.assertLineResultPackage(line1, "546879213579461324");
            },
        },
        { trigger: ".o_barcode_client_action", run: "scan 300008\x1D0100584687955629" },
        {
            trigger: ".o_barcode_line:nth-child(2)",
            run: function () {
                helper.assertLinesCount(2);
                const line1 = helper.getLine({ barcode: "82655853" });
                helper.assertLineIsHighlighted(line1, false);
                helper.assertLineQty(line1, "4");
                helper.assertLineResultPackage(line1, "546879213579461324");
                const line2 = helper.getLine({ barcode: "584687955629" });
                helper.assertLineIsHighlighted(line2, true);
                helper.assertLineQty(line2, "8");
            },
        },
        { trigger: ".o_barcode_client_action", run: "scan 00546879213579461324" },
        {
            trigger:
                ".o_barcode_line[data-barcode='584687955629'] :text('546879213579461324')",
            run: function () {
                helper.assertLinesCount(2);
                const line1 = helper.getLine({ barcode: "82655853" });
                helper.assertLineIsHighlighted(line1, false);
                helper.assertLineQty(line1, "4");
                helper.assertLineResultPackage(line1, "546879213579461324");
                const line2 = helper.getLine({ barcode: "584687955629" });
                helper.assertLineIsHighlighted(line2, true);
                helper.assertLineQty(line2, "8");
                helper.assertLineResultPackage(line2, "546879213579461324");
            },
        },
        {
            trigger: '.o_barcode_line[data-barcode="584687955629"]',
            run: "click",
        },
        { trigger: '.o_selected[data-barcode="584687955629"]', run: "scan 91WOODC" },
        ...stepUtils.checkNotificationMessage(
            "Package type Wooden Chest applied to the package 546879213579461324",
        ),
        {
            trigger: ".o_barcode_line",
            run: function () {
                helper.assertLinesCount(2);
                const line1 = helper.getLine({ barcode: "82655853" });
                helper.assertLineIsHighlighted(line1, false);
                helper.assertLineQty(line1, "4");
                helper.assertLineResultPackage(line1, "546879213579461324");
                const line2 = helper.getLine({ barcode: "584687955629" });
                helper.assertLineIsHighlighted(line2, true);
                helper.assertLineQty(line2, "8");
                helper.assertLineResultPackage(line2, "546879213579461324");
            },
        },

        { trigger: ".o_barcode_client_action", run: "scan 0100000082655853300006" },
        {
            trigger: ".o_barcode_line.o_selected .o_product_label:text('PRO_GTIN_8')",
            run: function () {
                helper.assertLinesCount(3);
                const line = helper.getLine({ selected: true });
                helper.assertLineQty(line, "6");
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 00130406658041178543\x1D91IRONC",
        },
        {
            trigger:
                ".o_barcode_line.o_selected .result-package:text('130406658041178543')",
            run: function () {
                helper.assertLinesCount(3);
                const line = helper.getLine({ selected: true });
                helper.assertLineQty(line, "6");
                helper.assertLineResultPackage(line, "130406658041178543");
            },
        },
        { trigger: ".o_barcode_client_action", run: "scan 30000000120100584687955629" },
        {
            trigger: '.o_barcode_line.o_selected[data-barcode="584687955629"]',
            run: function () {
                helper.assertLinesCount(4);
                const line = helper.getLine({ selected: true });
                helper.assertLineQty(line, "12");
            },
        },
        { trigger: ".o_barcode_client_action", run: "scan 91IRONC" },
        {
            trigger:
                '.o_barcode_line.o_selected[data-barcode="584687955629"] [name="package"]',
            run: function () {
                helper.assertLinesCount(4);
                const line = helper.getLine({ selected: true });
                helper.assertLineQty(line, "12");
                helper.assertLineResultPackage(line, "PACK0000123");
            },
        },
        ...stepUtils.validateBarcodeOperation(),
    ],
});

registry.category("web_tour.tours").add("test_gs1_package_delivery", {
    steps: () => [
        {
            trigger: ".o_stock_barcode_main_menu",
            run: "scan WHOUT",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 00546879213579461324",
        },
        {
            trigger: ".o_barcode_line:nth-child(2)",
            run: function () {
                helper.assertLinesCount(2);
                const line1 = helper.getLine({ barcode: "82655853" });
                helper.assertLineIsHighlighted(line1, true);
                helper.assertLineQty(line1, "4");
                helper.assert(
                    line1.querySelector(".package").innerText,
                    "546879213579461324",
                );
                helper.assert(
                    line1.querySelector(".result-package").innerText,
                    "546879213579461324",
                );
                const line2 = helper.getLine({ barcode: "584687955629" });
                helper.assertLineIsHighlighted(line2, true);
                helper.assertLineQty(line2, "8");
                helper.assert(
                    line2.querySelector(".package").innerText,
                    "546879213579461324",
                );
                helper.assert(
                    line2.querySelector(".result-package").innerText,
                    "546879213579461324",
                );
            },
        },
        ...stepUtils.validateBarcodeOperation(),
    ],
});

registry.category("web_tour.tours").add("test_gs1_reserved_delivery", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: function () {
                helper.assertLinesCount(1);
                const line = helper.getLine({ barcode: "11011019" });
                helper.assertLineIsHighlighted(line, false);
                helper.assertLineQty(line, "0/10");
                helper.assertValidateIsHighlighted(false);
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 0100000011011019306",
        },
        {
            trigger: ".o_barcode_line .qty-done:contains(6)",
            run: function () {
                helper.assertLinesCount(1);
                const line = helper.getLine({ barcode: "11011019" });
                helper.assertLineIsHighlighted(line, true);
                helper.assertLineQty(line, "6/10");
                helper.assertValidateIsHighlighted(false);
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 0100000011011019308",
        },
        {
            trigger: ".o_barcode_line  .qty-done:contains(10)",
            run: function () {
                helper.assertLinesCount(2);
                const [line1, line2] = helper.getLines();
                helper.assertLineIsHighlighted(line1, false);
                helper.assertLineIsHighlighted(line2, true);
                helper.assertLineQty(line1, "10/10");
                helper.assertLineQty(line2, "4");
                helper.assertValidateIsHighlighted(true);
            },
        },
        ...stepUtils.validateBarcodeOperation(".o_validate_page.btn-primary"),
    ],
});

registry.category("web_tour.tours").add("test_gs1_receipt_conflicting_barcodes_1", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: function () {
                helper.assertLinesCount(1);
                const line = helper.getLine({ barcode: "11011019" });
                helper.assertLineIsHighlighted(line, false);
                helper.assertLineQty(line, "0/1");
                helper.assertValidateIsHighlighted(false);
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 0100000011011019",
        },
        {
            trigger: ".o_barcode_line.o_selected",
            run: function () {
                helper.assertLinesCount(1);
                const line = helper.getLine({ barcode: "11011019" });
                helper.assertLineIsHighlighted(line, true);
                helper.assertLineQty(line, "1/1");
                helper.assertValidateIsHighlighted(true);
            },
        },
        ...stepUtils.validateBarcodeOperation(".o_validate_page.btn-primary"),
    ],
});

registry.category("web_tour.tours").add("test_gs1_delivery_ambiguous_lot_number", {
    steps: () => [
        { trigger: ".o_stock_barcode_main_menu", run: "scan WHOUT" },
        {
            trigger: ".o_scan_message.o_scan_product",
            run: "scan 0100000022222220152407101012345",
        },
        {
            trigger: ".o_barcode_line .qty-done:contains(1)",
            run: function () {
                helper.assertLinesCount(1);
                const line = helper.getLine({ barcode: "22222220" });
                helper.assertLineIsHighlighted(line, true);
                helper.assertLineQty(line, "1 Units");
                helper.assertLineTrackingNumber(line, "12345");
            },
        },

        { trigger: ".o_barcode_client_action", run: "scan OCDCANC" },
        { trigger: ".o_stock_barcode_main_menu", run: "scan WHIN" },
        {
            trigger: ".o_scan_message.o_scan_product",
            run: "scan 0110000000240489152407101012345",
        },
        {
            trigger: ".o_barcode_line .qty-done:contains(1)",
            run: function () {
                helper.assertLinesCount(1);
                const line = helper.getLine({ barcode: "22222220" });
                helper.assertLineIsHighlighted(line, true);
                helper.assertLineQty(line, "1 Packaging - Product A x1");
                helper.assertLineTrackingNumber(line, "12345");
            },
        },
        ...stepUtils.validateBarcodeOperation(".o_validate_page.btn-primary"),
    ],
});

registry.category("web_tour.tours").add("test_gs1_delivery_ambiguous_serial_number", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: "scan LOC-01-00-00",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 01057115440019521524071021304",
        },
        {
            trigger: ".o_barcode_line .qty-done:contains(1)",
            run: function () {
                helper.assertLinesCount(1);
                const $line = helper.getLine({ barcode: "05711544001952" });
                helper.assertLineIsHighlighted($line, true);
                helper.assertLineQty($line, "1/1");
            },
        },
        ...stepUtils.validateBarcodeOperation(".o_validate_page.btn-primary"),
    ],
});

registry.category("web_tour.tours").add("test_gs1_receipt_conflicting_barcodes_2", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: function () {
                helper.assertLinesCount(1);
                const line = helper.getLine({ barcode: "000011011019" });
                helper.assertLineIsHighlighted(line, false);
                helper.assertLineQty(line, "0/1");
                helper.assertValidateIsHighlighted(false);
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 0100000011011019",
        },
        {
            trigger: ".o_barcode_line.o_selected",
            run: function () {
                helper.assertLinesCount(1);
                const line = helper.getLine({ barcode: "000011011019" });
                helper.assertLineIsHighlighted(line, true);
                helper.assertLineQty(line, "1/1");
                helper.assertValidateIsHighlighted(true);
            },
        },
        ...stepUtils.validateBarcodeOperation(".o_validate_page.btn-primary"),
    ],
});

registry.category("web_tour.tours").add("test_gs1_receipt_conflicting_barcodes_3", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: function () {
                helper.assertLinesCount(2);
                const line1 = helper.getLine({ barcode: "11011019" });
                helper.assertLineIsHighlighted(line1, false);
                helper.assertLineQty(line1, "0/1");
                helper.assertLineProduct(line1, "PRO_GTIN_8");
                const line2 = helper.getLine({ barcode: "000011011019" });
                helper.assertLineIsHighlighted(line2, false);
                helper.assertLineQty(line2, "0/1");
                helper.assertLineProduct(line2, "PRO_GTIN_12");
                helper.assertValidateIsHighlighted(false);
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 0100000011011019",
        },
        {
            trigger: ".o_barcode_line.o_selected",
            run: function () {
                helper.assertLinesCount(2);
                const line1 = helper.getLine({ barcode: "11011019" });
                helper.assertLineIsHighlighted(line1, true);
                helper.assertLineQty(line1, "1/1");
                helper.assertLineProduct(line1, "PRO_GTIN_8");
                const line2 = helper.getLine({ barcode: "000011011019" });
                helper.assertLineIsHighlighted(line2, false);
                helper.assertLineQty(line2, "0/1");
                helper.assertLineProduct(line2, "PRO_GTIN_12");
                helper.assertValidateIsHighlighted(false);
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 0100000011011019",
        },
        {
            trigger: ".o_barcode_line:nth-child(3)",
            run: function () {
                helper.assertLinesCount(3);
                const [lineGTIN12, lineGTIN8_1, lineGTIN8_2] = helper.getLines();
                helper.assertLineIsHighlighted(lineGTIN12, false);
                helper.assertLineQty(lineGTIN12, "0/1");
                helper.assertLineProduct(lineGTIN12, "PRO_GTIN_12");
                helper.assertLineIsHighlighted(lineGTIN8_1, false);
                helper.assertLineQty(lineGTIN8_1, "1/1");
                helper.assertLineProduct(lineGTIN8_1, "PRO_GTIN_8");
                helper.assertLineIsHighlighted(lineGTIN8_2, true);
                helper.assertLineQty(lineGTIN8_2, "1");
                helper.assertLineProduct(lineGTIN8_2, "PRO_GTIN_8");
                helper.assertValidateIsHighlighted(false);
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 000011011019",
        },
        {
            trigger: ".o_validate_page.btn-primary",
            run: function () {
                helper.assertLinesCount(3);
                const [line1, line2] = helper.getLines({ barcode: "11011019" });
                helper.assertLineIsHighlighted(line1, false);
                helper.assertLineQty(line1, "1/1");
                helper.assertLineProduct(line1, "PRO_GTIN_8");
                helper.assertLineIsHighlighted(line2, false);
                helper.assertLineQty(line2, "1");
                helper.assertLineProduct(line2, "PRO_GTIN_8");
                const line3 = helper.getLine({ barcode: "000011011019" });
                helper.assertLineIsHighlighted(line3, true);
                helper.assertLineQty(line3, "1/1");
                helper.assertLineProduct(line3, "PRO_GTIN_12");
                helper.assertValidateIsHighlighted(true);
            },
        },
        ...stepUtils.validateBarcodeOperation(".o_validate_page.btn-primary"),
    ],
});

registry
    .category("web_tour.tours")
    .add("test_gs1_receipt_conflicting_barcodes_mistaken_as_gs1", {
        steps: () => [
            { trigger: ".o_stock_barcode_main_menu", run: "scan WHIN" },
            { trigger: ".o_barcode_client_action", run: "scan 3000000015" },
            {
                trigger: ".o_barcode_line",
                run: function () {
                    const line = helper.getLine({ barcode: "3000000015" });
                    helper.assertLineQty(line, "1");
                },
            },
            { trigger: ".o_barcode_client_action", run: "scan 21000000000003" },
            {
                trigger: ".o_barcode_line[data-barcode='21000000000003']",
                run: function () {
                    const line = helper.getLine({ barcode: "21000000000003" });
                    helper.assertLineQty(line, "1");
                },
            },
            { trigger: ".o_barcode_client_action", run: "scan 3000000015" },
            {
                trigger: ".o_barcode_line.o_selected .qty-done:contains('16')",
                run: function () {
                    const line = helper.getLine({ barcode: "21000000000003" });
                    helper.assertLineQty(line, "16");
                },
            },
            { trigger: ".o_barcode_client_action", run: "scan 21-Chouette-MegaPack" },
            {
                trigger:
                    ".o_barcode_line[data-barcode='21000000000003'] div[name='package']",
                run: function () {
                    const line = helper.getLine({ barcode: "21000000000003" });
                    helper.assertLineQty(line, "16");
                    helper.assert(
                        line.querySelector(".result-package").innerText,
                        "21-Chouette-MegaPack",
                    );
                },
            },
            { trigger: ".o_barcode_client_action", run: "scan productserial1" },
            {
                trigger: ".o_barcode_line[data-barcode='productserial1']",
                run: "scan 21-Chouette-MegaPack",
            },
            {
                trigger:
                    ".o_barcode_line.o_selected .o_line_lot_name:contains('-Chouette-MegaPack')",
            },
            { trigger: ".o_barcode_client_action", run: "scan 21000000000003" },
            {
                trigger: ".o_barcode_line.o_selected .o_line_button.o_toggle_sublines",
                run: "click",
            },
            {
                trigger: ".o_sublines .o_barcode_line.o_selected",
                run: function () {
                    helper.assert(
                        document.querySelector(".o_barcode_line_summary .qty-done")
                            .innerText,
                        "2",
                    );
                    helper.assert(
                        document.querySelector(
                            ".o_sublines .o_selected .o_line_lot_name",
                        ).innerText,
                        "000000000003",
                    );
                },
            },
        ],
    });

registry.category("web_tour.tours").add("test_gs1_receipt_lot_serial", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: function () {
                helper.assertLinesCount(1);
                helper.assertLineIsHighlighted(0, false);
                helper.assertLineQty(0, "0/40");
            },
        },
        ...stepUtils.inputManuallyBarcode("((01)00000076543210(30)00000008)"),

        {
            trigger: ".o_barcode_line.o_selected",
            run: function () {
                helper.assertLinesCount(1);
                helper.assertLineIsHighlighted(0, true);
                helper.assertLineQty(0, "8/40");
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 10b1-b001",
        },
        {
            trigger: '.o_barcode_line:contains("b1-b001")',
            run: function () {
                helper.assertLinesCount(1);
                helper.assertLineTrackingNumber(0, "b1-b001");
                helper.assertLineQty(0, "8/40");
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 010000007654321010b1-b002\x1D3000000004",
        },
        {
            trigger: ".o_barcode_line.o_selected .btn.o_toggle_sublines .fa-angle-down",
            run: "click",
        },
        {
            trigger: '.o_barcode_line:contains("b1-b002")',
            run: function () {
                helper.assertLinesCount(1);
                helper.assertSublinesCount(2);
                const parentLine = helper.getLine({ barcode: "76543210" });
                const [line1, line2] = helper.getSublines();
                helper.assertLinesTrackingNumbers(
                    [line1, line2],
                    ["b1-b001", "b1-b002"],
                );
                helper.assertLineQty(parentLine, "12/40");
                helper.assertLineQty(line1, "8");
                helper.assertLineQty(line2, "4");
                helper.assertLineIsHighlighted(line1, false);
                helper.assertLineIsHighlighted(line2, true);
            },
        },
        {
            trigger: ".o_sublines .o_barcode_line:nth-child(2).o_selected",
            run: "scan 010000007654321010b1-b002\x1D3000000004",
        },
        {
            trigger: '.o_sublines .o_barcode_line.o_selected .qty-done:contains("8")',
            run: function () {
                helper.assertSublinesCount(2);
                const [line1, line2] = helper.getSublines();
                helper.assertLinesTrackingNumbers(
                    [line1, line2],
                    ["b1-b001", "b1-b002"],
                );
                helper.assertLineQty(line1, "8");
                helper.assertLineQty(line2, "8");
                helper.assertLineIsHighlighted(line1, false);
                helper.assertLineIsHighlighted(line2, true);
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan b1-b003",
        },
        {
            trigger: '.o_barcode_line:contains("b1-b003")',
            run: function () {
                helper.assertSublinesCount(3);
                const sublines = helper.getSublines();
                helper.assertLinesTrackingNumbers(sublines, [
                    "b1-b001",
                    "b1-b002",
                    "b1-b003",
                ]);
                helper.assertLineQty(sublines[0], "8");
                helper.assertLineQty(sublines[1], "8");
                helper.assertLineQty(sublines[2], "1");
                helper.assertLineIsHighlighted(sublines[0], false);
                helper.assertLineIsHighlighted(sublines[1], false);
                helper.assertLineIsHighlighted(sublines[2], true);
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan b1-b003",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan b1-b003",
        },
        {
            trigger: '.o_barcode_line.o_selected .qty-done:contains("3")',
            run: function () {
                helper.assertLinesCount(1);
                helper.assertSublinesCount(3);
                const sublines = helper.getSublines();
                helper.assertLinesTrackingNumbers(sublines, [
                    "b1-b001",
                    "b1-b002",
                    "b1-b003",
                ]);
                helper.assertLineQty(sublines[0], "8");
                helper.assertLineQty(sublines[1], "8");
                helper.assertLineQty(sublines[2], "3");
                helper.assertLineIsHighlighted(sublines[0], false);
                helper.assertLineIsHighlighted(sublines[1], false);
                helper.assertLineIsHighlighted(sublines[2], true);
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 3000000005",
        },
        {
            trigger: '.o_sublines .o_barcode_line.o_selected:contains("8")',
            run: function () {
                helper.assertSublinesCount(3);
                const sublines = helper.getSublines();
                helper.assertLinesTrackingNumbers(sublines, [
                    "b1-b001",
                    "b1-b002",
                    "b1-b003",
                ]);
                helper.assertLineQty(sublines[0], "8");
                helper.assertLineQty(sublines[1], "8");
                helper.assertLineQty(sublines[2], "8");
                helper.assertLineIsHighlighted(sublines[0], false);
                helper.assertLineIsHighlighted(sublines[1], false);
                helper.assertLineIsHighlighted(sublines[2], true);
            },
        },
        {
            trigger: ".o_add_line",
            run: "click",
        },
        {
            trigger: ".o_field_widget[name=product_id] input",
            run: "edit B1",
        },
        {
            trigger: ".ui-menu-item > a:contains('Battle Droid')",
            run: "click",
        },
        {
            trigger: "[name=qty_done] input",
            run: "edit 0",
        },
        {
            trigger: ".o_save",
            run: "click",
        },
        {
            trigger: ".o_barcode_line:nth-child(4)",
            run: function () {
                helper.assertLinesCount(1);
                helper.assertSublinesCount(4);
                const sublines = helper.getSublines({ selected: false });
                helper.assertLinesTrackingNumbers(sublines, [
                    "b1-b001",
                    "b1-b002",
                    "b1-b003",
                ]);
                const line4 = helper.getSubline({ selected: true });
                helper.assertLineQty(sublines[0], "8");
                helper.assertLineQty(sublines[1], "8");
                helper.assertLineQty(sublines[2], "8");
                helper.assertLineQty(line4, "0");
                helper.assertLineIsHighlighted(sublines[0], false);
                helper.assertLineIsHighlighted(sublines[1], false);
                helper.assertLineIsHighlighted(sublines[2], false);
                helper.assertLineIsHighlighted(line4, true);
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 3000000004\x1D10b1-b004\x1D0100000076543210",
        },
        {
            trigger:
                '.o_sublines .o_barcode_line:contains("b1-b004") .qty-done:contains("4")',
            run: function () {
                helper.assertSublinesCount(4);
                const sublines = helper.getSublines();
                helper.assertLinesTrackingNumbers(sublines, [
                    "b1-b001",
                    "b1-b002",
                    "b1-b003",
                    "b1-b004",
                ]);
                helper.assertLineQty(sublines[0], "8");
                helper.assertLineQty(sublines[1], "8");
                helper.assertLineQty(sublines[2], "8");
                helper.assertLineQty(sublines[3], "4");
                helper.assertLineIsHighlighted(sublines[0], false);
                helper.assertLineIsHighlighted(sublines[1], false);
                helper.assertLineIsHighlighted(sublines[2], false);
                helper.assertLineIsHighlighted(sublines[3], true);
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 10b1-b005",
        },
        {
            trigger:
                '.o_sublines .o_barcode_line:contains("b1-b005") .qty-done:contains("1")',
            run: function () {
                helper.assertLinesCount(1);
                helper.assertSublinesCount(5);
                const sublines = helper.getSublines();
                helper.assertLinesTrackingNumbers(sublines, [
                    "b1-b001",
                    "b1-b002",
                    "b1-b003",
                    "b1-b004",
                    "b1-b005",
                ]);
                helper.assertLineQty(sublines[0], "8");
                helper.assertLineQty(sublines[1], "8");
                helper.assertLineQty(sublines[2], "8");
                helper.assertLineQty(sublines[3], "4");
                helper.assertLineQty(sublines[4], "1");
                helper.assertLineIsHighlighted(sublines[0], false);
                helper.assertLineIsHighlighted(sublines[1], false);
                helper.assertLineIsHighlighted(sublines[2], false);
                helper.assertLineIsHighlighted(sublines[3], false);
                helper.assertLineIsHighlighted(sublines[4], true);
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 3000007",
        },
        {
            trigger:
                '.o_sublines .o_barcode_line:contains("b1-b005") .qty-done:contains("8")',
            run: function () {
                helper.assertSublinesCount(5);
                const sublines = helper.getSublines();
                helper.assertLinesTrackingNumbers(sublines, [
                    "b1-b001",
                    "b1-b002",
                    "b1-b003",
                    "b1-b004",
                    "b1-b005",
                ]);
                helper.assertLineQty(sublines[0], "8");
                helper.assertLineQty(sublines[1], "8");
                helper.assertLineQty(sublines[2], "8");
                helper.assertLineQty(sublines[3], "4");
                helper.assertLineQty(sublines[4], "8");
                helper.assertLineIsHighlighted(sublines[0], false);
                helper.assertLineIsHighlighted(sublines[1], false);
                helper.assertLineIsHighlighted(sublines[2], false);
                helper.assertLineIsHighlighted(sublines[3], false);
                helper.assertLineIsHighlighted(sublines[4], true);
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 10b1-b004\x1D3000000004",
        },
        {
            trigger: '.o_sublines .o_barcode_line.o_selected:contains("b1-b004")',
            run: function () {
                helper.assertSublinesCount(5);
                const sublines = helper.getSublines();
                helper.assertLinesTrackingNumbers(sublines, [
                    "b1-b001",
                    "b1-b002",
                    "b1-b003",
                    "b1-b004",
                    "b1-b005",
                ]);
                helper.assertLineQty(sublines[0], "8");
                helper.assertLineQty(sublines[1], "8");
                helper.assertLineQty(sublines[2], "8");
                helper.assertLineQty(sublines[3], "8");
                helper.assertLineQty(sublines[4], "8");
                helper.assertLineIsHighlighted(sublines[0], false);
                helper.assertLineIsHighlighted(sublines[1], false);
                helper.assertLineIsHighlighted(sublines[2], false);
                helper.assertLineIsHighlighted(sublines[3], true);
                helper.assertLineIsHighlighted(sublines[4], false);
            },
        },
        ...stepUtils.validateBarcodeOperation(".o_validate_page"),
    ],
});

registry.category("web_tour.tours").add("test_gs1_receipt_quantity_with_uom", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: function () {
                helper.assertLinesCount(0);
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 01000000152643293100000005",
        },
        {
            trigger: ".o_barcode_line",
            run: function () {
                helper.assertLinesCount(1);
                const line = helper.getLine({ barcode: "15264329" });
                helper.assertLineIsHighlighted(line, true);
                helper.assertLineQty(line, "5 kg");
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 01000000152643293700000004",
        },
        {
            trigger: ".o_barcode_line .qty-done:contains(4)",
            run: function () {
                helper.assertLinesCount(2);
                const line = helper.getLines({ barcode: "15264329" })[1];
                helper.assertLineIsHighlighted(line, true);
                helper.assertLineQty(line, "4 Units");
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 01000000152643293100000005",
        },
        {
            trigger: ".o_barcode_line .qty-done:contains(10)",
            run: function () {
                helper.assertLinesCount(2);
                const line = helper.getLines({ barcode: "15264329" })[0];
                helper.assertLineIsHighlighted(line, true);
                helper.assertLineQty(line, "10 kg");
            },
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan 01000000152648793100000005",
        },
        {
            trigger: '.o_barcode_line:contains("Product by kg")',
            run: function () {
                helper.assertLinesCount(3);
                const line = helper.getLine({ barcode: "15264879" });
                helper.assertLineIsHighlighted(line, true);
                helper.assertLineQty(line, "5 kg");
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 01000000152648793700000006",
        },
        {
            trigger: ".o_barcode_line.o_selected .qty-done:contains(6)",
            run: function () {
                helper.assertLinesCount(4);
                const line = helper.getLines({ barcode: "15264879" })[1];
                helper.assertLineIsHighlighted(line, true);
                helper.assertLineQty(line, "6 Units");
            },
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan 01000000152648933102000125",
        },
        {
            trigger: '.o_barcode_line:contains("Product by g")',
            run: function () {
                helper.assertLinesCount(5);
                const line = helper.getLine({ barcode: "15264893" });
                helper.assertLineIsHighlighted(line, true);
                helper.assertLineQty(line, "1.25 kg");
            },
        },
        {
            trigger: ".o_barcode_line:nth-child(5) .o_edit",
            run: "click",
        },
        {
            trigger: "[name=qty_done] input",
            run: function () {
                helper.assertFormQuantity("4");
            },
        },
        ...stepUtils.discardBarcodeForm(),
    ],
});

registry.category("web_tour.tours").add("test_gs1_receipt_scan_not_gs1_multi_barcode", {
    steps: () => [
        { trigger: ".o_stock_barcode_main_menu", run: "scan WHIN" },
        {
            trigger: ".o_barcode_client_action",
            run: "scan productserial1,sn1,sn2,sn3,sn4,sn5,sn6,sn7,sn8",
        },
        { trigger: ".o_barcode_line .qty-done:contains(8)" },
        { trigger: "button.o_toggle_sublines", run: "click" },
        { trigger: ".o_sublines .o_barcode_line:nth-child(8)" },
        ...stepUtils.validateBarcodeOperation(),
    ],
});

registry.category("web_tour.tours").add("test_gs1_receipt_packaging", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: function () {
                helper.assertLinesCount(0);
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 0100000000002226",
        },
        {
            trigger: ".o_barcode_line",
            run: function () {
                helper.assertLinesCount(1);
                const line = helper.getLine({ barcode: "1113" });
                helper.assertLineIsHighlighted(line, true);
                helper.assertLineQty(line, "1 Dozens");
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan 01000000000022263700000004",
        },
        {
            trigger: '.o_barcode_line [name=quantity]:contains("5")',
            run: function () {
                helper.assertLinesCount(1);
                helper.assertLineIsHighlighted(0, true);
                helper.assertLineQty(0, "5 Dozens");
            },
        },
        {
            trigger: ".o_barcode_line:first-child .o_edit",
            run: "click",
        },
        {
            trigger: '[name="qty_done"] input',
            run: function () {
                helper.assertFormQuantity("5");
            },
        },
        ...stepUtils.discardBarcodeForm(),
    ],
});

registry.category("web_tour.tours").add("test_gs1_tracked_packaging", {
    steps: () => [
        { trigger: ".o_stock_barcode_main_menu", run: "scan WHIN" },
        { trigger: ".o_barcode_client_action", run: "scan 020000001265325610lot-001" },
        {
            trigger: ".o_barcode_line",
            run: () => {
                helper.assertLinesCount(1);
                helper.assertLineQty(
                    0,
                    "1 Dozens",
                    "Scanned packaging has quantity of 1",
                );
                helper.assertLineProduct(0, "productlot1");
                helper.assertLineTrackingNumber(0, "lot-001");
            },
        },
        { trigger: ".o_validate_page", run: "click" },

        { trigger: ".o_stock_barcode_main_menu", run: "scan WHOUT" },
        { trigger: ".o_barcode_client_action", run: "scan 020000001265325610lot-001" },
        {
            trigger: ".o_barcode_line",
            run: () => {
                helper.assertLinesCount(1);
                helper.assertLineQty(
                    0,
                    "1 Dozens",
                    "Scanned packaging has quantity of 1",
                );
                helper.assertLineProduct(0, "productlot1");
                helper.assertLineTrackingNumber(0, "lot-001");
            },
        },
        { trigger: ".o_validate_page", run: "click" },
        { trigger: ".o_notification_bar.bg-success" },
    ],
});

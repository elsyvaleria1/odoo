import { registry } from "@web/core/registry";

import * as helper from "./tour_helper_stock_barcode.js";
import { stepUtils } from "./tour_step_utils.js";

registry.category("web_tour.tours").add("test_internal_picking_from_scratch", {
    steps: () => [
        {
            trigger: ".o_add_line",
            run: "click",
        },
        {
            trigger: '.o_field_widget[name="product_id"]',
        },
        {
            trigger: ".o_field_widget[name=qty_done] input",
            run: "edit 2",
        },

        {
            trigger: ".o_field_widget[name=product_id] input",
            run: "edit product1",
        },

        {
            trigger: ".ui-menu-item > a:contains('product1')",
            run: "click",
        },

        {
            trigger: ".o_field_widget[name=location_id] input",
            run: "edit Section 1",
        },

        {
            trigger: ".ui-menu-item > a:contains('Section 1')",
            run: "click",
        },

        {
            trigger: ".o_field_widget[name=location_dest_id] input",
            run: "edit Section 2",
        },

        {
            trigger: ".ui-menu-item > a:contains('Section 2')",
            run: "click",
        },

        {
            trigger: ".o_save",
            run: "click",
        },
        {
            trigger:
                '.o_barcode_line .o_line_destination_location:contains("Section 2")',
        },
        {
            trigger:
                '.o_barcode_location_line[data-location="WH/Stock/Section 1"] + .o_barcode_line',
            run: function () {
                helper.assertLinesCount(1);
            },
        },

        {
            trigger: ".o_add_line",
            run: "click",
        },
        {
            trigger: '.o_field_widget[name="product_id"]',
        },
        {
            trigger: ".o_field_widget[name=product_id] input",
            run: "edit product2",
        },

        {
            trigger: ".ui-menu-item > a:contains('product2')",
            run: "click",
        },

        {
            trigger: ".o_field_widget[name=location_id] input",
            run: "edit Section 1",
        },

        {
            trigger: ".ui-menu-item > a:contains('Section 1')",
            run: "click",
        },

        {
            trigger: ".o_field_widget[name=location_dest_id] input",
            run: "edit WH/Stock/Section 3",
        },

        {
            trigger: ".ui-menu-item > a:contains('Section 3')",
            run: "click",
        },

        {
            trigger: ".o_save",
            run: "click",
        },
        {
            trigger:
                '.o_barcode_line .o_line_destination_location:contains("Section 3")',
        },
        {
            trigger:
                '.o_barcode_location_line[data-location="WH/Stock/Section 1"] + .o_barcode_line + .o_barcode_line',
            run: function () {
                helper.assertLinesCount(2);
                const lineProduct1 = helper.getLine({ barcode: "product1" });
                helper.assertLineIsHighlighted(lineProduct1, false);
                const lineProduct2 = helper.getLine({ barcode: "product2" });
                helper.assertLineIsHighlighted(lineProduct2, true);
            },
        },
        {
            trigger: ".o_barcode_line:nth-child(2) .o_edit",
            run: "click",
        },
        {
            trigger: '.o_field_widget[name="product_id"]',
            run: function () {
                helper.assertFormLocationSrc("WH/Stock/Section 1");
                helper.assertFormLocationDest("WH/Stock/Section 2");
                helper.assertFormQuantity("2");
            },
        },

        {
            trigger: ".o_save",
            run: "click",
        },

        {
            trigger: ".o_add_line",
            run: "click",
        },
        {
            trigger: '.o_field_widget[name="product_id"]',
        },
        {
            trigger: ".o_field_widget[name=product_id] input",
            run: "edit product2",
        },

        {
            trigger: ".ui-menu-item > a:contains('product2')",
            run: "click",
        },

        {
            trigger: ".o_field_widget[name=location_id] input",
            run: "edit Section 1",
        },

        {
            trigger: ".ui-menu-item > a:contains('Section 1')",
            run: "click",
        },

        {
            trigger: ".o_field_widget[name=location_dest_id] input",
            run: "edit Section 2",
        },

        {
            trigger: ".ui-menu-item > a:contains('Section 2')",
            run: "click",
        },

        {
            trigger: ".o_save",
            run: "click",
        },
        {
            trigger:
                '.o_barcode_line.o_selected .o_line_destination_location:contains("Section 2")',
        },
        {
            trigger: ".o_barcode_location_group .o_barcode_line:nth-child(4)",
            run: function () {
                helper.assertLinesCount(3);
            },
        },
        {
            trigger: ".o_barcode_line:nth-child(3).o_selected",
            run: "scan LOC-01-02-00",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan LOC-01-01-00",
        },

        {
            trigger:
                '.o_barcode_location_line[data-location="WH/Stock/Section 1"].text-bg-400',
            run: "scan product1",
        },

        {
            trigger: '.o_barcode_line[data-barcode="product1"].o_selected .o_edit',
            run: "click",
        },
        {
            trigger: '.o_field_widget[name="product_id"]:contains("product1")',
        },
        {
            trigger: ".o_save",
            run: "click",
        },
        {
            trigger: '.o_barcode_line[data-barcode="product1"].o_selected',
            run: "scan shelf3",
        },
        {
            trigger:
                '.o_barcode_line:nth-child(2) .o_line_destination_location:contains("Section 3")',
        },
        {
            trigger: ".o_validate_page",
            run: "click",
        },
        {
            trigger: ".o_notification_bar.bg-success",
        },
    ],
});

registry
    .category("web_tour.tours")
    .add("test_split_line_on_exit_for_delivery_with_lot", {
        steps: () => [
            {
                trigger: ".o_stock_barcode_main_menu",
                run: "scan delivery_split_move_on_exit",
            },
            {
                trigger: ".o_barcode_client_action",
                run: () => {
                    helper.assertLinesCount(1);
                    helper.assertLineProduct(0, "productlot1");
                    helper.assertLineQty(0, "0/3");
                },
            },
            { trigger: ".o_barcode_client_action", run: "scan productlot1" },
            { trigger: ".o_barcode_line.o_selected", run: "scan LOT002" },
            { trigger: ".o_barcode_line.o_selected", run: "scan LOT002" },
            { trigger: ".o_barcode_line.o_selected", run: "scan LOT001" },
            {
                trigger:
                    ".o_barcode_line.o_selected.o_line_completed  .o_line_button.o_toggle_sublines",
                run: "click",
            },
            {
                trigger: ".o_barcode_line_details .o_line_lot_name:contains(LOT001)",
                run: () => {
                    helper.assertLinesCount(1);
                    helper.assertLineQty(0, "3/3");
                    const [lot002Line, lot001Line] = helper.getSublines();
                    helper.assertLineTrackingNumber(lot002Line, "LOT002");
                    helper.assertLineQty(lot002Line, "2");
                    helper.assertLineTrackingNumber(lot001Line, "LOT001");
                    helper.assertLineQty(lot001Line, "1");
                },
            },
            { trigger: "button.o_exit", run: "click" },
            {
                trigger: ".o_stock_barcode_main_menu",
                run: "scan delivery_split_move_on_exit",
            },
            {
                trigger:
                    ".o_barcode_line.o_line_completed  .o_line_button.o_toggle_sublines",
                run: "click",
            },
            {
                trigger: ".o_barcode_line_details .o_line_lot_name:contains(LOT001)",
                run: () => {
                    helper.assertLinesCount(1);
                    helper.assertLineQty(0, "3/3");
                    const [lot002Line, lot001Line] = helper.getSublines();
                    helper.assertLineTrackingNumber(lot002Line, "LOT002");
                    helper.assertLineQty(lot002Line, "2");
                    helper.assertLineTrackingNumber(lot001Line, "LOT001");
                    helper.assertLineQty(lot001Line, "1");
                },
            },
            { trigger: "button.o_exit", run: "click" },
            { trigger: ".o_stock_barcode_main_menu", run() {} },
        ],
    });

registry
    .category("web_tour.tours")
    .add("test_split_uncomplete_moves_on_exit_with_neutral_changes", {
        steps: () => [
            {
                trigger: ".o_stock_barcode_main_menu",
                run: "scan SUMOEWNC",
            },
            {
                trigger: ".o_barcode_line .o_toggle_sublines",
                run: "click",
            },
            {
                trigger: ".o_barcode_line",
                run: () => {
                    helper.assertLinesCount(1);
                    helper.assertLineQty(0, "0/4");
                    const [subLine1, subLine2] = helper.getSublines();
                    helper.assert(
                        subLine1.querySelector(".o_line_lot_name").innerText,
                        "LN001",
                    );
                    helper.assertLineQty(subLine1, "0/2");
                    helper.assert(
                        subLine2.querySelector(".o_line_lot_name").innerText,
                        "LN002",
                    );
                    helper.assertLineQty(subLine2, "0/2");
                },
            },
            { trigger: ".o_barcode_client_action", run: "scan LN001" },
            { trigger: ".o_barcode_client_action", run: "scan LN001" },
            {
                trigger: ".o_barcode_line.o_line_completed .o_edit",
                run: "click",
            },
            {
                trigger: ".o_field_widget[name='qty_done'] input",
                run: "edit 0",
            },
            {
                trigger: ".o_save",
                run: "click",
            },
            {
                trigger: ".o_barcode_line",
                run: () => {
                    helper.assertLinesCount(1);
                    helper.assertLineQty(0, "0/4");
                    const [subLine1, subLine2] = helper.getSublines();
                    helper.assert(
                        subLine1.querySelector(".o_line_lot_name").innerText,
                        "LN001",
                    );
                    helper.assertLineQty(subLine1, "0/2");
                    helper.assert(
                        subLine2.querySelector(".o_line_lot_name").innerText,
                        "LN002",
                    );
                    helper.assertLineQty(subLine2, "0/2");
                },
            },
            { trigger: "button.o_exit", run: "click" },
            { trigger: ".o_stock_barcode_main_menu", run: "scan SUMOEWNC" },
            {
                trigger: ".o_barcode_line .o_toggle_sublines",
                run: "click",
            },
            {
                trigger: ".o_barcode_line",
                run: () => {
                    helper.assertLinesCount(1);
                    helper.assertLineQty(0, "0/4");
                    const [subLine1, subLine2] = helper.getSublines();
                    helper.assert(
                        subLine1.querySelector(".o_line_lot_name").innerText,
                        "LN002",
                    );
                    helper.assertLineQty(subLine1, "0/2");
                    helper.assert(
                        subLine2.querySelector(".o_line_lot_name").innerText,
                        "LN001",
                    );
                    helper.assertLineQty(subLine2, "0/2");
                },
            },
        ],
    });

registry
    .category("web_tour.tours")
    .add("test_internal_picking_from_scratch_with_package", {
        steps: () => [
            { trigger: ".o_stock_barcode_main_menu", run: "scan WHINT" },
            { trigger: ".o_barcode_client_action", run: "scan product1" },
            { trigger: ".o_barcode_line.o_selected", run: "scan P00001" },
            { trigger: ".o_barcode_line .result-package", run: "scan LOC-01-02-00" },
            { trigger: ".o_barcode_line:not(.o_selected)", run: "scan product2" },
            {
                trigger: '.o_barcode_line[data-barcode="product2"].o_selected',
                run: "scan P00001",
            },
            {
                trigger: '.o_barcode_line[data-barcode="product2"] .result-package',
                run: "scan LOC-01-02-00",
            },
            {
                trigger:
                    '.o_barcode_line[data-barcode="product2"] .o_line_destination_location',
                run: "scan OBTVALI",
            },
            {
                trigger: ".o_notification_bar.bg-success",
                run: "click",
            },
            {
                trigger: ".o_notification button.o_notification_close",
                run: "click",
            },

            { trigger: ".o_stock_barcode_main_menu", run: "scan WHINT" },
            {
                trigger: ".o_barcode_client_action",
                run: () => helper.assertLinesCount(0),
            },
            { trigger: ".o_barcode_client_action", run: "scan P00002" },
            {
                trigger:
                    '.o_barcode_line[data-barcode="product1"] + .o_barcode_line[data-barcode="product2"]',
                run: () => {
                    helper.assertLinesCount(2);
                    helper.assertLineQty(0, "1");
                    helper.assertLineQty(1, "2");
                },
            },
            {
                trigger: ".o_barcode_line.o_selected + .o_barcode_line.o_selected",
                run: "scan LOC-01-02-00",
            },
            { trigger: ".o_barcode_line:not(.o_selected)", run: "scan OBTVALI" },
            { trigger: ".o_notification_bar.bg-success" },

            { trigger: ".o_stock_barcode_main_menu", run: "scan WHINT" },
            { trigger: ".o_barcode_client_action", run: "scan P00003" },
            { trigger: ".o_barcode_line", run: "scan P00004" },
            {
                trigger: ".o_barcode_line .result-package:contains('P00004')",
                run: "scan PT_PALET",
            },
            {
                trigger: ".o_barcode_line .result-package:contains('PAL-')",
                run: function () {
                    helper.assertLinesCount(2);
                    helper.assertLineProduct(0, "product1");
                    helper.assertLinePackage(0, "P00003");
                    helper.assertLineLocations(0, "WH/Stock", "WH/Stock");
                    helper.assertLineResultPackage(0, "PAL-0000001 > P00003");
                    helper.assertLineProduct(1, "product2");
                    helper.assertLinePackage(1, "P00004");
                    helper.assertLineResultPackage(1, "PAL-0000001 > P00004");
                    helper.assertLineLocations(1, "WH/Stock", "WH/Stock");
                },
            },
            { trigger: ".o_barcode_line .result-package", run: "scan LOC-01-01-00" },
            {
                trigger:
                    ".o_barcode_line .o_line_destination_location:contains('Section 1')",
                run: function () {
                    helper.assertLinesCount(2);
                    helper.assertLineProduct(0, "product1");
                    helper.assertLinePackage(0, "P00003");
                    helper.assertLineLocations(0, "WH/Stock", ".../Section 1");
                    helper.assertLineResultPackage(0, "PAL-0000001 > P00003");
                    helper.assertLineProduct(1, "product2");
                    helper.assertLinePackage(1, "P00004");
                    helper.assertLineResultPackage(1, "PAL-0000001 > P00004");
                    helper.assertLineLocations(1, "WH/Stock", ".../Section 1");
                },
            },
            ...stepUtils.validateBarcodeOperation(),

            { trigger: ".o_stock_barcode_main_menu", run: "scan WHINT" },
            { trigger: ".o_barcode_client_action", run: "scan PAL-0000001" },
            {
                content: "Check package lines were correctly added.",
                trigger: ".o_barcode_line",
                run: function () {
                    helper.assertLinesCount(2);
                    helper.assertLineProduct(0, "[TEST] product1");
                    helper.assertLinePackages(
                        0,
                        "PAL-0000001 > P00003",
                        "PAL-0000001 > P00003",
                    );
                    helper.assertLineLocations(0, "WH/Stock/Section 1", "WH/Stock");
                    helper.assertLineProduct(1, "product2");
                    helper.assertLineLocations(1, "WH/Stock/Section 1", "WH/Stock");
                    helper.assertLinePackages(
                        1,
                        "PAL-0000001 > P00004",
                        "PAL-0000001 > P00004",
                    );
                },
            },
            { trigger: ".o_barcode_client_action", run: "scan PAL-0000001" },
            {
                trigger:
                    ".o_notification:contains('This package is already scanned.') .bg-danger",
            },
            {
                trigger: ".o_barcode_line",
                run: function () {
                    helper.assertLinesCount(2);
                    helper.assertLineProduct(0, "[TEST] product1");
                    helper.assertLinePackages(
                        0,
                        "PAL-0000001 > P00003",
                        "PAL-0000001 > P00003",
                    );
                    helper.assertLineLocations(0, "WH/Stock/Section 1", "WH/Stock");
                    helper.assertLineProduct(1, "product2");
                    helper.assertLineLocations(1, "WH/Stock/Section 1", "WH/Stock");
                    helper.assertLinePackages(
                        1,
                        "PAL-0000001 > P00004",
                        "PAL-0000001 > P00004",
                    );
                },
            },
            { trigger: ".o_barcode_line .result-package", run: "scan LOC-01-01-00" },
            {
                trigger:
                    ".o_barcode_line .o_line_destination_location:contains('Section 1')",
            },
            ...stepUtils.validateBarcodeOperation(),
            { trigger: ".o_stock_barcode_main_menu" },
        ],
    });

registry.category("web_tour.tours").add("test_internal_picking_reserved_1", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: function () {
                helper.assertLinesCount(3);
                helper.assertScanMessage("scan_src");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(false);
                helper.assertValidateEnabled(true);
                helper.assertLineIsHighlighted(0, false);
                helper.assertLineLocations(0, "WH/Stock/Section 1", ".../Section 2");
                helper.assertLineIsHighlighted(1, false);
                helper.assertLineLocations(1, "WH/Stock/Section 1", ".../Section 2");
                helper.assertLineIsHighlighted(2, false);
                helper.assertLineLocations(2, "WH/Stock/Section 3", ".../Section 4");
            },
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan shelf3",
        },

        {
            trigger:
                '.o_barcode_location_line[data-location="WH/Stock/Section 3"].text-bg-400',
            run: function () {
                helper.assertLinesCount(3);
                helper.assertScanMessage("scan_product");
                const locationInBold = document.querySelector(
                    ".o_barcode_location_line.text-bg-400",
                );
                const lineInSection3 =
                    locationInBold.parentElement.querySelector(".o_barcode_line");
                helper.assertLineLocations(
                    lineInSection3,
                    "WH/Stock/Section 3",
                    ".../Section 4",
                );
            },
        },

        { trigger: ".o_barcode_client_action", run: "scan product1" },
        {
            trigger: ".o_barcode_line.o_selected.o_line_completed",
            run: function () {
                helper.assertLinesCount(3);
                helper.assertScanMessage("scan_dest");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(false);
                helper.assertValidateEnabled(true);
                const lineproduct1 = helper.getLine({ selected: true });
                helper.assertLineIsHighlighted(lineproduct1, true);
                helper.assertLineLocations(
                    lineproduct1,
                    "WH/Stock/Section 3",
                    ".../Section 2",
                );
            },
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan LOC-01-02-00",
        },

        {
            trigger:
                '.o_barcode_location_group:nth-child(2) .o_barcode_line:not(.o_selected):nth-child(2) .o_line_destination_location:contains(".../Section 2")',
            run: function () {
                helper.assertLinesCount(3);
                helper.assertScanMessage("scan_src");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(false);
                helper.assertValidateEnabled(true);
                const lineproduct1 = helper.getLine({ barcode: "product1" });
                helper.assertLineIsHighlighted(lineproduct1, false);
                helper.assertLineLocations(
                    lineproduct1,
                    "WH/Stock/Section 3",
                    ".../Section 2",
                );
            },
        },

        { trigger: ".o_barcode_client_action", run: "scan LOC-01-01-00" },

        {
            trigger:
                '.o_barcode_location_line[data-location="WH/Stock/Section 1"].text-bg-400',
            run: function () {
                helper.assertLinesCount(3);
                helper.assertScanMessage("scan_product");
                helper.assertLineIsHighlighted(0, false);
                helper.assertLineIsHighlighted(1, false);
                helper.assertLineIsHighlighted(2, false);
            },
        },

        { trigger: ".o_barcode_client_action", run: "scan product1" },
        {
            trigger: ".o_barcode_location_group:first-child .o_barcode_line.o_selected",
            run: function () {
                helper.assertLinesCount(4);
                helper.assertScanMessage("scan_product_or_dest");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(false);
                helper.assertValidateEnabled(true);
                helper.assertLineIsHighlighted(0, false);
                helper.assertLineIsHighlighted(1, true);
                helper.assertLineLocations(1, "WH/Stock/Section 1", "WH/Stock");
                helper.assertLineIsHighlighted(2, false);
                helper.assertLineIsHighlighted(3, false);
            },
        },
        { trigger: ".o_barcode_client_action", run: "scan LOC-01-02-00" },

        { trigger: ".o_scan_message.o_scan_src", run: "scan LOC-01-01-00" },
        { trigger: ".o_scan_message.o_scan_product", run: "scan product2" },
        {
            trigger:
                ".o_barcode_location_group:first-child .o_barcode_line:nth-child(2).o_selected",
            run: function () {
                helper.assertLinesCount(4);
                helper.assertScanMessage("scan_dest");
                helper.assertValidateIsHighlighted(false);
                helper.assertLineIsHighlighted(0, true);
                helper.assertLineIsHighlighted(1, false);
                helper.assertLineIsHighlighted(2, false);
                helper.assertLineIsHighlighted(3, false);
            },
        },
        { trigger: ".o_barcode_client_action", run: "scan LOC-01-02-00" },

        { trigger: ".o_scan_message.o_scan_src", run: "scan shelf3" },
        { trigger: ".o_scan_message.o_scan_product", run: "scan product2" },
        {
            trigger:
                ".o_barcode_location_group:nth-child(2) .o_barcode_line:nth-child(3).o_selected",
            run: function () {
                helper.assertLinesCount(4);
                helper.assertScanMessage("scan_dest");
                helper.assertValidateIsHighlighted(false);
                helper.assertLineIsHighlighted(0, false);
                helper.assertLineIsHighlighted(1, false);
                helper.assertLineIsHighlighted(2, false);
                helper.assertLineIsHighlighted(3, true);
            },
        },
        { trigger: ".o_scan_message.o_scan_dest", run: "scan shelf4" },

        {
            trigger: ".o_scan_message.o_scan_validate",
            run: function () {
                helper.assertLinesCount(4);
                helper.assertScanMessage("scan_validate");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(true);
                helper.assertValidateEnabled(true);

                helper.assertLineIsHighlighted(0, false);
                helper.assertLineQty(0, "1/1");
                helper.assertLineLocations(0, "WH/Stock/Section 1", ".../Section 2");

                helper.assertLineIsHighlighted(1, false);
                helper.assertLineQty(1, "1");
                helper.assertLineLocations(1, "WH/Stock/Section 1", ".../Section 2");

                helper.assertLineIsHighlighted(2, false);
                helper.assertLineQty(2, "1/1");
                helper.assertLineLocations(2, "WH/Stock/Section 3", ".../Section 2");

                helper.assertLineIsHighlighted(3, false);
                helper.assertLineQty(3, "1/1");
                helper.assertLineLocations(3, "WH/Stock/Section 3", ".../Section 4");
            },
        },
    ],
});

registry
    .category("web_tour.tours")
    .add("test_internal_picking_reserved_move_packages_into_new_palet", {
        steps: () => [
            { trigger: ".o_stock_barcode_main_menu", run: "scan TEST/INT/0001" },
            {
                trigger: ".o_barcode_line",
                run: function () {
                    helper.assertLinesCount(2);
                    helper.assertLinePackages(0, "PAL-01", "PAL-01");
                    helper.assertLinePackages(1, "PAL-02", "PAL-02");
                },
            },
            { trigger: ".o_barcode_line[data-package='PAL-01']", run: "click" },
            {
                trigger:
                    ".o_barcode_line.o_selected button[name='completePackageButton']",
                run: "click",
            },
            {
                trigger: ".o_barcode_line.o_selected.o_line_completed button.o_unpack",
                run: "click",
            },
            {
                content: "Check PAL-01 was correctly unpacked",
                trigger:
                    ".o_barcode_line.o_line_not_completed + .o_barcode_line.o_selected.o_line_completed + .o_barcode_line.o_line_completed",
            },
            {
                trigger: ".o_barcode_line[data-package='PAL-02']",
                run: "click",
            },
            {
                trigger:
                    ".o_barcode_line[data-package='PAL-02'].o_selected button[name='completePackageButton']",
                run: "click",
            },
            {
                trigger: ".o_barcode_line.o_selected.o_line_completed button.o_unpack",
                run: "click",
            },
            {
                trigger: ".o_barcode_line[data-package='BOX-03']",
                run: function () {
                    helper.assertLinesCount(4);
                    helper.assertLinePackages(0, "PAL-01 > BOX-01", "BOX-01");
                    helper.assertLinePackages(1, "PAL-01 > BOX-02", "BOX-02");
                    helper.assertLinePackages(2, "PAL-02 > BOX-03", "BOX-03");
                    helper.assertLinePackages(3, "PAL-02 > BOX-04", "BOX-04");
                },
            },
            { trigger: "body", run: "scan PT_PALET" },
            {
                trigger: ".o_barcode_line .result-package:contains('PAL-0000001')",
                run: function () {
                    helper.assertLinesCount(4);
                    helper.assertLinePackages(
                        0,
                        "PAL-01 > BOX-01",
                        "PAL-0000001 > BOX-01",
                    );
                    helper.assertLinePackages(
                        1,
                        "PAL-01 > BOX-02",
                        "PAL-0000001 > BOX-02",
                    );
                    helper.assertLinePackages(
                        2,
                        "PAL-02 > BOX-03",
                        "PAL-0000001 > BOX-03",
                    );
                    helper.assertLinePackages(
                        3,
                        "PAL-02 > BOX-04",
                        "PAL-0000001 > BOX-04",
                    );
                },
            },
            ...stepUtils.validateBarcodeOperation(),

            { trigger: ".o_stock_barcode_main_menu", run: "scan TEST/INT/0002" },
            {
                trigger: ".o_barcode_line",
                run: function () {
                    helper.assertLinesCount(2);
                    helper.assertLinePackages(0, "BOX-05", "BOX-05");
                    helper.assertLinePackages(1, "BOX-06", "BOX-06");
                },
            },
            { trigger: ".o_barcode_line", run: "scan BOX-05" },
            {
                trigger:
                    ".o_barcode_line[data-package='BOX-05'].o_selected.o_line_completed",
                run: "scan BOX-06",
            },
            {
                trigger:
                    ".o_barcode_line[data-package='BOX-06'].o_selected.o_line_completed",
                run: "scan PAL-03",
            },
            {
                trigger: ".result-package:contains('PAL-03')",
                run: function () {
                    helper.assertLinesCount(2);
                    helper.assertLinePackages(0, "BOX-05", "PAL-03 > BOX-05");
                    helper.assertLinePackages(1, "BOX-06", "PAL-03 > BOX-06");
                },
            },
            ...stepUtils.validateBarcodeOperation(),
        ],
    });

registry.category("web_tour.tours").add("test_procurement_backorder", {
    steps: () => [
        { trigger: ".o_barcode_client_action", run: "scan PB" },
        { trigger: '.o_barcode_line:contains("PB")', run: "scan OBTVALI" },
        { trigger: ".o_notification_bar.bg-success" },
    ],
});

registry.category("web_tour.tours").add("test_receipt_reserved_1", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: function () {
                helper.assertLinesCount(2);
                helper.assertScanMessage("scan_product");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(false);
                helper.assertValidateEnabled(true);
                helper.assertLineDescription(
                    0,
                    "First Item\nMove carefully\nABC [123]",
                );
                helper.assertLineDescription(
                    1,
                    "Second Item\nMove carefully\nDEF [456]",
                );
            },
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan product2",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan product2",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan product2",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan product2",
        },

        {
            trigger: ".o_barcode_line.o_selected.o_line_completed",
            run: "scan WHSTOCK-2",
        },
        {
            trigger:
                ".o_notification:has(.bg-danger):text(The scanned location doesn't belong to this operation's destination)",
        },
        { trigger: ".o_barcode_client_action", run: "scan LOC-01-01-00" },

        {
            trigger: ".o_scan_message.o_scan_product",
            run: "scan product1",
        },

        {
            trigger: '.o_barcode_line[data-barcode="product1"] .qty-done:contains("1")',
            run: "scan product1",
        },

        {
            trigger: '.o_barcode_line[data-barcode="product1"] .qty-done:contains("2")',
            run: "scan product1",
        },

        {
            trigger: '.o_barcode_line[data-barcode="product1"] .qty-done:contains("3")',
            run: function () {
                helper.assertValidateIsHighlighted(false);
            },
        },

        ...stepUtils.inputManuallyBarcode("product1"),

        {
            trigger: '.o_barcode_line[data-barcode="product1"] .qty-done:contains("4")',
            run: function () {
                helper.assertValidateIsHighlighted(true);
            },
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan LOC-01-01-00",
        },

        {
            trigger: ".o_scan_message.o_scan_validate",
            run: function () {
                helper.assertLinesCount(2);
                helper.assertScanMessage("scan_validate");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(true);
                helper.assertValidateEnabled(true);
            },
        },

        {
            trigger: ".o_add_line",
            run: "click",
        },
        {
            trigger: '.o_field_widget[name="product_id"]',
            run: function () {
                helper.assertFormLocationDest("WH/Stock");
            },
        },
        ...stepUtils.discardBarcodeForm(),
    ],
});

registry.category("web_tour.tours").add("test_receipt_reserved_2_partial_put_in_pack", {
    steps: () => [
        { trigger: ".o_stock_barcode_main_menu", run: "scan receipt_test" },
        {
            trigger: ".o_barcode_line",
            run: function () {
                helper.assertLinesCount(2);
                helper.assertLineProduct(0, "product1");
                helper.assertLineQty(0, "0/3");
                helper.assertLineProduct(1, "product2");
                helper.assertLineQty(1, "0/3");
            },
        },

        { trigger: ".o_barcode_client_action", run: "scan product1" },
        { trigger: ".o_barcode_client_action", run: "scan product1" },
        {
            trigger: '.o_barcode_line.o_selected .qty-done:contains("2")',
            run: function () {
                helper.assertLinesCount(2);
                helper.assertLineProduct(0, "product1");
                helper.assertLineQty(0, "2/3");
                helper.assertLineProduct(1, "product2");
                helper.assertLineQty(1, "0/3");
            },
        },
        { trigger: ".o_barcode_client_action", run: "scan OBTPACK" },
        {
            trigger: '.o_barcode_line:contains("PACK0001000")',
            run: function () {
                const lines = helper.getLines();
                helper.assert(lines.length, 3);

                helper.assertLineProduct(lines[0], "product1");
                helper.assertLineQty(lines[0], "0/1");
                helper.assert(lines[0].querySelector(".result-package"), null);

                helper.assertLineProduct(lines[1], "product2");
                helper.assertLineQty(lines[1], "0/3");
                helper.assert(lines[1].querySelector(".result-package"), null);

                helper.assertLineProduct(lines[2], "product1");
                helper.assertLineQty(lines[2], "2/2");
                helper.assert(
                    lines[2].querySelector(".result-package").innerText,
                    "PACK0001000",
                );
            },
        },

        { trigger: ".o_barcode_client_action", run: "scan product1" },
        {
            trigger: ".o_barcode_line:first-child.o_selected.o_line_completed",
            run: "scan product2",
        },
        {
            trigger:
                '.o_barcode_line[data-barcode="product2"].o_selected .qty-done:contains("1")',
            run: function () {
                const lines = helper.getLines();
                helper.assert(lines.length, 3);

                helper.assertLineProduct(lines[0], "product1");
                helper.assertLineQty(lines[0], "1/1");
                helper.assert(lines[0].querySelector(".result-package"), null);

                helper.assertLineProduct(lines[1], "product2");
                helper.assertLineQty(lines[1], "1/3");
                helper.assert(lines[1].querySelector(".result-package"), null);

                helper.assertLineProduct(lines[2], "product1");
                helper.assertLineQty(lines[2], "2/2");
                helper.assert(
                    lines[2].querySelector(".result-package").innerText,
                    "PACK0001000",
                );
            },
        },
        {
            trigger: ".o_put_in_pack",
            run: "click",
        },
        {
            trigger: '.o_barcode_line:contains("PACK0001001")',
            run: function () {
                const lines = helper.getLines();
                helper.assert(lines.length, 4);

                helper.assertLineProduct(lines[0], "product2");
                helper.assertLineQty(lines[0], "0/2");
                helper.assert(lines[0].querySelector(".result-package"), null);

                helper.assertLineProduct(lines[1], "product1");
                helper.assertLineQty(lines[1], "2/2");
                helper.assert(
                    lines[1].querySelector(".result-package").innerText,
                    "PACK0001000",
                );

                helper.assertLineProduct(lines[2], "product1");
                helper.assertLineQty(lines[2], "1/1");
                helper.assert(
                    lines[2].querySelector(".result-package").innerText,
                    "PACK0001001",
                );

                helper.assertLineProduct(lines[3], "product2");
                helper.assertLineQty(lines[3], "1/1");
                helper.assert(
                    lines[3].querySelector(".result-package").innerText,
                    "PACK0001001",
                );
            },
        },
        { trigger: ".btn.o_validate_page", run: "click" },
        { trigger: ".modal-dialog button.btn-primary", run: "click" },
        { trigger: ".o_stock_barcode_main_menu" },
    ],
});

registry
    .category("web_tour.tours")
    .add("test_receipt_reserved_put_in_pack_after_interruption", {
        steps: () => [
            { trigger: ".o_stock_barcode_main_menu", run: "scan TEST/IN/0001" },
            {
                trigger: ".o_barcode_line",
                run: function () {
                    helper.assertLinesCount(4);
                },
            },
            { trigger: ".o_barcode_line", run: "scan product1" },
            {
                trigger: ".o_barcode_line[data-barcode='product1'].o_line_completed",
                run: "scan PT_BOX",
            },
            {
                trigger: ".o_barcode_line[data-barcode='product1'] .result-package",
                run: "scan product2",
            },
            { trigger: ".o_barcode_line[data-barcode='product2'].o_line_completed" },
            { trigger: "button.o_exit", run: "click" },
            { trigger: ".o_stock_barcode_main_menu", run: "scan TEST/IN/0001" },
            {
                trigger: ".o_barcode_line",
                run: function () {
                    helper.assertLinesCount(4);
                    helper.assertLineProduct(0, "product3");
                    helper.assertLineResultPackage(0, false);
                    helper.assertLineQty(0, "0/1");
                    helper.assertLineProduct(1, "product4");
                    helper.assertLineResultPackage(1, false);
                    helper.assertLineQty(1, "0/1");
                    helper.assertLineProduct(2, "product1");
                    helper.assertLineResultPackage(2, "BOX-0000001");
                    helper.assertLineQty(2, "1/1");
                    helper.assertLineProduct(3, "product2");
                    helper.assertLineResultPackage(3, false);
                    helper.assertLineQty(3, "1/1");
                },
            },
            { trigger: ".o_barcode_line", run: "scan PT_BOX" },
            {
                trigger: ".o_barcode_line[data-barcode='product2'] .result-package",
                run: function () {
                    helper.assertLinesCount(4);
                    helper.assertLineProduct(0, "product3");
                    helper.assertLineResultPackage(0, false);
                    helper.assertLineQty(0, "0/1");
                    helper.assertLineProduct(1, "product4");
                    helper.assertLineResultPackage(1, false);
                    helper.assertLineQty(1, "0/1");
                    helper.assertLineProduct(2, "product1");
                    helper.assertLineResultPackage(2, "BOX-0000001");
                    helper.assertLineQty(2, "1/1");
                    helper.assertLineProduct(3, "product2");
                    helper.assertLineResultPackage(3, "BOX-0000002");
                    helper.assertLineQty(3, "1/1");
                },
            },
            { trigger: "button.o_exit", run: "click" },
            { trigger: ".o_stock_barcode_main_menu", run: "scan TEST/IN/0001" },
            { trigger: ".o_barcode_line", run: "scan PT_PALET" },
            {
                trigger: ".result-package:contains('PAL')",
                run: function () {
                    helper.assertLinesCount(4);
                    helper.assertLineProduct(0, "product3");
                    helper.assertLineResultPackage(0, false);
                    helper.assertLineQty(0, "0/1");
                    helper.assertLineProduct(1, "product4");
                    helper.assertLineResultPackage(1, false);
                    helper.assertLineQty(1, "0/1");
                    helper.assertLineProduct(2, "product1");
                    helper.assertLineResultPackage(2, "PAL-0000001 > BOX-0000001");
                    helper.assertLineQty(2, "1/1");
                    helper.assertLineProduct(3, "product2");
                    helper.assertLineResultPackage(3, "PAL-0000001 > BOX-0000002");
                    helper.assertLineQty(3, "1/1");
                },
            },
            { trigger: ".o_barcode_line", run: "scan product4" },
            {
                trigger: ".o_barcode_line[data-barcode='product4'].o_line_completed",
                run: "scan PT_BOX",
            },
            { trigger: ".o_barcode_line[data-barcode='product4'] .result-package" },
            { trigger: "button.o_exit", run: "click" },
            { trigger: ".o_stock_barcode_main_menu", run: "scan TEST/IN/0001" },
            { trigger: ".o_barcode_line", run: "scan PAL-0000001" },
            {
                trigger:
                    ".o_barcode_line[data-barcode='product4'] .result-package:contains('PAL')",
                run: function () {
                    helper.assertLinesCount(4);
                    helper.assertLineProduct(0, "product3");
                    helper.assertLineResultPackage(0, false);
                    helper.assertLineQty(0, "0/1");
                    helper.assertLineProduct(1, "product1");
                    helper.assertLineResultPackage(1, "PAL-0000001 > BOX-0000001");
                    helper.assertLineQty(1, "1/1");
                    helper.assertLineProduct(2, "product2");
                    helper.assertLineResultPackage(2, "PAL-0000001 > BOX-0000002");
                    helper.assertLineQty(2, "1/1");
                    helper.assertLineProduct(3, "product4");
                    helper.assertLineResultPackage(3, "PAL-0000001 > BOX-0000003");
                    helper.assertLineQty(3, "1/1");
                },
            },
            { trigger: ".o_barcode_line", run: "scan product3" },
            {
                trigger:
                    ".o_barcode_line[data-barcode='product3'].o_selected.o_line_completed",
            },
            { trigger: "button.o_exit", run: "click" },
            { trigger: ".o_stock_barcode_main_menu", run: "scan TEST/IN/0001" },
            { trigger: "button.o_put_in_pack", run: "click" },
            {
                trigger: ".o_barcode_line[data-barcode='product3'] .result-package",
                run: function () {
                    helper.assertLinesCount(4);
                    helper.assertLineProduct(0, "product1");
                    helper.assertLineResultPackage(0, "PAL-0000001 > BOX-0000001");
                    helper.assertLineQty(0, "1/1");
                    helper.assertLineProduct(1, "product2");
                    helper.assertLineResultPackage(1, "PAL-0000001 > BOX-0000002");
                    helper.assertLineQty(1, "1/1");
                    helper.assertLineProduct(2, "product4");
                    helper.assertLineResultPackage(2, "PAL-0000001 > BOX-0000003");
                    helper.assertLineQty(2, "1/1");
                    helper.assertLineProduct(3, "product3");
                    helper.assertLineResultPackage(3, "PACK0000001");
                    helper.assertLineQty(3, "1/1");
                },
            },
            { trigger: "button.o_exit", run: "click" },
            { trigger: ".o_stock_barcode_main_menu", run: "scan TEST/IN/0001" },
            { trigger: ".o_barcode_line", run: "scan PAL-0000001" },
            {
                trigger:
                    ".o_barcode_line[data-barcode='product3'] .result-package:contains('PAL')",
                run: function () {
                    helper.assertLinesCount(4);
                    helper.assertLineProduct(0, "product1");
                    helper.assertLineResultPackage(0, "PAL-0000001 > BOX-0000001");
                    helper.assertLineQty(0, "1/1");
                    helper.assertLineProduct(1, "product2");
                    helper.assertLineResultPackage(1, "PAL-0000001 > BOX-0000002");
                    helper.assertLineQty(1, "1/1");
                    helper.assertLineProduct(2, "product4");
                    helper.assertLineResultPackage(2, "PAL-0000001 > BOX-0000003");
                    helper.assertLineQty(2, "1/1");
                    helper.assertLineProduct(3, "product3");
                    helper.assertLineResultPackage(3, "PAL-0000001 > PACK0000001");
                    helper.assertLineQty(3, "1/1");
                },
            },
            ...stepUtils.validateBarcodeOperation(),

            { trigger: ".o_stock_barcode_main_menu", run: "scan TEST/IN/0002" },
            { trigger: ".o_barcode_line", run: "scan product1" },
            {
                content: "Pack product1",
                trigger: ".o_barcode_line.o_selected.o_line_completed",
                run: "scan OBTPACK",
            },
            {
                trigger: ".o_barcode_line[data-barcode='product1'] .result-package",
                run: "scan product2",
            },
            {
                content: "Pack product2",
                trigger:
                    ".o_barcode_line[data-barcode='product2'].o_selected.o_line_completed",
                run: "scan OBTPACK",
            },
            {
                content: "Pack both packages into another package",
                trigger: ".o_barcode_line[data-barcode='product2'] .result-package",
                run: "scan OBTPACK",
            },
            {
                content: "Set the palet type to the parent package",
                trigger: ".result-package:text('PACK0000004 > PACK0000003')",
                run: "scan PT_PALET",
            },
            {
                trigger:
                    ".o_notification_content:text('Package type Palet applied to the package PACK0000004')",
                run: function () {
                    helper.assertLinesCount(2);
                    helper.assertLineProduct(0, "product1");
                    helper.assertLineResultPackage(0, "PACK0000004 > PACK0000002");
                    helper.assertLineQty(0, "1/1");
                    helper.assertLineProduct(1, "product2");
                    helper.assertLineResultPackage(1, "PACK0000004 > PACK0000003");
                    helper.assertLineQty(1, "1/1");
                },
            },
            ...stepUtils.validateBarcodeOperation(),
        ],
    });

registry.category("web_tour.tours").add("test_receipt_product_not_consecutively", {
    steps: () => [
        { trigger: ".o_barcode_client_action", run: "scan product1" },
        { trigger: ".o_barcode_line", run: "scan product2" },
        { trigger: '.o_barcode_line:contains("product2")', run: "scan product1" },
        {
            trigger: '.o_barcode_line[data-barcode="product1"] .qty-done:contains("2")',
            run: "scan OBTVALI",
        },
        {
            trigger: ".o_notification_bar.bg-success",
        },
    ],
});

registry.category("web_tour.tours").add("test_delivery_source_location", {
    steps: () => [
        { trigger: ".o_stock_barcode_main_menu", run: "scan delivery_from_stock" },
        { trigger: ".o_scan_message.o_scan_src", run: "scan WH-SECOND-STOCK" },
        {
            trigger:
                ".o_notification:has(.bg-danger):text(The scanned location doesn't belong to this operation's location)",
        },
        {
            trigger: "button.o_notification_close",
            run: "click",
        },
        { trigger: ".o_barcode_client_action", run: "scan LOC-01-00-00" },
        { trigger: ".o_scan_message.o_scan_product", run: "scan product1" },
        { trigger: ".o_barcode_line.o_selected", run: "scan product1" },
        { trigger: ".o_barcode_line.o_selected", run: "scan product1" },
        { trigger: ".o_barcode_line.o_selected", run: "scan product1" },
        {
            trigger: ".o_validate_page.btn-primary",
            run: "click",
        },

        {
            trigger: ".o_stock_barcode_main_menu",
            run: "scan delivery_from_second_stock",
        },
        { trigger: ".o_scan_message.o_scan_src", run: "scan LOC-01-00-00" },
        {
            trigger:
                ".o_notification:has(.bg-danger):text(The scanned location doesn't belong to this operation's location)",
        },
        {
            trigger: "button.o_notification_close",
            run: "click",
        },
        { trigger: ".o_barcode_client_action", run: "scan WH-SECOND-STOCK" },
        { trigger: ".o_scan_message.o_scan_product", run: "scan product1" },
        { trigger: ".o_barcode_line.o_selected", run: "scan product1" },
        { trigger: ".o_barcode_line.o_selected", run: "scan product1" },
        { trigger: ".o_barcode_line.o_selected", run: "scan product1" },
        ...stepUtils.validateBarcodeOperation(".o_validate_page.btn-primary"),

        { trigger: ".o_stock_barcode_main_menu", run: "scan WHOUT" },
        { trigger: ".o_barcode_client_action", run: "scan WH-SECOND-STOCK" },
        { trigger: ".o_scan_message.o_scan_product", run: "scan product1" },
        { trigger: ".o_barcode_line", run: "scan LOC-01-00-00" },
        { trigger: ".o_scan_message.o_scan_validate", run: "scan product1" },
        {
            trigger: ".o_barcode_location_group + .o_barcode_location_group",
            run: () => {
                helper.assertLinesCount(2);
                helper.assertLineSourceLocation(0, "WH/Second Stock");
                helper.assertLineSourceLocation(1, "WH/Stock");
            },
        },
    ],
});

registry.category("web_tour.tours").add("test_delivery_lot_with_multi_companies", {
    steps: () => [
        { trigger: ".o_barcode_client_action", run: "scan tsn-002" },
        { trigger: ".o_notification_bar.bg-danger", run: "scan tsn-001" },
        {
            trigger: ".o_barcode_line",
            run: function () {
                const line = helper.getLine({ barcode: "productserial1" });
                helper.assert(
                    line.querySelector(".o_line_lot_name").innerText,
                    "tsn-001",
                );
            },
        },
        { trigger: ".o_barcode_client_action", run: "scan tsn-003" },
        {
            trigger: ".o_toggle_sublines",
        },
        {
            trigger: ".o_validate_page",
            run: "click",
        },
        { trigger: ".o_notification_bar.bg-success" },
    ],
});

registry.category("web_tour.tours").add("test_delivery_lot_with_package", {
    steps: () => [
        {
            trigger: ".o_line_button.o_toggle_sublines",
            run: "click",
        },
        {
            trigger: '.o_barcode_client_action:contains("sn2")',
            run: function () {
                helper.assertLinesCount(1);
                helper.assertSublinesCount(2);
                helper.assertScanMessage("scan_serial");
                const [line1, line2] = helper.getSublines();
                helper.assert(line1.querySelector(".o_line_lot_name").innerText, "sn1");
                helper.assert(
                    line1
                        .querySelector(".fa-archive")
                        .parentElement.innerText.includes("pack_sn_1"),
                    true,
                );
                helper.assert(line2.querySelector(".o_line_lot_name").innerText, "sn2");
                helper.assert(
                    line2
                        .querySelector(".fa-archive")
                        .parentElement.innerText.includes("pack_sn_1"),
                    true,
                );
            },
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan productserial1",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan sn3",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan sn4",
        },

        {
            trigger: '.o_barcode_client_action:contains("sn4")',
            run: function () {
                helper.assertLinesCount(1);
                helper.assertSublinesCount(4);
                helper.assertScanMessage("scan_validate");
                const [line1, line2, line3, line4] = helper.getSublines();
                helper.assert(line1.querySelector(".o_line_lot_name").innerText, "sn1");
                helper.assert(line1.querySelector(".o_line_owner"), null);
                helper.assert(line1.querySelector(".package").innerText, "pack_sn_1");
                helper.assert(
                    line1.querySelector(".result-package").innerText,
                    "pack_sn_1",
                );
                helper.assert(line2.querySelector(".o_line_lot_name").innerText, "sn3");
                helper.assert(line2.querySelector(".o_line_owner"), null);
                helper.assert(line2.querySelector(".package").innerText, "pack_sn_2");
                helper.assert(line3.querySelector(".o_line_lot_name").innerText, "sn4");
                helper.assert(
                    line3.querySelector(".o_line_owner").innerText,
                    "Particulier",
                );
                helper.assert(line3.querySelector(".package").innerText, "pack_sn_2");
                helper.assert(line4.querySelector(".o_line_lot_name").innerText, "sn2");
                helper.assert(line4.querySelector(".o_line_owner"), null);
                helper.assert(
                    line1.querySelector(".result-package").innerText,
                    "pack_sn_1",
                );
                helper.assert(line4.querySelector(".package").innerText, "pack_sn_1");
            },
        },

        {
            trigger: ".o_sublines .o_barcode_line:nth-child(3) .fa-pencil",
            run: "click",
        },
        {
            trigger: '.o_field_widget[name="product_id"]',
            run: function () {
                helper.assertFormQuantity("1");
                helper.assert(
                    document.querySelector('div[name="package_id"] input').value,
                    "pack_sn_2",
                );
                helper.assert(
                    document.querySelector('div[name="result_package_id"] input').value,
                    "",
                );
                helper.assert(
                    document.querySelector('div[name="owner_id"] input').value,
                    "Particulier",
                );
                helper.assert(
                    document.querySelector('div[name="trace_id"] input').value,
                    "sn4",
                );
            },
        },
        {
            trigger: ".o_discard",
            run: "click",
        },
        ...stepUtils.validateBarcodeOperation(),
    ],
});

registry
    .category("web_tour.tours")
    .add("test_delivery_lot_with_package_delivery_step", {
        steps: () => [
            {
                trigger: ".o_barcode_line",
                run: "scan LOC-01-02-00",
            },
            {
                trigger: ".o_barcode_line",
                run: "scan productlot1",
            },
            {
                trigger: ".o_barcode_line",
                run: "scan sn",
            },
            {
                trigger: '.o_barcode_line:contains("sn")',
            },
            ...stepUtils.validateBarcodeOperation(),
            {
                trigger:
                    ".o_notification:has(.bg-success):text(The transfer has been validated)",
            },
        ],
    });

registry.category("web_tour.tours").add("test_delivery_pack_from_different_location", {
    steps: () => [
        { trigger: ".o_stock_barcode_main_menu", run: "scan WHOUT" },
        { trigger: ".o_scan_message.o_scan_src", run: "scan LOC-01-01-00" },
        { trigger: ".o_scan_message.o_scan_product", run: "scan product1" },
        { trigger: ".o_barcode_line.o_selected", run: "scan LOC-01-02-00" },
        { trigger: ".o_barcode_line:not(.o_selected)", run: "scan product1" },
        {
            content: "Check lines source location before to scan the package.",
            trigger: ".o_barcode_line:nth-child(2).o_selected",
            run: () => {
                helper.assertLinesCount(2);
                helper.assertLineSourceLocation(0, "WH/Stock/Section 1");
                helper.assertLineResultPackage(0);
                helper.assertLineSourceLocation(1, "WH/Stock/Section 2");
                helper.assertLineResultPackage(1);
            },
        },
        { trigger: ".o_barcode_line.o_selected", run: "scan pack-test" },
        {
            trigger: ".o_barcode_line .result-package",
            run: () => {
                helper.assertLinesCount(2);
                helper.assertLineSourceLocation(0, "WH/Stock/Section 1");
                helper.assertLineResultPackage(0, "pack-test");
                helper.assertLineSourceLocation(1, "WH/Stock/Section 2");
                helper.assertLineResultPackage(1, "pack-test");
            },
        },
    ],
});

registry.category("web_tour.tours").add("test_delivery_reserved_1", {
    steps: () => [
        {
            trigger: '.alert:contains("A Test Note")',
            run: "click",
        },
        {
            trigger: ".alert button.btn-close",
            run: "click",
        },
        {
            trigger: ".o_add_line",
            run: "click",
        },
        {
            trigger: ".o_discard",
            run: "click",
        },
        {
            trigger: ".o_barcode_lines",
            run: function () {
                const note = document.querySelector(".alert.alert-warning");
                helper.assert(Boolean(note), false, "Note must not be present");
            },
        },

        {
            trigger: ".o_barcode_client_action",
            run: function () {
                helper.assertLinesCount(2);
                helper.assertScanMessage("scan_src");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(false);
                helper.assertValidateEnabled(true);
            },
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan LOC-01-00-00",
        },

        {
            trigger: ".o_scan_message.o_scan_product",
            run: function () {
                helper.assertLinesCount(2);
                helper.assertScanMessage("scan_product");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(false);
                helper.assertValidateEnabled(true);
            },
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan product1",
        },

        {
            trigger: ".o_barcode_line:nth-child(2).o_selected",
            run: "scan product2",
        },
        { trigger: ".o_barcode_line:nth-child(3).o_selected" },

        {
            trigger: ".o_barcode_header .o_title",
            run: "click",
        },
        {
            trigger: ".o_barcode_control .btn.o_discard",
            run: "click",
        },
        { trigger: ".o_barcode_line" },
    ],
});

registry.category("web_tour.tours").add("test_delivery_reserved_2", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: function () {
                helper.assertLinesCount(2);
                helper.assertScanMessage("scan_product");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(false);
                helper.assertValidateEnabled(true);
            },
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan product1",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan product1",
        },

        {
            trigger: ".o_barcode_line.o_selected.o_line_completed",
            run: "scan product2",
        },
        ...stepUtils.confirmAddingUnreservedProduct(),

        {
            trigger: '.o_barcode_line.o_selected:contains("product2")',
            run: function () {
                helper.assertLinesCount(3);
                helper.assertScanMessage("scan_product");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(false);
                helper.assertValidateEnabled(true);
                const p1_lines = helper.getLines({ barcode: "product1" });
                helper.assertLineIsFaulty(p1_lines[0], false);
                helper.assertLineIsFaulty(p1_lines[1], false);
                const p2_line = helper.getLine({ barcode: "product2" });
                helper.assertLineIsFaulty(p2_line, true);
            },
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan product1",
        },

        {
            trigger: ".o_barcode_line.o_selected:not(.o_line_completed)",
            run: "scan product1",
        },

        {
            trigger: ".o_barcode_line.o_selected.o_line_completed",
            run: function () {
                helper.assertLinesCount(3);
                helper.assertScanMessage("scan_validate");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(true);
                helper.assertValidateEnabled(true);
                const lines = helper.getLines({ barcode: "product1" });
                [0, 1].map((i) => helper.assertLineQty(lines[i], "2/2"));
            },
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan product1",
        },

        {
            trigger: ".o_barcode_line:nth-child(4)",
            run: function () {
                helper.assertLinesCount(4);
                helper.assertScanMessage("scan_validate");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(true);
                helper.assertValidateEnabled(true);
                const p1_lines = helper.getLines({ barcode: "product1" });
                helper.assertLineIsFaulty(p1_lines[0], false);
                helper.assertLineIsFaulty(p1_lines[1], false);
                helper.assertLineIsFaulty(p1_lines[2], true);
                const p2_line = helper.getLine({ barcode: "product2" });
                helper.assertLineIsFaulty(p2_line, true);
            },
        },
    ],
});

registry.category("web_tour.tours").add("test_delivery_reserved_3", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: function () {
                helper.assertLinesCount(1);
                helper.assertScanMessage("scan_product");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(false);
                helper.assertValidateEnabled(true);
            },
        },
        { trigger: ".o_barcode_client_action", run: "scan product1" },
        { trigger: ".o_barcode_client_action", run: "scan this_is_not_a_barcode_dude" },
        {
            trigger: ".o_barcode_line.o_highlight",
            run: function () {
                helper.assertLinesCount(1);
                helper.assertScanMessage("scan_validate");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(true);
                helper.assertValidateEnabled(true);
                helper.assertLineIsHighlighted(0, true);
                helper.assertLineQty(0, "1/1");
            },
        },
    ],
});

registry.category("web_tour.tours").add("test_delivery_reserved_4_backorder", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: function () {
                helper.assertLinesCount(2);
                helper.assertLineQty(0, "0/4");
                helper.assertLineQty(1, "0/2");
            },
        },
        { trigger: ".o_barcode_client_action", run: "scan product1" },
        {
            trigger: ".o_barcode_line.o_selected",
        },
        {
            trigger: ".o_validate_page",
            run: "click",
        },
        {
            trigger: ".modal-content.o_barcode_backorder_dialog",
            run: function () {
                const incompleteLines = document.querySelectorAll(
                    ".o_barcode_backorder_product_row",
                );
                helper.assert(incompleteLines.length, 2);
                const [line1, line2] = incompleteLines;
                helper.assert(line1.querySelector("[name='qty-done']").innerText, "1");
                helper.assert(
                    line1.querySelector("[name='reserved-qty']").innerText,
                    "4",
                );
                helper.assert(
                    line1.querySelector("[name='backorder-qty']").innerText,
                    "3",
                );
                helper.assert(line2.querySelector("[name='qty-done']").innerText, "0");
                helper.assert(
                    line2.querySelector("[name='reserved-qty']").innerText,
                    "2",
                );
                helper.assert(
                    line2.querySelector("[name='backorder-qty']").innerText,
                    "2",
                );
            },
        },
        {
            trigger: ".modal-dialog button.btn-secondary",
            run: "click",
        },
        { trigger: ".o_barcode_client_action", run: "scan product1" },
        { trigger: ".o_barcode_client_action", run: "scan product1" },
        { trigger: ".o_barcode_client_action", run: "scan product1" },
        {
            trigger: ".o_barcode_line.o_selected.o_line_completed",
        },
        {
            trigger: ".o_validate_page",
            run: "click",
        },
        {
            trigger: ".modal-content.o_barcode_backorder_dialog",
            run: function () {
                const incompleteLines = document.querySelectorAll(
                    ".o_barcode_backorder_product_row",
                );
                helper.assert(incompleteLines.length, 1);
                const [incompleteLine] = incompleteLines;
                helper.assert(
                    incompleteLine.querySelector("[name='qty-done']").innerText,
                    "0",
                );
                helper.assert(
                    incompleteLine.querySelector("[name='reserved-qty']").innerText,
                    "2",
                );
                helper.assert(
                    incompleteLine.querySelector("[name='backorder-qty']").innerText,
                    "2",
                );
            },
        },
        {
            trigger: ".modal-dialog button.btn-primary",
            run: "click",
        },
        {
            trigger: ".o_notification",
            run: function () {
                const backorderLink = document.querySelector(
                    ".o_notification_buttons span",
                );
                helper.assert(
                    backorderLink.innerText.includes("WH/OUT/"),
                    true,
                    "The notification should contain a link to the created backorder.",
                );
            },
        },
    ],
});

registry
    .category("web_tour.tours")
    .add("test_delivery_reserved_5_dont_show_reserved_sn", {
        steps: () => [
            {
                trigger: ".o_barcode_client_action",
                run: function () {
                    helper.assertScanMessage("scan_product");
                    helper.assertLinesCount(1);
                    helper.assertLineQty(0, "0/4");
                    helper.assertLineProduct(0, "productserial1");
                    helper.assertLineTrackingNumber(0, "");
                    helper.assertButtonIsVisible(0, "toggle_sublines", false);
                    helper.assertButtonIsVisible(0, "edit");
                },
            },
            { trigger: ".o_barcode_client_action", run: "scan productserial1" },
            { trigger: ".o_barcode_line.o_selected .btn.o_edit", run: "click" },
            {
                trigger: ".o_form_view_container",
                run: () => {
                    const lotField = document.querySelector(
                        '.o_field_widget[name="trace_id"] input',
                    );
                    helper.assert(
                        lotField.value,
                        "sn1",
                        "Should display move line for sn1",
                    );
                },
            },
            { trigger: ".o_field_widget[name=qty_done] input", run: "clear" },
            { trigger: ".o_field_widget[name=qty_done] input", run: "edit 1" },
            { trigger: ".o_save", run: "click" },
            {
                trigger: ".o_barcode_line",
                run: () => {
                    helper.assertScanMessage("scan_serial");
                    helper.assertLinesCount(1);
                    helper.assertLineQty(0, "1/4");
                    helper.assertLineTrackingNumber(0, "sn1");
                    helper.assertButtonIsVisible(0, "toggle_sublines", false);
                },
            },
            { trigger: ".o_barcode_line.o_selected .btn.o_edit", run: "click" },
            {
                trigger: ".o_form_view_container",
                run: () => {
                    const lotField = document.querySelector(
                        '.o_field_widget[name="trace_id"] input',
                    );
                    helper.assert(
                        lotField.value,
                        "sn1",
                        "Should still display move line for sn1",
                    );
                },
            },
            { trigger: ".o_discard", run: "click" },

            { trigger: ".o_barcode_client_action", run: "scan sn5" },
            {
                trigger: ".o_line_button.o_toggle_sublines",
                run: function () {
                    helper.assertLineQty(0, "2/4");
                },
            },

            { trigger: ".o_line_button.o_toggle_sublines", run: "click" },
            {
                trigger: ".o_sublines",
                run: function () {
                    helper.assertLineQty(0, "2/4");
                    const unreservedLine = document.querySelector(".o_faulty");
                    helper.assert(
                        Boolean(unreservedLine),
                        false,
                        "There should be no faulty line if show reserved sn/lot is disabled",
                    );
                },
            },

            { trigger: ".o_barcode_client_action", run: "scan sn2" },
            { trigger: ".o_barcode_client_action", run: "scan sn3" },
            ...stepUtils.validateBarcodeOperation(
                ".o_barcode_line.o_selected.o_line_completed",
            ),
        ],
    });

registry
    .category("web_tour.tours")
    .add("test_delivery_reserved_6_dont_show_reserved_lots", {
        steps: () => [
            {
                trigger: ".o_barcode_client_action",
                run: function () {
                    helper.assertScanMessage("scan_product");
                    helper.assertLinesCount(1);
                    helper.assertLineQty(0, "0/12");
                    helper.assertLineProduct(0, "productlot1");
                    helper.assertButtonIsVisible(0, "toggle_sublines", false);
                    helper.assertButtonIsVisible(0, "edit");
                    helper.assertLineTrackingNumber(0, "");
                },
            },
            { trigger: ".o_barcode_client_action", run: "scan productlot1" },
            {
                trigger: ".o_barcode_line.o_selected",
                run: function () {
                    helper.assertScanMessage("scan_lot");
                    helper.assertLinesCount(1);
                    helper.assertLineQty(0, "0/12");
                    helper.assertLineProduct(0, "productlot1");
                    helper.assertButtonIsVisible(0, "toggle_sublines", false);
                    helper.assertButtonIsVisible(0, "edit");
                    helper.assertLineTrackingNumber(0, "");
                },
            },
            { trigger: ".o_barcode_client_action", run: "scan lot-001" },
            {
                trigger: '.o_line_lot_name:contains("lot")',
                run: function () {
                    helper.assertScanMessage("scan_lot");
                    helper.assertLinesCount(1);
                    helper.assertLineQty(0, "1/12");
                    helper.assertLineProduct(0, "productlot1");
                    helper.assertButtonIsVisible(0, "toggle_sublines", false);
                    helper.assertButtonIsVisible(0, "edit");
                    helper.assertLineTrackingNumber(0, "lot-001");
                },
            },
            { trigger: ".o_barcode_client_action", run: "scan lot-002" },
            {
                trigger: ".o_line_button.o_toggle_sublines",
                run: function () {
                    helper.assertScanMessage("scan_lot");
                    helper.assertLinesCount(1);
                    helper.assertLineQty(0, "2/12");
                    helper.assertLineProduct(0, "productlot1");
                    helper.assertButtonIsVisible(0, "toggle_sublines");
                    helper.assertButtonIsVisible(0, "edit", false);
                    helper.assertLineTrackingNumber(0, false);
                },
            },
            { trigger: ".o_line_button.o_toggle_sublines", run: "click" },
            {
                trigger: ".o_sublines .o_barcode_line",
                run: function () {
                    const sublines = helper.getSublines();
                    helper.assertLinesCount(1);
                    helper.assertSublinesCount(2);
                    helper.assertLineQty(sublines[0], "1");
                    helper.assertLineQty(sublines[1], "1");
                    helper.assertLinesTrackingNumbers(sublines, ["lot-001", "lot-002"]);
                },
            },
            { trigger: ".o_barcode_client_action", run: "scan lot-005" },
            {
                trigger: ".o_sublines .o_barcode_line:nth-child(3)",
                run: function () {
                    const sublines = helper.getSublines();
                    helper.assertLinesCount(1);
                    helper.assertSublinesCount(3);
                    helper.assertLineQty(sublines[0], "1");
                    helper.assertLineQty(sublines[1], "1");
                    helper.assertLineQty(sublines[2], "1");
                    helper.assertLinesTrackingNumbers(sublines, [
                        "lot-001",
                        "lot-002",
                        "lot-005",
                    ]);
                },
            },
        ],
    });

registry.category("web_tour.tours").add("test_delivery_using_buttons", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: function () {
                helper.assertLinesCount(3);
                helper.assertScanMessage("scan_product");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(false);
                helper.assertValidateEnabled(true);
                helper.assertLineQty(0, "0/2");
                helper.assertLineQty(1, "0/3");
                helper.assertLineQty(2, "0/4");
                helper.assertButtonIsVisible(0, "add_quantity", false);
                helper.assertButtonIsVisible(1, "add_quantity", false);
                helper.assertButtonIsVisible(2, "add_quantity", false);
                helper.assertButtonIsVisible(0, "add_remaining_quantity");
                helper.assertButtonIsVisible(1, "add_remaining_quantity");
                helper.assertButtonIsVisible(2, "add_remaining_quantity");
            },
        },

        {
            trigger: ".o_barcode_line:first-child .o_edit",
            run: "click",
        },
        {
            trigger: "button.o_digipad_increment",
            run: "click",
        },
        {
            trigger: ".o_save",
            run: "click",
        },
        {
            trigger: ".o_barcode_lines",
            run: function () {
                helper.assertButtonIsVisible(0, "remove_unit");
                helper.assertButtonIsVisible(0, "add_quantity", false);
                helper.assertButtonIsVisible(0, "add_remaining_quantity");
                helper.assertLineQty(0, "1/2");
                helper.assertLineIsHighlighted(0, true);
                helper.assertLineIsHighlighted(1, false);
                helper.assertLineIsHighlighted(2, false);
            },
        },
        {
            trigger: ".o_barcode_line:first-child .o_add_remaining_quantity",
            run: "click",
        },
        {
            trigger: ".o_barcode_line:first-child.o_selected.o_line_completed",
            run: function () {
                helper.assertLineQty(0, "2/2");
                helper.assertButtonIsVisible(0, "remove_unit");
                helper.assertButtonIsVisible(0, "add_quantity", false);
                helper.assertButtonIsVisible(0, "add_remaining_quantity", false);
                helper.assertLineQty(1, "0/3");
                helper.assertButtonIsVisible(1, "add_quantity", false);
                helper.assertButtonIsVisible(1, "add_remaining_quantity");
            },
        },
        {
            trigger: ".o_barcode_line:nth-child(2) .o_add_remaining_quantity",
            run: "click",
        },
        {
            trigger: ".o_barcode_line:nth-child(2).o_selected.o_line_completed",
            run: function () {
                helper.assertLineIsHighlighted(0, false);
                helper.assertLineIsHighlighted(1, true);
                helper.assertLineIsHighlighted(2, false);
                helper.assertLineQty(1, "3/3");
                helper.assertButtonIsVisible(1, "remove_unit");
                helper.assertButtonIsVisible(1, "add_quantity", false);
                helper.assertButtonIsVisible(1, "add_remaining_quantity", false);
                helper.assertLineQty(2, "0/4");
                helper.assertButtonIsVisible(2, "add_quantity", false);
                helper.assertButtonIsVisible(2, "add_remaining_quantity");
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan product3",
        },
        {
            trigger: '.o_barcode_line:last-child.o_selected .qty-done:contains("1")',
            run: function () {
                helper.assertLineQty(2, "1/4");
                helper.assertButtonIsVisible(2, "add_quantity");
                helper.assertButtonIsVisible(2, "add_remaining_quantity");
                helper.assertLineIsHighlighted(0, false);
                helper.assertLineIsHighlighted(1, false);
                helper.assertLineIsHighlighted(2, true);
            },
        },
        {
            trigger: ".o_barcode_line:last-child .o_edit",
            run: "click",
        },
        {
            trigger: "button.o_digipad_increment",
            run: "click",
        },
        {
            trigger: ".o_save",
            run: "click",
        },
        {
            trigger: ".o_barcode_lines",
            run: function () {
                helper.assertLineQty(0, "2/4");
                helper.assertButtonIsVisible(0, "add_quantity");
                helper.assertButtonIsVisible(0, "add_remaining_quantity");
            },
        },
        {
            trigger: ".o_barcode_line:first-child .o_add_remaining_quantity",
            run: "click",
        },
        {
            trigger: '.o_barcode_line:first-child .qty-done:contains("4")',
            run: function () {
                helper.assertLineQty(0, "4/4");
                helper.assertButtonIsVisible(0, "add_quantity", false);
                helper.assertButtonIsVisible(0, "add_remaining_quantity", false);
                helper.assertValidateIsHighlighted(true);
            },
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan product3",
        },
        {
            trigger: ".o_barcode_line:nth-child(2).o_selected",
            run: function () {
                helper.assertLinesCount(4);
                helper.assertLineIsHighlighted(0, false);
                helper.assertLineIsHighlighted(1, true);
                helper.assertLineIsHighlighted(2, false);
                helper.assertLineIsHighlighted(3, false);
                helper.assertLineQty(1, "1");
                helper.assertButtonIsVisible(1, "remove_unit");
                helper.assertButtonIsVisible(1, "add_quantity");
                helper.assertButtonIsVisible(1, "add_remaining_quantity", false);
                helper.assertButtonIsVisible(1, "delete_line");
            },
        },
        {
            trigger: ".o_barcode_line:nth-child(2) .o_add_quantity",
            run: "click",
        },
        {
            trigger: '.o_barcode_line:nth-child(2) .qty-done:contains("2")',
            run: function () {
                helper.assertLineIsHighlighted(0, false);
                helper.assertLineIsHighlighted(1, true);
                helper.assertLineIsHighlighted(2, false);
                helper.assertLineIsHighlighted(3, false);
                helper.assertLineQty(1, "2");
                helper.assertButtonIsVisible(1, "add_quantity");
            },
        },

        {
            trigger: ".o_validate_page",
            run: "click",
        },
        {
            trigger: ".o_notification_bar.bg-success",
        },
    ],
});

registry.category("web_tour.tours").add("test_remaining_decimal_accuracy", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: function () {
                helper.assertScanMessage("scan_product");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(false);
                helper.assertValidateEnabled(true);
                helper.assertLineQty(0, "0/4");
                helper.assertLineQty(1, "0/0.12");
                helper.assertLineQty(2, "0/4");
                helper.assertButtonIsVisible(0, "add_remaining_quantity");
                helper.assertButtonIsVisible(1, "add_remaining_quantity");
            },
        },

        {
            trigger: '.o_barcode_line[data-barcode="product1"] .o_edit',
            run: "click",
        },
        {
            trigger: "div[name=qty_done] input",
            run() {
                this.anchor.value = "2.2";
                this.anchor.dispatchEvent(new InputEvent("input", { bubbles: true }));
            },
        },
        {
            trigger: ".o_save",
            run: "click",
        },
        {
            trigger: ".o_barcode_lines",
            run: function () {
                helper.assertButtonIsVisible(0, "add_remaining_quantity");
                helper.assertLineQty(0, "2.2/4");
                const buttonAddQty = document.querySelector(
                    ".o_barcode_line:first-child .o_add_remaining_quantity",
                );
                helper.assert(
                    buttonAddQty.innerText,
                    "+1.8",
                    "Something wrong with the quantities",
                );
            },
        },
        {
            trigger:
                '.o_barcode_line:last-child .o_add_remaining_quantity:contains("0.12")',
            run: "click",
        },
        {
            trigger: ".o_barcode_lines",
            run: function () {
                helper.assertButtonIsVisible(1, "add_remaining_quantity", false);
                helper.assertLineQty(1, "0.12/0.12");
            },
        },

        {
            trigger: ".o_line_button.o_toggle_sublines",
            run: "click",
        },
        {
            trigger: ".o_sublines .o_barcode_line:first-child .fa-pencil",
            run: "click",
        },
        {
            trigger: "div[name=qty_done] input",
            run() {
                this.anchor.value = "2.345";
            },
        },
        {
            trigger: ".o_save",
            run: "click",
        },
        {
            trigger: ".o_sublines .o_barcode_line:first-child",
            run: function () {
                const buttonAddQty = document.querySelector(
                    ".o_sublines .o_barcode_line:first-child .o_add_remaining_quantity",
                );
                helper.assert(
                    buttonAddQty.innerText,
                    "+1.65",
                    "Something wrong with the quantities",
                );
            },
        },
    ],
});

registry.category("web_tour.tours").add("test_receipt_from_scratch_with_lots_1", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: "scan lot1",
        },

        {
            trigger:
                ".o_notification:has(.bg-danger):text(This product doesn't exist.)",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan productserial1",
        },

        {
            trigger: ".o_barcode_line",
            run: "scan lot1",
        },

        {
            trigger: '.o_line_lot_name:contains("lot1")',
            run: "scan LOC-01-00-00",
        },

        {
            trigger: ".o_scan_message.o_scan_validate",
            run: "scan productserial1",
        },
        {
            trigger: ".o_barcode_line.o_selected .btn.o_toggle_sublines .fa-angle-down",
            run: "click",
        },

        {
            trigger: ".o_barcode_line:nth-child(2)",
            run: "scan lot2",
        },

        {
            trigger: '.o_line_lot_name:contains("lot2")',
            run: "scan LOC-01-01-00",
        },

        { trigger: ".o_scan_message.o_scan_validate", run: "scan productserial1" },
        { trigger: ".o_scan_message.o_scan_serial", run: "scan lot3" },
        { trigger: ".o_scan_message.o_scan_product_or_dest", run: "scan WHSTOCK-2" },
        {
            trigger: ".o_scan_message.o_scan_validate",
            run: () => {
                helper.assertLinesCount(3);
                helper.assertLineDestinationLocation(0, "WH/Stock");
                helper.assertLineDestinationLocation(1, ".../Section 1");
                helper.assertLineDestinationLocation(2, "WH/Stock 2");
            },
        },
        ...stepUtils.validateBarcodeOperation(),
    ],
});

registry.category("web_tour.tours").add("test_receipt_from_scratch_with_lots_2", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: "scan productlot1",
        },

        {
            trigger: ".o_barcode_line .o_edit",
            run: "click",
        },

        {
            trigger: ".o_input[id=trace_id_0]",
            run: function () {
                helper.assert(document.querySelectorAll("#lot_name_0").length, 0);
            },
        },

        {
            trigger: ".o_save",
            run: "click",
        },

        {
            trigger: ".o_barcode_line",
            run: "scan lot1",
        },

        {
            trigger: ".o_line_lot_name:contains(lot1)",
            run: "click",
        },

        {
            trigger: ".o_barcode_line .o_edit",
            run: "click",
        },

        {
            trigger: '.o_input[id="lot_name_0"]',
            run: function () {
                helper.assert(document.querySelectorAll("#trace_id_0").length, 0);
            },
        },

        {
            trigger: ".o_save",
            run: "click",
        },

        {
            trigger: ".o_line_lot_name:contains(lot1)",
            run: "scan lot1",
        },

        {
            trigger: ".qty-done:contains(2)",
            run: "scan lot2",
        },
        {
            trigger: ".o_barcode_line.o_selected .btn.o_toggle_sublines .fa-angle-down",
            run: "click",
        },

        {
            trigger: ".o_barcode_line:nth-child(2)",
            run: "scan lot2",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan LOC-01-01-00",
        },
        ...stepUtils.validateBarcodeOperation(),
    ],
});

registry.category("web_tour.tours").add("test_receipt_from_scratch_with_lots_3", {
    steps: () => [
        { trigger: ".o_barcode_client_action", run: "scan product1" },
        {
            trigger: ".o_barcode_line",
            run: function () {
                helper.assertLinesCount(1);
                const line = helper.getLine({ barcode: "product1" });
                helper.assertLineIsHighlighted(line, true);
                helper.assertLineQty(line, "1");
            },
        },

        {
            trigger: ".o_barcode_line.o_selected .btn.o_edit",
            run: "click",
        },
        {
            trigger: ".o_discard",
            run: "click",
        },
        { trigger: ".o_barcode_client_action", run: "scan product1" },

        {
            trigger: '.o_barcode_line .qty-done:contains("2")',
            run: "scan productlot1",
        },

        {
            trigger: ".o_barcode_line:nth-child(2)",
            run: function () {
                helper.assertLinesCount(2);
                const line1 = helper.getLine({ barcode: "product1" });
                const line2 = helper.getLine({ barcode: "productlot1" });
                helper.assertLineIsHighlighted(line1, false);
                helper.assertLineQty(line1, "2");
                helper.assertLineIsHighlighted(line2, true);
                helper.assertLineQty(line2, "0");
            },
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan lot1",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan lot1",
        },

        {
            trigger: ".o_selected .qty-done:contains(2)",
            run: function () {
                helper.assertLinesCount(2);
                const line1 = helper.getLine({ barcode: "product1" });
                const line2 = helper.getLine({ barcode: "productlot1" });
                helper.assertLineIsHighlighted(line1, false);
                helper.assertLineQty(line1, "2");
                helper.assertLineIsHighlighted(line2, true);
                helper.assertLineQty(line2, "2");
            },
        },
        ...stepUtils.validateBarcodeOperation(),
    ],
});

registry.category("web_tour.tours").add("test_receipt_from_scratch_with_lots_4", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: "scan productserial1",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan productserial1",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan productserial1",
        },
        {
            trigger: '.qty-done:contains("3")',
        },
        {
            trigger: ".o_add_line",
            run: "click",
        },
        {
            trigger: '.o_field_widget[name="product_id"]',
            run: "click",
        },
        ...stepUtils.discardBarcodeForm(),
    ],
});

registry.category("web_tour.tours").add("test_delivery_from_scratch_with_lots_1", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: "scan lot1",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan lot1",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan lot2",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan lot2",
        },
        {
            trigger: ".o_barcode_line.o_selected .btn.o_toggle_sublines .fa-angle-down",
            run: "click",
        },
        {
            trigger: ".o_barcode_line:nth-child(2)",
        },
        {
            trigger: ".o_add_line",
            run: "click",
        },

        {
            trigger: '.o_field_widget[name="product_id"]',
            run: "click",
        },
        ...stepUtils.discardBarcodeForm(),
    ],
});

registry
    .category("web_tour.tours")
    .add("test_delivery_from_scratch_with_incompatible_lot", {
        steps: () => [
            { trigger: ".o_barcode_client_action", run: "scan 0000000001" },
            {
                trigger: ".o_barcode_line:first-child .o_edit",
                run: "click",
            },
            ...stepUtils.discardBarcodeForm(),
        ],
    });

registry
    .category("web_tour.tours")
    .add("test_delivery_from_scratch_with_common_lots_name", {
        steps: () => [
            {
                trigger: ".o_barcode_client_action",
                run: "scan product1",
            },
            {
                trigger: ".o_barcode_line",
                run: "scan LOT01",
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan LOT01",
            },
            {
                trigger:
                    '.o_barcode_line[data-barcode="product1"] .qty-done:contains("2")',
                run: "scan product2",
            },
            {
                trigger: '.o_barcode_line:contains("product2")',
                run: "scan LOT01",
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan LOT01",
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan LOT01",
            },
            {
                trigger: '.qty-done:contains("3")',
                run: "scan SUPERSN",
            },
            {
                trigger: '.o_barcode_line:contains("productserial1")',
                run: "click",
            },
            {
                trigger: ".o_barcode_line:first-child .o_edit",
                run: "click",
            },
            ...stepUtils.discardBarcodeForm(),
        ],
    });

registry.category("web_tour.tours").add("test_receipt_with_sn_1", {
    steps: () => [
        { trigger: ".o_barcode_client_action", run: "scan sn1" },
        ...stepUtils.validateBarcodeOperation(),
    ],
});

registry.category("web_tour.tours").add("test_delivery_reserved_lots_1", {
    steps: () => [
        { trigger: ".o_barcode_client_action", run: "scan productlot1" },
        { trigger: ".o_barcode_line.o_selected .o_toggle_sublines", run: "click" },
        {
            trigger: ".o_sublines",
            run: function () {
                helper.assertLinesCount(1);
                helper.assertSublinesCount(2);
                const sublines = helper.getSublines();
                helper.assertLineQty(sublines[0], "0/2");
                helper.assert(
                    sublines[0].querySelector("button.o_add_remaining_quantity")
                        .innerText,
                    "+2",
                );
                helper.assertLineQty(sublines[1], "0/3");
                helper.assert(
                    sublines[1].querySelector("button.o_add_remaining_quantity")
                        .innerText,
                    "+3",
                );
            },
        },
        { trigger: ".o_barcode_client_action", run: "scan lot1" },
        { trigger: ".o_barcode_line.o_selected", run: "scan lot2" },
        { trigger: ".o_barcode_line.o_selected", run: "scan lot3" },
        {
            trigger: ".o_sublines .o_barcode_line:nth-child(3)",
            run: function () {
                helper.assertLinesCount(1);
                helper.assertSublinesCount(3);
                const sublines = helper.getSublines();
                helper.assertLineQty(sublines[0], "1/2");
                helper.assertLineQty(sublines[1], "1/3");
                helper.assert(
                    sublines[1].querySelector("button.o_add_remaining_quantity")
                        .innerText,
                    "+2",
                );
                helper.assertLineQty(sublines[2], "1");
                helper.assert(
                    sublines[2].querySelector("button.o_add_remaining_quantity")
                        .innerText,
                    "+1",
                );
            },
        },
        { trigger: ".o_barcode_client_action", run: "scan lot1" },
        {
            trigger: ".o_sublines .o_barcode_line.o_selected.o_line_completed",
            run: function () {
                helper.assertLinesCount(1);
                helper.assertSublinesCount(3);
                const sublines = helper.getSublines();
                helper.assertLineQty(sublines[0], "2/2");
                helper.assert(
                    sublines[0].querySelector("button.o_add_remaining_quantity")
                        .innerText,
                    "+1",
                );
                helper.assertLineQty(sublines[1], "1/3");
                helper.assert(
                    sublines[1].querySelector("button.o_add_remaining_quantity")
                        .innerText,
                    "+1",
                );
                helper.assertLineQty(sublines[2], "1");
                helper.assert(
                    sublines[2].querySelector("button.o_add_remaining_quantity")
                        .innerText,
                    "+1",
                );
            },
        },
        {
            trigger: ".o_barcode_line.o_selected:not(.o_line_completed)",
            run: "scan lot2",
        },
        {
            trigger: ".o_barcode_location_group > .o_barcode_line.o_line_completed",
            run: function () {
                helper.assertLinesCount(1);
                helper.assertSublinesCount(3);
                const sublines = helper.getSublines();
                helper.assertLineQty(sublines[0], "2/2");
                helper.assertButtonIsVisible(sublines[0], "add_quantity", false);
                helper.assertButtonIsVisible(
                    sublines[0],
                    "o_add_remaining_quantity",
                    false,
                );
                helper.assertLineQty(sublines[1], "2/3");
                helper.assertButtonIsVisible(sublines[1], "add_quantity", false);
                helper.assertButtonIsVisible(
                    sublines[1],
                    "o_add_remaining_quantity",
                    false,
                );
                helper.assertLineQty(sublines[2], "1");
                helper.assertButtonIsVisible(sublines[2], "add_quantity", false);
                helper.assertButtonIsVisible(
                    sublines[2],
                    "o_add_remaining_quantity",
                    false,
                );
            },
        },
        { trigger: ".o_add_line", run: "click" },
        { trigger: '.o_field_widget[name="product_id"]' },
        ...stepUtils.discardBarcodeForm(),
    ],
});

registry
    .category("web_tour.tours")
    .add("test_delivery_different_products_with_same_lot_name", {
        steps: () => [
            {
                trigger: ".o_barcode_client_action",
                run: "scan productlot1",
            },

            {
                trigger: ".o_barcode_client_action",
                run: "scan lot1",
            },

            {
                trigger: ".o_barcode_client_action",
                run: "scan lot1",
            },

            {
                trigger:
                    ".o_barcode_line:has(.o_product_label:contains(productlot1)) .qty-done:contains(2)",
            },

            {
                trigger: ".o_barcode_client_action",
                run: "scan productlot2",
            },

            {
                trigger: ".o_barcode_client_action",
                run: "scan lot1",
            },

            {
                trigger: ".o_barcode_client_action",
                run: "scan lot1",
            },

            {
                trigger:
                    ".o_barcode_line:has(.o_product_label:contains(productlot2)) .qty-done:contains(2)",
            },
            {
                trigger: ".o_add_line",
                run: "click",
            },

            {
                trigger: '.o_field_widget[name="product_id"]',
                run: "click",
            },
            ...stepUtils.discardBarcodeForm(),
        ],
    });

registry.category("web_tour.tours").add("test_delivery_reserved_with_sn_1", {
    steps: () => [
        { trigger: ".o_barcode_client_action", run: "scan productserial1" },
        { trigger: ".o_barcode_line.o_selected", run: "scan sn3" },
        { trigger: ".o_barcode_client_action", run: "scan sn3" },
        {
            trigger:
                ".o_notification:has(.bg-danger):text(The scanned serial number sn3 is already used.)",
        },

        { trigger: ".o_barcode_client_action", run: "scan sn1" },
        { trigger: ".o_barcode_client_action", run: "scan sn4" },
        { trigger: ".o_barcode_client_action", run: "scan sn2" },
        { trigger: '.o_barcode_line .qty-done:contains("4")' },
        { trigger: ".o_add_line", run: "click" },
        {
            trigger: '.o_field_widget[name="product_id"]',
            run: "click",
        },
        ...stepUtils.discardBarcodeForm(),
    ],
});

registry.category("web_tour.tours").add("test_receipt_reserved_lots_multiloc_1", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: "scan productlot1",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan lot1",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan lot1",
        },

        {
            trigger: '.o_barcode_line .qty-done:contains("2")',
            run: "scan LOC-01-02-00",
        },

        {
            trigger:
                '.o_barcode_line .o_line_destination_location:contains("Section 2")',
            run: "scan productlot1",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan lot2",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan lot2",
        },

        {
            trigger:
                '.o_barcode_line.o_selected:contains("lot2") .qty-done:contains("2")',
            run: "scan LOC-01-01-00",
        },
        ...stepUtils.validateBarcodeOperation(),
    ],
});

registry.category("web_tour.tours").add("test_receipt_duplicate_serial_number", {
    steps: () => [
        { trigger: '.o_stock_barcode_main_menu:contains("Scan or tap")', run: "click" },
        { trigger: ".o_stock_barcode_main_menu", run: "scan WHIN" },

        {
            trigger: ".o_barcode_client_action",
            run: "scan productserial1",
        },

        {
            trigger: ".o_barcode_line",
            run: "scan sn1",
        },

        {
            trigger: '.o_barcode_line .o_line_lot_name:contains("sn1")',
            run: "scan LOC-01-01-00",
        },

        {
            trigger:
                '.o_barcode_line .o_line_destination_location:contains("../Section 1")',
            run: "scan productserial1",
        },

        {
            trigger: ".o_barcode_line:nth-child(2)",
            run: "scan sn1",
        },

        {
            trigger:
                ".o_notification:has(.bg-danger):text(The scanned serial number sn1 is already used.)",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan sn2",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan LOC-01-02-00",
        },
        {
            trigger:
                '.o_barcode_line:nth-child(2) .o_line_destination_location:contains("../Section 2")',
        },
        ...stepUtils.validateBarcodeOperation(),
        {
            trigger:
                ".o_notification:has(.bg-success):text(The transfer has been validated)",
        },
    ],
});

registry.category("web_tour.tours").add("test_delivery_duplicate_serial_number", {
    steps: () => [
        { trigger: ".o_stock_barcode_main_menu", run: "scan WHOUT" },
        { trigger: ".o_scan_message.o_scan_src", run: "scan LOC-01-01-00" },

        {
            trigger: ".o_scan_message.o_scan_product",
            run: "scan productserial1",
        },

        {
            trigger: '.o_barcode_line:contains("productserial1")',
            run: "scan sn1",
        },
        {
            trigger: '.o_barcode_line .o_line_lot_name:contains("sn1")',
            run: "scan LOC-01-02-00",
        },

        {
            trigger: ".o_scan_message.o_scan_validate",
            run: "scan productserial1",
        },

        {
            trigger: '.o_barcode_line:contains("productserial1")',
            run: "scan sn1",
        },

        {
            trigger:
                ".o_notification:has(.bg-danger):text(The scanned serial number sn1 is already used.)",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan sn2",
        },
        {
            trigger: ".o_barcode_line.o_selected:nth-child(2)",
            run: "click",
        },
        ...stepUtils.validateBarcodeOperation(),
        {
            trigger:
                ".o_notification:has(.bg-success):text(The transfer has been validated)",
        },
    ],
});

registry.category("web_tour.tours").add("test_bypass_source_scan", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: function () {
                helper.assertLinesCount(3);
                helper.assertScanMessage("scan_product");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(false);
                helper.assertValidateEnabled(true);
            },
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan serial1",
        },

        {
            trigger: '.o_barcode_line[data-barcode="productserial1"] .o_edit',
            run: "click",
        },
        {
            trigger: '.o_field_widget[name="qty_done"]',
        },
        {
            trigger: ".o_field_many2one[name=trace_id] input",
            tooltipPosition: "bottom",
            run: "clear",
        },

        {
            trigger: ".o_field_widget[name=qty_done] input",
            run: "edit 0",
        },

        {
            trigger: ".o_save",
            run: "click",
        },

        {
            trigger: ".o_barcode_line",
            run: "scan lot1",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan lot1",
        },

        { trigger: ".o_scan_message.o_scan_product", run: "scan SUSPACK" },
        {
            trigger:
                ".o_notification:has(.bg-danger):text(You are expected to scan one or more products or a package available at the picking location)",
        },
        {
            trigger: "button.o_notification_close",
            run: "click",
        },
        {
            trigger: ".o_scan_message.o_scan_product",
            run: "scan THEPACK",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan productserial1",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan serial1",
        },
        ...stepUtils.validateBarcodeOperation(),
    ],
});

registry
    .category("web_tour.tours")
    .add("test_picking_type_mandatory_scan_settings_pick_int_1", {
        steps: () => [
            {
                trigger: ".o_barcode_client_action",
                run: function () {
                    helper.assertLinesCount(2);
                    helper.assertScanMessage("scan_product");
                    helper.assertValidateVisible(true);
                    helper.assertValidateIsHighlighted(false);
                    helper.assertValidateEnabled(false);
                    const [lineProductNoBarcode, lineProduct1] = helper.getLines();
                    helper.assert(
                        lineProduct1.querySelector(".btn.o_edit").disabled,
                        true,
                        "Edit button should be disabled until the product was scanned",
                    );
                    helper.assertButtonIsVisible(lineProduct1, "add_quantity", false);
                    helper.assert(
                        lineProductNoBarcode.querySelector(".btn.o_edit").disabled,
                        false,
                        "Edit button is always enabled if the product has no barcode (it can't be scanned')",
                    );
                    helper.assertButtonIsVisible(
                        lineProductNoBarcode,
                        "add_remaining_quantity",
                    );
                    helper.assertLineLocations(
                        lineProductNoBarcode,
                        "WH/Stock/Section 1",
                        "WH/Stock",
                    );
                    helper.assertLineLocations(
                        lineProduct1,
                        "WH/Stock/Section 1",
                        "WH/Stock",
                    );
                },
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan LOC-01-01-00",
            },
            {
                trigger:
                    ".o_notification:has(.bg-danger):text(Not the expected scan. You must scan a product)",
            },

            {
                trigger: ".o_barcode_client_action",
                run: "scan product1",
            },
            {
                trigger: ".o_barcode_line.o_selected",
                run: function () {
                    const lineProduct1 = helper.getLine({ barcode: "product1" });
                    helper.assert(
                        lineProduct1.querySelector(".btn.o_edit").disabled,
                        false,
                        "product1 was scanned, the edit button should now be enabled",
                    );
                    helper.assertButtonIsVisible(lineProduct1, "add_quantity");
                    helper.assertValidateIsHighlighted(false);
                    helper.assertValidateEnabled(true);
                },
            },
            {
                trigger: ".o_barcode_line.o_selected .btn.o_add_remaining_quantity",
                run: "click",
            },
            {
                trigger: ".o_barcode_line .btn.o_add_remaining_quantity",
                run: "click",
            },
            {
                trigger: 'div[name="barcode_messages"] .fa-square-check',
            },
            {
                trigger: ".btn.o_validate_page.btn-primary",
                run: "click",
            },
            { trigger: ".o_notification_bar.bg-success" },
        ],
    });

registry
    .category("web_tour.tours")
    .add("test_picking_type_mandatory_scan_settings_pick_int_2", {
        steps: () => [
            {
                trigger: ".o_barcode_client_action",
                run: function () {
                    helper.assertLinesCount(2);
                    helper.assertScanMessage("scan_src");
                    helper.assertValidateVisible(true);
                    helper.assertValidateIsHighlighted(false);
                    helper.assertValidateEnabled(false);
                    const [lineProductNoBarcode, lineProduct1] = helper.getLines();
                    helper.assert(
                        lineProduct1.querySelector(".btn.o_edit").disabled,
                        true,
                        "Edit button should be disabled until the product was scanned",
                    );
                    helper.assertButtonIsVisible(lineProduct1, "add_quantity", false);
                    helper.assert(
                        lineProductNoBarcode.querySelector(".btn.o_edit").disabled,
                        true,
                        "All lines' buttons are disabled until a source location was scanned",
                    );
                    helper.assert(
                        lineProductNoBarcode.querySelector(
                            ".btn.o_add_remaining_quantity",
                        ).disabled,
                        true,
                        "All lines' buttons are disabled until a source location was scanned",
                    );
                },
            },
            { trigger: ".o_barcode_client_action", run: "scan product1" },
            {
                trigger:
                    ".o_notification:has(.bg-danger):text(Mandatory Source Location. You are supposed to scan WH/Stock or another source location)",
            },
            {
                trigger: ".btn-close.o_notification_close",
                run: "click",
            },

            {
                trigger: ".o_barcode_client_action",
                run: "scan LOC-01-00-00",
            },
            {
                trigger: ".o_scan_message.o_scan_product",
                run: function () {
                    const [lineProductNoBarcode, lineProduct1] = helper.getLines();
                    helper.assert(
                        lineProduct1.querySelector(".btn.o_edit").disabled,
                        true,
                        "Edit button should be disabled until the product was scanned",
                    );
                    helper.assert(
                        lineProduct1.querySelector(".btn.o_add_remaining_quantity")
                            .disabled,
                        true,
                        "Button to automatically add the quantity is disabled if the product scan is mandatory",
                    );
                    helper.assert(
                        lineProductNoBarcode.querySelector(".btn.o_edit").disabled,
                        true,
                        "Since the source of this line was not scanned, its buttons should be disabled",
                    );
                    helper.assert(
                        lineProductNoBarcode.querySelector(
                            ".btn.o_add_remaining_quantity",
                        ).disabled,
                        true,
                        "Since the source of this line was not scanned, its buttons should be disabled",
                    );
                },
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan LOC-01-01-00",
            },
            {
                trigger:
                    '.o_barcode_location_line[data-location="WH/Stock/Section 1"].text-bg-400',
                run: function () {
                    const [lineProductNoBarcode, lineProduct1] = helper.getLines();
                    helper.assert(
                        lineProduct1.querySelector(".btn.o_edit").disabled,
                        true,
                        "Edit button should be disabled until the product was scanned",
                    );
                    helper.assert(
                        lineProduct1.querySelector(".btn.o_add_remaining_quantity")
                            .disabled,
                        true,
                        "Button to automatically add the quantity is disabled if the product scan is mandatory",
                    );
                    helper.assert(
                        lineProductNoBarcode.querySelector(".btn.o_edit").disabled,
                        false,
                        "Since the source of this line was scanned and it has no barcode, its buttons should be enabled",
                    );
                    helper.assert(
                        lineProductNoBarcode.querySelector(
                            ".btn.o_add_remaining_quantity",
                        ).disabled,
                        false,
                        "Since the source of this line was scanned and it has no barcode, its buttons should be enabled",
                    );
                },
            },

            {
                trigger: ".o_barcode_client_action",
                run: "scan product1",
            },
            {
                trigger: ".o_barcode_line.o_selected",
                run: function () {
                    const lineProduct1 = helper.getLine({ barcode: "product1" });
                    helper.assert(
                        lineProduct1.querySelector(".btn.o_edit").disabled,
                        false,
                        "product1 was scanned, the edit button should now be enabled",
                    );
                    helper.assertButtonIsVisible(lineProduct1, "add_quantity");
                    helper.assertValidateIsHighlighted(false);
                    helper.assertValidateEnabled(true);
                },
            },
            { trigger: ".o_barcode_client_action", run: "scan product2" },
            {
                trigger:
                    ".o_notification:has(.bg-danger):text(Mandatory Destination Location. Please scan destination location for product1 before scanning other product)",
            },
            {
                trigger: ".btn-close.o_notification_close",
                run: "click",
            },

            {
                trigger: ".o_barcode_line.o_selected .btn.o_add_remaining_quantity",
                run: "click",
            },
            {
                trigger: ".o_barcode_line.o_selected.o_line_completed",
                run: "scan LOC-01-00-00",
            },
            { trigger: ".o_barcode_client_action", run: "scan product1" },
            {
                trigger:
                    ".o_notification:has(.bg-danger):text(Mandatory Source Location. You are supposed to scan WH/Stock or another source location)",
            },
            {
                trigger: ".btn-close.o_notification_close",
                run: "click",
            },

            {
                trigger: ".o_barcode_client_action",
                run: "scan LOC-01-01-00",
            },
            {
                trigger: ".o_scan_message.o_scan_product",
            },
            {
                trigger: ".o_barcode_line .btn.o_add_remaining_quantity",
                run: "click",
            },
            {
                trigger: ".o_barcode_line.o_selected.o_line_completed",
                run: "scan OBTVALI",
            },
            {
                trigger:
                    ".o_notification:has(.o_notification_bar.bg-danger) .o_notification_close.btn-close",
                run: "click",
            },

            {
                trigger: 'div[name="barcode_messages"] .fa-right-to-bracket',
                run: "scan LOC-01-00-00",
            },
            {
                trigger: 'div[name="barcode_messages"] .fa-square-check',
            },
            {
                trigger: ".btn.o_validate_page.btn-primary",
                run: "click",
            },
            { trigger: ".o_notification_bar.bg-success" },
        ],
    });

registry
    .category("web_tour.tours")
    .add("test_receipt_scan_package_and_location_after_group_of_product", {
        steps: () => [
            {
                trigger: ".o_barcode_client_action",
                run: function () {
                    helper.assertLinesCount(3);
                    helper.assertLineProduct(0, "Barcodeless Product");
                    helper.assertLineProduct(1, "product1");
                    helper.assertLineProduct(2, "productlot1");
                },
            },
            { trigger: ".o_barcode_line", run: "scan product1" },
            { trigger: ".o_barcode_line.o_selected", run: "scan product1" },
            {
                trigger: ".o_barcode_line.o_selected .qty-done:contains(2)",
            },
            {
                trigger:
                    ".o_barcode_line:not([data-barcode]) .o_line_button.o_add_remaining_quantity",
                run: "click",
            },
            {
                trigger: ".o_barcode_line.o_selected.o_line_completed",
                run: "scan productlot1",
            },
            {
                trigger: ".o_barcode_line[data-barcode='productlot1'].o_selected",
                run: "scan lot-01",
            },
            { trigger: ".o_barcode_line", run: "scan lot-01" },
            { trigger: ".o_barcode_line", run: "scan lot-02" },

            {
                trigger: ".o_barcode_line.o_selected .o_toggle_sublines",
                run: "scan LOC-01-01-00",
            },
            {
                trigger: ".o_barcode_line:nth-child(5)",
                run: function () {
                    helper.assertLinesCount(5);

                    helper.assertLineProduct(0, "Barcodeless Product");
                    helper.assertLineQty(0, "4/4");
                    helper.assertLineDestinationLocation(0, ".../Section 1");

                    helper.assertLineProduct(1, "product1");
                    helper.assertLineQty(1, "2/2");
                    helper.assertLineDestinationLocation(1, ".../Section 1");

                    helper.assertLineProduct(2, "product1");
                    helper.assertLineQty(2, "0/2");
                    helper.assertLineDestinationLocation(2, "WH/Stock");

                    helper.assertLineProduct(3, "productlot1");
                    helper.assertLineQty(3, "3/3");
                    helper.assertLineDestinationLocation(3, ".../Section 1");

                    helper.assertLineProduct(4, "productlot1");
                    helper.assertLineQty(4, "0/3");
                    helper.assertLineDestinationLocation(4, "WH/Stock");
                },
            },

            { trigger: ".o_barcode_client_action", run: "scan productlot1" },
            { trigger: ".o_scan_message.o_scan_lot", run: "scan lot-02" },
            {
                trigger:
                    ".o_barcode_line.o_selected .o_line_lot_name:contains('lot-02')",
                run: "scan LOC-01-02-00",
            },

            {
                trigger: ".o_scan_message.o_scan_product",
                run: function () {
                    helper.assertLinesCount(6);

                    helper.assertLineProduct(0, "Barcodeless Product");
                    helper.assertLineQty(0, "4/4");
                    helper.assertLineDestinationLocation(0, ".../Section 1");

                    helper.assertLineProduct(1, "product1");
                    helper.assertLineQty(1, "2/2");
                    helper.assertLineDestinationLocation(1, ".../Section 1");

                    helper.assertLineProduct(2, "product1");
                    helper.assertLineQty(2, "0/2");
                    helper.assertLineDestinationLocation(2, "WH/Stock");

                    helper.assertLineProduct(3, "productlot1");
                    helper.assertLineQty(3, "3/3");
                    helper.assertLineDestinationLocation(3, ".../Section 1");

                    helper.assertLineProduct(4, "productlot1");
                    helper.assertLineQty(4, "1/1");
                    helper.assertLineDestinationLocation(4, ".../Section 2");

                    helper.assertLineProduct(5, "productlot1");
                    helper.assertLineQty(5, "0/2");
                    helper.assertLineDestinationLocation(5, "WH/Stock");
                },
            },

            { trigger: ".o_barcode_client_action", run: "scan product1" },
            { trigger: ".o_barcode_line.o_selected", run: "scan product1" },
            {
                trigger: ".o_barcode_line.o_selected.o_line_completed",
                run: "scan productlot1",
            },
            {
                trigger: ".o_barcode_line.o_selected:not(.o_line_completed)",
                run: "scan lot-03",
            },
            {
                trigger: ".o_barcode_line.o_selected:not(.o_line_completed)",
                run: "scan lot-03",
            },
            {
                trigger: ".o_barcode_line.o_selected.o_line_completed",
                run: "scan pack-128",
            },
            { trigger: ".o_barcode_line [name='package']", run: "scan shelf3" },
            {
                trigger: ".o_scan_message.o_scan_validate",
                run: function () {
                    helper.assertLinesCount(6);

                    helper.assertLineProduct(0, "Barcodeless Product");
                    helper.assertLineQty(0, "4/4");
                    helper.assertLineDestinationLocation(0, ".../Section 1");

                    helper.assertLineProduct(1, "product1");
                    helper.assertLineQty(1, "2/2");
                    helper.assertLineDestinationLocation(1, ".../Section 1");

                    let line = helper.getLine({ index: 2 });
                    helper.assertLineProduct(line, "product1");
                    helper.assertLineQty(line, "2/2");
                    helper.assertLineDestinationLocation(line, ".../Section 3");
                    helper.assert(
                        line.querySelector('[name="package"]').innerText,
                        "pack-128",
                    );

                    helper.assertLineProduct(3, "productlot1");
                    helper.assertLineQty(3, "3/3");
                    helper.assertLineTrackingNumber(3, false);
                    helper.assertLineDestinationLocation(3, ".../Section 1");

                    helper.assertLineProduct(4, "productlot1");
                    helper.assertLineQty(4, "1/1");
                    helper.assertLineTrackingNumber(4, "lot-02");
                    helper.assertLineDestinationLocation(4, ".../Section 2");

                    line = helper.getLine({ index: 5 });
                    helper.assertLineProduct(5, "productlot1");
                    helper.assertLineQty(5, "2/2");
                    helper.assertLineTrackingNumber(5, "lot-03");
                    helper.assertLineDestinationLocation(5, ".../Section 3");
                    helper.assert(
                        line.querySelector('[name="package"]').innerText,
                        "pack-128",
                    );
                },
            },
            ...stepUtils.validateBarcodeOperation(),
        ],
    });

registry
    .category("web_tour.tours")
    .add("test_receipt_assign_sibling_reservation_no_empty_line", {
        steps: () => [
            {
                trigger: ".o_barcode_client_action",
                run: function () {
                    helper.assertLinesCount(1);
                    helper.assertLineProduct(0, "productlot1");
                },
            },
            { trigger: ".o_barcode_line", run: "scan productlot1" },
            {
                trigger: ".o_barcode_line[data-barcode='productlot1']",
                run: "scan lot-01",
            },
            {
                trigger: ".o_barcode_line[data-barcode='productlot1']",
                run: "scan lot-02",
            },

            { trigger: "button.o_line_button.o_toggle_sublines", run: "click" },
            {
                trigger:
                    ".o_sublines > .o_barcode_line[data-barcode='productlot1']:first-child",
                run: "click",
            },

            { trigger: ".o_barcode_line.o_selected", run: "scan LOC-01-01-00" },
            {
                trigger:
                    ".o_barcode_location_group>.o_barcode_line .o_line_destination_location:contains('Section 1')",
                run: function () {
                    helper.assertLinesCount(1);
                    helper.assertLineProduct(0, "productlot1");
                    helper.assertLineQty(0, "2/2");
                    helper.assertLineDestinationLocation(0, ".../Section 1");
                },
            },
            ...stepUtils.validateBarcodeOperation(),
        ],
    });

registry
    .category("web_tour.tours")
    .add("test_picking_type_mandatory_scan_complete_flux_receipt", {
        steps: () => [
            {
                trigger: ".o_barcode_client_action",
                run: function () {
                    helper.assertLinesCount(5);
                    helper.assertScanMessage("scan_product");
                    helper.assertValidateVisible(true);
                    helper.assertValidateIsHighlighted(false);
                    helper.assertValidateEnabled(false);
                },
            },
            { trigger: ".o_barcode_client_action", run: "scan product1" },
            { trigger: ".o_barcode_client_action", run: "scan product1" },
            {
                trigger: ".o_barcode_line.o_selected.o_line_completed",
                run: function () {
                    helper.assertScanMessage("scan_product_or_dest");
                    helper.assertValidateIsHighlighted(false);
                    helper.assertValidateEnabled(true);
                },
            },
            {
                trigger:
                    '.o_barcode_line[data-barcode="product2"] .btn.o_add_remaining_quantity',
                run: "click",
            },
            {
                trigger: '.o_barcode_line[data-barcode="product2"].o_line_completed',
            },
            {
                trigger:
                    ".o_barcode_line:not([data-barcode]) .btn.o_add_remaining_quantity",
                run: "click",
            },
            {
                trigger: ".o_barcode_line:not([data-barcode]).o_line_completed",
                run: "scan WHINPUT",
            },
            {
                trigger: ".o_scan_message.o_scan_product",
                run: "scan productlot1",
            },
            {
                trigger: '.o_barcode_line[data-barcode="productlot1"].o_selected',
                run: "scan lot-001",
            },
            { trigger: ".o_barcode_line", run: "scan lot-001" },
            { trigger: ".o_barcode_line", run: "scan lot-002" },
            { trigger: ".o_barcode_line", run: "scan lot-002" },
            { trigger: ".o_barcode_line", run: "scan lot-003" },
            { trigger: ".o_barcode_line", run: "scan lot-003" },
            {
                trigger:
                    '.o_barcode_line[data-barcode="productlot1"].o_selected.o_line_completed',
                run: function () {
                    helper.assertScanMessage("scan_product_or_dest");
                },
            },
            {
                trigger: ".o_scan_message.o_scan_product_or_dest",
                run: "scan productserial1",
            },
            {
                trigger: '.o_barcode_line[data-barcode="productserial1"].o_selected',
                run: "scan sn-001",
            },
            { trigger: ".o_barcode_line", run: "scan sn-002" },
            { trigger: ".o_barcode_line", run: "scan sn-003" },
            {
                trigger: 'div[name="barcode_messages"] .o_scan_product_or_dest',
                run: "scan WHINPUT",
            },
            {
                trigger: 'div[name="barcode_messages"] .o_scan_validate',
            },
            {
                trigger: ".o_validate_page.btn-primary",
                run: "click",
            },
            {
                trigger: ".o_notification_bar.bg-success",
            },
        ],
    });

registry
    .category("web_tour.tours")
    .add("test_picking_type_mandatory_scan_complete_flux_internal", {
        steps: () => [
            {
                trigger: ".o_barcode_client_action",
                run: function () {
                    helper.assertLinesCount(5);
                    helper.assertScanMessage("scan_product");
                    helper.assertValidateVisible(true);
                    helper.assertValidateIsHighlighted(false);
                    helper.assertValidateEnabled(false);
                },
            },
            { trigger: ".o_barcode_client_action", run: "scan product1" },
            { trigger: ".o_barcode_line.o_selected", run: "scan product2" },
            {
                trigger:
                    ".o_notification:has(.bg-danger):text(Mandatory Destination Location. Please scan destination location for product1 before scanning other product)",
            },
            {
                trigger: ".btn-close.o_notification_close",
                run: "click",
            },

            {
                trigger: ".o_barcode_line.o_selected",
                run: "scan LOC-01-01-00",
            },
            {
                trigger:
                    '.o_barcode_line.o_line_completed .o_line_destination_location .fw-bold:contains("Section 1")',
            },
            {
                trigger: ".o_barcode_client_action",
                run: function () {
                    helper.assertLinesCount(6);
                    helper.assertScanMessage("scan_product");
                },
            },

            {
                trigger: ".o_scan_message.o_scan_product",
                run: "scan product1",
            },
            {
                trigger: ".o_barcode_line.o_selected",
                run: "scan shelf3",
            },

            {
                trigger: ".o_scan_message.o_scan_product",
                run: "scan product2",
            },
            {
                trigger: ".o_barcode_line.o_selected",
                run: "scan LOC-01-02-00",
            },

            {
                trigger: ".o_scan_message.o_scan_product",
            },
            {
                trigger:
                    ".o_barcode_line:not([data-barcode]) .btn.o_add_remaining_quantity",
                run: "click",
            },
            {
                trigger: ".o_barcode_line.o_selected.o_line_completed",
                run: "scan LOC-01-01-00",
            },

            {
                trigger: ".o_scan_message.o_scan_product",
                run: "scan productlot1",
            },
            {
                trigger: '.o_barcode_line[data-barcode="productlot1"].o_selected',
                run: "scan lot-001",
            },
            {
                trigger:
                    ".o_barcode_line.o_selected .btn.o_toggle_sublines .fa-angle-down",
                run: "click",
            },
            {
                trigger: ".o_sublines .o_barcode_line.o_selected",
                run: "scan lot-001",
            },
            {
                trigger: ".o_sublines .o_barcode_line.o_selected.o_line_completed",
                run: "scan lot-002",
            },
            {
                trigger:
                    ".o_sublines .o_barcode_line.o_selected:not(.o_line_completed)",
                run: "scan lot-002",
            },
            {
                trigger: ".o_sublines .o_barcode_line.o_selected.o_line_completed",
                run: "scan shelf3",
            },

            {
                trigger: ".o_scan_message.o_scan_product",
                run: "scan lot-003",
            },
            {
                trigger: '.o_barcode_line[data-barcode="productlot1"].o_selected',
                run: "scan lot-003",
            },
            {
                trigger: '.o_barcode_line[data-barcode="productlot1"].o_selected',
                run: "scan shelf4",
            },

            {
                trigger: ".o_scan_message.o_scan_product",
                run: "scan productserial1",
            },
            {
                trigger: '.o_barcode_line[data-barcode="productserial1"].o_selected',
                run: "scan sn-001",
            },
            {
                trigger: '.o_barcode_line[data-barcode="productserial1"].o_selected',
                run: "scan sn-002",
            },
            {
                trigger: '.o_barcode_line[data-barcode="productserial1"].o_selected',
                run: "scan sn-003",
            },
            {
                trigger:
                    '.o_barcode_line[data-barcode="productserial1"].o_selected.o_line_completed',
                run: "scan shelf4",
            },
            {
                trigger: 'div[name="barcode_messages"] .fa-square-check',
            },
            {
                trigger: ".o_validate_page.btn-primary",
                run: "click",
            },
            {
                trigger: ".o_notification_bar.bg-success",
            },
        ],
    });

registry
    .category("web_tour.tours")
    .add("test_picking_type_mandatory_scan_complete_flux_pick", {
        steps: () => [
            {
                trigger: ".o_barcode_client_action",
                run: function () {
                    helper.assertLinesCount(7);
                    helper.assertScanMessage("scan_src");
                    helper.assertValidateVisible(true);
                    helper.assertValidateEnabled(false);
                    const lineButtons = document.querySelectorAll(
                        ".btn.o_edit,.btn.o_add_remaining_quantity",
                    );
                    helper.assert(
                        lineButtons.length,
                        10,
                        "Should have 1 edit & 1 add qty. buttons on 5 lines",
                    );
                    for (const button of lineButtons) {
                        helper.assert(
                            button.disabled,
                            true,
                            "All lines' buttons are disabled until a source location was scanned",
                        );
                    }
                },
            },
            {
                trigger: ".o_scan_message.o_scan_src",
                run: "scan product1",
            },
            {
                trigger:
                    ".o_notification:contains(Mandatory Source Location. You are supposed to scan WH/Stock or another source location)",
            },
            {
                trigger: ".btn-close.o_notification_close",
                run: "click",
            },

            {
                trigger: ".o_scan_message.o_scan_src",
                run: "scan LOC-01-02-00",
            },
            {
                trigger:
                    '.o_barcode_location_line[data-location="WH/Stock/Section 2"].text-bg-400',
                run: function () {
                    helper.assertLinesCount(7);
                    helper.assertScanMessage("scan_product");
                    const lineProduct2 = helper.getLine({ barcode: "product2" });
                    helper.assert(
                        lineProduct2.querySelector(".btn.o_edit").disabled,
                        false,
                        "Since the source location was scanned, its buttons should be enabled",
                    );
                    helper.assert(
                        lineProduct2.querySelector(".btn.o_add_remaining_quantity")
                            .disabled,
                        false,
                        "Since the source location was scanned, its buttons should be enabled",
                    );
                },
            },
            { trigger: ".o_barcode_client_action", run: "scan product2" },
            { trigger: ".o_barcode_line.o_line_completed", run: "scan shelf3" },
            {
                trigger:
                    ".o_notification:contains(Not the expected scan. You must scan a package or put in pack)",
            },
            {
                trigger: ".btn-close.o_notification_close",
                run: "click",
            },

            {
                trigger: ".o_barcode_line.o_line_completed",
                run: "scan cluster-pack-01",
            },
            {
                trigger: ".o_barcode_line.o_selected .result-package",
                run: "scan LOC-01-01-00",
            },
            {
                trigger:
                    '.o_barcode_location_line[data-location="WH/Stock/Section 1"].text-bg-400',
                run: function () {
                    helper.assertLinesCount(7);
                    helper.assertScanMessage("scan_product");
                },
            },
            { trigger: ".o_barcode_client_action", run: "scan product1" },
            {
                trigger: '.o_barcode_line[data-barcode="product1"].o_selected',
                run: "scan cluster-pack-01",
            },
            {
                trigger: ".o_barcode_line.o_line_completed .result-package",
                run: "scan shelf3",
            },
            {
                trigger:
                    '.o_barcode_location_line[data-location="WH/Stock/Section 3"].text-bg-400',
                run: "scan product1",
            },
            {
                trigger:
                    '.o_barcode_location_line[data-location="WH/Stock/Section 3"] + .o_barcode_line.o_selected.o_line_completed',
                run: "scan productlot1",
            },
            {
                trigger:
                    ".o_notification:contains(Not the expected scan. You must scan a package or put in pack)",
            },
            {
                trigger: ".btn-close.o_notification_close",
                run: "click",
            },
            { trigger: ".o_barcode_client_action", run: "scan cluster-pack-01" },
            {
                trigger: ".o_barcode_line.o_selected.o_line_completed .result-package",
                run: "scan productlot1",
            },
            {
                trigger:
                    ".o_barcode_line.o_selected .btn.o_toggle_sublines .fa-angle-down",
                run: "click",
            },
            {
                trigger: ".o_barcode_line.o_selected .o_sublines",
                run: function () {
                    const [lot001Line, lot002Line] = helper.getSublines();
                    helper.assert(
                        lot001Line.querySelector(".btn.o_add_quantity").disabled,
                        true,
                        "Lot number not scanned yet, so line's buttons are disabled.",
                    );
                    helper.assert(
                        lot001Line.querySelector(".btn.o_add_remaining_quantity")
                            .disabled,
                        true,
                        "Lot number not scanned yet, so line's buttons are disabled.",
                    );
                    helper.assert(
                        lot002Line.querySelector(".btn.o_add_remaining_quantity")
                            .disabled,
                        true,
                        "Lot number not scanned yet, so line's buttons are disabled.",
                    );
                },
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan lot-001",
            },
            {
                trigger: ".o_barcode_line.o_selected .qty-done:contains(1)",
                run: function () {
                    const [lot001Line, lot002Line] = helper.getSublines();
                    helper.assert(
                        lot001Line.querySelector(".btn.o_remove_unit").disabled,
                        false,
                        "lot-001 was scanned, its line's buttons should be enable",
                    );
                    helper.assert(
                        lot001Line.querySelector(".btn.o_add_remaining_quantity")
                            .disabled,
                        false,
                        "lot-001 was scanned, its line's buttons should be enable",
                    );
                    helper.assert(
                        lot002Line.querySelector(".btn.o_add_remaining_quantity")
                            .disabled,
                        true,
                        "Lot number not scanned yet, so line's buttons are disabled.",
                    );
                },
            },
            {
                trigger: ".o_barcode_line.o_selected:not(.o_line_completed)",
                run: "scan lot-001",
            },
            {
                trigger: ".o_barcode_line.o_selected.o_line_completed",
                run: function () {
                    const lot001Line = helper.getSubline({ completed: true });
                    const lot002Line = helper.getSubline({ completed: false });
                    helper.assertButtonIsVisible(lot001Line, "remove_unit");
                    helper.assertButtonIsVisible(lot001Line, "add_quantity", false);
                    helper.assertButtonIsVisible(lot001Line, "add_remaining_quantity");
                    helper.assert(
                        lot002Line.querySelector(".btn.o_add_remaining_quantity")
                            .disabled,
                        true,
                    );
                },
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan lot-002",
            },
            {
                trigger: ".o_barcode_line.o_selected .qty-done:contains(1)",
                run: function () {
                    const lot002Line = helper.getSubline({
                        selected: true,
                        completed: false,
                    });
                    helper.assert(
                        lot002Line.querySelector(".btn.o_remove_unit").disabled,
                        false,
                        "lot-002 was scanned, the button to remove quantity should be enabled.",
                    );
                    helper.assert(
                        lot002Line.querySelector(".btn.o_add_remaining_quantity")
                            .disabled,
                        false,
                        "lot-002 was scanned, the button to add quantity should be enabled.",
                    );
                },
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan lot-002",
            },

            {
                trigger: ".o_barcode_line.o_selected.o_line_completed",
                run: function () {
                    const lot002Line = helper.getSubline({
                        selected: true,
                        completed: true,
                    });
                    helper.assertButtonIsVisible(lot002Line, "remove_unit");
                    helper.assertButtonIsVisible(lot002Line, "add_quantity", false);
                    helper.assertButtonIsVisible(
                        lot002Line,
                        "add_remaining_quantity",
                        false,
                    );
                },
            },
            { trigger: ".o_barcode_client_action", run: "scan cluster-pack-02" },

            {
                trigger: ".o_barcode_line.o_selected.o_line_completed .result-package",
                run: "scan LOC-01-01-00",
            },
            {
                trigger:
                    '.o_barcode_location_line[data-location="WH/Stock/Section 1"].text-bg-400',
            },
            {
                trigger:
                    ".o_barcode_line:not([data-barcode]) .btn.o_add_remaining_quantity",
                run: "click",
            },
            {
                trigger:
                    ".o_barcode_line.o_selected.o_line_completed:not([data-barcode])",
                run: "scan cluster-pack-01",
            },

            {
                trigger: ".o_barcode_line.o_selected.o_line_completed .result-package",
                run: "scan shelf4",
            },
            {
                trigger: ".o_scan_message.o_scan_product",
            },
            {
                trigger:
                    '.o_barcode_location_line[data-location="WH/Stock/Section 4"].text-bg-400',
                run: "scan lot-003",
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan sn-001",
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan sn-003",
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan sn-002",
            },
            {
                trigger: ".o_scan_message.o_scan_package",
            },
            {
                trigger:
                    '.o_barcode_line[data-barcode="productserial1"].o_selected.o_line_completed',
                run: "scan cluster-pack-02",
            },
            {
                trigger: ".o_scan_message.o_scan_product",
                run: "scan lot-003",
            },
            {
                trigger:
                    '.o_barcode_line[data-barcode="productlot1"].o_selected.o_line_completed',
                run: "scan cluster-pack-02",
            },
            {
                trigger: 'div[name="barcode_messages"] .fa-square-check',
            },
            {
                trigger: ".o_validate_page.btn-primary",
                run: "click",
            },
            {
                trigger: ".o_notification_bar.bg-success",
            },
        ],
    });

registry
    .category("web_tour.tours")
    .add("test_picking_type_mandatory_scan_complete_flux_pack", {
        steps: () => [
            {
                trigger: ".o_barcode_client_action",
                run: function () {
                    helper.assertLinesCount(5);
                    helper.assertScanMessage("scan_product");
                    helper.assertValidateVisible(true);
                    helper.assertValidateEnabled(true);
                    helper.assertValidateIsHighlighted(false);
                },
            },
            { trigger: ".o_barcode_client_action", run: "scan cluster-pack-01" },
            { trigger: ".o_barcode_client_action", run: "scan cluster-pack-02" },
            {
                trigger: ".o_validate_page.btn-primary",
                run: "click",
            },
            {
                trigger:
                    ".o_notification:has(.bg-danger):text(All products need to be packed)",
            },
            {
                trigger: ".btn-close.o_notification_close",
                run: "click",
            },
            { trigger: ".o_barcode_client_action", run: "scan OBTPACK" },
            {
                trigger: ".o_scan_message.o_scan_validate",
            },
            {
                trigger: ".o_validate_page.btn-primary",
                run: "click",
            },
            { trigger: ".o_notification_bar.bg-success" },
        ],
    });

registry
    .category("web_tour.tours")
    .add("test_picking_type_mandatory_scan_complete_flux_delivery", {
        steps: () => [
            {
                trigger: ".o_barcode_client_action",
                run: function () {
                    helper.assertLinesCount(1);
                    helper.assertScanMessage("scan_product_or_package");
                },
            },
            {
                trigger: '.o_barcode_line:contains("PACK0000001")',
                run: "scan PACK0000001",
            },
            {
                trigger: ".o_scan_message.o_scan_validate",
            },
            {
                trigger: ".o_barcode_line.o_line_completed",
                run: "scan OBTVALI",
            },
            { trigger: ".o_notification_bar.bg-success" },
        ],
    });

registry.category("web_tour.tours").add("test_pack_multiple_scan", {
    steps: () => [
        { trigger: ".o_stock_barcode_main_menu", run: "scan WHIN" },
        { trigger: ".o_barcode_client_action", run: "scan product1" },
        { trigger: ".o_barcode_client_action", run: "scan product2" },
        { trigger: ".o_barcode_line + .o_barcode_line", run: "scan OBTPACK" },
        ...stepUtils.validateBarcodeOperation(),
        {
            trigger:
                ".o_notification:has(.bg-success):text(The transfer has been validated)",
        },
        { trigger: ".o_notification_close", run: "click" },

        { trigger: ".o_stock_barcode_main_menu", run: "scan WHOUT" },
        { trigger: ".o_barcode_client_action", run: "scan PACK0001000" },
        {
            trigger: ".o_barcode_line",
            run: function () {
                const line1 = helper.getLine({ barcode: "product1" });
                helper.assertLineIsHighlighted(line1, true);
                const line2 = helper.getLine({ barcode: "product2" });
                helper.assertLineIsHighlighted(line2, true);
            },
        },
        { trigger: ".o_barcode_line:nth-child(2)", run: "scan PACK0001000" },
        {
            trigger:
                ".o_notification:has(.bg-danger):text(This package is already scanned.)",
            run: function () {
                helper.assertLineIsHighlighted(0, false);
                helper.assertLineIsHighlighted(0, false);
            },
        },
        ...stepUtils.validateBarcodeOperation(),
        {
            trigger:
                ".o_notification:has(.bg-success):text(The transfer has been validated)",
        },
    ],
});

registry.category("web_tour.tours").add("test_pack_common_content_scan", {
    steps: () => [
        {
            trigger: ".o_stock_barcode_main_menu",
            run: "scan WHOUT",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan product1",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan PACK1",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan PACK2",
        },

        {
            trigger: '.o_barcode_client_action:contains("PACK2")',
            run: function () {
                helper.assertLinesCount(5);
            },
        },
        ...stepUtils.validateBarcodeOperation(),
        {
            trigger:
                ".o_notification:has(.bg-success):text(The transfer has been validated)",
        },
    ],
});

registry.category("web_tour.tours").add("test_pack_multiple_location", {
    steps: () => [
        {
            trigger: ".o_stock_barcode_main_menu",
            run: "scan WHINT",
        },

        {
            trigger: ".o_barcode_client_action .o_scan_message.o_scan_src",
            run: "scan LOC-01-01-00",
        },

        {
            trigger: ".o_scan_message.o_scan_product",
            run: "scan PACK0000666",
        },

        {
            trigger: ".o_package_content",
            run: () => helper.assertLineQty(0, "1"),
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan PACK0000666",
        },
        {
            trigger: ".o_notification_bar.bg-danger",
            run: () => helper.assertLineQty(0, "1"),
        },

        {
            trigger: ".o_package_content",
            run: "click",
        },
        {
            trigger: '.o_kanban_view:contains("product1")',
            run: function () {
                helper.assertKanbanRecordsCount(2);
            },
        },
        {
            trigger: ".o_close",
            run: "click",
        },

        {
            trigger: ".o_scan_message.o_scan_dest",
            run: "scan LOC-01-02-00",
        },

        ...stepUtils.validateBarcodeOperation(),
        {
            trigger:
                ".o_notification:has(.bg-success):text(The transfer has been validated)",
        },
    ],
});

registry.category("web_tour.tours").add("test_pack_multiple_location_02", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: "scan LOC-01-01-00",
        },

        {
            trigger: ".o_scan_message.o_scan_product",
            run: "scan PACK0002020",
        },
        {
            trigger: ".o_barcode_line.o_line_completed",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan LOC-01-02-00",
        },

        {
            trigger:
                '.o_barcode_line .o_line_destination_location:contains("WH/Stock/Section 2")',
            run: "scan OBTVALI",
        },

        {
            trigger: ".o_notification_bar.bg-success",
        },
    ],
});

registry.category("web_tour.tours").add("test_pack_multiple_location_03", {
    steps: () => [
        { trigger: ".o_barcode_client_action", run: "scan shelf3" },
        {
            trigger: ".o_barcode_line",
            run: function () {
                helper.assertLinesCount(1);
                helper.assert(
                    document.querySelector(".o_barcode_line .package").textContent,
                    "PACK000666",
                );
            },
        },
        { trigger: ".o_barcode_client_action", run: "scan product1" },
        {
            trigger: ".qty-done:contains(1)",
            run: function () {
                helper.assertLinesCount(1);
                helper.assert(
                    document.querySelectorAll(
                        ".o_barcode_lines .o_barcode_line .package",
                    ).length,
                    0,
                );
            },
        },
        ...stepUtils.validateBarcodeOperation(),
    ],
});

registry.category("web_tour.tours").add("test_pack_source_location", {
    steps: () => [
        {
            trigger: ".o_stock_barcode_main_menu",
            run: "scan WHINT",
        },
        {
            trigger: ".o_scan_message.o_scan_product",
            run: "scan PACK123666",
        },
        {
            trigger: ".o_barcode_line",
            run: function () {
                const line = helper.getLine({ barcode: "product1" });
                helper.assertLineSourceLocation(line, "WH/Stock/Section 4");
            },
        },
        ...stepUtils.validateBarcodeOperation(),
    ],
});

registry.category("web_tour.tours").add("test_put_in_pack_from_multiple_pages", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: function () {
                helper.assertLinesCount(4);
                helper.assertScanMessage("scan_src");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(false);
                helper.assertValidateEnabled(true);
            },
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan LOC-01-01-00",
        },

        {
            trigger: ".o_scan_message.o_scan_product",
            run: function () {
                helper.assertLinesCount(4);
                helper.assertScanMessage("scan_product");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(false);
                helper.assertValidateEnabled(true);
            },
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan product1",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan product2",
        },

        {
            trigger: ".o_barcode_line:nth-child(2).o_line_completed",
            run: "scan LOC-01-02-00",
        },

        {
            trigger: '.o_scan_message:contains("Scan a product from Section 2")',
            run: "scan product1",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan product2",
        },

        {
            trigger: ".o_validate_page.btn-primary",
            run: "scan OBTPACK",
        },

        ...stepUtils.validateBarcodeOperation('.o_barcode_line:contains("PACK")'),
    ],
});

registry.category("web_tour.tours").add("test_put_in_pack_in_new_created_package", {
    steps: () => [
        { trigger: ".o_stock_barcode_main_menu", run: "scan TEST/IN/0001" },
        { trigger: ".o_barcode_line", run: "scan product1" },
        { trigger: ".o_barcode_line.o_selected.o_line_completed", run: "scan OBTPACK" },
        {
            trigger: ".o_barcode_line.o_selected.o_line_completed .result-package",
            run: "scan product2",
        },
        {
            trigger: ".o_barcode_line:first-child.o_selected.o_line_completed",
            run: "scan PACK0000042",
        },
        {
            trigger: ".o_barcode_line:first-child .result-package",
            run: function () {
                helper.assertLinesCount(2);
                helper.assertLineProduct(0, "product2");
                helper.assertLineResultPackage(0, "PACK0000042");
                helper.assertLineProduct(1, "product1");
                helper.assertLineResultPackage(1, "PACK0000042");
            },
        },
        ...stepUtils.validateBarcodeOperation(),
    ],
});

registry.category("web_tour.tours").add("test_put_in_pack_no_freeze", {
    steps: () => [
        { trigger: "button.o_button_operations", run: "click" },

        { trigger: ".o_kanban_record:contains(Receipts)", run: "click" },

        {
            trigger: 'button[name="action_view_picking_client_action"]:last',
            run: "click",
        },

        { trigger: ".o_edit", run: "click" },

        {
            trigger: ".o_field_widget[name=qty_done] input",
            run() {
                this.anchor.value = "5.66";
            },
        },

        { trigger: ".o_save", run: "click" },

        { trigger: ".o_put_in_pack", run: "click" },

        { trigger: "button.o_exit", run: "click" },
    ],
});

registry.category("web_tour.tours").add("test_unpack_package_lines", {
    steps: () => [
        {
            trigger: ".o_barcode_line:not(.o_selected)",
            run: () => {
                helper.assertLinesCount(1);
                helper.assertLinePackage(0, "PAL01");
                helper.assertLineResultPackage(0, "PAL01");
                helper.assertButtonIsVisible(0, "unpack", false);
            },
        },
        { trigger: ".o_barcode_line", run: "click" },
        {
            trigger: ".o_barcode_line.o_selected",
            run: () => {
                helper.assertLinesCount(1);
                helper.assertLinePackage(0, "PAL01");
                helper.assertLineResultPackage(0, "PAL01");
                helper.assertButtonIsVisible(0, "unpack");
            },
        },
        { trigger: ".o_line_button.o_package_content", run: "click" },
        {
            trigger: ".o_kanban_view .o_kanban_record",
            run: function () {
                helper.assertKanbanRecordsCount(4);
            },
        },
        { trigger: "button.o_close", run: "click" },
        { trigger: ".o_barcode_line button.o_unpack", run: "click" },
        {
            trigger: ".o_barcode_line:nth-child(2)",
            run: () => {
                helper.assertLinesCount(2);
                helper.assertLinePackage(0, "PAL01 > BOX01");
                helper.assertLineResultPackage(0, "BOX01");
                helper.assertButtonIsVisible(0, "unpack", true);
                helper.assertLinePackage(1, "PAL01 > BOX02");
                helper.assertLineResultPackage(1, "BOX02");
                helper.assertButtonIsVisible(1, "unpack", false);
            },
        },
        { trigger: ".o_barcode_line:first-child button.o_unpack", run: "click" },
        {
            trigger: ".o_barcode_line:nth-child(2)[data-barcode='product2']",
            run: () => {
                helper.assertLinesCount(3);
                helper.assertLinePackage(0, "PAL01 > BOX01");
                helper.assertLineResultPackage(0, false);
                helper.assertButtonIsVisible(0, "unpack", false);
                helper.assertLinePackage(1, "PAL01 > BOX01");
                helper.assertLineResultPackage(1, false);
                helper.assertButtonIsVisible(1, "unpack", false);
                helper.assertLinePackage(2, "PAL01 > BOX02");
                helper.assertLineResultPackage(2, "BOX02");
                helper.assertButtonIsVisible(2, "unpack", false);
            },
        },
        { trigger: ".o_barcode_line:last-child", run: "click" },
        {
            trigger: ".o_barcode_line:last-child.o_selected button.o_unpack",
            run: "click",
        },
        {
            trigger: ".o_barcode_line:nth-child(4)[data-barcode='product2']",
            run: () => {
                helper.assertLinesCount(4);
                helper.assertLinePackage(0, "PAL01 > BOX01");
                helper.assertLineResultPackage(0, false);
                helper.assertButtonIsVisible(0, "unpack", false);
                helper.assertLinePackage(1, "PAL01 > BOX01");
                helper.assertLineResultPackage(1, false);
                helper.assertButtonIsVisible(1, "unpack", false);
                helper.assertLinePackage(2, "PAL01 > BOX02");
                helper.assertLineResultPackage(2, false);
                helper.assertButtonIsVisible(2, "unpack", false);
                helper.assertLinePackage(3, "PAL01 > BOX02");
                helper.assertLineResultPackage(3, false);
                helper.assertButtonIsVisible(3, "unpack", false);
            },
        },
        {
            trigger: ".o_barcode_line:first-child button.o_add_remaining_quantity",
            run: "click",
        },
        {
            trigger: ".o_barcode_line:nth-child(2) button.o_add_remaining_quantity",
            run: "click",
        },
        {
            trigger: ".o_barcode_line:nth-child(3) button.o_add_remaining_quantity",
            run: "click",
        },
        {
            trigger: ".o_barcode_line:last-child button.o_add_remaining_quantity",
            run: "click",
        },
        { trigger: "button.o_validate_page.btn-primary" },
        { trigger: ".o_barcode_client_action", run: "scan PAL02" },
        {
            trigger: ".o_barcode_line:last-child .result-package",
            run: () => {
                helper.assertLinesCount(4);
                helper.assertLinePackage(0, "PAL01 > BOX01");
                helper.assertLineResultPackage(0, "PAL02");
                helper.assertButtonIsVisible(0, "unpack", false);
                helper.assertLinePackage(1, "PAL01 > BOX01");
                helper.assertLineResultPackage(1, "PAL02");
                helper.assertButtonIsVisible(1, "unpack", false);
                helper.assertLinePackage(2, "PAL01 > BOX02");
                helper.assertLineResultPackage(2, "PAL02");
                helper.assertButtonIsVisible(2, "unpack", false);
                helper.assertLinePackage(3, "PAL01 > BOX02");
                helper.assertLineResultPackage(3, "PAL02");
                helper.assertButtonIsVisible(3, "unpack", false);
            },
        },
        ...stepUtils.validateBarcodeOperation(),
    ],
});

registry.category("web_tour.tours").add("test_unpack_palet_then_pack_another_palet", {
    steps: () => [
        { trigger: ".o_stock_barcode_main_menu", run: "scan WHINT" },
        { trigger: ".o_barcode_client_action", run: "scan PAL01" },
        {
            trigger: ".o_barcode_line",
            run: () => {
                helper.assertLinesCount(1);
                helper.assertLinePackages(0, "PAL01", "PAL01");
            },
        },
        { trigger: ".o_barcode_line", run: "click" },
        { trigger: ".o_barcode_line.o_selected", run: "scan OBTUPCK" },
        { trigger: ".o_barcode_line:nth-child(2)", run: "scan PT_PALET" },
        {
            trigger: ".o_barcode_line .result-package:contains('PAL-0000001')",
            run: () => {
                helper.assertLinesCount(2);
                helper.assertLinePackage(0, "PAL01 > BOX01", "PAL-0000001 > BOX01");
                helper.assertLinePackage(1, "PAL01 > BOX02", "PAL-0000001 > BOX02");
            },
        },
        { trigger: ".o_barcode_line", run: "scan OBTVALI" },
        { trigger: ".o_stock_barcode_main_menu", run: "scan WHOUT" },
        { trigger: ".o_barcode_client_action", run: "scan PAL-0000001" },
        {
            trigger: ".o_barcode_line",
            run: () => {
                helper.assertLinesCount(1);
                helper.assertLinePackages(0, "PAL-0000001", "PAL-0000001");
            },
        },
        { trigger: ".o_barcode_line", run: "click" },
        { trigger: "button.o_unpack", run: "click" },
        { trigger: ".o_barcode_line:nth-child(2)", run: "scan PT_PALET" },
        {
            trigger: ".o_barcode_line .result-package:contains('PAL-0000002')",
            run: () => {
                helper.assertLinesCount(2);
                helper.assertLinePackage(
                    0,
                    "PAL-0000001 > BOX01",
                    "PAL-0000002 > BOX01",
                );
                helper.assertLinePackage(
                    1,
                    "PAL-0000001 > BOX02",
                    "PAL-0000002 > BOX02",
                );
            },
        },
        ...stepUtils.validateBarcodeOperation(),
    ],
});

registry.category("web_tour.tours").add("test_reload_flow", {
    steps: () => [
        {
            trigger: ".o_stock_barcode_main_menu",
            run: "scan WHIN",
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan product1",
        },

        {
            trigger: ".o_edit",
            run: "click",
        },
        {
            trigger: '.o_field_widget[name="product_id"]',
        },
        {
            trigger: ".o_field_widget[name=qty_done] input",
            run: "edit 2",
        },

        {
            trigger: ".o_save",
            run: "click",
        },

        {
            trigger: ".o_add_line",
            run: "click",
        },

        {
            trigger: ".o_field_widget[name=product_id] input",
            run: "edit product2",
        },

        {
            trigger: ".ui-menu-item > a:contains('product2')",
            run: "click",
        },

        {
            trigger: ".o_save",
            run: "click",
        },

        {
            trigger: ".o_barcode_line:nth-child(2).o_selected",
            run: function () {
                helper.assertScanMessage("scan_product_or_dest");
            },
        },

        { trigger: ".o_barcode_client_action", run: "scan LOC-01-01-00" },
        {
            trigger:
                '.o_barcode_line:nth-child(2) .o_line_destination_location:contains(".../Section 1")',
        },
        {
            trigger: ".o_barcode_line:first-child",
            run: "click",
        },
        {
            trigger: ".o_barcode_line:first-child.o_selected",
            run: "scan LOC-01-01-00",
        },
        {
            trigger:
                '.o_barcode_line:nth-child(1) .o_line_destination_location:contains(".../Section 1")',
            run: "click",
        },
        ...stepUtils.validateBarcodeOperation(),
    ],
});

registry.category("web_tour.tours").add("test_highlight_packs", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: function () {
                helper.assertLinesCount(1);
                helper.assertScanMessage("scan_product_or_package");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(false);
                helper.assertValidateEnabled(true);
                helper.assertLineIsHighlighted(0, false);
            },
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan PACK002",
        },

        {
            trigger: '.o_barcode_client_action:contains("PACK002")',
            run: "click",
        },

        {
            trigger: ".o_barcode_client_action",
            run: function () {
                helper.assertLinesCount(2);
                helper.assertScanMessage("scan_product_or_package");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(false);
                helper.assertValidateEnabled(true);
                const packageLine = document.querySelector(
                    '.o_barcode_line[data-package="PACK002"]',
                );
                helper.assertLineIsHighlighted(packageLine, true);
            },
        },
    ],
});

registry.category("web_tour.tours").add("test_put_in_pack_from_different_location", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: "scan product1",
        },

        {
            trigger: ".o_barcode_line.o_selected.o_line_completed",
            run: "scan product2",
        },

        {
            trigger: ".o_validate_page.btn-primary",
            run: "scan OBTPACK",
        },

        {
            trigger: '.o_barcode_line:contains("PACK")',
            run: function () {
                const lines = helper.getLines();
                helper.assert(
                    lines[0].querySelector(".result-package").innerText,
                    "PACK0000001",
                );
                helper.assert(
                    lines[1].querySelector(".result-package").innerText,
                    "PACK0000001",
                );
            },
        },
        {
            trigger: ".o_scan_message.o_scan_product_or_dest",
            run: "scan LOC-01-02-00",
        },
        ...stepUtils.validateBarcodeOperation(".o_scan_message.o_scan_validate"),
    ],
});

registry.category("web_tour.tours").add("test_put_in_pack_before_dest", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: "scan LOC-01-01-00",
        },

        {
            trigger:
                '.o_barcode_location_line[data-location="WH/Stock/Section 1"].text-bg-400',
            run: "scan product1",
        },
        { trigger: ".o_scan_message.o_scan_product_or_dest", run: "scan LOC-01-02-00" },

        {
            trigger: ".o_scan_message.o_scan_src",
            run: "scan shelf3",
        },

        {
            trigger:
                '.o_barcode_location_line[data-location="WH/Stock/Section 3"].text-bg-400',
            run: "scan product2",
        },

        {
            trigger: '.o_barcode_line.o_selected .qty-done:contains("1")',
            run: "scan shelf4",
        },

        {
            trigger: ".o_scan_message.o_scan_validate",
            run: "scan OBTPACK",
        },

        {
            trigger: '.modal .modal-title:contains("Choose destination location")',
            run: "click",
        },

        {
            trigger: '.modal .o_field_widget[name="location_dest_id"] input',
            run: "click",
        },
        {
            isActive: ["auto"],
            trigger: '.modal .ui-menu-item > a:contains("Section 2")',
            run: "click",
        },

        {
            trigger: '.modal .o_field_widget[name="location_dest_id"]',
            run: function () {
                helper.assert(
                    document.querySelector(
                        '.o_field_widget[name="location_dest_id"] input',
                    ).value,
                    "WH/Stock/Section 2",
                );
            },
        },

        {
            trigger: ".modal .btn-primary",
            run: "click",
        },
        {
            trigger: "body:not(:has(.modal))",
        },
        ...stepUtils.validateBarcodeOperation(),
    ],
});

registry.category("web_tour.tours").add("test_put_in_pack_scan_package", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: function () {
                helper.assertLinesCount(3);
            },
        },
        {
            trigger: ".o_scan_message.o_scan_src",
            run: "scan LOC-01-01-00",
        },

        {
            trigger: ".o_scan_message.o_scan_product",
            run: "scan product1",
        },
        {
            trigger: '.o_barcode_line[data-barcode="product1"] .qty-done:contains("1")',
            run: "scan OBTPACK",
        },
        {
            trigger: '.o_barcode_line:contains("product1"):contains("PACK0000001")',
            run: function () {
                const line1 = helper.getLine({ barcode: "product1", selected: true });
                const product1_package =
                    line1.querySelector('div[name="package"]').innerText;
                helper.assert(product1_package, "PACK0000001");
            },
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan product2",
        },
        {
            trigger: '.o_barcode_line.o_highlight:contains("product2")',
            run: "scan PACK0000001",
        },
        {
            trigger: '.o_barcode_line:contains("product2"):contains("PACK0000001")',
            run: function () {
                const line1 = helper.getLine({ barcode: "product1", completed: true });
                const line2 = helper.getLine({ barcode: "product2", selected: true });
                const product1_package =
                    line1.querySelector('div[name="package"]').innerText;
                const product2_package =
                    line2.querySelector('div[name="package"]').innerText;
                helper.assert(product1_package, "PACK0000001");
                helper.assert(product2_package, "PACK0000001");
            },
        },

        {
            trigger: ".o_barcode_client_action",
            run: "scan LOC-01-02-00",
        },
        {
            trigger:
                '.o_barcode_location_line[data-location="WH/Stock/Section 2"].text-bg-400',
            run: "scan product1",
        },
        {
            trigger:
                '.o_barcode_line[data-barcode="product1"].o_selected .qty-done:contains("1")',
            run: "scan PACK0000001",
        },
        {
            trigger:
                '.o_barcode_line:contains("product1").o_selected:contains("PACK0000001")',
            run: function () {
                const line1 = helper.getLine({ barcode: "product1", selected: true });
                const product1_package =
                    line1.querySelector('div[name="package"]').innerText;
                helper.assert(product1_package, "PACK0000001");
            },
        },
        ...stepUtils.validateBarcodeOperation(),
    ],
});

registry.category("web_tour.tours").add("test_put_in_pack_new_lines", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: "scan P00001",
        },
        {
            trigger: ".o_notification_bar.bg-danger",
            run: "click",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan product1",
        },
        {
            trigger: '.o_barcode_line:contains("product1")',
            run: "scan P00001",
        },
        {
            trigger: '.o_barcode_line:contains("product1"):contains("P00001")',
            run: "scan OBTVALI",
        },
        {
            trigger: ".o_notification_bar.bg-success",
        },
    ],
});

registry.category("web_tour.tours").add("test_put_packs_in_existing_pack", {
    steps: () => [
        { trigger: ".o_barcode_line", run: "scan MNB-0000001" },
        {
            trigger: ".o_barcode_line:first-child.o_selected.o_line_completed",
            run: "scan MNB-0000002",
        },
        {
            trigger: ".o_barcode_line:nth-child(2).o_selected.o_line_completed",
            run: "scan MXB-0000001",
        },
        {
            trigger: ".o_barcode_line:nth-child(2):not(.o_selected)",
            run: "scan MNB-0000003",
        },
        {
            trigger: ".o_barcode_line:first-child.o_selected.o_line_completed",
            run: "scan MNB-0000004",
        },
        {
            trigger: ".o_barcode_line:nth-child(2).o_selected.o_line_completed",
            run: "scan MXB-0000002",
        },
        {
            trigger: "[name='package']:contains('MXB-0000002')",
            run: () => {
                helper.assertLineResultPackage(0, "MXB-0000001 > MNB-0000001");
                helper.assertLineResultPackage(1, "MXB-0000001 > MNB-0000002");
                helper.assertLineResultPackage(2, "MXB-0000002 > MNB-0000003");
                helper.assertLineResultPackage(3, "MXB-0000002 > MNB-0000004");
            },
        },
    ],
});

registry.category("web_tour.tours").add("test_put_packs_in_new_pack", {
    steps: () => [
        { trigger: ".o_stock_barcode_main_menu", run: "scan WHIN" },
        { trigger: ".o_barcode_client_action", run: "scan product1" },
        { trigger: ".o_barcode_line", run: "scan product2" },
        { trigger: ".o_barcode_line", run: "scan minibox" },
        {
            trigger: ".o_barcode_line.o_selected .result-package",
            run: () => {
                helper.assertLinesCount(2);
                helper.assertLineProduct(0, "product1");
                helper.assertLineResultPackage(0, "MNB-0000005");
                helper.assertLineProduct(1, "product2");
                helper.assertLineResultPackage(1, "MNB-0000005");
            },
        },
        { trigger: ".o_barcode_client_action", run: "scan product1" },
        { trigger: ".o_barcode_line", run: "scan product2" },
        { trigger: ".o_barcode_line:nth-child(4)", run: "scan minibox" },
        {
            trigger: ".o_barcode_line.o_selected .result-package",
            run: () => {
                helper.assertLinesCount(4);
                helper.assertLineProduct(2, "product1");
                helper.assertLineResultPackage(2, "MNB-0000006");
                helper.assertLineProduct(3, "product2");
                helper.assertLineResultPackage(3, "MNB-0000006");
            },
        },
        { trigger: ".o_barcode_client_action", run: "scan maxibox" },
        {
            trigger: ".o_barcode_line.o_selected .result-package:contains('MXB')",
            run: () => {
                helper.assertLinesCount(4);
                helper.assertLineProduct(0, "product1");
                helper.assertLineResultPackage(0, "MXB-0000001 > MNB-0000005");
                helper.assertLineProduct(1, "product2");
                helper.assertLineResultPackage(1, "MXB-0000001 > MNB-0000005");
                helper.assertLineProduct(2, "product1");
                helper.assertLineResultPackage(2, "MXB-0000001 > MNB-0000006");
                helper.assertLineProduct(3, "product2");
                helper.assertLineResultPackage(3, "MXB-0000001 > MNB-0000006");
            },
        },
        { trigger: ".o_barcode_client_action", run: "scan product1" },
        { trigger: ".o_barcode_line", run: "scan product2" },
        { trigger: ".o_barcode_line:nth-child(6)", run: "scan minibox" },
        { trigger: ".o_barcode_line.o_selected .result-package", run: "scan product1" },
        { trigger: ".o_barcode_line", run: "scan product2" },
        { trigger: ".o_barcode_line:nth-child(8)", run: "scan minibox" },
        { trigger: ".o_barcode_line.o_selected .result-package", run: "scan maxibox" },
        {
            trigger: ".o_barcode_line.o_selected .result-package:contains('MXB')",
            run: () => {
                helper.assertLinesCount(8);
                helper.assertLineProduct(0, "product1");
                helper.assertLineResultPackage(0, "MXB-0000001 > MNB-0000005");
                helper.assertLineProduct(1, "product2");
                helper.assertLineResultPackage(1, "MXB-0000001 > MNB-0000005");
                helper.assertLineProduct(2, "product1");
                helper.assertLineResultPackage(2, "MXB-0000001 > MNB-0000006");
                helper.assertLineProduct(3, "product2");
                helper.assertLineResultPackage(3, "MXB-0000001 > MNB-0000006");
                helper.assertLineProduct(4, "product1");
                helper.assertLineResultPackage(4, "MXB-0000002 > MNB-0000007");
                helper.assertLineProduct(5, "product2");
                helper.assertLineResultPackage(5, "MXB-0000002 > MNB-0000007");
                helper.assertLineProduct(6, "product1");
                helper.assertLineResultPackage(6, "MXB-0000002 > MNB-0000008");
                helper.assertLineProduct(7, "product2");
                helper.assertLineResultPackage(7, "MXB-0000002 > MNB-0000008");
            },
        },
        ...stepUtils.validateBarcodeOperation(),

        { trigger: ".o_stock_barcode_main_menu", run: "scan WH/OUT/TEST/001" },
        { trigger: ".o_barcode_line", run: "scan MNB-0000001" },
        {
            trigger: ".o_barcode_line:first-child.o_selected.o_line_completed",
            run: "scan MNB-0000002",
        },
        {
            trigger: ".o_barcode_line:nth-child(2).o_selected.o_line_completed",
            run: "scan maxibox",
        },
        {
            trigger:
                ".o_barcode_line.o_line_completed:not(.o_selected) :contains('MXB-0000003')",
            run: "scan MNB-0000003",
        },
        {
            trigger: ".o_barcode_line:first-child.o_selected.o_line_completed",
            run: "scan MNB-0000004",
        },
        {
            trigger: ".o_validate_page.btn-primary",
            run: "scan maxibox",
        },
        {
            trigger: "[name='package']:contains('MXB-0000004')",
            run: () => {
                helper.assertLineResultPackage(0, "MXB-0000003 > MNB-0000001");
                helper.assertLineResultPackage(1, "MXB-0000003 > MNB-0000002");
                helper.assertLineResultPackage(2, "MXB-0000004 > MNB-0000003");
                helper.assertLineResultPackage(3, "MXB-0000004 > MNB-0000004");
            },
        },
    ],
});

registry.category("web_tour.tours").add("test_picking_owner_scan_package", {
    steps: () => [
        {
            trigger: ".o_stock_barcode_main_menu",
            run: "scan WHOUT",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan P00001",
        },
        { trigger: '.o_barcode_client_action:contains("P00001")' },
        { trigger: '.o_barcode_client_action:contains("Azure Interior")' },
        ...stepUtils.validateBarcodeOperation(),
    ],
});

registry.category("web_tour.tours").add("test_receipt_delete_button", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: "scan product1",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan product2",
        },
        ...stepUtils.confirmAddingUnreservedProduct(),
        {
            trigger: '.o_barcode_line[data-barcode="product2"] .o_edit',
            run: "click",
        },
        {
            trigger: '.o_field_widget[name="product_id"]',
            run: function () {
                helper.assert(document.querySelectorAll(".o_delete").length, 1);
            },
        },
        {
            trigger: ".o_discard",
            run: "click",
        },
        {
            trigger: ".o_barcode_line:nth-child(2) .o_edit",
            run: "click",
        },
        {
            trigger: '.o_field_widget[name="product_id"]',
            run: function () {
                helper.assert(document.querySelectorAll(".o_delete").length, 0);
            },
        },
        {
            trigger: ".o_discard",
            run: "click",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan product3",
        },
        ...stepUtils.confirmAddingUnreservedProduct(),
        {
            trigger: '.o_barcode_line[data-barcode="product3"] .o_edit',
            run: "click",
        },
        {
            trigger: ".o_delete",
            run: "click",
        },
        {
            trigger: ".o_validate_page",
            run: "scan OBTVALI",
        },
        {
            content: "check the picking is validated",
            trigger: ".o_notification_bar.bg-success",
        },
    ],
});

registry.category("web_tour.tours").add("test_scan_aggregate_barcode", {
    steps: () => [
        { trigger: ".o_stock_barcode_main_menu", run: "scan WHIN" },
        { trigger: ".o_barcode_client_action", run: "scan product1,product1,product1" },
        {
            trigger: ".o_barcode_line.o_selected .qty-done:contains(3)",
            run: function () {
                helper.assertLinesCount(1);
                const line = helper.getLine({ barcode: "product1" });
                helper.assertLineQty(line, "3");
            },
        },
        { trigger: ".o_barcode_client_action", run: "scan product1|product2|product2" },
        {
            trigger: ".o_barcode_line.o_selected .qty-done:contains(2)",
            run: function () {
                helper.assertLinesCount(2);
                const notSelectedLine = helper.getLine({ selected: false });
                const selectedLine = helper.getLine({ selected: true });
                helper.assertLineProduct(notSelectedLine, "product1");
                helper.assertLineQty(notSelectedLine, "4");
                helper.assertLineProduct(selectedLine, "product2");
                helper.assertLineQty(selectedLine, "2");
            },
        },
        {
            content: "Scan a tracked product and all of its SNs",
            trigger: ".o_barcode_client_action",
            run: "scan productserial1|sn01,sn02,sn05,sn04,sn03,sn06,sn10,sn07,sn08,sn09",
        },
        {
            trigger: ".o_barcode_line.o_selected .qty-done:contains(10)",
        },
        {
            content: "Unfold grouped lines (productserial1)",
            trigger: ".o_line_button.o_toggle_sublines",
            run: "click",
        },
        ...stepUtils.validateBarcodeOperation(),
    ],
});

registry.category("web_tour.tours").add("test_scrap_change_source_location", {
    steps: () => [
        { trigger: ".o_barcode_actions", run: "click" },
        { trigger: "input#manual_barcode", run: "edit LOC-01-01-00" },
        { trigger: "button:contains('Apply')", run: "click" },
        { trigger: ".o_barcode_actions", run: "click" },
        { trigger: "input#manual_barcode", run: "edit Lot1" },
        { trigger: "button:contains('Apply')", run: "click" },
        { trigger: ".o_line_button:contains('+9')", run: "click" },
        { trigger: ".o_barcode_actions", run: "click" },
        { trigger: ".o_scrap", run: "click" },
        { trigger: "div[name='product_id'] input", run: "edit product1" },
        { trigger: ".ui-menu-item > a:contains('product1')", run: "click" },
        { trigger: "div[name='scrap_qty'] input", run: "edit 15" },
        { trigger: "div[name='location_id'] input", run: "edit WH/Stock/Section 1" },
        { trigger: ".ui-menu-item > a:contains('WH/Stock/Section 1')", run: "click" },
        { trigger: "div[name='trace_id'] input", run: "edit lot1" },
        { trigger: ".ui-menu-item > a:contains('lot1')", run: "click" },
        { trigger: "button.o_save", run: "click" },
        ...stepUtils.validateBarcodeOperation(),
    ],
});

registry.category("web_tour.tours").add("test_scrap", {
    steps: () => [
        { trigger: ".o_stock_barcode_main_menu", run: "scan receipt_scrap_test" },
        {
            trigger: ".o_barcode_actions",
            run: "click",
        },
        {
            trigger: ".o_barcode_settings",
            run: function () {
                const scrapButton = document.querySelector("button.o_scrap");
                helper.assert(
                    Boolean(scrapButton),
                    false,
                    "Scrap button shouldn't be displayed",
                );
            },
        },
        {
            trigger: "button.o_close",
            run: "click",
        },
        {
            trigger: ".o_barcode_lines",
            run: "scan OBTSCRA",
        },
        {
            trigger:
                ".o_notification:has(.o_notification_bar.bg-warning):contains('You can\\'t register scrap')",
            run: "click",
        },
        {
            trigger: ".o_line_button.o_add_remaining_quantity",
            run: "click",
        },
        {
            trigger: ".o_validate_page.btn-primary",
            run: "click",
        },
        { trigger: ".o_stock_barcode_main_menu", run: "scan receipt_scrap_test" },
        {
            trigger: ".o_scan_message.o_picking_already_done",
            run: "scan OBTSCRA",
        },
        {
            trigger: ".o_field_widget[name='scrap_qty']",
        },
        {
            trigger: ".btn[special='cancel']",
            run: "click",
        },
        {
            trigger: ".o_barcode_actions",
            run: "click",
        },
        {
            trigger: ".o_barcode_settings",
            run: function () {
                const scrapButton = document.querySelector("button.o_scrap");
                helper.assert(
                    Boolean(scrapButton),
                    true,
                    "Scrap button should be displayed",
                );
            },
        },
        {
            trigger: "button.o_exit",
            run: "click",
        },
        {
            trigger: ".o_barcode_lines_header",
        },
        {
            trigger: "button.o_exit",
            run: "click",
        },
        { trigger: ".o_stock_barcode_main_menu", run: "scan delivery_scrap_test" },
        {
            trigger: ".o_barcode_actions",
            run: "click",
        },
        {
            trigger: ".o_barcode_settings",
            run: function () {
                const scrapButton = document.querySelector("button.o_scrap");
                helper.assert(
                    Boolean(scrapButton),
                    true,
                    "Scrap button should be displayed",
                );
            },
        },
        {
            trigger: "button.o_close",
            run: "click",
        },
        { trigger: ".o_barcode_lines", run: "scan OBTSCRA" },
        {
            trigger: ".o_field_widget[name='scrap_qty']",
        },
        {
            trigger: ".btn[special='cancel']",
            run: "click",
        },
        {
            trigger: ".o_line_button.o_add_remaining_quantity",
            run: "click",
        },
        {
            trigger: ".o_validate_page.btn-primary",
            run: "click",
        },
        { trigger: ".o_stock_barcode_main_menu", run: "scan delivery_scrap_test" },
        { trigger: ".o_barcode_lines_header", run: "scan OBTSCRA" },
        {
            trigger:
                ".o_notification:has(.o_notification_bar.bg-warning):contains('You can\\'t register scrap')",
            run: "click",
        },
        {
            trigger: ".o_barcode_actions",
            run: "click",
        },
        {
            trigger: ".o_barcode_settings",
            run: function () {
                const scrapButton = document.querySelector("button.o_scrap");
                helper.assert(
                    Boolean(scrapButton),
                    false,
                    "Scrap button shouldn't be displayed",
                );
            },
        },
        {
            trigger: "button.o_exit",
            run: "click",
        },
        {
            trigger: ".o_barcode_lines_header",
        },
        {
            trigger: "button.o_exit",
            run: "click",
        },
        { trigger: ".o_stock_barcode_main_menu", run: "scan receipt_scrap_test" },
        {
            trigger: ".o_barcode_actions",
            run: "click",
        },
        {
            trigger: ".o_barcode_settings",
            run: "click",
        },
        {
            trigger: ".o_scrap",
            run: "click",
        },
        {
            trigger: ".o_qty_done_field_not_completed",
            run: function () {
                const digipadView = document.querySelector(".o_digipad_widget");
                helper.assert(
                    Boolean(digipadView),
                    true,
                    "Scrap view should use the digipad widget.",
                );
            },
        },
        {
            content: "Select SN product from the dropdown",
            trigger: ".o_input_dropdown .o_input#product_id_0",
            run: "click",
        },
        {
            content:
                "Product `productserial1` should be available, despite not having any move lines",
            trigger: "a.dropdown-item:contains('productserial1')",
            run: "click",
        },
        {
            content: "Digipad should be hidden after selecting the SN product",
            trigger: "body:not(:has(.o_digipad_widget))",
        },
        {
            content: "Check available lots",
            trigger: ".o_input_dropdown .o_input#trace_id_0",
            run: "click",
        },
        {
            trigger: "ul.o-autocomplete--dropdown-menu",
        },
        {
            trigger: "a.dropdown-item:contains('SN')",
            run: function () {
                const dropdownContent =
                    document.querySelector(".dropdown-menu").textContent;
                helper.assert(
                    dropdownContent.includes("SN0001") &&
                        dropdownContent.includes("SN0002"),
                    true,
                    "All SN lots for productserial1 should be available in the dropdown.",
                );
            },
        },
        {
            trigger: "input#should_replenish_0",
            run: "click",
        },
        {
            trigger: "button.o_discard",
            run: "click",
        },
        {
            trigger: "button.o_exit",
            run: "click",
        },
        {
            trigger: "button.o_button_operations",
        },
    ],
});

registry.category("web_tour.tours").add("test_picking_scan_package_confirmation", {
    steps: () => [
        { trigger: ".o_barcode_client_action", run: "scan product1" },
        { trigger: '.o_barcode_line .qty-done:contains("1")', run: "scan package001" },
        {
            trigger: ".modal-content button.btn-secondary",
            run: "click",
        },
        { trigger: '.o_barcode_line .qty-done:contains("1")', run: "scan package001" },
        {
            trigger: ".modal-content button.btn-primary",
            run: "click",
        },
        { trigger: '.o_barcode_line .qty-done:contains("2")' },
    ],
});

registry.category("web_tour.tours").add("test_show_entire_package", {
    steps: () => [
        {
            trigger: "button.o_button_operations",
            run: "click",
        },
        {
            trigger: ".o_kanban_record:contains(Delivery Orders)",
            run: "click",
        },

        {
            trigger: ".o_kanban_record:contains(Delivery with Package Level)",
            run: "click",
        },
        {
            trigger: ".o_barcode_client_action",
            run: function () {
                helper.assertLinesCount(1);
                helper.assertScanMessage("scan_product_or_package");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(false);
                helper.assertValidateEnabled(true);
                const line = helper.getLine();
                helper.assertLineIsHighlighted(line, false);
                helper.assertButtonIsVisible(line, "package_content");
                helper.assertButtonIsVisible(line, "add_remaining_quantity", false);
                helper.assert(
                    line.querySelector('[name="package"]').innerText,
                    "package001package001",
                );
                helper.assertLineQty(line, "0/1");
            },
        },
        {
            trigger: ".o_line_button.o_package_content",
            run: "click",
        },
        {
            trigger: ".o_kanban_view .o_kanban_record",
            run: function () {
                helper.assertKanbanRecordsCount(1);
            },
        },
        {
            trigger: "button.o_close",
            run: "click",
        },
        { trigger: ".o_barcode_lines", run: "scan package002" },
        {
            trigger: ".o_barcode_line[data-package=package002]",
            run: function () {
                helper.assertLinesCount(2);
                const [line1, line2] = helper.getLines();
                helper.assert(
                    line1.querySelector("[name=package]").innerText,
                    "package001package001",
                );
                helper.assertLineQty(line1, "0/1");
                helper.assertLineIsFaulty(line1, false);
                helper.assert(
                    line2.querySelector("[name=package]").innerText,
                    "package002package002",
                );
                helper.assertLineQty(line2, "1");
                helper.assertLineIsFaulty(line2, true);
            },
        },
        {
            trigger: ".o_barcode_line[data-package=package002] .o_delete_line",
            run: "click",
        },
        {
            trigger: ".o_barcode_lines:not(:has(.o_delete_line))",
        },
        { trigger: ".o_barcode_lines", run: "scan package001" },
        {
            trigger: ".o_barcode_line.o_line_completed",
            run: function () {
                helper.assertLinesCount(1);
                helper.assertScanMessage("scan_validate");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(true);
                helper.assertValidateEnabled(true);
                const line = helper.getLine();
                helper.assertLineIsHighlighted(line, true);
                helper.assertButtonIsVisible(line, "package_content");
                helper.assert(
                    line.querySelector('[name="package"]').innerText,
                    "package001package001",
                );
                helper.assertLineQty(line, "1/1");
            },
        },
        {
            trigger: "button.o_exit",
            run: "click",
        },

        {
            trigger: ".o_kanban_record:contains(Delivery with Stock Move)",
            run: "click",
        },
        {
            trigger: ".o_barcode_client_action",
            run: function () {
                helper.assertLinesCount(1);
                helper.assertScanMessage("scan_product");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(false);
                helper.assertValidateEnabled(true);
                const line = helper.getLine();
                helper.assertLineIsHighlighted(line, false);
                helper.assertButtonIsVisible(line, "package_content", false);
                helper.assert(
                    line.querySelector('[name="package"]').innerText,
                    "package002",
                );
                helper.assertLineQty(0, "0/2");
            },
        },
    ],
});

registry.category("web_tour.tours").add("test_define_the_destination_package", {
    steps: () => [
        {
            trigger: ".o_line_button.o_add_remaining_quantity",
            run: "click",
        },
        {
            trigger: '.o_barcode_line .qty-done:contains("1")',
            run: "scan PACK02",
        },
        {
            trigger: '.o_barcode_line:contains("PACK02")',
        },
        {
            trigger: ".btn.o_validate_page",
            run: "click",
        },
        {
            trigger: ".o_notification_bar.bg-success",
        },
    ],
});

registry.category("web_tour.tours").add("stock_barcode_package_with_lot", {
    steps: () => [
        {
            trigger: "[data-menu-xmlid='stock_barcode.stock_barcode_menu']",
            run: "click",
        },
        {
            trigger: ".o_button_inventory",
            run: "click",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan Lot-test",
        },
        {
            trigger: ".o_barcode_line .package:contains(Package-test)",
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

registry.category("web_tour.tours").add("test_scan_same_lot_different_products", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: "scan 123",
        },
        {
            trigger: ".o_notification_bar.bg-danger",
            run: "scan bbb",
        },
        {
            trigger: '.o_barcode_line:contains("bbb")',
            run: "scan 123",
        },
        {
            trigger: '.o_barcode_line:contains("bbb"):contains("123")',
            run: function () {
                helper.assertLinesCount(1);
            },
        },
    ],
});

registry.category("web_tour.tours").add("test_avoid_useless_line_creation", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: "scan LOT01",
        },
        {
            trigger: ".o_barcode_line",
            run: "scan LOREM",
        },
        {
            trigger:
                ".o_notification:has(.bg-danger):text(This product doesn't exist.)",
        },
        {
            trigger: ".o_barcode_line:first-child .o_edit",
            run: "click",
        },
        ...stepUtils.discardBarcodeForm(),
    ],
});

registry.category("web_tour.tours").add("test_setting_barcode_allow_extra_product", {
    steps: () => [
        { trigger: ".o_stock_barcode_main_menu", run: "scan delivery_test" },
        { trigger: ".o_barcode_line", run: "scan product1" },
        {
            trigger: ".o_barcode_line.o_selected.o_line_completed",
            run: "scan product2",
        },
        {
            trigger:
                ".o_notification:has(.bg-danger):text(The product product2 should not be picked in this operation.)",
        },
        { trigger: ".o_barcode_client_action", run: "scan OBTVALI" },
        { trigger: ".o_stock_barcode_main_menu", run: "scan WHOUT" },
        { trigger: ".o_barcode_client_action", run: "scan product1" },
        { trigger: ".o_barcode_line", run: "scan product2" },
        {
            trigger: ".o_barcode_line:nth-child(2)",
            run: function () {
                const lines = helper.getLines();
                helper.assert(lines.length, 2);
                helper.assertLineProduct(lines[0], "product1");
                helper.assertLineProduct(lines[1], "product2");
            },
        },
    ],
});

registry
    .category("web_tour.tours")
    .add("test_setting_barcode_allow_extra_product_with_packages", {
        steps: () => [
            {
                trigger: ".o_stock_barcode_main_menu",
                run: "scan SBAEPWP",
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan PACK04",
            },
            {
                trigger:
                    ".o_notification:has(.bg-danger):text(This package contains extra products and extra products are not allowed on this operation.)",
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan PACK01",
            },
            {
                trigger: ".o_barcode_line:contains(PACK01)",
                run: () => {
                    helper.assertLinesCount(2);
                    const [line1, line2] = helper.getLines();
                    helper.assertLineQty(line1, "0/5");
                    helper.assertLineQty(line2, "10");
                },
            },
            {
                trigger: "button.o_exit",
                run: "click",
            },
            {
                trigger: ".o_stock_barcode_main_menu",
                run: "scan SBAEPWMEP",
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan PACK04",
            },
            {
                trigger:
                    ".o_notification:has(.bg-danger):text(This package contains extra products and extra products are not allowed on this operation.)",
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan PACK03",
            },
            {
                trigger: ".o_barcode_line[data-package=PACK03]",
                run: () => {
                    helper.assertLinesCount(2);
                    const [line1, line2] = helper.getLines();
                    helper.assert(
                        line1.querySelector("[name=package]").innerText,
                        "PACK02PACK02",
                    );
                    helper.assert(
                        line2.querySelector("[name=package]").innerText,
                        "PACK03PACK03",
                    );
                },
            },
        ],
    });

registry.category("web_tour.tours").add("test_split_line_reservation", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: function () {
                helper.assertLinesCount(3);
                helper.assertScanMessage("scan_src");
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan LOC-01-00-00",
        },
        {
            trigger: ".o_scan_message.o_scan_product",
            run: "scan productlot1",
        },
        {
            trigger: ".o_scan_message.o_scan_lot",
            run: "scan LOT01",
        },
        {
            trigger: ".o_scan_message.o_scan_lot",
            run: "scan LOT02",
        },
        {
            trigger: ".o_barcode_line.o_selected .qty-done:contains(2)",
            run: "scan LOC-01-01-00",
        },
        {
            trigger:
                '.o_barcode_location_line[data-location="WH/Stock/Section 1"].text-bg-400',
            run: function () {
                helper.assertLinesCount(4);
                let line = helper.getLine({ barcode: "productlot1", completed: true });
                helper.assertLineSourceLocation(line, "WH/Stock");
                helper.assertLineQty(line, "2/2");
                line = helper.getLine({ barcode: "productlot1", completed: false });
                helper.assertLineSourceLocation(line, "WH/Stock/Section 1");
                helper.assertLineQty(line, "0/3");
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan productlot1",
        },
        {
            trigger: ".o_barcode_line.o_selected",
            run: "scan LOT02",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan LOT02",
        },
        {
            trigger: ".o_barcode_line.o_selected .qty-done:contains(2)",
            run: "scan LOC-01-02-00",
        },
        {
            trigger:
                '.o_barcode_location_line[data-location="WH/Stock/Section 2"].text-bg-400',
            run: function () {
                helper.assertLinesCount(5);
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan productlot1",
        },
        {
            trigger: ".o_barcode_line.o_selected",
            run: "scan LOT03",
        },
        {
            trigger: '.o_barcode_line .o_line_lot_name:contains("LOT03")',
            run: function () {
                const lines = helper.getLines({ barcode: "productlot1" });
                [0, 1, 2].map((i) =>
                    helper.assertLineQty(lines[i], ["2/2", "2/2", "1/1"][i]),
                );
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan LOC-01-00-00",
        },
        {
            trigger: '.o_barcode_location_line.text-bg-400[data-location="WH/Stock"]',
            run: "scan product1",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan product1",
        },
        {
            trigger: ".o_barcode_line.o_selected .qty-done:contains(2)",
            run: "scan LOC-01-01-00",
        },
        {
            trigger: '.o_barcode_line[data-barcode="product1"].o_line_completed',
            run: function () {
                helper.assertLinesCount(6);
                const lines = helper.getLines({ barcode: "product1" });
                [0, 1].map((i) => helper.assertLineQty(lines[i], ["2/2", "0/2"][i]));
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan product1",
        },
        {
            trigger: ".o_barcode_line.o_selected:not(.o_line_completed)",
            run: "scan product1",
        },
        {
            trigger: ".o_barcode_line.o_selected.o_line_completed",
            run: "scan LOC-01-00-00",
        },
        {
            trigger: '.o_barcode_location_line.text-bg-400[data-location="WH/Stock"]',
            run: "scan product2",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan product2",
        },
        {
            trigger: ".o_barcode_line.o_selected .qty-done:contains(2)",
            run: "scan LOC-01-01-00",
        },
        {
            trigger: '.o_barcode_line[data-barcode="product2"].o_line_completed',
            run: function () {
                helper.assertLinesCount(7);
                const lines = helper.getLines({ barcode: "product2" });
                [0, 1].map((i) => helper.assertLineQty(lines[i], ["2/2", "0/1"][i]));
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan product2",
        },
        { trigger: ".o_validate_page.btn-primary" },
        { trigger: ".o_barcode_line .o_edit", run: "click" },
        { trigger: ".o_discard", run: "click" },
        {
            trigger: ".o_barcode_line",
            run: function () {
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(true);
                helper.assertValidateEnabled(true);
                let lines = helper.getLines({ barcode: "product1" });
                [0, 1].map((i) => helper.assertLineQty(lines[i], ["2/2", "2/2"][i]));
                lines = helper.getLines({ barcode: "product2" });
                [0, 1].map((i) => helper.assertLineQty(lines[i], ["2/2", "1/1"][i]));
                lines = helper.getLines({ barcode: "productlot1" });
                [0, 1, 2].map((i) =>
                    helper.assertLineQty(lines[i], ["2/2", "2/2", "1/1"][i]),
                );
            },
        },
    ],
});

registry.category("web_tour.tours").add("test_split_line_on_destination_scan", {
    steps: () => [
        {
            trigger: ".o_stock_barcode_main_menu",
            run: "scan receipt_split_line_on_destination_scan",
        },
        { trigger: ".o_barcode_line", run: "scan product1" },
        { trigger: ".o_barcode_line", run: "scan product1" },
        {
            trigger: '.o_barcode_line.o_selected .qty-done:contains("2")',
            run: () => {
                helper.assertLinesCount(1);
                helper.assertLineDestinationLocation(0, "WH/Stock");
                helper.assertLineQty(0, "2/4");
            },
        },
        { trigger: ".o_barcode_line", run: "scan LOC-01-00-00" },
        {
            trigger: ".o_barcode_line:nth-child(2)",
            run: () => {
                helper.assertLinesCount(2);
                helper.assertLineDestinationLocation(0, "WH/Stock");
                helper.assertLineDestinationLocation(1, "WH/Stock");
                helper.assertLineQty(0, "2/2");
                helper.assertLineQty(1, "0/2");
            },
        },
        { trigger: ".o_barcode_line", run: "scan product1" },
        {
            trigger: ".o_barcode_line.o_selected:not(.o_line_completed)",
            run: "scan product1",
        },
        {
            trigger: ".o_barcode_line.o_selected.o_line_completed",
            run: "scan LOC-01-01-00",
        },
        {
            trigger: ".o_line_destination_location:contains('.../Section 1')",
            run: () => {
                helper.assertLinesCount(2);
                helper.assertLineDestinationLocation(0, "WH/Stock");
                helper.assertLineDestinationLocation(1, ".../Section 1");
                helper.assertLineQty(0, "2/2");
                helper.assertLineQty(1, "2/2");
            },
        },
        ...stepUtils.validateBarcodeOperation(),
        {
            trigger: ".o_stock_barcode_main_menu",
            run: "scan internal_split_line_on_destination_scan",
        },
        {
            trigger: ".o_barcode_line",
            run: () => {
                helper.assertLinesCount(2);
                helper.assertLineLocations(0, "WH/Stock/Section 1", "WH/Stock");
                helper.assertLineQty(0, "0/3");
                helper.assertLineLocations(1, "WH/Stock/Section 2", "WH/Stock");
                helper.assertLineQty(1, "0/4");
            },
        },
        { trigger: ".o_scan_message.o_scan_src", run: "scan LOC-01-01-00" },
        { trigger: ".o_barcode_line", run: "scan product2" },
        { trigger: ".o_barcode_line", run: "scan product2" },
        {
            trigger: '.o_barcode_line.o_selected .qty-done:contains("2")',
            run: "scan shelf3",
        },
        {
            trigger: ".o_scan_message.o_scan_src",
            run: () => {
                helper.assertLinesCount(3);
                helper.assertLineLocations(0, "WH/Stock/Section 1", ".../Section 3");
                helper.assertLineQty(0, "2/2");
                helper.assertLineLocations(1, "WH/Stock/Section 1", "WH/Stock");
                helper.assertLineQty(1, "0/1");
                helper.assertLineLocations(2, "WH/Stock/Section 2", "WH/Stock");
                helper.assertLineQty(2, "0/4");
            },
        },
        { trigger: ".o_barcode_line", run: "scan LOC-01-01-00" },
        { trigger: ".o_scan_message.o_scan_product", run: "scan product2" },
        {
            trigger: ".o_barcode_line.o_selected.o_line_completed",
            run: "scan LOC-01-00-00",
        },
        {
            trigger: ".o_scan_message.o_scan_src",
            run: () => {
                helper.assertLinesCount(3);
                helper.assertLineLocations(0, "WH/Stock/Section 1", ".../Section 3");
                helper.assertLineQty(0, "2/2");
                helper.assertLineLocations(1, "WH/Stock/Section 1", "WH/Stock");
                helper.assertLineQty(1, "1/1");
                helper.assertLineLocations(2, "WH/Stock/Section 2", "WH/Stock");
                helper.assertLineQty(2, "0/4");
            },
        },
        { trigger: ".o_barcode_line", run: "scan LOC-01-02-00" },
        { trigger: ".o_scan_message.o_scan_product", run: "scan product2" },
        { trigger: ".o_scan_message.o_scan_product_or_dest", run: "scan product2" },
        {
            trigger: '.o_barcode_line.o_selected .qty-done:contains("2")',
            run: "scan LOC-01-02-00",
        },
        {
            trigger: ".o_scan_message.o_scan_src",
            run: () => {
                helper.assertLinesCount(4);
                helper.assertLineLocations(0, "WH/Stock/Section 1", ".../Section 3");
                helper.assertLineQty(0, "2/2");
                helper.assertLineLocations(1, "WH/Stock/Section 1", "WH/Stock");
                helper.assertLineQty(1, "1/1");
                helper.assertLineLocations(2, "WH/Stock/Section 2", ".../Section 2");
                helper.assertLineQty(2, "2/2");
                helper.assertLineLocations(3, "WH/Stock/Section 2", "WH/Stock");
                helper.assertLineQty(3, "0/2");
            },
        },
        { trigger: ".o_scan_message.o_scan_src", run: "scan LOC-01-02-00" },
        { trigger: ".o_scan_message.o_scan_product", run: "scan product2" },
        { trigger: ".o_scan_message.o_scan_product_or_dest", run: "scan product2" },
        { trigger: ".o_scan_message.o_scan_dest", run: "scan LOC-01-01-00" },
        ...stepUtils.validateBarcodeOperation(".o_validate_page.btn-primary"),
    ],
});

registry.category("web_tour.tours").add("test_split_line_on_exit_for_delivery", {
    steps: () => [
        {
            trigger: ".o_stock_barcode_main_menu",
            run: "scan delivery_split_line_on_exit",
        },
        {
            trigger: ".o_barcode_client_action",
            run: () => {
                helper.assertLinesCount(3);
                helper.assertLineProduct(0, "product1");
                helper.assertLineQty(0, "0/4");
                helper.assertLineProduct(1, "product2");
                helper.assertLineQty(1, "0/4");
                helper.assertLineProduct(2, "product3");
                helper.assertLineQty(2, "0/2");
            },
        },
        { trigger: ".o_barcode_client_action", run: "scan product1" },
        { trigger: ".o_barcode_client_action", run: "scan product1" },
        { trigger: ".o_barcode_client_action", run: "scan product1" },
        { trigger: ".o_barcode_client_action", run: "scan product1" },
        {
            trigger: ".o_barcode_line.o_selected.o_line_completed",
            run: "scan product2",
        },
        {
            trigger: ".o_barcode_line.o_selected:not(.o_line_completed)",
            run: "scan product2",
        },
        { trigger: ".o_barcode_line.o_selected .qty-done:contains(2)" },
        { trigger: "button.o_exit", run: "click" },
        { trigger: ".o_stock_barcode_main_menu" },
    ],
});

registry.category("web_tour.tours").add("test_split_line_on_exit_for_receipt", {
    steps: () => [
        {
            trigger: ".o_stock_barcode_main_menu",
            run: "scan receipt_split_line_on_exit",
        },
        {
            trigger: ".o_barcode_client_action",
            run: () => {
                helper.assertLinesCount(2);
                helper.assertLineProduct(0, "product1");
                helper.assertLineQty(0, "0/4");
                helper.assertLineProduct(1, "product2");
                helper.assertLineQty(1, "0/4");
            },
        },
        { trigger: ".o_barcode_client_action", run: "scan product1" },
        { trigger: ".o_barcode_line.o_selected", run: "scan OBTPACK" },
        { trigger: ".o_barcode_line.o_selected .result-package", run: "scan product1" },
        {
            trigger: ".o_barcode_line.o_selected.o_line_not_completed",
            run: "scan product1",
        },
        {
            trigger: ".o_barcode_line.o_selected .qty-done:contains('2')",
            run: "scan product2",
        },
        {
            trigger: ".o_barcode_line.o_selected .qty-done:contains('1')",
            run: () => {
                helper.assertLinesCount(3);
                const [line1, line2, line3] = helper.getLines();
                helper.assertLineProduct(line1, "product1");
                helper.assertLineQty(line1, "2/3");
                helper.assertLineProduct(line2, "product2");
                helper.assertLineQty(line2, "1/4");
                helper.assertLineProduct(line3, "product1");
                helper.assertLineQty(line3, "1/1");
                helper.assert(
                    line3.querySelector(".result-package").innerText,
                    "PACK0001000",
                );
            },
        },
        {
            trigger: "button.o_exit",
            run: "click",
        },
        {
            trigger: ".o_stock_barcode_main_menu",
            run: "scan receipt_split_line_on_exit",
        },
        {
            trigger: ".o_barcode_client_action",
            run: () => {
                helper.assertLinesCount(5);
                const [line1, line2, line3, line4, line5] = helper.getLines();
                helper.assertLineProduct(line1, "product1");
                helper.assertLineQty(line1, "0/1");
                helper.assertLineProduct(line2, "product2");
                helper.assertLineQty(line2, "0/3");
                helper.assertLineProduct(line3, "product1");
                helper.assertLineQty(line3, "2/2");
                helper.assertLineProduct(line4, "product1");
                helper.assertLineQty(line4, "1/1");
                helper.assert(
                    line4.querySelector(".result-package").innerText,
                    "PACK0001000",
                );
                helper.assertLineProduct(line5, "product2");
                helper.assertLineQty(line5, "1/1");
            },
        },
    ],
});

registry.category("web_tour.tours").add("test_split_line_on_scan", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: "scan product2",
        },
        {
            trigger: ".o_barcode_line.o_selected .qty-done:contains(1)",
            run: "scan product2",
        },
        {
            trigger: ".o_barcode_line.o_selected .qty-done:contains(2)",
            run: "scan THEPACK1",
        },
        {
            trigger: '.o_barcode_line[data-barcode="product2"].o_line_completed',
            run: function () {
                helper.assertLinesCount(2);
                [0, 1].map((i) => helper.assertLineQty(i, ["0/3", "2/2"][i]));
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan THEPACK2",
        },
        {
            trigger:
                '.o_barcode_line.o_selected:contains("THEPACK2") .qty-done:contains(0)',
            run: function () {
                helper.assertLinesCount(2);
                const lines = helper.getLines({ barcode: "product2" });
                helper.assert(
                    lines[0].querySelector(".result-package").innerText,
                    "THEPACK2",
                );
                helper.assert(
                    lines[1].querySelector(".result-package").innerText,
                    "THEPACK1",
                );
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan product2",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan product2",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan product2",
        },
        {
            trigger: ".o_validate_page",
            run: function () {
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(true);
                helper.assertValidateEnabled(true);
                helper.assertLinesCount(2);
                [0, 1].map((i) => helper.assertLineQty(i, ["3/3", "2/2"][i]));
            },
        },
        {
            trigger: ".btn.o_validate_page",
            run: "click",
        },
        { trigger: ".o_notification_bar.bg-success" },
    ],
});

registry
    .category("web_tour.tours")
    .add("test_split_line_on_exit_for_receipt_with_grouped_lot", {
        steps: () => [
            { trigger: ".o_stock_barcode_main_menu", run: "scan SPLOEFRWGL" },
            {
                trigger: ".o_barcode_client_action",
                run: () => {
                    helper.assertLinesCount(1);
                    helper.assertLineProduct(0, "productlot1");
                    helper.assertLineQty(0, "0/3");
                },
            },
            {
                trigger: ".o_edit .fa-pencil",
                run: "click",
            },
            {
                trigger: ".o_digipad_increment",
                run: "click",
            },
            {
                trigger: ".o_save",
                run: "click",
            },
            {
                trigger: ".o_barcode_line_details",
                run: () => {
                    helper.assertLinesCount(1);
                    helper.assertLineQty(0, "1/3");
                },
            },
            { trigger: "button.o_exit", run: "click" },
            { trigger: ".o_stock_barcode_main_menu", run: "scan SPLOEFRWGL" },
            {
                trigger: ".o_barcode_line_details",
                run: () => {
                    helper.assertLinesCount(1);
                    helper.assertLineQty(0, "1/3");
                },
            },
            {
                trigger: ".o_add_remaining_quantity",
                run: "click",
            },
            {
                trigger: ".o_barcode_line .qty-done:contains(3)",
                run: () => {
                    helper.assertLinesCount(1);
                    helper.assertLineQty(0, "3/3");
                },
            },
            { trigger: "button.o_exit", run: "click" },
            { trigger: ".o_stock_barcode_main_menu", run: "scan SPLOEFRWGL" },
            {
                trigger: ".o_barcode_line .qty-done:contains(3)",
                run: () => {
                    helper.assertLinesCount(1);
                    helper.assertLineQty(0, "3/3");
                },
            },
        ],
    });

registry.category("web_tour.tours").add("test_editing_done_picking", {
    steps: () => [
        { trigger: ".o_barcode_client_action", run: "scan OBTVALI" },
        {
            trigger:
                ".o_notification:has(.bg-danger):text(This picking is already done)",
        },
    ],
});

registry.category("web_tour.tours").add("test_barcode_picking_return", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
        },
        {
            trigger: "span.o_scan_message:contains('This picking is already done')",
        },
        {
            trigger: "button.o_create_return",
            run: "click",
        },
        {
            trigger: "span.o_scan_message:contains('Scan a product')",
        },
        {
            trigger: '.o_barcode_line_title > div.o_product_label:contains("product2")',
        },
        {
            trigger: "span.o_scan_message:contains('Scan a product')",
            run: "scan product1",
        },
        ...stepUtils.confirmAddingUnreservedProduct(),
        {
            trigger: '.o_barcode_line_title > div.o_product_label:contains("product1")',
        },
        {
            trigger: "button.o_validate_page",
            run: "click",
        },
        { trigger: ".o_notification_bar.bg-success" },
    ],
});

registry.category("web_tour.tours").add("test_split_uncomplete_moves_on_exit", {
    steps: () => [
        {
            trigger: ".o_barcode_line",
            run: "scan product1",
        },
        {
            trigger: ".o_barcode_line[data-barcode='product1'] .qty-done:contains('1')",
        },
        {
            trigger: ".o_edit .fa-pencil",
            run: "click",
        },
        {
            trigger: ".o_field_widget[name='qty_done'] input",
        },
        {
            content: "Exit the barcode app to look at look at back end data.",
            trigger: ".o_field_widget[name=product_id] a.o_form_uri",
            run: "click",
        },
        {
            trigger: ".breadcrumb-item.o_back_button",
        },
        {
            content: "Come back to the record in the barcode App.",
            trigger: ".breadcrumb-item.o_back_button",
            run: "click",
        },
        {
            trigger: ".o_barcode_client_action",
        },
        {
            trigger: ".o_barcode_client_action",
            run: () => {
                helper.assertLinesCount(3);
                helper.assertLineQty(0, "0/3");
                helper.assertLineQty(1, "0/5");
                helper.assertLineQty(2, "1/1");
            },
        },
        {
            trigger: ".o_barcode_line",
            run: "scan product2",
        },
        {
            trigger: ".o_barcode_line[data-barcode='product2'] .qty-done:contains('1')",
        },
        {
            trigger: ".o_edit .fa-pencil",
            run: "click",
        },
        {
            trigger: ".o_field_widget[name='qty_done'] input",
        },
        {
            content: "Exit the barcode app to look at look at back end data.",
            trigger: ".o_field_widget[name=product_id] a.o_form_uri",
            run: "click",
        },
        {
            trigger: ".breadcrumb-item.o_back_button",
        },
        {
            content: "Come back to the record in the barcode App.",
            trigger: ".breadcrumb-item.o_back_button",
            run: "click",
        },
        {
            trigger: ".o_barcode_client_action",
        },
        {
            trigger: ".o_barcode_client_action",
            run: () => {
                helper.assertLinesCount(4);
                helper.assertLineQty(0, "0/3");
                helper.assertLineQty(1, "0/4");
                helper.assertLineQty(2, "1/1");
                helper.assertLineQty(3, "1/1");
            },
        },
    ],
});

registry
    .category("web_tour.tours")
    .add("test_split_uncomplete_manually_assigned_moves_on_exit", {
        steps: () => [
            {
                trigger: ".o_barcode_line",
                run: "scan product1",
            },
            {
                trigger:
                    ".o_barcode_line[data-barcode='product1'] .qty-done:contains('1')",
                run() {},
            },
            {
                trigger: "button.o_exit",
                run: "click",
            },
            {
                trigger: ".o_stock_barcode_main_menu",
                run: "scan SUMAMOE",
            },
            {
                trigger: ".o_barcode_client_action",
                run: () => {
                    helper.assertLinesCount(2);
                    helper.assertLineQty(0, "0/2");
                    helper.assertLineQty(1, "1/1");
                },
            },
        ],
    });

registry.category("web_tour.tours").add("test_sml_sort_order_by_product_category", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: () => {
                helper.assertLinesCount(3);
                const line1 = document.querySelector(".o_barcode_line:first-child");
                helper.assertLineProduct(line1, "Product B");
                const line2 = document.querySelector(".o_barcode_line:nth-child(2)");
                helper.assertLineProduct(line2, "Product A");
                const line3 = document.querySelector(".o_barcode_line:last-child");
                helper.assertLineProduct(line3, "Product C");
            },
        },
    ],
});

registry.category("web_tour.tours").add("test_barcode_signature_flow", {
    steps: () => [
        {
            trigger:
                "div[name='o_kanban_record_title'] > span:contains(Delivery Orders)",
            run: "click",
        },
        {
            trigger: "button > span:contains(Delivery Order 1)",
            run: "click",
        },
        {
            trigger: "button.o_validate_page",
            run: "click",
        },
        {
            trigger: "a.o_web_sign_auto_button",
            run: "click",
        },
        {
            trigger: ".modal-footer button.btn-primary:enabled",
            run: "click",
        },
        { trigger: ".o_kanban_tip_filter" },
        {
            trigger: "button > span:contains(Delivery Order 2)",
            run: "click",
        },
        {
            trigger: "button.o_barcode_actions",
            run: "click",
        },
        {
            trigger: "button.o_sign",
            run: "click",
        },
        {
            trigger: "a.o_web_sign_auto_button",
            run: "click",
        },
        {
            trigger: ".modal-footer button.btn-primary:enabled",
            run: "click",
        },
        {
            trigger: "button.o_validate_page",
            run: "click",
        },
        { trigger: ".o_kanban_tip_filter" },
    ],
});

registry.category("web_tour.tours").add("test_create_backorder_after_qty_modified", {
    steps: () => [
        { trigger: ".o_edit", run: "click" },
        { trigger: ".o_digipad_increment", run: "click" },
        { trigger: ".o_save", run: "click" },
        { trigger: ".o_validate_page", run: "click" },
        { trigger: ".modal-dialog button.btn-primary", run: "click" },
    ],
});

registry.category("web_tour.tours").add("test_barcode_lazy_cache_scan_two_lots", {
    steps: () => [
        { trigger: ".o_barcode_line", run: "scan SN-001" },
        { trigger: ".o_barcode_line", run: "scan SN-002" },
        { trigger: ".o_barcode_scanner_qty .qty-done:contains(2)" },
    ],
});

registry
    .category("web_tour.tours")
    .add("test_open_picking_dont_override_assigned_user", {
        steps: () => [
            {
                trigger: ".o_button_operations",
                run: "click",
            },
            {
                trigger: "div[name='o_kanban_record_title'] > span:contains(Receipts)",
                run: "click",
            },
            {
                trigger: '.o_facet_value:contains("To Do") + .o_facet_remove',
                run: "click",
            },
            {
                trigger: '.btn > span:contains("test_responsible_receipt")',
                run: "click",
            },
            {
                trigger: ".o_exit",
                run: "click",
            },
            {
                trigger: ".o_breadcrumb > ol > li > a:contains(Operations)",
            },
            {
                content: `Wait kanban is rendered before closing the tour or The following error occurred in onWillStart: "Component is destroyed" can occurs`,
                trigger:
                    ".o_kanban_renderer:has(.o_kanban_record:contains(test_responsible_receipt))",
            },
        ],
    });

registry.category("web_tour.tours").add("test_serial_product_packaging", {
    steps: () => [
        { trigger: ".o_stock_barcode_main_menu", run: "scan WHIN" },
        { trigger: ".o_barcode_client_action", run: "scan PCK4" },
        {
            trigger: ".o_barcode_line.o_highlight",
            run: function () {
                helper.assertLinesCount(1);
                helper.assertScanMessage("scan_serial");
                helper.assertLineProduct(0, "productserial1");
                helper.assertLineQty(0, "0/4 Units");
                helper.assertButtonIsVisible(0, "toggle_sublines", false);
                helper.assertButtonIsVisible(0, "edit");
            },
        },
        { trigger: ".o_barcode_client_action", run: "scan sn1,sn2,sn3,sn4" },
        {
            trigger:
                ".o_barcode_line.o_selected.o_line_completed .o_line_button.o_toggle_sublines",
            run: "click",
        },
        {
            trigger: ".o_barcode_line.o_selected .o_sublines",
            run: function () {
                const line = helper.getLine();
                helper.assertLineQty(line, "4/4 Units");
                helper.assertSublinesCount(4);
                const sublines = helper.getSublines();
                helper.assertLinesTrackingNumbers(sublines, [
                    "sn4",
                    "sn3",
                    "sn2",
                    "sn1",
                ]);
                helper.assertLineQty(sublines[0], "1 Units");
                helper.assertLineQty(sublines[1], "1 Units");
                helper.assertLineQty(sublines[2], "1 Units");
                helper.assertLineQty(sublines[3], "1 Units");
            },
        },
    ],
});

registry.category("web_tour.tours").add("test_scan_package_with_different_uom", {
    steps: () => [
        { trigger: ".o_barcode_client_action", run: "scan LOC-01-00-00" },
        {
            trigger: ".o_barcode_client_action",
            run: function () {
                helper.assertLinesCount(2);
                helper.assertLineQty(0, "0/10000 g");
                helper.assertLineProduct(0, "product1");
                helper.assertLineQty(1, "0/8 kg");
                helper.assertLineProduct(1, "product2");
            },
        },
        { trigger: ".o_barcode_client_action", run: "scan package001" },
        { trigger: ".o_barcode_line.o_line_completed", run: "scan package002" },
        {
            trigger: ".o_validate_page.btn-primary",
            run: function () {
                helper.assertLinesCount(3);
                helper.assertLineQty(0, "10000/10000 g");
                helper.assertLineProduct(0, "product1");
                helper.assertLineQty(1, "8/8 kg");
                helper.assertLineProduct(1, "product2");
                helper.assertLineQty(2, "2000 g");
                helper.assertLineProduct(2, "product2");
            },
        },
    ],
});

registry
    .category("web_tour.tours")
    .add("test_scan_packaging_on_picking_with_mixed_uom", {
        steps: () => [
            {
                trigger: ".o_stock_barcode_main_menu",
                run: "scan SPOPWMU1",
            },
            {
                trigger: ".o_barcode_line",
                run: () => {
                    helper.assertLinesCount(1);
                    helper.assertLineQty(0, "0/2 Pack of 6");
                },
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan love",
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan love",
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan love",
            },
            {
                trigger: ".o_barcode_line .qty-done:contains(0.5)",
                run: () => {
                    helper.assertLinesCount(1);
                    helper.assertLineQty(0, "0.5/2 Pack of 6");
                },
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan 6love",
            },
            {
                trigger: ".o_barcode_line .qty-done:contains(1.5)",
                run: () => {
                    helper.assertLinesCount(1);
                    helper.assertLineQty(0, "1.5/2 Pack of 6");
                },
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan love",
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan love",
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan love",
            },
            {
                trigger: ".o_barcode_line .qty-done:contains(2)",
                run: () => {
                    helper.assertLinesCount(1);
                    helper.assertLineQty(0, "2/2 Pack of 6");
                },
            },
            {
                trigger: ".o_validate_page",
                run: "click",
            },
            {
                trigger: ".o_notification:has(.bg-success) .o_notification_close",
                run: "click",
            },
            {
                trigger: ".o_stock_barcode_main_menu",
                run: "scan SPOPWMU2",
            },
            {
                trigger: ".o_barcode_line",
                run: () => {
                    helper.assertLinesCount(1);
                    helper.assertLineQty(0, "0/12 Units");
                    const line = helper.getLine({ barcode: "love" });
                    helper.assert(
                        line.querySelector(".o_packaging").innerText,
                        "Packaging: 2 Pack of 6",
                    );
                },
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan 12love",
            },
            {
                trigger: ".o_barcode_line .qty-done:contains('1')",
                run: () => {
                    helper.assertLinesCount(2);
                    helper.assertLineQty(0, "0/12 Units");
                    helper.assertLineQty(1, "1 Dozens");
                },
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan 6love",
            },
            {
                trigger: ".o_barcode_line .qty-done:contains('6')",
                run: () => {
                    helper.assertLinesCount(2);
                    helper.assertLineQty(0, "6/12 Units");
                    helper.assertLineQty(1, "1 Dozens");
                },
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan love",
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan love",
            },
            {
                trigger: ".o_barcode_line .qty-done:contains('8')",
                run: () => {
                    helper.assertLinesCount(2);
                    helper.assertLineQty(0, "8/12 Units");
                    helper.assertLineQty(1, "1 Dozens");
                },
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan 6love",
            },
            {
                trigger: ".o_barcode_line .qty-done:contains('2')",
                run: () => {
                    helper.assertLinesCount(3);
                    helper.assertLineQty(0, "12/12 Units");
                    helper.assertLineQty(1, "2 Units");
                    helper.assertLineQty(2, "1 Dozens");
                    const [line1, line2, line3] = helper.getLines({ barcode: "love" });
                    helper.assert(
                        line1.querySelector(".o_packaging").innerText,
                        "Packaging: 2 Pack of 6",
                    );
                    helper.assert(line2.querySelector(".o_packaging"), null);
                    helper.assert(line3.querySelector(".o_packaging"), null);
                },
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan 6love",
            },
            {
                trigger: ".o_barcode_line .o_line_uom:contains('Pack')",
                run: () => {
                    helper.assertLinesCount(4);
                    helper.assertLineQty(0, "12/12 Units");
                    helper.assertLineQty(1, "2 Units");
                    helper.assertLineQty(2, "1 Pack of 6");
                    helper.assertLineQty(3, "1 Dozens");
                },
            },
            {
                trigger: ".o_validate_page",
                run: "click",
            },
            {
                trigger: ".o_notification:has(.bg-success) .o_notification_close",
                run: "click",
            },
            {
                trigger: ".o_stock_barcode_main_menu",
                run: "scan SPOPWMU3",
            },
            {
                trigger: ".o_barcode_line",
                run: () => {
                    helper.assertLinesCount(2);
                    helper.assertLineQty(0, "0/10 Units");
                    helper.assertLineQty(1, "0/1 Pack of 6");
                },
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan 6love",
            },
            {
                trigger: ".o_barcode_line .qty-done:contains(1)",
                run: () => {
                    helper.assertLinesCount(2);
                    helper.assertLineQty(0, "0/10 Units");
                    helper.assertLineQty(1, "1/1 Pack of 6");
                },
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan 6love",
            },
            {
                trigger: ".o_barcode_line .qty-done:contains(6)",
                run: () => {
                    helper.assertLinesCount(2);
                    helper.assertLineQty(0, "6/10 Units");
                    helper.assertLineQty(1, "1/1 Pack of 6");
                },
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan 6love",
            },
            {
                trigger: ".o_barcode_line .qty-done:contains(2)",
                run: () => {
                    helper.assertLinesCount(3);
                    helper.assertLineQty(0, "10/10 Units");
                    helper.assertLineQty(1, "2 Units");
                    helper.assertLineQty(2, "1/1 Pack of 6");
                },
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan love",
            },
            {
                trigger: ".o_barcode_line .qty-done:contains(3)",
                run: () => {
                    helper.assertLinesCount(3);
                    helper.assertLineQty(0, "10/10 Units");
                    helper.assertLineQty(1, "3 Units");
                    helper.assertLineQty(2, "1/1 Pack of 6");
                },
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan 6love",
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan 6love",
            },
            {
                trigger: ".o_barcode_line .qty-done:contains(2)",
                run: () => {
                    helper.assertLinesCount(4);
                    helper.assertLineQty(0, "10/10 Units");
                    helper.assertLineQty(1, "3 Units");
                    helper.assertLineQty(2, "2 Pack of 6");
                    helper.assertLineQty(3, "1/1 Pack of 6");
                },
            },
            {
                trigger: ".o_validate_page",
                run: "click",
            },
            {
                trigger: ".o_notification_bar.bg-success",
                run() {},
            },
        ],
    });

registry.category("web_tour.tours").add("test_remove_sublines_and_scan_serial_again", {
    steps: () => [
        { trigger: ".o_barcode_line:nth-child(1)", run: "click" },
        { trigger: ".o_barcode_line.o_selected", run: "scan abc1" },
        { trigger: ".o_barcode_line.o_selected", run: "scan abc2" },
        { trigger: ".o_barcode_line.o_selected", run: "scan abc3" },
        {
            trigger:
                ".o_barcode_line_summary:has(.qty-done:contains(3)) .o_toggle_sublines",
            run: "click",
        },
        {
            trigger:
                ".o_sublines .o_barcode_line:has(.o_line_lot_name:contains('abc1'))",
            run: "click",
        },
        {
            trigger:
                ".o_sublines .o_barcode_line.o_selected:has(.o_line_lot_name:contains('abc1')) .o_remove_unit",
            run: "click",
        },
        { trigger: ".o_sublines:not(:has(.o_line_lot_name:contains('abc1'))" },
        {
            trigger:
                ".o_sublines .o_barcode_line:has(.o_line_lot_name:contains('abc2'))",
            run: "click",
        },
        {
            trigger:
                ".o_sublines .o_barcode_line.o_selected:has(.o_line_lot_name:contains('abc2')) .o_remove_unit",
            run: "click",
        },
        {
            trigger:
                ".o_barcode_line_summary:has(.qty-done:contains(1)) .o_remove_unit",
            run: "click",
        },
        { trigger: ".o_barcode_line_summary:has(.qty-done:contains(0))" },
        { trigger: ".o_barcode_line", run: "scan abc3" },
        { trigger: ".o_barcode_line", run: "scan abc2" },
        { trigger: ".o_barcode_line", run: "scan abc1" },
        {
            trigger:
                ".o_barcode_line:nth-child(1) .o_barcode_line_details:contains(3/3)",
        },
        ...stepUtils.validateBarcodeOperation(),
    ],
});

registry.category("web_tour.tours").add("test_multi_company_record_access_in_barcode", {
    steps: () => [
        { trigger: ".o_stock_barcode_main_menu", run: "scan company2_receipt" },
        { trigger: ".o_barcode_client_action", run: "scan company1_product" },
        {
            trigger:
                ".o_notification:has(.bg-danger):text(This product doesn't exist.)",
        },
        { trigger: ".o_barcode_client_action", run: "scan company2_product" },
        { trigger: ".o_barcode_line" },
        { trigger: ".btn.o_validate_page", run: "click" },
        { trigger: ".o_stock_barcode_main_menu" },
    ],
});

registry.category("web_tour.tours").add("test_no_zero_demand_new_line_from_split", {
    steps: () => [
        { trigger: ".o_stock_barcode_main_menu", run: "scan TNZDNLFS picking" },
        { trigger: ".o_edit", run: "click" },
        { trigger: "button.o_digipad_increment", run: "click" },
        { trigger: ".o_save", run: "click" },
        { trigger: ".o_barcode_line" },
        { trigger: ".o_exit", run: "click" },
        { trigger: ".o_stock_barcode_main_menu", run: "scan TNZDNLFS picking" },
        { trigger: ".o_edit", run: "click" },
        { trigger: "button.o_digipad_decrement", run: "click" },
        { trigger: ".o_save", run: "click" },
        { trigger: ".o_barcode_line" },
        { trigger: ".o_exit", run: "click" },
        { trigger: ".o_stock_barcode_main_menu" },
    ],
});

registry.category("web_tour.tours").add("test_barcode_pack_lot_tour", {
    steps: () => [
        { trigger: ".o_barcode_line", run: "scan LOT005" },
        { trigger: ".o_barcode_line .o_line_lot_name:contains(LOT005)" },
        { trigger: "button.o_put_in_pack", run: "click" },
        { trigger: ".o_line_button.o_toggle_sublines", run: "click" },
        { trigger: ".o_barcode_line:nth-child(2):has(.fa-archive):contains(LOT005)" },
        { trigger: ".o_barcode_line_summary", run: "click" },
        { trigger: ".o_barcode_line_summary", run: "scan LOT005" },
        {
            trigger:
                ".o_barcode_line.o_line_not_completed:contains(LOT005):not(:has(.fa-archive))",
        },
        { trigger: "button.o_put_in_pack", run: "click" },
        { trigger: ".o_barcode_line:nth-child(3):has(.fa-archive)" },
        { trigger: ".o_barcode_line_summary", run: "scan LOT004" },
        { trigger: ".o_barcode_line_summary span.qty-done:contains(3)" },
        { trigger: "button.o_put_in_pack", run: "click" },
        { trigger: ".o_barcode_line:nth-child(4):has(.fa-archive)" },
        { trigger: ".o_barcode_line_summary", run: "click" },
        { trigger: ".o_barcode_line_summary", run: "scan LOT004" },
        { trigger: ".o_barcode_line_summary span.qty-done:contains(4)" },
        { trigger: "button.o_put_in_pack", run: "click" },
        { trigger: ".o_barcode_line:nth-child(1):has(.fa-archive)" },
        { trigger: ".btn.o_validate_page", run: "click" },
        { trigger: ".o_notification_bar.bg-success" },
    ],
});

registry
    .category("web_tour.tours")
    .add("test_barcode_create_serials_in_batch_with_single_scan", {
        steps: () => [
            { trigger: ".o_barcode_line", run: "scan productlot1" },
            {
                trigger: ".o_barcode_line",
                run:
                    "scan " +
                    Array.from(
                        { length: 100 },
                        (_, i) => `SN${(i + 1).toString().padStart(4, "0")}`,
                    ).join(";"),
            },
            { trigger: ".o_barcode_scanner_qty .qty-done:contains(100)" },
        ],
    });

registry
    .category("web_tour.tours")
    .add("test_scan_location_destination_for_internal_transfers", {
        steps: () => [
            {
                trigger: ".o_button_operations",
                run: "click",
            },
            {
                trigger:
                    ".o_barcode_picking_type:has(div[name='o_kanban_record_title']:contains('Internal Transfers'))",
                run: "click",
            },
            {
                trigger: "button.o-kanban-button-new",
            },
            {
                trigger: "button.o-kanban-button-new",
                run: "click",
            },
            {
                trigger: "button.o_add_line:contains('Add Product')",
                run: "click",
            },
            {
                trigger: ".o_field_widget[name='product_id'] input.o_input",
                run: "click",
            },
            {
                trigger: ".o_field_widget[name='product_id'] input.o_input",
                run: "edit Lovely Product",
            },
            {
                trigger: ".dropdown-item:contains('Lovely Product')",
                run: "click",
            },
            {
                trigger: ".o_save",
                run: "click",
            },
            {
                trigger: ".o_scan_message.o_scan_product_or_dest",
            },
            {
                trigger: ".o_barcode_line",
                run: "scan WH-LOVE",
            },
            {
                trigger: "div[name='destination_location']:contains(Lovely)",
            },
            {
                trigger: ".o_validate_page",
                run: "click",
            },
            {
                trigger: ".o_notification_bar.bg-success",
            },
        ],
    });

registry.category("web_tour.tours").add("test_scan_product_when_in_form_view", {
    steps: () => [
        { trigger: ".o_stock_barcode_main_menu", run: "scan shelf3" },
        { trigger: ".o_barcode_client_action", run: "scan product1" },
        { trigger: ".o_barcode_line .o_edit", run: "click" },
        { trigger: ".o_field_widget[name=qty_done] input", run: "edit 5" },
        { trigger: ".o_barcode_line_form", run: "scan product2" },
        {
            trigger: ".o_barcode_line_form",
            run: () => {
                helper.assertFormQuantity("5");
            },
        },
        { trigger: ".o_save", run: "click" },
        ...stepUtils.validateBarcodeOperation(".o_barcode_line .qty-done:contains(5)"),
    ],
});

registry
    .category("web_tour.tours")
    .add("test_fetch_archived_records_in_lazy_barcode_cache", {
        steps: () => [
            {
                trigger: "button.o_add_remaining_quantity",
                run: "click",
            },
            {
                trigger: ".o_validate_page",
                run: "click",
            },
            {
                trigger: ".o_notification_bar.bg-success",
                run() {},
            },
        ],
    });

registry.category("web_tour.tours").add("test_validate_uncomplete_return", {
    steps: () => [
        { trigger: ".o_stock_barcode_main_menu", run: "scan TEST/IN/0001" },
        { trigger: ".o_barcode_client_action", run: "scan product1" },
        { trigger: ".o_barcode_line", run: "scan product1" },
        ...stepUtils.validateBarcodeOperation(".o_barcode_line.o_line_completed"),
        { trigger: ".o_stock_barcode_main_menu", run: "scan TEST/IN/0001" },
        { trigger: "button.o_create_return", run: "click" },
        { trigger: ".o_barcode_line", run: "scan product1" },
        ...stepUtils.validateBarcodeOperation(".o_barcode_line.o_selected"),
        { trigger: ".o_web_client:not(.modal-open)" },
    ],
});

registry.category("web_tour.tours").add("test_select_with_same_product_and_lot", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: () => {
                helper.assertLinesCount(1);
                helper.assertValidateVisible(true);
                helper.assertValidateEnabled(true);
            },
        },
        {
            trigger: ".o_line_button.o_toggle_sublines",
            run: "click",
        },
        {
            trigger: ".o_sublines .o_barcode_line",
            run: () => {
                const sublines = document.querySelectorAll(
                    ".o_sublines .o_barcode_line",
                );
                helper.assert(sublines.length, 2, "it should have 2 sublines");
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan LOC-01-00-00",
        },
        {
            trigger: ".o_sublines .o_barcode_line:last-child",
            run: "click",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan lot_xyz",
        },
        {
            trigger: '.o_barcode_scanner_qty .qty-done:contains("1")',
            run() {},
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan lot_xyz",
        },
        {
            trigger: '.o_barcode_scanner_qty .qty-done:contains("2")',
            run() {},
        },
        {
            trigger: ".o_barcode_lines",
            run: () => {
                const line1 = document.querySelector(
                    ".o_sublines .o_barcode_line:first-child",
                );
                const line2 = document.querySelector(
                    ".o_sublines .o_barcode_line:last-child",
                );
                helper.assert(
                    line1.querySelector(".o_barcode_scanner_qty .qty-done").innerText,
                    "0",
                    "No product should be scanned for the first line",
                );
                helper.assert(
                    line2.querySelector(".o_barcode_scanner_qty .qty-done").innerText,
                    "2",
                    "2 products should be scanned for the second line",
                );
            },
        },
        {
            trigger: ".o_sublines .o_barcode_line:first-child",
            run: "click",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan lot_xyz",
        },
        {
            trigger: '.o_barcode_scanner_qty .qty-done:contains("3")',
            run() {},
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan lot_xyz",
        },
        {
            trigger: '.o_barcode_scanner_qty .qty-done:contains("4")',
            run() {},
        },
        {
            trigger: ".o_barcode_line.o_line_completed",
            run: () => {
                helper.assertLinesCount(1);
                helper.assert(
                    document.querySelectorAll(
                        ".o_sublines .o_barcode_line.o_line_completed",
                    ).length,
                    2,
                    "Both sublines should be completed",
                );
            },
        },
    ],
});

registry.category("web_tour.tours").add("test_quant_selection_delivery_picking", {
    steps: () => [
        {
            trigger: ".o_barcode_line",
            run: function () {
                helper.assertLinesCount(1);
                helper.assertLineProduct(0, "product1");
                helper.assertLineQty(0, "0/2");
                helper.assertScanMessage("scan_src");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(false);
                helper.assertValidateEnabled(true);
                helper.assertLineIsHighlighted(0, false);
                helper.assertLineLocations(0, "WH/Stock", "");
                helper.assert(
                    document.querySelector("div[name='package']").innerText,
                    "package001",
                );
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan LOC-01-00-00",
        },
        {
            trigger: ".o_barcode_line:not(.o_selected)",
            run: "scan product1",
        },
        {
            trigger: ".o_barcode_line[data-barcode='product1'].o_selected .o_edit",
            run: "click",
        },
        {
            trigger: ".o_field_widget[name='product_id']:contains('product1')",
        },
        {
            trigger: ".o_field_widget[name='product_id']",
            run: function () {
                helper.assertFormLocationSrc("WH/Stock");
                helper.assertFormQuantity("1");
                helper.assert(
                    document.querySelector("div[name='package_id'] input").value,
                    "package001",
                );
                helper.assert(
                    document.querySelector("div[name='result_package_id'] input").value,
                    "",
                );
                helper.assertKanbanRecordsCount(3);
            },
        },
        {
            trigger:
                ".o_field_stock_barcode_quant_one2many .o_kanban_record:nth-child(3)",
            run: "click",
        },
        {
            trigger: "div[name='location_id'] input:value('WH/Stock/Section 1')",
            run: function () {
                helper.assertFormLocationSrc("WH/Stock/Section 1");
                helper.assertFormQuantity("1");
                helper.assert(
                    document.querySelector("div[name='package_id'] input").value,
                    "",
                );
                helper.assert(
                    document.querySelector("div[name='result_package_id'] input").value,
                    "",
                );
                helper.assertKanbanRecordsCount(3);
            },
        },
        { trigger: ".o_save", run: "click" },
        {
            trigger: ".o_barcode_line",
            run: function () {
                helper.assertLinesCount(1);
                helper.assertLineProduct(0, "product1");
                helper.assertLineQty(0, "1/2");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(false);
                helper.assertValidateEnabled(true);
                helper.assertLineIsHighlighted(0, true);
                helper.assertLineLocations(0, "WH/Stock/Section 1", "");
                helper.assert(document.querySelector("div[name='package']"), null);
            },
        },
        {
            trigger: ".o_barcode_line[data-barcode='product1'].o_selected .o_edit",
            run: "click",
        },
        {
            trigger: "button.o_digipad_increment",
            run: "click",
        },
        {
            trigger: ".o_field_widget[name='product_id']",
            run: function () {
                helper.assertFormLocationSrc("WH/Stock/Section 1");
                helper.assertFormQuantity("2");
                helper.assert(
                    document.querySelector("div[name='package_id'] input").value,
                    "",
                );
                helper.assert(
                    document.querySelector("div[name='result_package_id'] input").value,
                    "",
                );
                helper.assertKanbanRecordsCount(3);
            },
        },
        {
            trigger:
                ".o_field_stock_barcode_quant_one2many .o_kanban_record:nth-child(1)",
            run: "click",
        },
        {
            trigger: "div[name='package_id'] input:value('package001')",
            run: function () {
                helper.assertFormLocationSrc("WH/Stock");
                helper.assertFormQuantity("2");
                helper.assert(
                    document.querySelector("div[name='package_id'] input").value,
                    "package001",
                );
                helper.assert(
                    document.querySelector("div[name='result_package_id'] input").value,
                    "",
                );
                helper.assertKanbanRecordsCount(3);
            },
        },
        { trigger: ".o_save", run: "click" },
        ...stepUtils.validateBarcodeOperation(".o_barcode_line"),
    ],
});

registry.category("web_tour.tours").add("test_confirmation_location_delivery_picking", {
    steps: () => [
        {
            trigger: ".o_barcode_line",
            run: function () {
                helper.assertLinesCount(1);
                helper.assertLineProduct(0, "product1");
                helper.assertLineQty(0, "0/1");
                helper.assertScanMessage("scan_src");
                helper.assertValidateVisible(true);
                helper.assertValidateIsHighlighted(false);
                helper.assertValidateEnabled(true);
                helper.assertLineIsHighlighted(0, false);
                helper.assertLineLocations(0, "WH/Stock", "");
                helper.assert(
                    document.querySelector("div[name='package']").innerText,
                    "package001",
                );
            },
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan LOC-01-00-00",
        },
        {
            trigger: ".o_barcode_line:not(.o_selected)",
            run: "scan product1",
        },
        {
            trigger: ".o_barcode_line[data-barcode='product1'].o_selected .o_edit",
            run: "click",
        },
        {
            trigger: ".o_field_widget[name='product_id']:contains('product1')",
        },
        {
            trigger: ".o_field_widget[name='product_id']",
            run: function () {
                helper.assertFormLocationSrc("WH/Stock");
                helper.assertFormQuantity("1");
                helper.assert(
                    document.querySelector("div[name='package_id'] input").value,
                    "package001",
                );
                helper.assert(
                    document.querySelector("div[name='result_package_id'] input").value,
                    "",
                );
                helper.assertKanbanRecordsCount(2);
            },
        },
        {
            trigger: ".o_field_widget[name='location_id'] input",
            run: "edit Section 2",
        },

        {
            trigger: ".ui-menu-item > a:contains('Section 2')",
            run: "click",
        },
        {
            trigger: ".o_field_widget[name='product_id']",
            run: function () {
                helper.assertFormLocationSrc("WH/Stock/Section 2");
                helper.assertFormQuantity("1");
                helper.assert(
                    document.querySelector("div[name='package_id'] input").value,
                    "package001",
                );
                helper.assert(
                    document.querySelector("div[name='result_package_id'] input").value,
                    "",
                );
                helper.assertKanbanRecordsCount(2);
            },
        },
        { trigger: ".o_save", run: "click" },
        {
            trigger: ".modal-dialog",
            run: function () {
                helper.assert(
                    document.querySelector(".modal-dialog .modal-body").innerText,
                    "Oops! It seems that this product is not located in WH/Stock/Section 2.\nDo you confirm you picked from there?",
                );
            },
        },
        { trigger: ".modal-dialog button.btn-secondary", run: "click" },
        { trigger: ".o_save", run: "click" },
        { trigger: ".modal-dialog button.btn-primary", run: "click" },
        ...stepUtils.validateBarcodeOperation(".o_barcode_line"),
    ],
});

registry.category("web_tour.tours").add("test_description_picking_tour", {
    steps: () => [
        { trigger: ".o_stock_barcode_main_menu", run: "scan WHIN" },
        { trigger: ".o_barcode_client_action", run: "scan test_product" },
        ...stepUtils.validateBarcodeOperation(),
    ],
});

registry.category("web_tour.tours").add("test_no_validate_no_dest_package", {
    steps: () => [
        {
            trigger: "button.o_button_operations",
            run: "click",
        },
        {
            trigger: ".o_kanban_record:contains(Internal)",
            run: "click",
        },
        {
            trigger: "button.o-kanban-button-new",
            run: "click",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan LOC-01-00-00",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan Pack1",
        },
        {
            trigger: ".btn.o_validate_page",
            run: "click",
        },
        {
            trigger:
                ".o_notification:has(.bg-danger):text(Destination location must be scanned)",
        },
    ],
});

registry.category("web_tour.tours").add("test_split_line_preserve_package", {
    steps: () => [
        {
            trigger: ".o_barcode_line",
            run: function () {
                helper.assertLinesCount(1);
                helper.assertLineQty(0, "0/50");
                helper.assertLinePackage(0, "THEPACK1");
            },
        },
        { trigger: ".o_barcode_line .o_edit", run: "click" },
        {
            trigger: "div[name='qty_done'] input",
            run() {
                this.anchor.value = "25";
                this.anchor.dispatchEvent(new InputEvent("input", { bubbles: true }));
            },
        },
        { trigger: "div[name='qty_done'] input:value('25')" },
        { trigger: ".o_save", run: "click" },
        { trigger: ".o_barcode_line.o_selected", run: "scan THEPACK2" },
        {
            trigger: ".o_barcode_line .result-package:contains('THEPACK2')",
            run: () => {
                helper.assertLinesCount(2);
                helper.assertLinePackage(0, "THEPACK1");
                helper.assertLinePackage(1, "THEPACK1");
            },
        },
        { trigger: "button.o_exit", run: "click" },
    ],
});

registry.category("web_tour.tours").add("test_qty_after_uom_update_picking_tour", {
    steps: () => [
        {
            trigger: ".o_stock_barcode_main_menu",
            run: "scan receipt_test",
        },
        {
            trigger: ".o_barcode_line .o_edit",
            run: "click",
        },
        {
            trigger: ".o_field_widget[name='product_uom_id'] input",
            run: "click",
        },
        {
            trigger: ".ui-menu-item > a:contains('Units')",
            run: "click",
        },
        {
            trigger: ".o_digipad_increment",
            run: "click",
        },
        {
            trigger: ".o_barcode_control .o_save",
            run: "click",
        },
        {
            trigger: ".o_barcode_line",
            run: () => {
                helper.assertLineQty(0, "1/120 Units");
            },
        },
    ],
});

registry
    .category("web_tour.tours")
    .add("test_quantity_distribution_sublines_same_lot", {
        steps: () => [
            {
                trigger: ".o_barcode_client_action",
                run: "scan lot 1",
            },
            {
                trigger: ".o_barcode_client_action",
                run: "scan lot 1",
            },
            ...stepUtils.validateBarcodeOperation(
                ".o_barcode_location_group > .o_barcode_line.o_line_completed",
            ),
        ],
    });

registry.category("web_tour.tours").add("test_rental_partial_reception", {
    steps: () => [
        {
            trigger: ".o_barcode_client_action",
            run: "scan RNT01",
        },
        {
            trigger: '.o_barcode_line[data-barcode="RNT01"] .qty-done:contains("1")',
            run: "scan OBTVALI",
        },
        {
            trigger: ".modal-content.o_barcode_backorder_dialog",
            run: function () {
                const incompleteLines = document.querySelectorAll(
                    ".o_barcode_backorder_product_row",
                );
                helper.assert(incompleteLines.length, 1);
                const line = incompleteLines[0];
                helper.assert(line.querySelector("[name='qty-done']").innerText, "1");
                helper.assert(
                    line.querySelector("[name='reserved-qty']").innerText,
                    "4",
                );
                helper.assert(
                    line.querySelector("[name='backorder-qty']").innerText,
                    "3",
                );
            },
        },
        {
            trigger: ".modal-dialog button.btn-primary",
            run: "click",
        },
        {
            trigger: ".o_notification",
            run: function () {
                const backorderLink = document.querySelector(
                    ".o_notification_buttons span",
                );
                helper.assert(
                    backorderLink.innerText.includes("WH/IN/"),
                    true,
                    "The notification should contain a link to the created backorder.",
                );
            },
        },
    ],
});

registry.category("web_tour.tours").add("test_no_validate_multiple_times", {
    steps: () => [
        {
            trigger: ".o_button_operations",
            run: "click",
        },
        {
            trigger: ".o_kanban_record:contains(Internal)",
            run: "click",
        },
        {
            trigger: "button.o-kanban-button-new",
            run: "click",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan product2",
        },
        {
            trigger: ".o_barcode_client_action",
            run: "scan LOC-01-01-00",
        },
        {
            trigger: ".o_validate_page.btn-primary",
            async run(helpers) {
                for (let i = 0; i < 2; i++) {
                    helpers.scan("O-BTN.validate");
                }
            },
        },
        {
            trigger: ".o_notification_bar.bg-success",
        },
    ],
});

registry.category("web_tour.tours").add("test_barcode_draft_picking", {
    steps: () => [
        { trigger: ".o_stock_barcode_main_menu", run: "scan WHOUT" },
        { trigger: ".o_barcode_client_action .o_title:contains(New)" },
        { trigger: "button.o_exit", run: "click" },
        { trigger: ".o_stock_barcode_main_menu", run: "scan WHOUT" },
        {
            trigger: ".o_barcode_client_action .o_title:contains(New)",
            run: "scan product1",
        },
        {
            trigger: '.o_barcode_line[data-barcode="product1"] .o_edit',
            run: "click",
        },
        {
            trigger: '.o_field_widget[name="qty_done"]',
            run: () => {
                if (!/\/\d+\/action-[\w.-]+$/.test(window.location.pathname)) {
                    helper.fail(
                        `the URL should name the created picking: ${window.location.pathname}`,
                    );
                }
            },
        },
        ...stepUtils.discardBarcodeForm(),
        { trigger: ".o_title:contains(WH/OUT/)" },
        { trigger: "button.o_exit", run: "click" },
        { trigger: ".o_stock_barcode_main_menu" },
    ],
});

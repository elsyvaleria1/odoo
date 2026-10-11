/** @odoo-module native */

import { simulateBarCode } from "@barcodes/../tests/barcode_test_helpers";
import { barcodeService } from "@barcodes/barcode_service";
import { beforeEach, expect, test } from "@odoo/hoot";
import { advanceTime, queryFirst } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import {
    contains,
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { appContextOf } from "@web/core/app_context";
import { FormController } from "@web/views/form";

class Product extends models.Model {
    name = fields.Char({ string: "Product name" });
    float_field = fields.Float({ string: "Float" });
    float_field_2 = fields.Float({ string: "Float" });
    barcode = fields.Char({ string: "Barcode" });
    _records = [
        { id: 1, name: "Large Cabinet", barcode: "1234567890" },
        { id: 2, name: "Cabinet with Doors", barcode: "0987654321" },
    ];
}

defineModels([Product]);

beforeEach(() => {
    patchWithCleanup(barcodeService, {
        maxTimeBetweenKeysInMs: 0,
    });
});

test.tags("mobile");
test("widget field_float_scannable", async () => {
    Product._records[0].float_field = 4;

    const onBarcodeScanned = (event) => {
        expect.step(`barcode scanned ${event.detail.barcode}`);
    };

    const view = await mountView({
        type: "form",
        resModel: "product",
        resId: 1,
        arch: `
            <form>
                <field name="display_name"/>
                <field name="float_field" widget="field_float_scannable"/>
                <field name="float_field_2"/>
            </form>
        `,
    });
    appContextOf(view).services.barcode.bus.addEventListener(
        "barcode_scanned",
        onBarcodeScanned,
    );

    expect(".o_field_widget[name=float_field] input").toHaveValue("4.00");

    await contains(".o_field_widget[name=float_field] input").focus();
    await simulateBarCode(["6", "0", "1", "6", "4", "7", "8", "5"]);
    await animationFrame();
    expect.verifySteps(["barcode scanned 60164785"]);
    expect(".o_field_widget[name=float_field] input").toBeFocused();

    await contains(".o_field_widget[name=float_field_2] input").focus();
    await simulateBarCode(["6", "0", "1", "6", "4", "7", "8", "5"]);
    await animationFrame();
    expect.verifySteps([]);

    appContextOf(view).services.barcode.bus.removeEventListener(
        "barcode_scanned",
        onBarcodeScanned,
    );
});

test.tags("mobile");
test("mobile Chrome: a scan into field_float_scannable reaches the field", async () => {
    patchWithCleanup(barcodeService, { isMobileChrome: true });
    const view = await mountView({
        type: "form",
        resModel: "product",
        resId: 1,
        arch: `<form><field name="float_field" widget="field_float_scannable"/></form>`,
    });
    appContextOf(view).services.barcode.bus.addEventListener("barcode_scanned", (ev) =>
        expect.step(`${ev.detail.barcode} on ${ev.detail.target.tagName}`),
    );

    await contains(".o_field_widget[name=float_field] input").focus();
    await simulateBarCode([..."60164785", "Enter"]);
    await animationFrame();
    expect.verifySteps(["60164785 on INPUT"]);
});

test.tags("desktop");
test("an interleaved keystroke does not steal a pending scan's target", async () => {
    patchWithCleanup(barcodeService, { maxTimeBetweenKeysInMs: 50 });

    const onBarcodeScanned = (event) => {
        expect.step(`barcode scanned ${event.detail.barcode}`);
    };
    await mountView({
        type: "form",
        resModel: "product",
        resId: 1,
        arch: `
            <form>
                <field name="float_field" widget="field_float_scannable"/>
            </form>
        `,
    });

    const scanInput = queryFirst(".o_field_widget[name=float_field] input");
    scanInput.addEventListener("barcode_scanned", onBarcodeScanned);

    const otherInput = document.createElement("input");
    document.body.appendChild(otherInput);

    for (const key of ["6", "0", "1"]) {
        scanInput.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
    }
    otherInput.dispatchEvent(new KeyboardEvent("keydown", { key: "z", bubbles: true }));

    await advanceTime(50);
    expect.verifySteps(["barcode scanned 601"]);

    otherInput.remove();
});

test.tags("mobile");
test("do no update form twice after a command barcode scanned", async () => {
    patchWithCleanup(FormController.prototype, {
        onPagerUpdate(...args) {
            expect.step("update");
            super.onPagerUpdate(...args);
        },
    });

    onRpc("web_read", () => {
        expect.step("web_read");
    });

    await mountView({
        type: "form",
        resModel: "product",
        arch: `
            <form>
                <field name="display_name"/>
                <field name="float_field" widget="field_float_scannable"/>
            </form>
        `,
        resId: 1,
        resIds: [1, 2],
    });

    expect.verifySteps(["web_read"]);

    await simulateBarCode(["O", "C", "D", "N", "E", "X", "T", "Enter"]);

    expect.verifySteps(["update", "web_read"]);
});

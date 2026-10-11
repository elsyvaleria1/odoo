/** @odoo-module native */

import { simulateBarCode } from "@barcodes/../tests/barcode_test_helpers";
import { BarcodeHandlerField } from "@barcodes/barcode_handler_field";
import { barcodeService } from "@barcodes/barcode_service";
import { beforeEach, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-dom";
import {
    contains,
    defineModels,
    defineWebModels,
    fields,
    getService,
    mockService,
    models,
    mountView,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { appContextOf } from "@web/core/app_context";
import { Macro } from "@web/core/utils/macro";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";

class Product extends models.Model {
    name = fields.Char({ string: "Product name" });
    handler = fields.Char({ string: "Handler" });
    _records = [{ id: 1, name: "Large Cabinet" }];
}
defineWebModels();
defineModels([Product]);

beforeEach(() => {
    patchWithCleanup(barcodeService, { maxTimeBetweenKeysInMs: 0 });
});

test.tags("desktop");
test("a barcode cannot inject a selector and click unrelated buttons", async () => {
    mockService("action", {
        doActionButton: (data) => expect.step(data.name),
    });
    const view = await mountView({
        type: "form",
        resModel: "product",
        resId: 1,
        arch: `<form>
                <header>
                    <button name="intended" string="Intended" type="object" barcode_trigger="DOIT"/>
                    <button name="unrelated" string="Unrelated" type="object" class="o_danger"/>
                </header>
            </form>`,
    });

    appContextOf(view).services.barcode.scan("OBTDOIT], [class");
    await animationFrame();
    expect.verifySteps([]);

    appContextOf(view).services.barcode.scan("OBTDOIT");
    await animationFrame();
    expect.verifySteps(["intended"]);
});

test.tags("desktop");
test("an unmapped OCD command reports itself instead of doing nothing", async () => {
    mockService("notification", {
        add: (message, options) => expect.step(`${options.type}:${options.title}`),
    });
    const view = await mountView({
        type: "form",
        resModel: "product",
        resId: 1,
        arch: `<form><field name="name"/></form>`,
    });

    appContextOf(view).services.barcode.scan("OCDEDIT");
    await animationFrame();
    expect.verifySteps(["danger:Unknown barcode command"]);
});

test.tags("desktop");
test("a barcode_handler field ignores scans aimed at another active element", async () => {
    let field;
    patchWithCleanup(BarcodeHandlerField.prototype, {
        setup() {
            super.setup();
            field = this;
        },
    });
    const view = await mountView({
        type: "form",
        resModel: "product",
        resId: 1,
        arch: `<form>
                <field name="name"/>
                <field name="handler" widget="barcode_handler"/>
            </form>`,
    });
    const ui = appContextOf(view).services.ui;
    const stored = () => field.props.record.data[field.props.name];

    appContextOf(view).services.barcode.scan("12345");
    await animationFrame();
    expect(stored()).toBe("12345");

    const dialog = document.createElement("div");
    document.body.appendChild(dialog);
    ui.activateElement(dialog);
    appContextOf(view).services.barcode.scan("67890");
    await animationFrame();
    expect(stored()).toBe("12345");

    ui.deactivateElement(dialog);
    appContextOf(view).services.barcode.scan("13579");
    await animationFrame();
    expect(stored()).toBe("13579");
    dialog.remove();
});

test.tags("desktop");
test("cleanBarcode no longer rewrites scanned content", async () => {
    for (const barcode of ["ShiftKnob", "ControlValve", "Altima", "ALTIMA", "cobalt"]) {
        expect(barcodeService.cleanBarcode(barcode)).toBe(barcode);
    }
});

test.tags("desktop");
test("a pager command does not apply to a multi-record view", async () => {
    patchWithCleanup(Macro.prototype, {
        start() {
            expect.step("macro started");
            super.start(...arguments);
        },
    });
    const view = await mountView({
        type: "list",
        resModel: "product",
        arch: `<list><field name="name"/></list>`,
    });
    expect("nav.o_pager .o_pager_value").toHaveCount(1);

    appContextOf(view).services.barcode.scan("OCDPAGERLAST");
    await animationFrame();
    appContextOf(view).services.barcode.scan("OCDPAGERFIRST");
    await animationFrame();
    expect.verifySteps([]);
});

test.tags("desktop");
test("a pager command does nothing when already on the target record", async () => {
    patchWithCleanup(Macro.prototype, {
        start() {
            expect.step("macro started");
            super.start(...arguments);
        },
    });
    const view = await mountView({
        type: "form",
        resModel: "product",
        resId: 1,
        arch: `<form><field name="name"/></form>`,
    });

    appContextOf(view).services.barcode.scan("OCDPAGERFIRST");
    await animationFrame();
    expect.verifySteps([]);
});

test.tags("desktop");
test("an OCD command acts on the active element, not the view behind it", async () => {
    onRpc("web_save", () => expect.step("form saved"));
    const view = await mountView({
        type: "form",
        resModel: "product",
        resId: 1,
        arch: `<form><field name="name"/></form>`,
    });
    await contains(".o_field_widget[name=name] input").edit("dirty", {
        confirm: "blur",
    });
    expect(".o_form_button_save").toHaveCount(1);

    const dialog = document.createElement("div");
    const dialogSave = document.createElement("button");
    dialogSave.className = "o_form_button_save";
    dialogSave.addEventListener("click", () => expect.step("dialog saved"));
    dialog.appendChild(dialogSave);
    document.body.appendChild(dialog);
    const ui = appContextOf(view).services.ui;
    ui.activateElement(dialog);

    appContextOf(view).services.barcode.scan("OCDSAVE");
    await animationFrame();
    expect.verifySteps(["dialog saved"]);

    ui.deactivateElement(dialog);
    dialog.remove();
    appContextOf(view).services.barcode.scan("OCDSAVE");
    await animationFrame();
    expect.verifySteps(["form saved"]);
});

test.tags("desktop");
test("typing into any editable element is not taken for a scan", async () => {
    const view = await mountView({
        type: "form",
        resModel: "product",
        resId: 1,
        arch: `<form><field name="name"/></form>`,
    });
    appContextOf(view).services.barcode.bus.addEventListener("barcode_scanned", (ev) =>
        expect.step(ev.detail.barcode),
    );
    for (const value of ["", "true", "plaintext-only"]) {
        const editor = document.createElement("div");
        editor.setAttribute("contenteditable", value);
        document.body.appendChild(editor);
        editor.focus();
        await simulateBarCode([..."12345670", "Enter"]);
        editor.remove();
    }
    expect.verifySteps([]);

    await simulateBarCode([..."98765432", "Enter"]);
    expect.verifySteps(["98765432"]);
});

test.tags("desktop");
test("OCDSAVE in a form dialog saves the dialog's record, not the form behind it", async () => {
    Product._records.push({ id: 2, name: "Cabinet with Doors" });
    Product._views = { form: `<form><field name="name"/></form>` };
    onRpc("web_save", ({ args }) => expect.step(`saved ${args[0]}`));
    const view = await mountView({
        type: "form",
        resModel: "product",
        resId: 1,
        arch: `<form><field name="name"/></form>`,
    });
    await contains(".o_field_widget[name=name] input").edit("behind", {
        confirm: "blur",
    });

    getService("dialog").add(FormViewDialog, { resModel: "product", resId: 2 });
    await animationFrame();
    await contains(".modal .o_field_widget[name=name] input").edit("in dialog", {
        confirm: "blur",
    });

    appContextOf(view).services.barcode.scan("OCDSAVE");
    await animationFrame();
    expect.verifySteps(["saved 2"]);
});

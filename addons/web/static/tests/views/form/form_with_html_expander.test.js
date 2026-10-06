// @ts-check

import { expect, test } from "@odoo/hoot";
import { Deferred, tick } from "@odoo/hoot-mock";
import {
    defineModels,
    fields,
    models,
    mountView,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { FormController } from "@web/views/form";
import { FormControllerWithHTMLExpander } from "@web/views/form_with_html_expander/form_controller_with_html_expander";

class Partner extends models.Model {
    name = fields.Char();

    _records = [{ id: 1, name: "first" }];
}
defineModels([Partner]);

test("onRecordSaved settles only once the base controller's onRecordSaved has", async () => {
    const baseSaved = new Deferred();
    /** @type {any} */
    let controller = null;
    patchWithCleanup(FormController.prototype, {
        async onRecordSaved() {
            await baseSaved;
            expect.step("base saved");
        },
    });
    patchWithCleanup(FormControllerWithHTMLExpander.prototype, {
        setup() {
            super.setup();
            controller = this;
        },
    });

    await mountView({
        resModel: "partner",
        type: "form",
        resId: 1,
        arch: `<form js_class="form_description_expander"><field name="name"/></form>`,
    });

    controller
        .onRecordSaved(controller.model.root, {})
        .then(() => expect.step("expander saved"));
    await tick();
    expect.verifySteps([]);

    baseSaved.resolve();
    await tick();
    expect.verifySteps(["base saved", "expander saved"]);
});

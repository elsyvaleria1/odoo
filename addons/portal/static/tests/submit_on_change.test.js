import { expect, test } from "@odoo/hoot";
import { manuallyDispatchProgrammaticEvent } from "@odoo/hoot-dom";
import { SubmitOnChange } from "@portal/interactions/submit_on_change";
import { startInteraction } from "@web/../tests/public/helpers";

test("changing the input submits its form", async () => {
    await startInteraction(
        SubmitOnChange,
        `<form action="#"><input type="file" name="ufile" data-o-submit-on-change=""/></form>`,
    );
    const formEl = document.querySelector("form");
    formEl.submit = () => expect.step("submitted");
    await manuallyDispatchProgrammaticEvent(document.querySelector("input"), "change");
    expect.verifySteps(["submitted"]);
});

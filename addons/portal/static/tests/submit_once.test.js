import { expect, test } from "@odoo/hoot";
import { click } from "@odoo/hoot-dom";
import { SubmitOnce } from "@portal/interactions/submit_once";
import { startInteraction } from "@web/../tests/public/helpers";

test("submitting disables every submit button of the form", async () => {
    await startInteraction(
        SubmitOnce,
        `<form data-o-submit-once="" action="#">
            <button type="submit" class="a">A</button>
            <button type="submit" class="b">B</button>
            <button type="button" class="c">C</button>
        </form>`,
    );
    document
        .querySelector("form")
        .addEventListener("submit", (ev) => ev.preventDefault());
    await click(".a");
    expect(".a").toHaveProperty("disabled", true);
    expect(".b").toHaveProperty("disabled", true);
    expect(".c").toHaveProperty("disabled", false);
});

import { expect, getFixture, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import { contains, getService, mountWithCleanup } from "@web/../tests/web_test_helpers";
import { askRecurrenceUpdate } from "@web/components/ask_recurrence_update_dialog/ask_recurrence_update_dialog";
import { MainComponentsContainer } from "@web/ui/main_components_container";

const choices = { self_only: "This event", all_events: "All events" };

test("the chosen occurrences are what the dialog resolves with", async () => {
    await mountWithCleanup(MainComponentsContainer);
    const answer = askRecurrenceUpdate(getService("dialog"), {
        title: "Edit recurrence",
        choices,
    });
    await animationFrame();
    expect(".modal input[value=self_only]").toBeChecked();
    await contains(".modal label:contains('All events')").click();
    await contains(".modal-footer .btn-primary").click();
    expect(await answer).toBe("all_events");
});

test("two dialogs keep their own choices and borrow no page id", async () => {
    const stranger = document.createElement("input");
    stranger.id = "all_events";
    getFixture().append(stranger);
    await mountWithCleanup(MainComponentsContainer);
    const dialog = getService("dialog");
    askRecurrenceUpdate(dialog, { title: "First", choices });
    askRecurrenceUpdate(dialog, { title: "Second", choices });
    await animationFrame();
    const radios = [...document.querySelectorAll(".modal input[type=radio]")];
    expect(radios).toHaveLength(4);
    expect(new Set(radios.map((radio) => radio.id)).size).toBe(4);
    expect(new Set(radios.map((radio) => radio.name)).size).toBe(2);
    expect(radios.map((radio) => radio.id)).not.toInclude("all_events");
});

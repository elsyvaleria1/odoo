import { describe, expect, test } from "@odoo/hoot";
import { queryAll, queryOne } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import {
    setupInteractionWhiteList,
    startInteractions,
} from "@web/../tests/public/helpers";

setupInteractionWhiteList("website_event_track.website_event_track_reminder");
describe.current.tags("interaction_dev");

const bell = `
    <form class="o_wetrack_js_reminder" method="post" action="/event/track/toggle_reminder"
          data-fragment-form="website_event_track.reminder.7" data-track-id="7">
        <button type="submit">
            <span class="d-contents" data-fragment="website_event_track.reminder.7">
                <input type="hidden" name="set_reminder_on" value="1"/>
                <i class="o_wetrack_js_reminder_bell fa-bell fa-regular" title="Set Favorite"></i>
            </span>
        </button>
    </form>`;

/** @param {string} name */
function answer(name, detail) {
    document.dispatchEvent(new CustomEvent(name, { detail }));
}

function submitFirstBell() {
    const form = queryAll(".o_wetrack_js_reminder")[0];
    form.addEventListener("submit", (ev) => ev.preventDefault());
    form.requestSubmit();
}

test("a toggle queued offline shows on every copy of the track's bell", async () => {
    await startInteractions(bell + bell);

    submitFirstBell();
    answer("website_event_track:reminder_queued", { track_id: 7, reminder_on: true });
    await animationFrame();

    for (const icon of queryAll(".o_wetrack_js_reminder_bell")) {
        expect(icon).toHaveClass("fa-solid");
        expect(icon).toHaveAttribute("title", "Favorite On");
    }
    expect(
        queryAll("input[name='set_reminder_on']").map((input) => input.value),
    ).toEqual(["0", "0"]);
});

test("an answer the bell did not ask for changes nothing", async () => {
    await startInteractions(bell);

    answer("website_event_track:reminder_queued", { track_id: 7, reminder_on: true });
    await animationFrame();

    expect(queryOne(".o_wetrack_js_reminder_bell")).toHaveClass("fa-regular");
    expect(queryOne("input[name='set_reminder_on']")).toHaveValue("1");
});

test("an answer for another track changes nothing", async () => {
    await startInteractions(bell);

    submitFirstBell();
    answer("website_event_track:reminder_queued", { track_id: 8, reminder_on: true });
    await animationFrame();

    expect(queryOne(".o_wetrack_js_reminder_bell")).toHaveClass("fa-regular");
});

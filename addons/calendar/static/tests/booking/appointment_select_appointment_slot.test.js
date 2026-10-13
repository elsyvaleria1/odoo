import { describe, expect, test } from "@odoo/hoot";
import { queryOne } from "@odoo/hoot-dom";
import { advanceTime, animationFrame } from "@odoo/hoot-mock";
import {
    setupInteractionWhiteList,
    startInteractions,
} from "@web/../tests/public/helpers";
import { onRpc } from "@web/../tests/web_test_helpers";

setupInteractionWhiteList("appointment.appointment_select_appointment_slot");
describe.current.tags("interaction_dev");

/** @param {string[]} days */
const calendar = (days) => `
    <div class="d-contents" data-fragment="calendar.appointment_calendar">
        <div id="slots_availabilities">
            <div id="calendar">
                <div class="o_appointment_month">
                    <span class="o_appointment_month_name">October 2026</span>
                    <table><tr>${days
                        .map(
                            (day) => `<td class="o_day">
                                <div class="o_slot_button" id="${day}" data-slot-date="${day}" data-available-slots="[]">${day}</div>
                            </td>`,
                        )
                        .join("")}</tr></table>
                </div>
            </div>
        </div>
    </div>`;

const page = () => `
    <div class="o_appointment_info">
        <input type="hidden" name="appointment_type_id" value="1"/>
        <input type="hidden" name="filter_appointment_type_ids" value="[]"/>
        <input type="hidden" name="filter_staff_user_ids" value="[]"/>
        <input type="hidden" name="filter_resource_ids" value="[]"/>
        <input type="hidden" name="invite_token" value=""/>
        <input type="hidden" name="schedule_based_on" value="users"/>
        <input type="hidden" name="resource_selected_id" value=""/>
        <select id="resourceCapacity" name="resourceCapacity">
            <option value="1">1</option>
            <option value="2">2</option>
        </select>
        <div class="o_appointment_no_slot_overall_helper"></div>
        <div class="o_appointment_no_capacity"></div>
        <div class="o_appointment_calendar">${calendar(["2026-10-12"])}</div>
        <div class="o_appointment_timezone_selection"></div>
        <div class="o_appointment_slot_list_loading d-none"></div>
        <div id="slotsList" data-appointments-count="1"></div>
    </div>`;

test("a capacity with no slot left swaps the calendar and says so", async () => {
    onRpc("/appointment/get_upcoming_appointments", () => false);
    onRpc("/appointment/1/update_available_slots", async (request) => {
        const { params } = JSON.parse(
            new TextDecoder("utf-8").decode(await request.arrayBuffer()),
        );
        expect.step(`asked_capacity ${params.asked_capacity}`);
        return {
            fragments: [
                {
                    key: "calendar.appointment_calendar",
                    html: calendar([]),
                    swap: "morph",
                },
            ],
            events: [],
            redirect: null,
            data: {},
        };
    });
    await startInteractions(page());
    const calendarEl = queryOne("#calendar");
    expect(".o_appointment_no_capacity").toHaveText("");

    const capacity = queryOne("#resourceCapacity");
    capacity.value = "2";
    capacity.dispatchEvent(new Event("change", { bubbles: true }));
    await advanceTime(250);
    await animationFrame();

    expect.verifySteps(["asked_capacity 2"]);
    expect(".o_slot_button").toHaveCount(0);
    expect(queryOne("#calendar")).toBe(calendarEl);
    expect(".o_appointment_no_capacity").toHaveText(
        "Sorry, there is not any more availability for the asked capacity.",
    );
});

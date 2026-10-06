import { registry } from "@web/core/registry";

const ACTOR_SHIFT =
    "#calendar_employee .o_planning_shift_block:not(.o_planning_shift_open):contains(Actor)";

function assertColor(el, property, expected) {
    const actual = getComputedStyle(el)[property];
    if (actual !== expected) {
        throw new Error(`Expected ${property} ${expected}, got ${actual}`);
    }
}

registry.category("web_tour.tours").add("planning_front_end_tour", {
    steps: () => [
        {
            trigger: "button[aria-label='Week view']",
            content: "The front end calendar should be rendered",
        },
        {
            trigger: "button[aria-label='Month view']",
            content: "Switch the calendar to month view",
            run: "click",
        },
        {
            trigger: "button[aria-label='List view']",
            content: "Switch the calendar to list view",
            run: "click",
        },
        {
            trigger: "button[aria-label='Week view']",
            content: "Switch the calendar back to week view",
            run: "click",
        },
        {
            trigger: `${ACTOR_SHIFT}:not(.o_planning_shift_switch_requested)`,
            content: "The employee's shift should be painted in its role's color",
            run() {
                assertColor(this.anchor, "backgroundColor", "rgb(238, 75, 57)");
            },
        },
        {
            trigger: `${ACTOR_SHIFT}:not(.o_planning_shift_switch_requested)`,
            content: "Click on shift of the employee on the calendar",
            run: "click",
        },
        {
            trigger: "form[id='modal_action_switch_shift'] button[type='submit']",
            content: "Click on the 'Ask to Switch' button in the popover",
            run: "click",
            expectUnloadPage: true,
        },
        {
            trigger: "div.o_planning_toast.bg-success",
            content: "A success planning toast notification should appear",
        },
        {
            trigger: `${ACTOR_SHIFT}.o_planning_shift_switch_requested`,
            content:
                "The shift's calendar entry should have changed in style to indicate that a request to switch has been filed",
            run() {
                assertColor(this.anchor, "borderTopColor", "rgb(238, 75, 57)");
                const { backgroundImage, opacity } = getComputedStyle(this.anchor);
                if (
                    !backgroundImage.startsWith("repeating-linear-gradient") ||
                    opacity !== "0.5"
                ) {
                    throw new Error(
                        `The switch request is not shown: ${backgroundImage}, opacity ${opacity}`,
                    );
                }
            },
        },
        {
            trigger: "div.o_planning_calendar_unwanted_shifts",
            content:
                "After switching a shift, the unwanted shifts section should appear",
        },
        {
            trigger:
                "div.o_planning_calendar_unwanted_shifts td[name='buttons'] div button[type='submit']",
            content:
                "Click on the 'Cancel Switch' button to cancel the switch shift request",
            run: "click",
            expectUnloadPage: true,
        },
        {
            trigger: "div.o_planning_calendar_open_shifts",
            content:
                "Since we have an open shift available, the open shifts section be rendered",
        },
        {
            trigger:
                "div.o_planning_calendar_open_shifts td[name='buttons'] div button[type='submit']",
            content:
                "Click on the 'I take it' button to cancel the switch shift request",
            run: "click",
            expectUnloadPage: true,
        },
    ],
});

registry.category("web_tour.tours").add("planning_front_end_allow_unassign_tour", {
    steps: () => [
        {
            trigger: `${ACTOR_SHIFT}:not(.o_planning_shift_switch_requested)`,
            content: "The employee's shift should be painted in its role's color",
            run() {
                assertColor(this.anchor, "backgroundColor", "rgb(238, 75, 57)");
            },
        },
        {
            trigger: `${ACTOR_SHIFT}:not(.o_planning_shift_switch_requested)`,
            content: "Click on shift of the employee on the calendar",
            run: "click",
        },
        {
            trigger: "form[id='modal_action_dismiss_shift'] button[type='submit']",
            content: "Click on the 'I am Unavailable' button in the popover",
            run: "click",
            expectUnloadPage: true,
        },
        {
            trigger: "div.o_planning_toast.bg-success",
            content: "A success planning toast notification should appear",
        },
        {
            trigger: "div.o_planning_calendar_open_shifts",
            content:
                "Since we have an open shift available, the open shifts section be rendered",
        },
    ],
});

registry.category("web_tour.tours").add("planning_front_end_buttons_tour", {
    steps: () => [
        {
            trigger: "div.o_planning_toast.bg-success",
            content: "A success planning toast notification should appear",
        },
        {
            trigger: "button[aria-label='Week view']",
            content: "The front end calendar should be rendered",
        },
        {
            trigger: "#calendar_employee .o_planning_shift_block:contains(Camera Man)",
            content: "The slots inside the front end calendar should be rendered",
            run() {
                assertColor(this.anchor, "backgroundColor", "rgb(242, 150, 72)");
            },
        },
    ],
});

registry.category("web_tour.tours").add("planning_preview_tour", {
    steps: () => [
        {
            trigger: "div.o_planning_calendar_container",
            content: "The planning preview container should be displayed",
        },
    ],
});

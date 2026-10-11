import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { stepUtils } from "@web_tour/tour_utils";

import {
    embeddedViewPatchFunctions,
    endKnowledgeTour,
    openCommandBar,
} from "../knowledge_tour_utils.js";

const embeddedViewPatchUtil = embeddedViewPatchFunctions();

function mockDate() {
    const now = "2025-02-15T08:00:00";
    class MockDate extends Date {
        static now() {
            return new Date(now).getTime();
        }
    }
    return patch(window, { Date: MockDate });
}

let unpatchDate;

function dispatchPointer(el, phase, x, y) {
    const params = {
        bubbles: true,
        cancelable: true,
        clientX: x,
        clientY: y,
        button: 0,
        buttons: phase === "up" ? 0 : 1,
    };
    el.dispatchEvent(
        new PointerEvent(`pointer${phase}`, {
            ...params,
            pointerId: 1,
            pointerType: "mouse",
            isPrimary: true,
        }),
    );
    el.dispatchEvent(new MouseEvent(`mouse${phase}`, params));
}

function laneInFirstColumn(lane) {
    const column = lane
        .closest(".fc")
        .querySelector('[role="gridcell"][data-date]:not(.fc-daygrid-day)');
    const columnRect = column.getBoundingClientRect();
    return {
        column,
        x: columnRect.left + columnRect.width / 2,
        y: lane.getBoundingClientRect().top + 1,
    };
}

function clickDate(lane) {
    lane.scrollIntoView({ block: "center" });
    const { column, x, y } = laneInFirstColumn(lane);
    dispatchPointer(column, "down", x, y);
    dispatchPointer(column, "up", x, y);
    column.dispatchEvent(
        new MouseEvent("click", {
            bubbles: true,
            cancelable: true,
            clientX: x,
            clientY: y,
        }),
    );
}

function dragDate(el, targetLane) {
    const { column, x, y } = laneInFirstColumn(targetLane);
    const elRect = el.getBoundingClientRect();
    const startX = elRect.left + Math.min(1, elRect.width / 2);
    const startY = elRect.top + Math.min(1, elRect.height / 2);
    dispatchPointer(el, "down", startX, startY);
    dispatchPointer(el, "move", startX, startY + 10);
    dispatchPointer(column, "move", x, y);
    dispatchPointer(column, "up", x, y);
}

function laneTop(time) {
    return document
        .querySelector(`.fc-timegrid-slot-lane[data-time="${time}"]`)
        .getBoundingClientRect().top;
}

const WAIT_MS = 8000;

async function measuredLane(time) {
    const deadline = performance.now() + WAIT_MS;
    while (performance.now() < deadline) {
        const lane = document.querySelector(
            `.fc-timegrid-slot-lane[data-time="${time}"]`,
        );
        if (lane?.clientHeight) {
            return lane;
        }
        await new Promise(requestAnimationFrame);
    }
    throw new Error(`The ${time} time slot was never given its height`);
}

async function waitForItemEvent(isSettled) {
    const deadline = performance.now() + WAIT_MS;
    while (performance.now() < deadline) {
        const eventEl = [...document.querySelectorAll(".fc-timegrid-event")].find(
            (el) => el.textContent.includes("Item Article"),
        );
        if (eventEl && isSettled(eventEl.getBoundingClientRect())) {
            return eventEl;
        }
        await new Promise(requestAnimationFrame);
    }
    throw new Error("The item event never reached its expected position");
}

registry.category("web_tour.tours").add("knowledge_calendar_command_tour", {
    url: "/odoo",
    steps: () => [
        stepUtils.showAppsMenuItem(),
        {
            trigger: '.o_app[data-menu-xmlid="knowledge.knowledge_menu_root"]',
            run: "click",
        },
        {
            trigger: "body",
            run: () => {
                embeddedViewPatchUtil.before();
                unpatchDate = mockDate();
            },
        },
        {
            trigger: ".odoo-editor-editable > p",
            run: function () {
                openCommandBar(this.anchor);
            },
        },
        {
            trigger: '.o-we-command-name:contains("Calendar")',
            run: "click",
        },
        {
            trigger: ".modal-footer .btn-primary",
            run: "click",
        },
        {
            trigger: '[data-embedded="view"]',
            run: function () {
                this.anchor.scrollIntoView(true);
            },
        },
        {
            trigger: "[data-embedded='view']",
        },
        {
            trigger: '.fc-timegrid-slot.fc-timegrid-slot-lane[data-time="08:00:00"]',
            async run() {
                clickDate(await measuredLane("08:00:00"));
            },
        },
        {
            trigger: ".o_hierarchy_article_name input:empty",
        },
        {
            trigger:
                '.o_widget_knowledge_properties_panel .o_property_field:contains("Start Date")',
            run: function () {
                const input = this.anchor.querySelector("input");
                if (!input.value.includes("08:00")) {
                    throw new Error(
                        "Item was not created with the correct property value",
                    );
                }
            },
        },
        {
            trigger: ".o_knowledge_editor .odoo-editor-editable h1",
            run: "editor Item Article",
        },
        {
            trigger:
                '.o_knowledge_tree .o_article_name:contains("EditorCommandsArticle")',
            run: "click",
        },
        {
            trigger: '.fc-timegrid-event .o_event_title:contains("Item Article")',
        },
        {
            content: "Remove previous item calendar view",
            trigger: ".odoo-editor-editable",
            run: "editor ",
        },
        {
            trigger: ".odoo-editor-editable:not(:has( [data-embedded='view']))",
        },
        {
            trigger: ".o_knowledge_helper .o_knowledge_add_item_calendar",
            run: "click",
        },
        {
            trigger:
                ".o_knowledge_item_calendar_dialog_date_start .o_select_menu_toggler",
            run: "click",
        },
        ...stepUtils.editSelectMenuInput(
            ".o_knowledge_item_calendar_dialog_date_start .o_select_menu_input",
            "Start Property",
        ),
        {
            trigger: ".o_select_menu_menu .o_select_menu_item.o_create_datetime",
            run: "click",
        },
        {
            trigger:
                ".o_knowledge_item_calendar_dialog_date_stop .o_select_menu_toggler",
            run: "click",
        },
        ...stepUtils.editSelectMenuInput(
            ".o_knowledge_item_calendar_dialog_date_stop .o_select_menu_input",
            "Stop Property",
        ),
        {
            trigger: ".o_select_menu_menu .o_select_menu_item.o_create_choice",
            run: "click",
        },
        {
            trigger: ".o_knowledge_item_calendar_dialog_slot_min_time input",
            run: function () {
                this.anchor.value = "08:00";
                this.anchor.dispatchEvent(new Event("change"));
            },
        },
        {
            trigger: ".o_knowledge_item_calendar_dialog_slot_max_time input",
            run: function () {
                this.anchor.value = "16:30";
                this.anchor.dispatchEvent(new Event("change"));
            },
        },
        {
            trigger: "input[type='checkbox']",
            run: "click",
        },
        {
            trigger: ".modal-footer .btn-primary",
            run: "click",
        },
        {
            trigger:
                "[data-embedded='view'] .o_knowledge_article_view_calendar_embedded_view",
        },
        {
            trigger:
                ".fc-view:has(.fc-timegrid-slot-lane):not(:has(.fc-timegrid-slot-lane[data-time='07:00:00']))",
        },
        {
            trigger: ".fc-timegrid-slot.fc-timegrid-slot-lane[data-time='08:00:00']",
        },
        {
            trigger:
                ".fc-view:has(.fc-timegrid-slot-lane):not(:has(.fc-timegrid-slot-lane[data-time='16:30:00']))",
        },
        {
            trigger: ".fc-timegrid-slot.fc-timegrid-slot-lane[data-time='16:00:00']",
        },
        {
            trigger: ".o_calendar_widget:not(:has(.fc-day-sat, .fc-day-sun))",
        },
        {
            trigger: '.fc-timegrid-slot.fc-timegrid-slot-lane[data-time="08:00:00"]',
            async run() {
                clickDate(await measuredLane("08:00:00"));
            },
        },
        {
            trigger: ".o_hierarchy_article_name input:empty",
        },
        {
            trigger:
                '.o_widget_knowledge_properties_panel .o_property_field:contains("Start Property")',
            run: function () {
                const input = this.anchor.querySelector("input");
                if (!input.value.includes("08:00")) {
                    throw new Error(
                        "Item was not created with the correct property value",
                    );
                }
            },
        },
        {
            trigger:
                ".o_widget_knowledge_properties_panel .o_field_property_add button",
            run: "click",
        },
        {
            trigger: ".o_field_property_definition_header",
            run: "edit Date Property",
        },
        {
            trigger: ".o_field_property_definition_type button.dropdown-toggle",
            run: "click",
        },
        {
            trigger:
                '.dropdown-menu .dropdown-item:contains("Date"):not(:contains("Time"))',
            run: "click",
        },
        {
            trigger: ".o_knowledge_editor .odoo-editor-editable",
            run: "click",
        },
        {
            trigger:
                ".o_widget_knowledge_properties_panel .o_field_property_add button",
            run: "click",
        },
        {
            trigger: ".o_field_property_definition_header",
            run: "edit Boolean Property",
        },
        {
            trigger: ".o_field_property_definition_type button.dropdown-toggle",
            run: "click",
        },
        {
            trigger: '.dropdown-menu .dropdown-item:contains("Checkbox")',
            run: "click",
        },
        {
            trigger: ".o_knowledge_editor .odoo-editor-editable",
            run: "click",
        },
        {
            trigger:
                ".o_widget_knowledge_properties_panel .o_field_property_add button",
            run: "click",
        },
        {
            trigger: ".o_field_property_definition_header",
            run: "edit Text Property",
        },
        {
            trigger: ".o_field_property_definition_type button.dropdown-toggle",
            run: "click",
        },
        {
            trigger: '.dropdown-menu .dropdown-item:contains("Text")',
            run: "click",
        },
        {
            trigger: ".o_knowledge_editor .odoo-editor-editable",
            run: "click",
        },
        {
            trigger:
                '.o_widget_knowledge_properties_panel .o_property_field:contains("Text Property") input',
            run: "edit Custom text && click body",
        },
        {
            trigger: ".o_knowledge_editor .odoo-editor-editable h1",
            run: "editor Item Article",
        },
        {
            trigger: '.o_knowledge_tree .o_article_name:contains("Article Items")',
            run: "click",
        },
        {
            trigger: '.fc-timegrid-event .o_event_title:contains("Item Article")',
        },
        {
            trigger: ".o_control_panel_breadcrumbs_actions .dropdown-toggle",
            run: "click",
        },
        {
            trigger: ".dropdown-item:contains(Edit)",
            run: "click",
        },
        {
            trigger:
                ".o_knowledge_item_calendar_dialog_date_start .o_select_menu_toggler",
            run: "click",
        },
        {
            trigger:
                '.o_select_menu_menu .o_select_menu_item:contains("Date Property")',
            run: "click",
        },
        {
            trigger:
                ".o_knowledge_item_calendar_dialog_date_stop .o_select_menu_toggler:empty",
        },
        {
            trigger:
                ".o_knowledge_item_calendar_dialog_date_stop .o_select_menu_toggler",
            run: "click",
        },
        {
            trigger:
                '.o_knowledge_item_calendar_dialog_date_stop .o_select_menu:not(:contains("Date Property"))',
        },
        {
            trigger: ".o_knowledge_item_calendar_props_dialog",
            run: "click",
        },
        {
            trigger: ".o_color .o_select_menu_toggler",
            run: "click",
        },
        {
            trigger:
                '.o_select_menu_menu .o_select_menu_item:contains("Boolean Property")',
            run: "click",
        },
        {
            trigger: ".o_scale .o_select_menu_toggler",
            run: "click",
        },
        {
            trigger: '.o_select_menu_menu .o_select_menu_item:contains("Month")',
            run: "click",
        },
        {
            trigger: ".modal-footer .btn-primary",
            run: "click",
        },
        {
            trigger: ".fc-view:not(:has(.fc-event-container))",
        },
        {
            trigger:
                '.o_knowledge_article_view_calendar_embedded_view .o_calendar_header .o_view_scale_selector:contains("Month")',
        },
        {
            trigger: ".o_control_panel_breadcrumbs_actions .dropdown-toggle",
            run: "click",
        },
        {
            trigger: ".dropdown-item:contains(Edit)",
            run: "click",
        },
        {
            trigger:
                ".o_knowledge_item_calendar_dialog_date_start .o_select_menu_toggler",
            run: "click",
        },
        {
            trigger:
                '.o_select_menu_menu .o_select_menu_item:contains("Start Property")',
            run: "click",
        },
        {
            trigger:
                ".o_knowledge_item_calendar_dialog_date_stop .o_select_menu_toggler:empty",
        },
        {
            trigger:
                ".o_knowledge_item_calendar_dialog_date_stop .o_select_menu_toggler",
            run: "click",
        },
        {
            trigger:
                '.o_select_menu_menu .o_select_menu_item:contains("Stop Property")',
            run: "click",
        },
        {
            trigger: ".modal-footer .btn-primary",
            run: "click",
        },
        {
            trigger: ".o_control_panel_breadcrumbs_actions .dropdown-toggle",
            run: "click",
        },
        {
            trigger: ".dropdown-item:contains(Open)",
            run: "click",
        },
        {
            trigger: ".o_knowledge_article_view_calendar_embedded_view.o_action",
        },
        {
            trigger: '.fc-view .o_event_title:contains("Item Article")',
        },
        {
            trigger: ".o_main_navbar .o_menu_toggle",
            run: "click",
        },
        {
            trigger: '.o_app[data-menu-xmlid="knowledge.knowledge_menu_root"]',
            run: "click",
        },
        {
            trigger: "[data-embedded='view']",
        },
        {
            trigger:
                '.o_knowledge_article_view_calendar_embedded_view .o_calendar_header .o_view_scale_selector button:contains("Month")',
            run: "click",
        },
        {
            trigger: ".o-dropdown--menu .o_scale_button_week",
            run: "click",
        },
        {
            trigger: '.fc-timegrid-event .o_event_title:contains("Item Article")',
            async run() {
                const target = await measuredLane("09:00:00");
                dragDate(await waitForItemEvent(() => true), target);
            },
        },
        {
            trigger: '.fc-timegrid-event:contains("Item Article")',
            async run({ hover }) {
                const eventEl = await waitForItemEvent(
                    (rect) =>
                        rect.top > (laneTop("08:00:00") + laneTop("09:00:00")) / 2,
                );
                await hover(eventEl.querySelector(`.fc-event-main`));
            },
        },
        {
            trigger: '.fc-timegrid-event:contains("Item Article")',
            async run() {
                const hoveredEl = await waitForItemEvent(
                    (rect) =>
                        rect.top > (laneTop("08:00:00") + laneTop("09:00:00")) / 2,
                );
                const resizer = hoveredEl.querySelector(`.fc-event-resizer-end`);
                Object.assign(resizer.style, {
                    display: "block",
                    height: "1px",
                    bottom: "0",
                });
                dragDate(resizer, await measuredLane("11:00:00"));
            },
        },
        {
            trigger: ".fc-timegrid-event",
            async run({ dblclick }) {
                const eventEl = await waitForItemEvent(
                    (rect) => rect.bottom > laneTop("11:00:00") + 3,
                );
                await dblclick(eventEl);
            },
        },
        {
            trigger: '.o_hierarchy_article_name input:value("Item Article")',
        },
        {
            trigger:
                '.o_widget_knowledge_properties_panel .o_property_field:contains("Start Property")',
            run: function () {
                const input = this.anchor.querySelector("input");
                if (!input.value.includes("09:00")) {
                    console.error("Item start date property has not been updated");
                }
            },
        },
        {
            trigger:
                '.o_widget_knowledge_properties_panel .o_property_field:contains("Stop Property")',
            run: function () {
                const input = this.anchor.querySelector("input");
                if (!input.value.includes("11:15")) {
                    console.error("Item stop date property has not been updated");
                }
            },
        },
        {
            trigger:
                '.o_widget_knowledge_properties_panel .o_property_field:contains("Text Property")',
            run: function () {
                const input = this.anchor.querySelector("input");
                if (!input.value.includes("Custom text")) {
                    console.error("Item text property has changed");
                }
            },
        },
        {
            trigger:
                ".o_widget_knowledge_properties_panel .o_property_field:contains(Start Property)",
            run: "hover && click .o_widget_knowledge_properties_panel .o_property_field:contains(Start Property) .o_field_property_open_popover",
        },
        {
            trigger: ".o_field_property_definition .o_field_property_definition_delete",
            run: "click",
        },
        {
            trigger: ".modal-dialog .btn-primary",
            run: "click",
        },
        {
            trigger: '.o_knowledge_tree .o_article_name:contains("Article Items")',
            run: "click",
        },
        {
            trigger:
                ".o_knowledge_article_view_calendar_embedded_view .o_knowledge_item_calendar_nocontent",
        },
        {
            trigger: "body",
            run: () => {
                unpatchDate();
                embeddedViewPatchUtil.after();
            },
        },
        ...endKnowledgeTour(),
    ],
});

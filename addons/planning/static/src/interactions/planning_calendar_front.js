/** @odoo-module native */

import {
    DATE_SHORT,
    fromJSDate,
    parseFormatted,
    TIME_24_SIMPLE,
    toJSDate,
    toLocaleString,
} from "@web/core/l10n/dates";
import { FullCalendar, loadFullCalendar } from "@web/core/lib/fullcalendar";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { Modal, Popover, Toast } from "@web/libs/bootstrap";
import { Interaction } from "@web/public/interaction";

function setFieldVisibility(el, visible) {
    el.style.display = visible ? "" : "none";
    if (el.previousElementSibling) {
        el.previousElementSibling.style.display = visible ? "" : "none";
    }
}

export class PlanningCalendarFront extends Interaction {
    static selector = "#calendar_employee";

    async willStart() {
        await this.waitFor(loadFullCalendar());
    }

    start() {
        const messageSlug = document.querySelector(".message_slug");
        if (messageSlug?.getAttribute("value")) {
            const toastEl = document.getElementById("PlanningToast");
            if (toastEl) {
                new Toast(toastEl).show();
            }
        }
        const noData = document.querySelector(".no_data");
        if (noData?.getAttribute("value")) {
            return;
        }
        this.calendarElement = this.el.querySelector(".o_calendar_widget");
        const employeeSlotsFcData = JSON.parse(
            document
                .querySelector(".employee_slots_fullcalendar_data")
                .getAttribute("value"),
        );
        const locale = document.querySelector(".locale").getAttribute("value");
        const popoverEls = document.querySelectorAll('[data-bs-toggle="popover"]');
        const popovers = [];
        for (const el of popoverEls) {
            const popover = new Popover(el);
            popovers.push(popover);
            this.registerCleanup(() => popover.dispose());
        }
        this.addListener(document.body, "click", (e) => {
            let shouldHide = true;
            let parent = e.target;
            while (parent) {
                if (
                    parent.classList &&
                    (parent.classList.contains("assignee-cell") ||
                        parent.classList.contains("contact-assignee-popover"))
                ) {
                    shouldHide = false;
                    break;
                }
                parent = parent.parentElement;
            }
            if (shouldHide) {
                for (const p of popovers) {
                    p.hide();
                }
            }
        });
        this.addListener(popoverEls, "click", (ev) => {
            for (const p of popovers) {
                if (p._element !== ev.currentTarget) {
                    p.hide();
                }
            }
        });
        const defaultStartValue = document
            .querySelector(".default_start")
            .getAttribute("value");
        const parsedDefaultStart = parseFormatted(defaultStartValue, "yyyy-MM-dd");
        const defaultStart = parsedDefaultStart
            ? toJSDate(parsedDefaultStart)
            : new Date(NaN);
        const defaultView = document
            .querySelector(".default_view")
            .getAttribute("value");
        const minTime = document.querySelector(".mintime").getAttribute("value");
        const maxTime = document.querySelector(".maxtime").getAttribute("value");
        let calendarHeaders = {
            left: "dayGridMonth,timeGridWeek,listMonth",
            center: "title",
            right: "today,prev,next",
        };
        if (employeeSlotsFcData.length === 0) {
            calendarHeaders = {
                left: false,
                center: "title",
                right: false,
            };
        }
        const titleFormat = { month: "long", year: "numeric" };
        let noEventsContent = _t("You don't have any shifts planned yet.");
        const openSlotsIds = document
            .querySelector(".open_slots_ids")
            ?.getAttribute("value");
        if (openSlotsIds) {
            noEventsContent = _t(
                "You don't have any shifts planned yet. You can assign yourself some of the available open shifts.",
            );
        }
        this.calendar = new FullCalendar.Calendar(this.calendarElement, {
            locale: locale,
            initialView: defaultView,
            navLinks: true,
            dayMaxEventRows: 3,
            titleFormat: titleFormat,
            initialDate: defaultStart,
            displayEventEnd: true,
            height: "auto",
            eventContrastColor: "white",
            eventClass: this.getEventClass.bind(this),
            blockEventClass: "o_planning_shift_block",
            listItemEventClass: "o_planning_shift_item",
            listItemEventBeforeClass: "o_planning_shift_dot",
            eventContent: (info) => ({ domNodes: this.renderEventContent(info) }),
            dayHeaderClass: "o_planning_day_header",
            allDayHeaderClass: "o_planning_day_header",
            allDayDividerClass: "o_planning_day_header",
            moreLinkClass: "o_planning_more_link",
            eventOverlap: true,
            eventTimeFormat: {
                hour: "numeric",
                minute: "2-digit",
                meridiem: "long",
                omitZeroMinute: true,
            },
            slotMinTime: minTime,
            slotMaxTime: maxTime,
            headerToolbar: calendarHeaders,
            events: employeeSlotsFcData,
            eventClick: this.eventFunction.bind(this),
            buttons: {
                today: { text: _t("Today") },
                dayGridMonth: { text: _t("Month") },
                timeGridWeek: { text: _t("Week") },
                listMonth: { text: _t("List") },
            },
            noEventsContent: noEventsContent,
        });
        this.registerCleanup(() => this.calendar.destroy());
        this.calendar.setOption("locale", locale);
        this.calendar.render();
    }

    getEventClass({ event, view }) {
        const { request_to_switch, allow_self_unassign, is_open_shift } =
            event.extendedProps;
        return [
            "o_planning_shift",
            "cursor-pointer",
            view.type !== "listMonth" && "px-2 py-1",
            request_to_switch &&
                !allow_self_unassign &&
                "o_planning_shift_switch_requested",
            is_open_shift && "o_planning_shift_open",
        ]
            .filter(Boolean)
            .join(" ");
    }

    renderEventContent({ event, timeText }) {
        const { alloc_hours, alloc_perc } = event.extendedProps;
        const time = document.createElement("div");
        time.classList.add("o_planning_shift_time", "fw-bold", "text-truncate");
        time.textContent = timeText;
        const hours = document.createElement("span");
        hours.classList.add("ps-1");
        hours.textContent = `(${alloc_hours})`;
        time.append(hours);
        if (parseFloat(alloc_perc) < 100) {
            const percent = document.createElement("span");
            percent.classList.add("ps-1");
            percent.textContent = `(${alloc_perc}%)`;
            time.append(percent);
        }
        const title = document.createElement("div");
        title.classList.add("o_planning_shift_title", "text-truncate");
        title.textContent = event.title;
        return [time, title];
    }

    formatDateAsBackend(date) {
        return toLocaleString(fromJSDate(date), {
            ...DATE_SHORT,
            ...TIME_24_SIMPLE,
            weekday: "short",
        });
    }

    eventFunction(calEvent) {
        const planningToken = document
            .querySelector(".planning_token")
            .getAttribute("value");
        const employeeToken = document
            .querySelector(".employee_token")
            .getAttribute("value");
        let displayFooter = false;

        const modalTitle = document.querySelector(".modal-title");
        modalTitle.textContent = calEvent.event.title;
        const modalHeader = document.querySelector(".modal-header");
        modalHeader.style.backgroundColor = calEvent.event.backgroundColor;

        if (
            calEvent.event.extendedProps.request_to_switch &&
            !calEvent.event.extendedProps.allow_self_unassign
        ) {
            document.getElementById("switch-warning").style.display = "block";
            document.querySelector(".warning-text").textContent =
                "You requested to switch this shift. Other employees can now assign themselves to it.";
        } else {
            document.getElementById("switch-warning").style.display = "none";
        }

        document.querySelector(".o_start_date").textContent = this.formatDateAsBackend(
            calEvent.event.start,
        );
        let textValue = this.formatDateAsBackend(calEvent.event.end);
        if (calEvent.event.extendedProps.alloc_hours) {
            textValue += ` (${calEvent.event.extendedProps.alloc_hours})`;
        }
        if (parseFloat(calEvent.event.extendedProps.alloc_perc) < 100) {
            textValue += ` (${calEvent.event.extendedProps.alloc_perc}%)`;
        }
        document.querySelector(".o_end_date").textContent = textValue;

        const roleEl = document.getElementById("role");
        setFieldVisibility(roleEl, !!calEvent.event.extendedProps.role);
        if (calEvent.event.extendedProps.role) {
            roleEl.textContent = calEvent.event.extendedProps.role;
        }

        const noteEl = document.getElementById("note");
        setFieldVisibility(noteEl, !!calEvent.event.extendedProps.note);
        if (calEvent.event.extendedProps.note) {
            noteEl.textContent = calEvent.event.extendedProps.note;
        }

        if (
            calEvent.event.extendedProps.allow_self_unassign &&
            !calEvent.event.extendedProps.is_unassign_deadline_passed &&
            !calEvent.event.extendedProps.is_open_shift
        ) {
            document.getElementById("dismiss_shift").style.display = "block";
            displayFooter = true;
        } else {
            document.getElementById("dismiss_shift").style.display = "none";
        }
        if (
            !calEvent.event.extendedProps.request_to_switch &&
            !calEvent.event.extendedProps.is_past &&
            !calEvent.event.extendedProps.allow_self_unassign &&
            !calEvent.event.extendedProps.is_open_shift
        ) {
            document.getElementById("switch_shift").style.display = "block";
            displayFooter = true;
        } else {
            document.getElementById("switch_shift").style.display = "none";
        }
        if (
            calEvent.event.extendedProps.request_to_switch &&
            !calEvent.event.extendedProps.allow_self_unassign &&
            !calEvent.event.extendedProps.is_open_shift
        ) {
            document.getElementById("cancel_switch").style.display = "block";
            displayFooter = true;
        } else {
            document.getElementById("cancel_switch").style.display = "none";
        }
        if (calEvent.event.extendedProps.is_open_shift) {
            document.getElementById("take_open_switch").style.display = "block";
            displayFooter = true;
        } else {
            document.getElementById("take_open_switch").style.display = "none";
        }

        const slotId = calEvent.event.extendedProps.slot_id;
        const basePath = `/planning/${planningToken}/${employeeToken}`;
        document
            .getElementById("modal_action_dismiss_shift")
            .setAttribute("action", `${basePath}/unassign/${slotId}`);
        document
            .getElementById("modal_action_switch_shift")
            .setAttribute("action", `${basePath}/switch/${slotId}`);
        document
            .getElementById("modal_action_cancel_switch")
            .setAttribute("action", `${basePath}/cancel_switch/${slotId}`);
        document
            .getElementById("modal_action_take_open_switch")
            .setAttribute("action", `${basePath}/take_open_shift/${slotId}`);

        const modalEl = document.getElementById("fc-slot-onclick-modal");
        const modal = Modal.getOrCreateInstance(modalEl);
        modal.show();

        document.getElementsByClassName("modal-footer")[0].style.display = displayFooter
            ? "block"
            : "none";
    }
}

registry
    .category("public.interactions")
    .add("planning.planning_calendar_front", PlanningCalendarFront);

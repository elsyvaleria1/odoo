/** @odoo-module native */
import { browser } from "@web/core/browser/browser";
import { compareDates, deserializeDateTime, now } from "@web/core/l10n/dates";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { Tooltip } from "@web/libs/bootstrap";
import { Interaction } from "@web/public/interaction";

import { findInvalidEmailFromText } from "../js/utils.js";

export class AppointmentValidation extends Interaction {
    static selector = ".o_appointment_validation_details";
    dynamicContent = {
        ".o_appointment_copy_link": {
            "t-on-click": this.onCopyVideocallLink,
        },
        ".o_appointment_guest_addition_open": {
            "t-on-click.noUpdate": this.onGuestAdditionOpen,
            "t-att-class": () => ({
                "d-none": this.showGuestAddition,
            }),
        },
        ".o_appointment_guest_discard": {
            "t-on-click": this.onGuestDiscard,
            "t-att-class": () => ({
                "d-none": !this.showGuestAddition,
            }),
        },
        ".o_appointment_guest_add": {
            "t-on-click": this.locked(this.onGuestAdd),
            "t-att-class": () => ({
                "d-none": !this.showGuestAddition,
            }),
        },
        ".o_appointment_validation_error": {
            "t-att-class": () => ({
                "d-none": this.errorMessage.length === 0,
            }),
        },
        ".o_appointment_error_text": {
            "t-out": () => this.errorMessage,
        },
        "#o_appointment_input_guest_emails": {
            "t-att-class": () => ({
                "d-none": !this.showGuestAddition,
            }),
        },
    };

    setup() {
        this.errorMessage = "";
        this.showGuestAddition = false;
    }

    start() {
        if (user.userId) {
            return;
        }
        const eventAccessToken = this.el.dataset.eventAccessToken;
        const eventStart =
            (this.el.dataset.eventStart &&
                deserializeDateTime(this.el.dataset.eventStart)) ||
            false;
        const allAppointmentsToken =
            JSON.parse(
                localStorage.getItem("appointment.upcoming_events_access_token"),
            ) || [];
        if (
            eventAccessToken &&
            !allAppointmentsToken.includes(eventAccessToken) &&
            eventStart &&
            compareDates(eventStart, now("UTC")) > 0
        ) {
            allAppointmentsToken.push(eventAccessToken);
            localStorage.setItem(
                "appointment.upcoming_events_access_token",
                JSON.stringify(allAppointmentsToken),
            );
        }
    }

    onCopyVideocallLink(ev) {
        const copyButtonEl = ev.target;
        const tooltip = Tooltip.getOrCreateInstance(copyButtonEl, {
            title: _t("Link Copied!"),
            trigger: "manual",
            placement: "right",
        });
        this.waitForTimeout(
            async () =>
                await browser.navigator.clipboard.writeText(copyButtonEl.dataset.value),
            0,
        );
        tooltip.show();
        this.waitForTimeout(() => tooltip.hide(), 1200);
    }

    async onGuestAdd() {
        const guestEmails = this.el.querySelector(
            "#o_appointment_input_guest_emails",
        ).value;
        const accessToken = this.el.querySelector("#access_token").value;
        const emailInfo = findInvalidEmailFromText(guestEmails);
        if (emailInfo.emailList.length > 10) {
            this.errorMessage = _t("You cannot invite more than 10 people");
        } else if (emailInfo.invalidEmails.length) {
            this.errorMessage = _t("Invalid Email");
        } else {
            this.errorMessage = "";
            try {
                await rpc(`/calendar/${accessToken}/add_attendees_from_emails`, {
                    access_token: accessToken,
                    emails_str: guestEmails,
                });
            } catch (error) {
                this.errorMessage = _t("An error occurred while adding the guests.");
                this.updateContent();
                throw error;
            }
            location.reload();
        }
    }

    onGuestAdditionOpen() {
        this.showGuestAddition = true;
        this.updateContent();
        this.el.querySelector("#o_appointment_input_guest_emails").focus();
    }

    onGuestDiscard() {
        this.showGuestAddition = false;
        this.el.querySelector("#o_appointment_input_guest_emails").value = "";
    }
}

registry
    .category("public.interactions")
    .add("appointment.appointment_validation", AppointmentValidation);

/** @odoo-module native */
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { isEmail } from "@web/core/utils/format/strings";
import { renderToElement } from "@web/core/utils/render";
import { getRootAppContext } from "@web/env";
import { Interaction } from "@web/public/interaction";

export class WebsiteEventTrackReminder extends Interaction {
    static selector = ".o_wetrack_js_reminder";

    dynamicContent = {
        _root: {
            "t-on-submit": () => {
                this.submitted = true;
            },
        },
        _document: {
            "t-on-website_event_track:reminder_toggled": this.onReminderToggled,
            "t-on-website_event_track:reminder_queued": this.onReminderQueued,
        },
        ".o_wetrack_js_reminder_bell": {
            "t-on-mouseover.withTarget": (ev, targetEl) => {
                if (!this.reminderOn) {
                    targetEl.classList.replace("fa-regular", "fa-solid");
                }
            },
            "t-on-mouseout.withTarget": (ev, targetEl) => {
                if (!this.reminderOn) {
                    targetEl.classList.replace("fa-solid", "fa-regular");
                }
            },
        },
    };

    setup() {
        this.notification = this.services.notification;
        this.trackId = parseInt(this.el.dataset.trackId);
        this.submitted = false;
        this.favoriteAddedConfirmation = "";
    }

    get reminderOn() {
        return this.el.querySelector("input[name='set_reminder_on']")?.value === "0";
    }

    /** @param {{ track_id: number }} detail */
    _isAnswerToThis(detail) {
        if (!this.submitted || detail.track_id !== this.trackId) {
            return false;
        }
        this.submitted = false;
        return true;
    }

    /** @param {CustomEvent<{ track_id: number, reminder_on: boolean, email: Object | null }>} ev */
    onReminderToggled(ev) {
        if (!this._isAnswerToThis(ev.detail)) {
            return;
        }
        const { reminder_on: reminderOn, email } = ev.detail;
        if (!reminderOn) {
            this.favoriteAddedConfirmation = "";
            this.notification.add(_t("Talk removed from your Favorites"), {
                type: "info",
            });
            return;
        }
        this.favoriteAddedConfirmation = _t(
            "Track successfully added to your favorites.",
        );
        getRootAppContext().bus.trigger("open_notification_request", [
            "add_track_to_favorite",
            {
                title: _t("Allow push notifications?"),
                body: _t(
                    "You have to enable push notifications to get reminders for your favorite tracks.",
                ),
                delay: 0,
            },
        ]);
        if (email) {
            this._showEmailReminderResult(email);
        } else {
            this._checkEmailReminder();
        }
    }

    /** @param {CustomEvent<{ track_id: number, reminder_on: boolean }>} ev */
    onReminderQueued(ev) {
        if (!this._isAnswerToThis(ev.detail)) {
            return;
        }
        const reminderOn = ev.detail.reminder_on;
        for (const stateEl of document.querySelectorAll(
            `[data-fragment="website_event_track.reminder.${this.trackId}"]`,
        )) {
            stateEl.querySelector("input[name='set_reminder_on']").value = reminderOn
                ? "0"
                : "1";
            const bellEl = stateEl.querySelector(".o_wetrack_js_reminder_bell");
            bellEl.classList.toggle("fa-solid", reminderOn);
            bellEl.classList.toggle("fa-regular", !reminderOn);
            bellEl.setAttribute(
                "title",
                reminderOn ? _t("Favorite On") : _t("Set Favorite"),
            );
        }
    }

    _checkEmailReminder() {
        const emailReminder = sessionStorage.getItem(
            "website_event_track.email_reminder_email",
        );
        if (emailReminder) {
            this._sendEmailReminder(emailReminder);
        } else if (!sessionStorage.getItem("website_event_track.email_reminder_off")) {
            this._openEmailReminderModal();
        } else {
            this.notification.add(this.favoriteAddedConfirmation, { type: "info" });
        }
    }

    _openEmailReminderModal() {
        this.opacityManagerElement = this.el.closest(".o_we_agenda_card") ?? this.el;
        this.initialOpacity = window
            .getComputedStyle(this.opacityManagerElement)
            .getPropertyValue("opacity");
        this.opacityManagerElement.style.opacity = 1;
        this.modalEl = renderToElement("website_event_track.email_reminder_modal", {
            track_id: this.trackId,
        });
        this.insert(this.modalEl, this.el, "afterend");
        for (const cancelEl of this.modalEl.querySelectorAll(".o_form_button_cancel")) {
            this.addListener(cancelEl, "click", this.modalEmailReminderCancel);
        }
        this.addListener(
            this.modalEl.querySelector(".o_form_button_dont_ask_again"),
            "click",
            () => {
                sessionStorage.setItem(
                    "website_event_track.email_reminder_off",
                    "true",
                );
                this.modalEmailReminderCancel();
            },
        );
        this.addListener(
            this.modalEl.querySelector("#o_wetrack_email_reminder_form"),
            "submit",
            this.modalEmailReminderSubmit,
        );
    }

    modalEmailReminderCancel() {
        this._modalEmailReminderRemove();
        if (this.favoriteAddedConfirmation) {
            this.notification.add(this.favoriteAddedConfirmation, { type: "info" });
        }
    }

    _modalEmailReminderRemove() {
        this.modalEl?.remove();
        this.modalEl = null;
        this.opacityManagerElement.style.opacity = this.initialOpacity;
    }

    /** @param {SubmitEvent} ev */
    modalEmailReminderSubmit(ev) {
        ev.preventDefault();
        const data = Object.fromEntries(
            new FormData(/** @type {HTMLFormElement} */ (ev.target)).entries(),
        );
        if (this.favoriteAddedConfirmation) {
            this.notification.add(this.favoriteAddedConfirmation, { type: "info" });
        }
        if (data.track_id && !isNaN(data.track_id) && isEmail(data.email)) {
            sessionStorage.setItem(
                "website_event_track.email_reminder_email",
                data.email,
            );
            this._sendEmailReminder(data.email);
        } else if (!isEmail(data.email)) {
            this.notification.add(_t("Invalid email"), {
                type: "danger",
                title: _t("Email Error"),
            });
        } else {
            this.notification.add(_t("Invalid data"), {
                type: "danger",
                title: _t("Email Error"),
            });
        }
        this._modalEmailReminderRemove();
    }

    /** @param {string} emailTo */
    async _sendEmailReminder(emailTo) {
        const result = await this.waitFor(
            rpc("/event/track/send_email_reminder", {
                track_id: this.trackId,
                email_to: emailTo,
            }),
        );
        this._showEmailReminderResult(result);
    }

    /** @param {{ success: boolean, error?: string, message?: string }} result */
    _showEmailReminderResult(result) {
        if (result.success || result.error === "missing_template") {
            const emailSentInfo =
                result.error !== "missing_template"
                    ? _t("Check your email to add the track to your agenda.")
                    : "";
            this.notification.add(
                [this.favoriteAddedConfirmation, emailSentInfo].join(" "),
                { type: "info", className: "o_send_email_reminder_success" },
            );
        } else {
            if (this.favoriteAddedConfirmation) {
                this.notification.add(this.favoriteAddedConfirmation, { type: "info" });
            }
            this.notification.add(result.message, {
                type: "danger",
                title: _t("Email Error"),
            });
        }
    }
}

registry
    .category("public.interactions")
    .add("website_event_track.website_event_track_reminder", WebsiteEventTrackReminder);

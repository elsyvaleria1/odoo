/** @odoo-module native */
import { AppointmentForm } from "@calendar/booking/interactions/appointment_form";
import { Captcha } from "@captcha/captcha";
import { patch } from "@web/core/utils/patch";

patch(AppointmentForm.prototype, {
    setup() {
        super.setup();
        this.captcha = new Captcha();
        this.notification = this.services.notification;
    },

    async willStart() {
        this.captcha.load();
        await super.willStart();
    },

    /**
     * @override
     */
    async onConfirmAppointment(ev) {
        const button = ev.target;
        const form = button.closest("form");
        if (!(await this.addCaptchaToken(form))) {
            button.setAttribute("disabled", true);
            setTimeout(() => button.removeAttribute("disabled"), 2000);
        } else {
            super.onConfirmAppointment.call(this, ...arguments);
        }
    },

    /**
     * @returns {boolean}
     */
    async addCaptchaToken(form) {
        const tokenObj = await this.captcha.getToken("appointment_form_submission");
        if (tokenObj.error) {
            this.notification.add(tokenObj.error, {
                sticky: true,
                type: "danger",
            });
            return false;
        } else if (tokenObj.token) {
            const tokenInput = document.createElement("input");
            tokenInput.setAttribute("name", "captcha_token");
            tokenInput.setAttribute("type", "hidden");
            tokenInput.setAttribute("value", tokenObj.token);
            form.appendChild(tokenInput);
        }
        return true;
    },
});

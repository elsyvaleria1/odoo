/** @odoo-module native */
import { Captcha } from "@captcha/captcha";
import { registry } from "@web/core/registry";
import { Modal } from "@web/libs/bootstrap";
import { Interaction } from "@web/public/interaction";

export class ModalRegistration extends Interaction {
    static selector =
        "#modal_attendees_registration,.o_wevent_modal_slot_ticket_registration";
    dynamicContent = {
        "#attendee_registration": {
            "t-on-submit": this.onSubmit,
        },
        ".js_goto_event, .btn-close": {
            "t-on-click": this.onClick,
        },
    };

    setup() {
        this.captcha = new Captcha();
    }

    async willStart() {
        await this.captcha.load();
    }

    start() {
        const formModal = Modal.getOrCreateInstance(this.el, {
            backdrop: "static",
            keyboard: false,
        });

        formModal.show();
        this.registerCleanup(() => formModal.dispose());
    }

    onClick() {
        this.el.remove();
    }

    /**
     * @param {SubmitEvent} ev
     */
    async onSubmit(ev) {
        ev.preventDefault();

        const form = ev.currentTarget;
        const tokenObj = await this.captcha.getToken("website_event_registration");
        if (tokenObj.error) {
            this.services.notification.add(tokenObj.error, {
                type: "danger",
                sticky: true,
            });
            this.el.remove();
            this.services["public.interactions"].stopInteractions(this.el);
            return;
        }
        if (tokenObj.token) {
            const tokenInput = document.createElement("input");
            tokenInput.setAttribute("name", "captcha_token");
            tokenInput.setAttribute("type", "hidden");
            tokenInput.setAttribute("value", tokenObj.token);
            this.insert(tokenInput, form);
        }
        form.submit();
    }
}

registry
    .category("public.interactions")
    .add("website_event.modal_registration", ModalRegistration);

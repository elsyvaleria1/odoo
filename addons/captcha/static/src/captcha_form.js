/** @odoo-module native */
import { registry } from "@web/core/registry";
import { addLoadingEffect } from "@web/core/utils/dom/ui";
import { Interaction } from "@web/public/interaction";

import { Captcha } from "./captcha.js";

export class CaptchaForm extends Interaction {
    static selector = "form[data-captcha]";
    dynamicContent = {
        _root: { "t-on-submit": this.onSubmit },
    };

    setup() {
        this.captcha = new Captcha();
    }

    async willStart() {
        await this.captcha.load();
    }

    /**
     * @param {SubmitEvent} ev
     */
    async onSubmit(ev) {
        const submitEl = this.el.querySelector("button[type='submit']");
        if (!submitEl.disabled) {
            addLoadingEffect(submitEl);
        }
        if (!this.el.querySelector("input[name='captcha_token']")) {
            ev.preventDefault();
            const action = this.el.dataset.captcha || "generic";
            const result = await this.waitFor(this.captcha.getToken(action));
            if (result.token) {
                const inputEl = document.createElement("input");
                inputEl.name = "captcha_token";
                inputEl.type = "hidden";
                inputEl.value = result.token;
                this.insert(inputEl);
            }
            this.el.submit();
        }
    }
}

registry.category("public.interactions").add("captcha.captcha_form", CaptchaForm);

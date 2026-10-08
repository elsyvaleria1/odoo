/** @odoo-module native */
import { Captcha } from "@captcha/captcha";
import { isVisible } from "@html_editor/utils/dom_info";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { Modal } from "@web/libs/bootstrap";
import { Interaction } from "@web/public/interaction";

export class Subscribe extends Interaction {
    static selector = ".js_subscribe";
    dynamicContent = {
        ".js_subscribe_btn": { "t-on-click": this.onSubscribeClick },
    };

    setup() {
        this.captcha = new Captcha();
        this.notification = this.services["notification"];
    }

    async willStart() {
        const inputName = this.el.querySelector("input").name;
        const data = await this.waitFor(
            rpc("/website_mass_mailing/is_subscriber", {
                list_id: this._getListId(),
                subscription_type: inputName,
            }),
        );
        this._updateView(data);
        await this.captcha.load();
    }

    destroy() {
        this._updateView({ is_subscriber: false });
    }

    /**
     * @param {Object} data
     */
    _updateView(data) {
        this._updateSubscribeControlsStatus(!!data.is_subscriber);

        const valueInputEl = this.el.querySelector(
            "input.js_subscribe_value, input.js_subscribe_email",
        );
        valueInputEl.value = data.value || "";

        this.el.classList.remove("d-none");
    }

    /**
     * @param {boolean} isSubscriber
     */
    _updateSubscribeControlsStatus(isSubscriber) {
        const thanksWrapEl = this.el.querySelector(".js_subscribed_wrap");
        const subscribeWrapEl = this.el.querySelector(".js_subscribe_wrap");
        const subscribeBtnEl = this.el.querySelector(".js_subscribe_btn");

        subscribeBtnEl.disabled = isSubscriber;
        subscribeWrapEl.classList.toggle("d-none", isSubscriber);
        thanksWrapEl.classList.toggle("d-none", !isSubscriber);

        const valueInputEl = this.el.querySelector(
            "input.js_subscribe_value, input.js_subscribe_email",
        );
        valueInputEl.disabled = isSubscriber;
    }

    _getListId() {
        return (
            this.el.closest("section[data-list-id]")?.dataset.listId ||
            this.el.dataset.listId
        );
    }

    async onSubscribeClick() {
        const inputName = this.el.querySelector("input").name;
        const input = this.el.querySelector(".js_subscribe_value, .js_subscribe_email");
        if (inputName === "email" && isVisible(input) && !input.value.match(/.+@.+/)) {
            this.el.classList.add("o_has_error");
            this.el.querySelector(".form-control").classList.add("is-invalid");
            return;
        }
        this.el.classList.remove("o_has_error");
        this.el.querySelector(".form-control").classList.remove("is-invalid");
        const tokenObj = await this.waitFor(
            this.captcha.getToken("website_mass_mailing_subscribe"),
        );
        if (tokenObj.error) {
            this.notification.add(tokenObj.error, {
                type: "danger",
                sticky: true,
            });
            return;
        }
        const result = await this.waitFor(
            rpc("/website_mass_mailing/subscribe", {
                list_id: this._getListId(),
                value: input?.value ?? false,
                subscription_type: inputName,
                ...(tokenObj.token ? { captcha_token: tokenObj.token } : {}),
            }),
        );
        const toastType = result.toast_type;
        if (toastType === "success") {
            this._updateSubscribeControlsStatus(true);
            const modalEl = this.el.closest(".o_newsletter_modal");
            if (modalEl) {
                Modal.getOrCreateInstance(modalEl).hide();
            }
        }
        this.notification.add(result.toast_content, {
            type: toastType,
            sticky: true,
        });
    }
}

registry
    .category("public.interactions")
    .add("website_mass_mailing.subscribe", Subscribe);

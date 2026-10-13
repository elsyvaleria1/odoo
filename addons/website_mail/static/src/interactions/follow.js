/** @odoo-module native */
import { Captcha } from "@captcha/captcha";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

/** @type {{ records: Record<string, number[]>, answer: Promise<any> } | null} */
let pendingFollowState = null;

/**
 * @param {string} model
 * @param {number} id
 * @returns {Promise<[{ is_user: boolean, email: string }, Record<string, number[]>]>}
 */
function fetchFollowState(model, id) {
    if (!pendingFollowState) {
        const records = {};
        pendingFollowState = {
            records,
            answer: Promise.resolve().then(() => {
                pendingFollowState = null;
                return rpc("/website_mail/is_follower", { records });
            }),
        };
    }
    (pendingFollowState.records[model] ||= []).push(id);
    return pendingFollowState.answer;
}

export class Follow extends Interaction {
    static selector = ".js_follow";
    dynamicContent = {
        ":scope > .d-none": {
            "t-att-class": () => ({ "d-none": false }),
        },
        ".js_follow_btn, .js_unfollow_btn": {
            "t-on-click.prevent": this.onToggleFollowClick,
        },
    };

    setup() {
        this.isUser = false;
        this.captcha = new Captcha();
    }

    async willStart() {
        const model = this.el.dataset.object;
        const id = parseInt(this.el.dataset.id);
        const [[user, followed]] = await this.waitFor(
            Promise.all([fetchFollowState(model, id), this.captcha.load()]),
        );
        this.isUser = user.is_user;
        this.toggleSubscription(Boolean(followed[model]?.includes(id)), user.email);
        this.el.classList.remove("d-none");
    }

    /**
     * @param {boolean} follow
     * @param {string} email
     */
    toggleSubscription(follow, email) {
        this.updateSubscriptionDOM(
            follow || (!email && this.el.dataset.unsubscribe),
            email,
        );
    }

    /**
     * @param {boolean} follow
     * @param {string} email
     */
    updateSubscriptionDOM(follow, email) {
        const jsFollowEmailEl = this.el.querySelector("input.js_follow_email");
        if (jsFollowEmailEl) {
            jsFollowEmailEl.setAttribute("value", email || "");
            if (email && (follow || this.isUser)) {
                jsFollowEmailEl.setAttribute("disabled", true);
            } else {
                jsFollowEmailEl.removeAttribute("disabled");
            }
        }
        this.el.dataset.follow = follow ? "on" : "off";
    }

    /** @param {boolean} status */
    toggleEmailError(status) {
        this.el.classList.toggle("o_has_error", status);
        const formEls = this.el.querySelectorAll(".form-control, .form-select");
        for (const formEl of formEls) {
            formEl.classList.toggle("is-invalid", status);
        }
    }

    async onToggleFollowClick() {
        let email = this.el.querySelector(".js_follow_email");

        if (email && !/.+@.+/.test(email.value)) {
            this.toggleEmailError(true);
            return false;
        }

        this.toggleEmailError(false);
        email = email ? email.value : false;
        if (email || this.isUser) {
            const tokenCaptcha = await this.captcha.getToken("website_mail_follow");
            const token = tokenCaptcha.token;

            if (tokenCaptcha.error) {
                this.services.notification.add(tokenCaptcha.error, {
                    type: "danger",
                    sticky: true,
                });
                return false;
            }

            const data = await this.waitFor(
                rpc("/website_mail/follow", {
                    id: parseInt(this.el.dataset.id),
                    object: this.el.dataset.object,
                    message_is_follower: this.el.dataset.follow || "off",
                    email: email,
                    ...(token ? { captcha_token: token } : {}),
                }),
            );

            this.toggleSubscription(data, email);
        }
    }
}

registry.category("public.interactions").add("website_mail.follow", Follow);

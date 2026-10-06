/** @odoo-module native */

import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { WarningDialog } from "@web/components/errors";
import { colorScheme } from "@web/core/color_scheme";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { Dialog } from "@web/ui/dialog";

import { InputVerificationCode } from "./verification_code_input.js";

class PrivateCardViewDialog extends Component {
    static template = "hr_expense_stripe.privateCardViewDialog";
    static components = { Dialog, InputVerificationCode };

    static props = { action: t.object(), close: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        this.card_id = this.props.action.params.res_id;
        this.stripe_id = this.props.action.params.stripe_id;

        this.dialog = useService("dialog");
        this.ui = useService("ui");
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.numberPlaceholder = elementRef();
        this.cvcPlaceholder = elementRef();
        this.numberCopyPlaceholder = elementRef();
        this.cvcCopyPlaceholder = elementRef();
        this.pinPlaceholder = elementRef();

        this.state = proxy({
            ephemeralKey: undefined,
            nonce: undefined,
            session: undefined,
            phone_number_last3: _t("(Fetching...)"),
            card: {
                name: _t("Cardholder Name"),
                number: "**** **** **** 1234",
                type: _t("Virtual"),
                card_type: "virtual",
                exp: "12/29",
                cvc: "***",
            },
        });

        this.close = this.props.close;

        useLayoutEffect(
            (ephemeralKey) => {
                if (ephemeralKey) {
                    this.buildStripeIframes();
                }
            },
            () => [this.state.ephemeralKey],
        );

        onWillStart(async () => {
            await this.initStripeJS();
            this.send2FARequest();
        });
    }
    // Common
    async initStripeJS() {
        const result = await this.ormCardCall("get_stripe_js_init_params");
        if (!result) {
            this.raiseUIError(_t("Failed to fetch StripeJS initialization params."));
        }

        this.stripejs = Stripe(result.public_key, {
            stripeAccount: result.account,
        });
    }

    // Card View
    async fetchCardInfo() {
        try {
            const result = (
                await this.orm.read(
                    "hr.expense.stripe.card",
                    [this.card_id],
                    ["name", "card_number_public", "card_type", "expiration"],
                )
            )[0];

            this.state.card.name = result.name;
            this.state.card.exp = result.expiration;
            this.state.card.number = result.card_number_public;
            this.state.card.type =
                result.card_type === "virtual" ? _t("Virtual") : _t("Physical");
            this.state.card.card_type = result.card_type;
        } catch (error) {
            this.close();
            throw error;
        }
    }

    async buildStripeIframes() {
        const elements = this.stripejs.elements();
        const cardNumberElement = elements.create("issuingCardNumberDisplay", {
            issuingCard: this.stripe_id,
            nonce: this.state.nonce,
            ephemeralKeySecret: this.state.ephemeralKey,
            style: {
                base: {
                    color: "#fff",
                    fontWeight: 700,
                    fontSize: "16px",
                    alignSelf: "center",
                },
            },
        });

        // Small Fix as sometimes when we click on the numbers it calls focus which is not available for issuing elements
        cardNumberElement.focus = () => {};
        cardNumberElement.mount(this.numberPlaceholder.el);

        const cardCvcElement = elements.create("issuingCardCvcDisplay", {
            issuingCard: this.stripe_id,
            nonce: this.state.nonce,
            ephemeralKeySecret: this.state.ephemeralKey,
            style: {
                base: {
                    color: "#fff",
                    fontWeight: 400,
                    fontSize: "14px",
                    alignSelf: "center",
                },
            },
        });
        // Small Fix as sometimes when we click on the numbers it calls focus which is not available for issuing elements
        cardCvcElement.focus = () => {};
        cardCvcElement.mount(this.cvcPlaceholder.el);

        if (this.state.card.card_type === "physical") {
            const cardPinElement = elements.create("issuingCardPinDisplay", {
                issuingCard: this.stripe_id,
                nonce: this.state.nonce,
                ephemeralKeySecret: this.state.ephemeralKey,
                style: {
                    base: {
                        color: colorScheme.isDark ? "#fff" : "#000",
                        fontWeight: 400,
                        fontSize: "14px",
                        alignSelf: "center",
                    },
                },
            });
            // Small Fix as sometimes when we click on the numbers it calls focus which is not available for issuing elements
            cardPinElement.focus = () => {};
            cardPinElement.mount(this.pinPlaceholder.el);
        }

        //Copy buttons
        const cardNumberCopyElement = elements.create("issuingCardCopyButton", {
            toCopy: "number",
            style: {
                base: {
                    fontSize: "1.1rem",
                },
            },
        });
        cardNumberCopyElement.mount(this.numberCopyPlaceholder.el);
        cardNumberCopyElement.on("click", () => {
            this.notification.add(_t("Card number copied to the clipboard."), {
                type: "info",
            });
        });

        const cardCvcCopyElement = elements.create("issuingCardCopyButton", {
            toCopy: "cvc",
            style: {
                base: {
                    fontSize: "0.9rem",
                },
            },
        });
        cardCvcCopyElement.mount(this.cvcCopyPlaceholder.el);
        cardCvcCopyElement.on("click", () => {
            this.notification.add(_t("Card cvc copied to the clipboard."), {
                type: "info",
            });
        });
    }

    // 2FA
    async send2FARequest() {
        const phoneResult = await this.ormCardCall("action_send_iap_2fa_code");
        this.state.session = phoneResult.session_id;
        this.state.phone_number_last3 = phoneResult.phone_number_last3;
    }

    async requestEphemeralKey(code) {
        const nonceResult = await this.stripejs.createEphemeralKeyNonce({
            issuingCard: this.stripe_id,
        });
        this.ui.unblock();
        this.state.nonce = nonceResult.nonce;
        const ephemeralKeyResult = await this.ormCardCall(
            "action_request_ephemeral_key",
            nonceResult.nonce,
            code,
            this.state.session,
        );
        if (ephemeralKeyResult) {
            await this.fetchCardInfo();
            this.state.ephemeralKey = ephemeralKeyResult.secret;
        }
    }

    // Utility functions
    ormCardCall(functionName, ...params) {
        try {
            return this.orm.call("hr.expense.stripe.card", functionName, [
                this.card_id, // res_id
                ...params,
            ]);
        } catch (error) {
            this.close();
            throw error;
        }
    }

    raiseUIError(message) {
        this.dialog.add(WarningDialog, {
            title: _t("Error"),
            message: message,
        });
        this.close();
    }
}

export function PrivateCardViewAction(env, action) {
    return new Promise((resolve) => {
        env.services.dialog.add(
            PrivateCardViewDialog,
            {
                action,
            },
            {
                onClose: () => {
                    resolve({ type: "ir.actions.act_window_close" });
                },
            },
        );
    });
}

registry
    .category("actions")
    .add("hr_expense_stripe.private_card_view_action", PrivateCardViewAction);

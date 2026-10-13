/** @odoo-module native */
import { rpc, RPCError } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { renderToMarkup } from "@web/core/utils/render";
import { Tooltip } from "@web/libs/bootstrap";
import { Interaction } from "@web/public/interaction";
import { ConfirmationDialog } from "@web/ui/dialog";

export class PaymentForm extends Interaction {
    static selector = "#o_payment_form";
    dynamicContent = {
        '[name="o_payment_radio"]': { "t-on-change": this.selectPaymentOption },
        '[name="o_payment_delete_token"]': { "t-on-click": this.fetchTokenData },
        '[name="o_payment_expand_button"]': { "t-on-click": this.hideExpandButton },
        '[name="o_payment_submit_button"]': { "t-on-click": this.submitForm },
    };

    setup() {
        this.paymentContext = {};
        Object.assign(this.paymentContext, this.el.dataset);

        this.defaultSubmitButtonLabel = document.querySelector(
            'button[name="o_payment_submit_button"]',
        )?.textContent;

        this.el.querySelectorAll('[data-bs-toggle="tooltip"]').forEach((el) => {
            const tooltip = Tooltip.getOrCreateInstance(el);
            this.registerCleanup(() => tooltip.dispose());
        });
    }

    async willStart() {
        const checkedRadio = document.querySelector(
            'input[name="o_payment_radio"]:checked',
        );
        if (checkedRadio) {
            await this.waitFor(this._expandInlineForm(checkedRadio));
            this._enableButton(false);
        } else {
            this._setPaymentFlow();
        }
    }

    /**
     * @param {Event} ev
     * @return {void}
     */
    async selectPaymentOption(ev) {
        this._showInputs();

        this._disableButton();

        const checkedRadio = ev.target;
        await this.waitFor(this._expandInlineForm(checkedRadio));

        this._enableButton(false);
    }

    /**
     * @param {Event} ev
     * @return {void}
     */
    async fetchTokenData(ev) {
        ev.preventDefault();

        const linkedRadio = document.getElementById(
            ev.currentTarget.dataset["linkedRadio"],
        );
        const tokenId = this._getPaymentOptionId(linkedRadio);
        try {
            const linkedRecordsInfo = await this.waitFor(
                this.services.orm.call("payment.token", "get_linked_records_info", [
                    tokenId,
                ]),
            );
            this._challengeTokenDeletion(tokenId, linkedRecordsInfo);
        } catch (error) {
            if (error instanceof RPCError) {
                this._displayErrorDialog(
                    _t("Cannot delete payment method"),
                    error.data.message,
                );
            } else {
                return Promise.reject(error);
            }
        }
    }

    /**
     * @param {Event} ev
     * @return {void}
     */
    hideExpandButton(ev) {
        ev.target.classList.add("d-none");
    }

    /**
     * @param {Event} ev
     * @return {void}
     */
    async submitForm(ev) {
        ev.stopPropagation();
        ev.preventDefault();

        const checkedRadio = this.el.querySelector(
            'input[name="o_payment_radio"]:checked',
        );

        this._disableButton(true);

        const flow = (this.paymentContext.flow = this._getPaymentFlow(checkedRadio));
        const paymentOptionId = (this.paymentContext.paymentOptionId =
            this._getPaymentOptionId(checkedRadio));
        if (flow === "token" && this.paymentContext["assignTokenRoute"]) {
            await this._assignToken(paymentOptionId);
        } else {
            const providerCode = (this.paymentContext.providerCode =
                this._getProviderCode(checkedRadio));
            const pmCode = (this.paymentContext.paymentMethodCode =
                this._getPaymentMethodCode(checkedRadio));
            this.paymentContext.providerId = this._getProviderId(checkedRadio);
            if (this._getPaymentOptionType(checkedRadio) === "token") {
                this.paymentContext.tokenId = paymentOptionId;
            } else {
                this.paymentContext.paymentMethodId = paymentOptionId;
            }
            const inlineForm = this._getInlineForm(checkedRadio);
            this.paymentContext.tokenizationRequested =
                inlineForm?.querySelector('[name="o_payment_tokenize_checkbox"]')
                    ?.checked ?? this.paymentContext["mode"] === "validation";
            await this._initiatePaymentFlow(
                providerCode,
                paymentOptionId,
                pmCode,
                flow,
            );
        }
    }

    /**
     * @private
     * @param {boolean} unblockUI
     * @return {void}
     */
    _enableButton(unblockUI = true) {
        this.env.bus.trigger("enablePaymentButton");
        if (unblockUI) {
            this.env.bus.trigger("ui", "unblock");
        }
    }

    /**
     * @private
     * @param {boolean} blockUI
     * @return {void}
     */
    _disableButton(blockUI = false) {
        this.env.bus.trigger("disablePaymentButton");
        if (blockUI) {
            this.env.bus.trigger("ui", "block");
        }
    }

    /**
     * @private
     * @return {void}
     */
    _showInputs() {
        const tokenizeContainer = this.el.querySelector(
            '[name="o_payment_tokenize_container"]',
        );
        tokenizeContainer?.classList.remove("d-none");

        this.env.bus.trigger("showPaymentButton");
    }

    /**
     * @private
     * @return {void}
     */
    _hideInputs() {
        const tokenizeContainer = this.el.querySelector(
            '[name="o_payment_tokenize_container"]',
        );
        tokenizeContainer?.classList.add("d-none");

        this.env.bus.trigger("hidePaymentButton");
    }

    /**
     * @private
     * @param {HTMLInputElement} radio
     * @return {void}
     */
    async _expandInlineForm(radio) {
        this._collapseInlineForms();
        this._setPaymentFlow();

        const providerId = this._getProviderId(radio);
        const providerCode = this._getProviderCode(radio);
        const paymentOptionId = this._getPaymentOptionId(radio);
        const paymentMethodCode = this._getPaymentMethodCode(radio);
        const flow = this._getPaymentFlow(radio);
        await this.waitFor(
            this._prepareInlineForm(
                providerId,
                providerCode,
                paymentOptionId,
                paymentMethodCode,
                flow,
            ),
        );

        this._adaptSubmitButtonLabel(paymentMethodCode);

        const isVisible = (element) => {
            if (
                element.getAttribute("name") !== "o_payment_inline_form" &&
                element.classList.contains("d-none")
            ) {
                return false;
            }
            if (element.children.length === 0) {
                return true;
            }
            return Array.from(element.children).some((child) => isVisible(child));
        };
        const inlineForm = this._getInlineForm(radio);
        if (inlineForm && isVisible(inlineForm)) {
            inlineForm.classList.remove("d-none");
        }
    }

    /**
     * @private
     * @return {void}
     */
    _collapseInlineForms() {
        this.el
            .querySelectorAll('[name="o_payment_inline_form"]')
            .forEach((inlineForm) => {
                inlineForm.classList.add("d-none");
            });
    }

    /**
     * @private
     * @param {number} providerId
     * @param {string} providerCode
     * @param {number} paymentOptionId
     * @param {string} paymentMethodCode
     * @param {string} flow
     * @return {void}
     */
    async _prepareInlineForm() {}

    /**
     * @private
     * @param {string} paymentMethodCode
     * @return {void}
     */
    _adaptSubmitButtonLabel(paymentMethodCode) {
        const buttonLabel = this._isPayLaterPaymentMethod(paymentMethodCode)
            ? _t("Confirm")
            : this.defaultSubmitButtonLabel;
        for (const btn of document.querySelectorAll(
            'button[name="o_payment_submit_button"]',
        )) {
            if (btn.textContent !== buttonLabel) {
                btn.textContent = buttonLabel;
            }
        }
    }

    /**
     * @private
     * @param {string} paymentMethodCode
     * @return {boolean}
     */
    _isPayLaterPaymentMethod() {
        return false;
    }

    /**
     * @private
     * @param {string} title
     * @param {string} errorMessage
     * @return {void}
     */
    _displayErrorDialog(title, errorMessage = "") {
        this.services.dialog.add(ConfirmationDialog, {
            title: title,
            body: errorMessage || "",
        });
    }

    /**
     * @private
     * @param {number} tokenId
     * @param {object} linkedRecordsInfo
     * @return {void}
     */
    _challengeTokenDeletion(tokenId, linkedRecordsInfo) {
        const body = renderToMarkup("payment.deleteTokenDialog", { linkedRecordsInfo });
        this.services.dialog.add(ConfirmationDialog, {
            title: _t("Warning!"),
            body,
            confirmLabel: _t("Confirm Deletion"),
            confirm: () => this._archiveToken(tokenId),
            cancel: () => {},
        });
    }

    /**
     * @private
     * @param {string} flow
     * @return {void}
     */
    _setPaymentFlow(flow = "redirect") {
        if (["redirect", "direct", "token"].includes(flow)) {
            this.paymentContext.flow = flow;
        } else {
            console.warn(
                `The value ${flow} is not a supported flow. Falling back to redirect.`,
            );
            this.paymentContext.flow = "redirect";
        }
    }

    /**
     * @private
     * @param {number} tokenId
     * @return {void}
     */
    async _assignToken(tokenId) {
        try {
            await this.waitFor(
                rpc(this.paymentContext["assignTokenRoute"], {
                    token_id: tokenId,
                    access_token: this.paymentContext["accessToken"],
                }),
            );
            window.location = this.paymentContext["landingRoute"];
        } catch (error) {
            if (error instanceof RPCError) {
                this._displayErrorDialog(
                    _t("Cannot save payment method"),
                    error.data.message,
                );
                this._enableButton();
            } else {
                return Promise.reject(error);
            }
        }
    }

    /**
     * @private
     * @param {string} providerCode
     * @param {number} paymentOptionId
     * @param {string} paymentMethodCode
     * @param {string} flow
     * @return {void}
     */
    async _initiatePaymentFlow(providerCode, paymentOptionId, paymentMethodCode, flow) {
        try {
            const processingValues = await this.waitFor(
                rpc(
                    this.paymentContext["transactionRoute"],
                    this._prepareTransactionRouteParams(),
                ),
            );
            if (processingValues.state === "error") {
                this._displayErrorDialog(
                    _t("Payment processing failed"),
                    processingValues.state_message,
                );
                this._enableButton();
                return;
            }
            if (flow === "redirect") {
                this._processRedirectFlow(
                    providerCode,
                    paymentOptionId,
                    paymentMethodCode,
                    processingValues,
                );
            } else if (flow === "direct") {
                this._processDirectFlow(
                    providerCode,
                    paymentOptionId,
                    paymentMethodCode,
                    processingValues,
                );
            } else if (flow === "token") {
                this._processTokenFlow(
                    providerCode,
                    paymentOptionId,
                    paymentMethodCode,
                    processingValues,
                );
            }
        } catch (error) {
            if (error instanceof RPCError) {
                this._displayErrorDialog(
                    _t("Payment processing failed"),
                    error.data.message,
                );
                this._enableButton();
            }
            return Promise.reject(error);
        }
    }

    /**
     * @private
     * @return {object}
     */
    _prepareTransactionRouteParams() {
        const transactionRouteParams = {
            provider_id: this.paymentContext.providerId,
            payment_method_id: this.paymentContext.paymentMethodId ?? null,
            token_id: this.paymentContext.tokenId ?? null,
            amount:
                this.paymentContext["amount"] !== undefined
                    ? parseFloat(this.paymentContext["amount"])
                    : null,
            flow: this.paymentContext["flow"],
            tokenization_requested: this.paymentContext["tokenizationRequested"],
            landing_route: this.paymentContext["landingRoute"],
            is_validation: this.paymentContext["mode"] === "validation",
            access_token: this.paymentContext["accessToken"],
            csrf_token: odoo.csrf_token,
        };
        if (this.paymentContext["transactionRoute"] === "/payment/transaction") {
            Object.assign(transactionRouteParams, {
                currency_id: this.paymentContext["currencyId"]
                    ? parseInt(this.paymentContext["currencyId"])
                    : null,
                partner_id: parseInt(this.paymentContext["partnerId"]),
                reference_prefix: this.paymentContext["referencePrefix"]?.toString(),
            });
        }
        return transactionRouteParams;
    }

    /**
     * @private
     * @param {string} providerCode
     * @param {number} paymentOptionId
     * @param {string} paymentMethodCode
     * @param {object} processingValues
     * @return {void}
     */
    _processRedirectFlow(
        providerCode,
        paymentOptionId,
        paymentMethodCode,
        processingValues,
    ) {
        const div = document.createElement("div");
        div.innerHTML = processingValues["redirect_form_html"];
        const redirectForm = div.querySelector("form");
        redirectForm.setAttribute("id", "o_payment_redirect_form");
        redirectForm.setAttribute("target", "_top");

        document.body.appendChild(redirectForm);
        redirectForm.submit();
    }

    /**
     * @private
     * @param {string} providerCode
     * @param {number} paymentOptionId
     * @param {string} paymentMethodCode
     * @param {object} processingValues
     * @return {void}
     */
    _processDirectFlow() {}

    /**
     * @private
     * @param {string} providerCode
     * @param {number} paymentOptionId
     * @param {string} paymentMethodCode
     * @param {object} processingValues
     * @return {void}
     */
    _processTokenFlow() {
        window.location = "/payment/status";
    }

    /**
     * @private
     * @param {number} tokenId
     * @return {void}
     */
    _archiveToken(tokenId) {
        const form = document.getElementById("o_payment_archive_token_form");
        form.querySelector('input[name="token_id"]').value = tokenId;
        form.requestSubmit();
    }

    /**
     * @private
     * @param {HTMLInputElement} radio
     * @return {Element | null}
     */
    _getInlineForm(radio) {
        const inlineFormContainer = radio.closest('[name="o_payment_option"]');
        return inlineFormContainer?.querySelector('[name="o_payment_inline_form"]');
    }

    /**
     * @private
     * @param {HTMLInputElement} radio
     * @return {string}
     */
    _getPaymentFlow(radio) {
        if (
            this._getPaymentOptionType(radio) === "token" ||
            this.paymentContext.flow === "token"
        ) {
            return "token";
        } else if (this.paymentContext.flow === "redirect") {
            return "redirect";
        } else {
            return "direct";
        }
    }

    /**
     * @private
     * @param {HTMLElement} radio
     * @return {string}
     */
    _getPaymentMethodCode(radio) {
        return radio.dataset["paymentMethodCode"];
    }

    /**
     * @private
     * @param {HTMLElement} radio
     * @return {number}
     */
    _getPaymentOptionId(radio) {
        return Number(radio.dataset["paymentOptionId"]);
    }

    /**
     * @private
     * @param {HTMLElement} radio
     * @return {string}
     */
    _getPaymentOptionType(radio) {
        return radio.dataset["paymentOptionType"];
    }

    /**
     * @private
     * @param {HTMLElement} radio
     * @return {number}
     */
    _getProviderId(radio) {
        return Number(radio.dataset["providerId"]);
    }

    /**
     * @private
     * @param {HTMLElement} radio
     * @return {string}
     */
    _getProviderCode(radio) {
        return radio.dataset["providerCode"];
    }

    /**
     * @private
     * @param {HTMLElement} radio
     * @return {string}
     */
    _getProviderState(radio) {
        return radio.dataset["providerState"];
    }
}

registry.category("public.interactions").add("payment.payment_form", PaymentForm);

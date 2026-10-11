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
     * Open the inline form of the selected payment option, if any.
     *
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
     * Fetch data relative to the documents linked to the token and delegate them to the token
     * deletion confirmation dialog.
     *
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
     * Hide the button to expand the payment methods section once it has been clicked.
     *
     * @param {Event} ev
     * @return {void}
     */
    hideExpandButton(ev) {
        ev.target.classList.add("d-none");
    }

    /**
     * Update the payment context with the selected payment option and initiate its payment flow.
     *
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
     * Enable the submit button.
     *
     * @private
     * @param {boolean} unblockUI - Whether the UI should also be unblocked.
     * @return {void}
     */
    _enableButton(unblockUI = true) {
        this.env.bus.trigger("enablePaymentButton");
        if (unblockUI) {
            this.env.bus.trigger("ui", "unblock");
        }
    }

    /**
     * Disable the submit button.
     *
     * @private
     * @param {boolean} blockUI - Whether the UI should also be blocked.
     * @return {void}
     */
    _disableButton(blockUI = false) {
        this.env.bus.trigger("disablePaymentButton");
        if (blockUI) {
            this.env.bus.trigger("ui", "block");
        }
    }

    /**
     * Show the tokenization checkbox, its label, and the submit button.
     *
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
     * Hide the tokenization checkbox, its label, and the submit button.
     *
     * The inputs should typically be hidden when the customer has to perform additional actions in
     * the inline form. All inputs are automatically shown again when the customer selects another
     * payment option.
     *
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
     * Open the inline form of the selected payment option and collapse the others.
     *
     * @private
     * @param {HTMLInputElement} radio - The radio button linked to the payment option.
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
     * Collapse all inline forms of the current interaction.
     *
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
     * Prepare the provider-specific inline form of the selected payment option.
     *
     * For a provider to manage an inline form, it must override this method and render the content
     * of the form.
     *
     * @private
     * @param {number} providerId - The id of the selected payment option's provider.
     * @param {string} providerCode - The code of the selected payment option's provider.
     * @param {number} paymentOptionId - The id of the selected payment option.
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @param {string} flow - The online payment flow of the selected payment option.
     * @return {void}
     */
    async _prepareInlineForm() {}

    /**
     * Update the payment button's label for "pay later" payment methods.
     *
     * @private
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
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
     * Check whether the given payment method defers payment (pay later).
     *
     * Override this method to change the submit button label from the default label to "Confirm".
     *
     * @private
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @return {boolean}
     */
    _isPayLaterPaymentMethod() {
        return false;
    }

    /**
     * Display an error dialog.
     *
     * @private
     * @param {string} title - The title of the dialog.
     * @param {string} errorMessage - The error message.
     * @return {void}
     */
    _displayErrorDialog(title, errorMessage = "") {
        this.services.dialog.add(ConfirmationDialog, {
            title: title,
            body: errorMessage || "",
        });
    }

    /**
     * Display the token deletion confirmation dialog.
     *
     * @private
     * @param {number} tokenId - The id of the token whose deletion was requested.
     * @param {object} linkedRecordsInfo - The data relative to the documents linked to the token.
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
     * Set the payment flow for the selected payment option.
     *
     * For a provider to manage direct payments, it must call this method and set the payment flow
     * when its payment option is selected.
     *
     * @private
     * @param {string} flow - The flow for the selected payment option. Either 'redirect', 'direct',
     *                        or 'token'
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
     * Assign the selected token to a document through the `assignTokenRoute`.
     *
     * @private
     * @param {number} tokenId - The id of the token to assign.
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
     * Make an RPC to initiate the payment flow by creating a new transaction.
     *
     * For a provider to do pre-processing work (e.g., perform checks on the form inputs), or to
     * process the payment flow in its own terms (e.g., re-schedule the RPC to the transaction
     * route), it must override this method.
     *
     * To alter the flow-specific processing, it is advised to override `_processRedirectFlow`,
     * `_processDirectFlow`, or `_processTokenFlow` instead.
     *
     * @private
     * @param {string} providerCode - The code of the selected payment option's provider.
     * @param {number} paymentOptionId - The id of the selected payment option.
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @param {string} flow - The payment flow of the selected payment option.
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
     * Prepare the params for the RPC to the transaction route.
     *
     * @private
     * @return {object} The transaction route params.
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
     * Redirect the customer by submitting the redirect form included in the processing values.
     *
     * @private
     * @param {string} providerCode - The code of the selected payment option's provider.
     * @param {number} paymentOptionId - The id of the selected payment option.
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @param {object} processingValues - The processing values of the transaction.
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
     * Process the provider-specific implementation of the direct payment flow.
     *
     * @private
     * @param {string} providerCode - The code of the selected payment option's provider.
     * @param {number} paymentOptionId - The id of the selected payment option.
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @param {object} processingValues - The processing values of the transaction.
     * @return {void}
     */
    _processDirectFlow() {}

    /**
     * Redirect the customer to the status route.
     *
     * @private
     * @param {string} providerCode - The code of the selected payment option's provider.
     * @param {number} paymentOptionId - The id of the selected payment option.
     * @param {string} paymentMethodCode - The code of the selected payment method, if any.
     * @param {object} processingValues - The processing values of the transaction.
     * @return {void}
     */
    _processTokenFlow() {
        window.location = "/payment/status";
    }

    /**
     * Archive the provided token.
     *
     * @private
     * @param {number} tokenId - The id of the token whose deletion was requested.
     * @return {void}
     */
    _archiveToken(tokenId) {
        const form = document.getElementById("o_payment_archive_token_form");
        form.querySelector('input[name="token_id"]').value = tokenId;
        form.requestSubmit();
    }

    /**
     * Determine and return the inline form of the selected payment option.
     *
     * @private
     * @param {HTMLInputElement} radio - The radio button linked to the payment option.
     * @return {Element | null} The inline form of the selected payment option, if any.
     */
    _getInlineForm(radio) {
        const inlineFormContainer = radio.closest('[name="o_payment_option"]');
        return inlineFormContainer?.querySelector('[name="o_payment_inline_form"]');
    }

    /**
     * Determine and return the payment flow of the selected payment option.
     *
     * As some providers implement both direct payments and the payment with redirection flow, we
     * cannot infer it from the radio button only. The radio button indicates only whether the
     * payment option is a token. If not, the payment context is looked up to determine whether the
     * flow is 'direct' or 'redirect'.
     *
     * @private
     * @param {HTMLInputElement} radio - The radio button linked to the payment option.
     * @return {string} The flow of the selected payment option: 'redirect', 'direct' or 'token'.
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
     * Determine and return the code of the selected payment method.
     *
     * @private
     * @param {HTMLElement} radio - The radio button linked to the payment method.
     * @return {string} The code of the selected payment method.
     */
    _getPaymentMethodCode(radio) {
        return radio.dataset["paymentMethodCode"];
    }

    /**
     * Determine and return the id of the selected payment option.
     *
     * @private
     * @param {HTMLElement} radio - The radio button linked to the payment option.
     * @return {number} The id of the selected payment option.
     */
    _getPaymentOptionId(radio) {
        return Number(radio.dataset["paymentOptionId"]);
    }

    /**
     * Determine and return the type of the selected payment option.
     *
     * @private
     * @param {HTMLElement} radio - The radio button linked to the payment option.
     * @return {string} The type of the selected payment option: 'token' or 'payment_method'.
     */
    _getPaymentOptionType(radio) {
        return radio.dataset["paymentOptionType"];
    }

    /**
     * Determine and return the id of the provider of the selected payment option.
     *
     * @private
     * @param {HTMLElement} radio - The radio button linked to the payment option.
     * @return {number} The id of the provider of the selected payment option.
     */
    _getProviderId(radio) {
        return Number(radio.dataset["providerId"]);
    }

    /**
     * Determine and return the code of the provider of the selected payment option.
     *
     * @private
     * @param {HTMLElement} radio - The radio button linked to the payment option.
     * @return {string} The code of the provider of the selected payment option.
     */
    _getProviderCode(radio) {
        return radio.dataset["providerCode"];
    }

    /**
     * Determine and return the state of the provider of the selected payment option.
     *
     * @private
     * @param {HTMLElement} radio - The radio button linked to the payment option.
     * @return {string} The state of the provider of the selected payment option.
     */
    _getProviderState(radio) {
        return radio.dataset["providerState"];
    }
}

registry.category("public.interactions").add("payment.payment_form", PaymentForm);

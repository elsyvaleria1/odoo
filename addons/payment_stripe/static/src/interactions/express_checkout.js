/** @odoo-module native */

import { ExpressCheckout } from "@payment/interactions/express_checkout";
import { StripeOptions } from "@payment_stripe/interactions/stripe_options";
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";
import { redirect } from "@web/core/utils/urls";

patch(ExpressCheckout.prototype, {
    /**
     * Get the order details to display on the payment form.
     *
     * @private
     * @param {number} deliveryAmount - The delivery costs.
     * @param {number} amountFreeShipping - The free shipping discount amount, <= 0.
     * @returns {Object} The information to be displayed on the payment form.
     */
    _getOrderDetails(deliveryAmount, amountFreeShipping) {
        const pending =
            this.paymentContext["shippingInfoRequired"] && deliveryAmount === undefined;
        const minorAmount = parseInt(this.paymentContext["minorAmount"] || 0);
        const displayItems = [
            {
                label: _t("Your order"),
                amount: minorAmount,
            },
        ];
        if (
            this.paymentContext["shippingInfoRequired"] &&
            deliveryAmount !== undefined
        ) {
            displayItems.push({
                label: _t("Delivery"),
                amount: deliveryAmount,
            });
        }
        if (amountFreeShipping) {
            displayItems.push({
                label: _t("Free Shipping"),
                amount: amountFreeShipping,
            });
        }
        return {
            total: {
                label: this.paymentContext["merchantName"],
                amount: minorAmount + (deliveryAmount ?? 0) + (amountFreeShipping ?? 0),
                pending: pending,
            },
            displayItems: displayItems,
        };
    },

    /**
     * Prepare the express checkout form of Stripe for direct payment.
     *
     * @override method from payment.express_form
     * @private
     * @param {Object} providerData - The provider-specific data.
     * @return {void}
     */
    async _prepareExpressCheckoutForm(providerData) {
        if (providerData.providerCode !== "stripe" || !this.paymentContext["amount"]) {
            super._prepareExpressCheckoutForm(...arguments);
            return;
        }

        const stripeJS = Stripe(
            providerData.stripePublishableKey,
            new StripeOptions()._prepareStripeOptions(providerData),
        );
        const paymentRequest = stripeJS.paymentRequest({
            country: providerData.countryCode,
            currency: this.paymentContext["currencyName"],
            requestPayerName: true,
            requestPayerEmail: true,
            requestPayerPhone: true,
            requestShipping: this.paymentContext["shippingInfoRequired"],
            ...this._getOrderDetails(),
        });
        if (this.stripePaymentRequests === undefined) {
            this.stripePaymentRequests = [];
        }
        this.stripePaymentRequests.push(paymentRequest);
        const paymentRequestButton = stripeJS
            .elements()
            .create("paymentRequestButton", {
                paymentRequest: paymentRequest,
                style: { paymentRequestButton: { type: "buy" } },
            });

        const canMakePayment = await this.waitFor(paymentRequest.canMakePayment());
        if (canMakePayment) {
            paymentRequestButton.mount(
                `#o_stripe_express_checkout_container_${providerData.providerId}`,
            );
        } else {
            document.querySelector(
                `#o_stripe_express_checkout_container_${providerData.providerId}`,
            ).style.display = "none";
        }

        paymentRequest.on("paymentmethod", async (ev) => {
            const addresses = {
                billing_address: {
                    name: ev.payerName,
                    email: ev.payerEmail,
                    phone: ev.payerPhone,
                    street: ev.paymentMethod.billing_details.address.line1,
                    street2: ev.paymentMethod.billing_details.address.line2,
                    zip: ev.paymentMethod.billing_details.address.postal_code,
                    city: ev.paymentMethod.billing_details.address.city,
                    country: ev.paymentMethod.billing_details.address.country,
                    state: ev.paymentMethod.billing_details.address.state,
                },
            };
            if (this.paymentContext["shippingInfoRequired"]) {
                addresses.shipping_address = {
                    name: ev.shippingAddress.recipient,
                    email: ev.payerEmail,
                    phone: ev.shippingAddress.phone || ev.payerPhone,
                    street: ev.shippingAddress.addressLine[0],
                    street2: ev.shippingAddress.addressLine[1],
                    zip: ev.shippingAddress.postalCode,
                    city: ev.shippingAddress.city,
                    country: ev.shippingAddress.country,
                    state: ev.shippingAddress.region,
                };
                addresses.shipping_option = ev.shippingOption;
            }
            this.paymentContext.partnerId = parseInt(
                await this.waitFor(
                    rpc(this.paymentContext["expressCheckoutRoute"], addresses),
                ),
            );
            const { client_secret } = await this.waitFor(
                rpc(
                    this.paymentContext["transactionRoute"],
                    this._prepareTransactionRouteParams(providerData.providerId),
                ),
            );
            const { paymentIntent, error: confirmError } = await this.waitFor(
                stripeJS.confirmCardPayment(
                    client_secret,
                    { payment_method: ev.paymentMethod.id },
                    { handleActions: false },
                ),
            );
            if (confirmError) {
                ev.complete("fail");
            } else {
                ev.complete("success");
                if (paymentIntent.status === "requires_action") {
                    await this.waitFor(stripeJS.confirmCardPayment(client_secret));
                }
                redirect("/payment/status");
            }
        });

        if (this.paymentContext["shippingInfoRequired"]) {
            paymentRequest.on("shippingaddresschange", async (ev) => {
                const availableCarriersData = await this.waitFor(
                    rpc(this.paymentContext["shippingAddressUpdateRoute"], {
                        partial_delivery_address: {
                            zip: ev.shippingAddress.postalCode,
                            city: ev.shippingAddress.city,
                            country: ev.shippingAddress.country,
                            state: ev.shippingAddress.region,
                        },
                    }),
                );
                this.paymentContext["minorAmount"] = await this.waitFor(
                    rpc(
                        this.paymentContext["shippingAddressUpdateRoute"] +
                            "/compute_taxes",
                    ),
                );
                const { delivery_methods, delivery_discount_minor_amount } =
                    availableCarriersData;
                if (delivery_methods.length === 0) {
                    ev.updateWith({ status: "invalid_shipping_address" });
                } else {
                    ev.updateWith({
                        status: "success",
                        shippingOptions: delivery_methods.map((carrier) => ({
                            id: String(carrier.id),
                            label: carrier.name,
                            detail: carrier.description ? carrier.description : "",
                            amount: carrier.minorAmount,
                        })),
                        ...this._getOrderDetails(
                            delivery_methods[0].minorAmount,
                            delivery_discount_minor_amount,
                        ),
                    });
                }
            });

            paymentRequest.on("shippingoptionchange", async (ev) => {
                const result = await this.waitFor(
                    rpc("/shop/set_delivery_method", {
                        dm_id: parseInt(ev.shippingOption.id),
                    }),
                );
                ev.updateWith({
                    status: "success",
                    ...this._getOrderDetails(
                        ev.shippingOption.amount,
                        parseInt(result.delivery_discount_minor_amount) || 0,
                    ),
                });
            });
        }
    },

    /**
     * Update the amount of the express checkout form.
     *
     * @override method from payment.express_form
     * @private
     * @param {number} newAmount - The new amount.
     * @param {number} newMinorAmount - The new minor amount.
     * @return {void}
     */
    _updateAmount() {
        super._updateAmount(...arguments);
        this.stripePaymentRequests &&
            this.stripePaymentRequests.map((paymentRequest) =>
                paymentRequest.update(this._getOrderDetails()),
            );
    },
});

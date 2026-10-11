/** @odoo-module native */
import { rpc } from "@web/core/network";
const REQUEST_TIMEOUT = 5000;
const INACTIVITY_TIMEOUT = 110000;

export class PineLabsError extends Error {}

export class PineLabs {
    constructor(...args) {
        this.setup(...args);
    }

    setup(pineLabsPaymentMethod, access_token, pos_config, errorCallback) {
        this.pineLabsPaymentMethod = pineLabsPaymentMethod;
        this.access_token = access_token;
        this.pos_config = pos_config;
        this.errorCallback = errorCallback;
        this.savedOrder = false;
        this.pollingTimeout = null;
        this.inactivityTimeout = null;
        this.paymentStopped = false;
    }

    async startPayment(order) {
        const paymentRequestResponse = await this.processPayment(order);
        if (paymentRequestResponse) {
            await this.paymentPolling(this.savedOrder);
        }
        this.removePaymentHandler(["plutusTransactionReferenceID", "paymentRefNo"]);
    }

    async processPayment(order) {
        try {
            const initialResponse = await rpc(
                `/kiosk/payment/${this.pos_config.id}/kiosk`,
                {
                    order: order.serializeForORM(),
                    access_token: this.access_token,
                    payment_method_id: this.pineLabsPaymentMethod.id,
                },
            );
            if (initialResponse) {
                this.savedOrder = initialResponse.order[0];
                return this.handlePineLabsResponse(initialResponse.payment_status);
            }
        } catch (error) {
            this.errorCallback(error);
            return false;
        }
    }

    async cancelPayment(order) {
        try {
            const data = {
                plutusTransactionReferenceID: localStorage.getItem(
                    "plutusTransactionReferenceID",
                ),
                amount: order.currency.toMinorUnits(order.amount_total),
            };
            const cancelResponse = await rpc(
                "/pos-self-order/pine-labs-cancel-transaction/",
                {
                    access_token: this.access_token,
                    order_id: order.id,
                    payment_data: data,
                    payment_method_id: this.pineLabsPaymentMethod.id,
                },
            );

            if (cancelResponse?.outcome === "failed") {
                this.errorCallback(
                    new PineLabsError(cancelResponse.notification, "warning"),
                );
                return true;
            }
            return false;
        } catch {
            await new Promise((resolve) => setTimeout(resolve, REQUEST_TIMEOUT));
            return this.cancelPayment(order);
        }
    }

    async paymentPolling(order) {
        const data = {
            plutusTransactionReferenceID: localStorage.getItem(
                "plutusTransactionReferenceID",
            ),
            payment_ref_no: localStorage.getItem("paymentRefNo"),
        };
        this.stopInactivePayment().then(() => (this.paymentStopped = true));
        const fetchPaymentStatus = async (resolve, reject) => {
            clearTimeout(this.pollingTimeout);
            if (this.paymentStopped) {
                await this.cancelPayment(order);
                return resolve(false);
            }
            let statusResponse = null;
            try {
                statusResponse = await rpc(
                    "/pos-self-order/pine-labs-fetch-payment-status/",
                    {
                        access_token: this.access_token,
                        order_id: order.id,
                        payment_data: data,
                        payment_method_id: this.pineLabsPaymentMethod.id,
                    },
                );
            } catch {}
            const outcome = statusResponse?.outcome;
            if (outcome === "approved") {
                return resolve(true);
            }
            if (outcome === "unverified") {
                return resolve(false);
            }
            this.pollingTimeout = setTimeout(
                fetchPaymentStatus,
                REQUEST_TIMEOUT,
                resolve,
                reject,
            );
        };
        return new Promise(fetchPaymentStatus);
    }

    handlePineLabsResponse(response) {
        if (response.error) {
            this.errorCallback(new PineLabsError(response.error));
            return false;
        }
        if (response.plutusTransactionReferenceID) {
            localStorage.setItem(
                "plutusTransactionReferenceID",
                response.plutusTransactionReferenceID,
            );
        }
        if (response.payment_ref_no) {
            localStorage.setItem("paymentRefNo", response.payment_ref_no);
        }
        return true;
    }

    stopInactivePayment() {
        return new Promise(
            (resolve) =>
                (this.inactivityTimeout = setTimeout(resolve, INACTIVITY_TIMEOUT)),
        );
    }

    removePaymentHandler(payment_data) {
        payment_data.forEach((data) => {
            localStorage.removeItem(data);
        });
        clearTimeout(this.pollingTimeout);
        clearTimeout(this.inactivityTimeout);
        this.paymentStopped = false;
    }
}

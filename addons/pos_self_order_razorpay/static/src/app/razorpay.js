/** @odoo-module native */
import { rpc } from "@web/core/network";
const REQUEST_TIMEOUT = 10000;

export class RazorpayError extends Error {}

export class Razorpay {
    constructor(...args) {
        this.setup(...args);
    }

    setup(env, razorpayPaymentMethod, access_token, pos_config, errorCallback) {
        this.env = env;
        this.access_token = access_token;
        this.razorpayPaymentMethod = razorpayPaymentMethod;
        this.pos_config = pos_config;
        this.errorCallback = errorCallback;
        this.savedOrder = false;
        this.pollTimeout = null;
        this.inactivityTimeout = null;
        this.queued = false;
        this.payment_stopped = false;
    }

    handleRazorpayResponse(response) {
        if (response?.error) {
            this.errorCallback(
                new RazorpayError(
                    this.payment_stopped
                        ? "Transaction canceled due to inactivity"
                        : response.error,
                ),
            );
            this.removePaymentHandler(["p2pRequestId"]);
            return false;
        }
        localStorage.setItem("p2pRequestId", response?.p2pRequestId);
        return true;
    }

    async cancelPayment(order) {
        let response;
        try {
            response = await rpc("/pos-self-order/razorpay-cancel-transaction/", {
                access_token: this.access_token,
                order_id: order.id,
                payment_data: {},
                payment_method_id: this.razorpayPaymentMethod.id,
            });
        } catch {
            await new Promise((resolve) => setTimeout(resolve, REQUEST_TIMEOUT));
            return this.cancelPayment(order);
        }
        if (response?.outcome === "failed") {
            return !this.handleRazorpayResponse({
                error: response.error || "Razorpay POS transaction canceled",
            });
        }
        this.removePaymentHandler(["p2pRequestId"]);
        return false;
    }

    async startPayment(order) {
        const call_razorpay = await this.processPayment(order);
        if (call_razorpay) {
            await this.paymentPolling(this.savedOrder);
        }
    }

    async processPayment(order) {
        try {
            const initial_response = await rpc(
                `/kiosk/payment/${this.pos_config.id}/kiosk`,
                {
                    order: order.serializeForORM(),
                    access_token: this.access_token,
                    payment_method_id: this.razorpayPaymentMethod.id,
                },
            );
            if (initial_response) {
                this.savedOrder = initial_response.order[0];
                return this.handleRazorpayResponse(initial_response.payment_status);
            }
        } catch (error) {
            this.errorCallback(error);
            return false;
        }
    }

    async paymentPolling(order) {
        this.stopInactivePayment().then(() => (this.payment_stopped = true));
        const fetchPaymentStatus = async () => {
            if (this.payment_stopped) {
                await this.cancelPayment(order);
                return;
            }
            let response = null;
            try {
                response = await rpc("/pos-self-order/razorpay-fetch-payment-status/", {
                    access_token: this.access_token,
                    order_id: order.id,
                    payment_data: {},
                    payment_method_id: this.razorpayPaymentMethod.id,
                });
            } catch {}
            const outcome = response?.outcome;
            if (outcome === "failed") {
                this.handleRazorpayResponse({
                    error: response.error || "Razorpay POS transaction failed",
                });
                return;
            }
            if (outcome === "approved" || outcome === "unverified") {
                this.removePaymentHandler(["p2pRequestId"]);
                return;
            }
            if (response?.status === "QUEUED" && !this.queued) {
                this.queued = true;
                if (await this.cancelPayment(order)) {
                    await this.startPayment(order);
                }
                return;
            }
            clearTimeout(this.pollTimeout);
            this.pollTimeout = setTimeout(fetchPaymentStatus, REQUEST_TIMEOUT);
        };
        await fetchPaymentStatus();
    }

    stopInactivePayment() {
        return new Promise(
            (resolve) => (this.inactivityTimeout = setTimeout(resolve, 90000)),
        );
    }

    removePaymentHandler(payment_data) {
        payment_data.forEach((data) => {
            localStorage.removeItem(data);
        });
        clearTimeout(this.pollTimeout);
        clearTimeout(this.inactivityTimeout);
        this.queued = this.payment_stopped = false;
    }
}

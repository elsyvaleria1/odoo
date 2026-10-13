/** @odoo-module native */
import { PaymentInterface } from "@point_of_sale/app/utils/payment/payment_interface";
import { _t } from "@web/core/translation";
import { AlertDialog } from "@web/ui/dialog";

export class PaymentInterfaceIot extends PaymentInterface {
    get terminal() {
        return this.payment_method_id.terminal_proxy;
    }

    /**
     * @param {string} uuid
     * @returns {object}
     */
    getPaymentData(uuid) {}

    /**
     * @param {string} uuid
     * @returns {object}
     */
    getCancelData(uuid) {}

    /**
     * @param {PosOrder} order
     * @param {object} data
     * @returns {PosPayment | null}
     */
    getPaymentLineForMessage(order, data) {}

    /**
     * @param {object} data
     * @param {PosPayment} line
     */
    onTerminalMessageReceived(data, line) {}

    sendPaymentRequest(uuid) {
        super.sendPaymentRequest(...arguments);
        return this._sendTerminalRequest(this.getPaymentData(uuid), false);
    }

    sendPaymentCancel(order, uuid) {
        super.sendPaymentCancel(...arguments);

        return this._sendTerminalRequest(this.getCancelData(uuid), true);
    }

    _sendTerminalRequest(data, isCancellation) {
        if (!this.terminal) {
            this._showErrorConfig();
            return Promise.resolve(false);
        }

        return new Promise((resolve) => {
            const resolveRequest = (result) => {
                resolve(result);
                if (isCancellation) {
                    this._resolveCancellation = null;
                } else {
                    this._resolvePayment = null;
                }
                if (!this._resolveCancellation && !this._resolvePayment) {
                    this.transactionInProgress = false;
                }
            };
            if (isCancellation) {
                this._resolveCancellation = resolveRequest;
            } else {
                this._resolvePayment = resolveRequest;
            }

            this.transactionInProgress = true;
            this.pos.iotHttp.action(
                this.terminal.iotId,
                this.terminal.identifier,
                data,
                (e) => this._onValueChange(this.pos.getOrder(), e.result),
                (e) => this._onActionFail(e),
            );
        });
    }

    _keepListening() {
        if (this.transactionInProgress) {
            this.pos.iotHttp.onMessage(
                this.terminal.iotId,
                this.terminal.identifier,
                (e) => this._onValueChange(this.pos.getOrder(), e.result),
                (e) => this._onActionFail(e),
            );
        }
    }

    _onActionFail(data) {
        if (data.status === "timeout") {
            return this._keepListening();
        }
        this.transactionInProgress = false;
        this._resolvePayment?.(false);
        if (data?.Disconnected === "disconnected") {
            this.env.services.dialog.add(AlertDialog, {
                title: _t("Connection to terminal failed"),
                body: _t("Please check if the terminal is still connected."),
            });
        }
    }

    _showErrorConfig() {
        this.env.services.dialog.add(AlertDialog, {
            title: _t("Configuration of payment terminal failed"),
            body: _t("You must select a payment terminal in your POS config."),
        });
    }

    _onValueChange(order, data) {
        this._keepListening();
        const line = this.getPaymentLineForMessage(order, data);
        if (line) {
            this.onTerminalMessageReceived(data, line);
        }
    }
}

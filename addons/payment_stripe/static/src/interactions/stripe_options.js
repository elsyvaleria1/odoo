/** @odoo-module native */

export class StripeOptions {
    /**
     * @param {object} processingValues
     * @return {object}
     */
    _prepareStripeOptions() {
        const locale = document.documentElement.lang;
        return {
            apiVersion: "2019-05-16",
            ...(locale ? { locale } : {}),
        };
    }
}

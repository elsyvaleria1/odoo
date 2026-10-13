/** @odoo-module native */
/**
 * @param {object} currency
 * @returns {object}
 */
export function createDefaultCurrency(currency) {
    if (!currency) {
        return undefined;
    }
    return {
        symbol: currency.symbol,
        position: currency.position,
        decimalPlaces: currency.decimalPlaces,
    };
}

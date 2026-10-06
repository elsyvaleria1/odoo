/** @odoo-module native */

/**
 * @param {Object} item
 * @returns {Object}
 */
export function savedValues(item) {
    return item?._values || item?.data || item || {};
}

/**
 * @param {Object} item
 * @returns {Object}
 */
export function displayValues(item) {
    return item?.data || item?._values || item || {};
}

/**
 * @param {Object} item
 * @param {string} fieldName
 * @returns {*}
 */
export function savedValue(item, fieldName) {
    return savedValues(item)[fieldName];
}

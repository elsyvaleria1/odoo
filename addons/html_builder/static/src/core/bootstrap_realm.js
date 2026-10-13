/** @odoo-module native */

/**
 * @param {Window} win
 * @param {string} name
 * @returns {Function|undefined}
 */
export function getBootstrapComponent(win, name) {
    return win?.__odooWebsiteEditBootstrap?.[name];
}

/** @odoo-module native */
import { browser } from "@web/core/browser/browser";

/**
 * @param {string} ip
 * @param {string} route
 * @param {boolean} forceHttp
 * @returns {string}
 */
export function formatEndpoint(ip, route, forceHttp = false) {
    const protocol = forceHttp ? "http:" : window.location.protocol;
    const rawIp = forceHttp
        ? ip.replace(/^(\d+)-(\d+)-(\d+)-(\d+).*/, "$1.$2.$3.$4")
        : ip;
    const url = new URL(`${protocol}//${rawIp}`);
    url.pathname = route;
    return url.toString();
}

/**
 * @param {string} ip
 * @param {string} route
 * @param {Record<string, unknown>} params
 * @param {number} timeout
 * @param {Record<string, unknown>} headers
 * @param {AbortSignal} abortSignal
 * @param {boolean} useLna
 * @returns {Promise<any>}
 */
export async function post(
    ip,
    route,
    params = {},
    timeout = 6000,
    headers = {},
    abortSignal = null,
    useLna = false,
) {
    const endpoint = formatEndpoint(ip, route, useLna);
    const timeoutSignal = AbortSignal.timeout(timeout);
    const response = await browser.fetch(endpoint, {
        body: JSON.stringify({ params: params }),
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        signal: abortSignal
            ? AbortSignal.any([abortSignal, timeoutSignal])
            : timeoutSignal,
        targetAddressSpace: useLna ? "local" : undefined,
    });

    return response.json();
}

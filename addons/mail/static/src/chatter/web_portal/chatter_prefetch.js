// @ts-check
/** @odoo-module native */
import { toRaw } from "@odoo/owl";

/** @type {WeakMap<object, { requestList: string[], promise: Promise<boolean> }>} */
const prefetches = new WeakMap();

/**
 * @param {import("models").Thread} thread
 * @param {string[]} requestList
 */
export function prefetchThreadData(thread, requestList) {
    const promise = thread.fetchThreadData(requestList).then(
        () => true,
        () => false,
    );
    prefetches.set(toRaw(thread), { requestList, promise });
}

/**
 * @param {import("models").Thread} thread
 * @param {string[]} requestList
 * @returns {Promise<string[] | null>}
 */
export async function takeThreadPrefetch(thread, requestList) {
    const prefetch = prefetches.get(toRaw(thread));
    if (!prefetch) {
        return null;
    }
    prefetches.delete(toRaw(thread));
    if (!(await prefetch.promise)) {
        return requestList;
    }
    return requestList.filter((name) => !prefetch.requestList.includes(name));
}

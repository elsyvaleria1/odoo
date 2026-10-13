// @ts-check
/** @odoo-module native */

import { swapFragment } from "@web/public/fragments";

/** @typedef {import("@web/public/interaction_service").InteractionService} InteractionService */

export const PARTIAL_NAVIGATION_HEADER = "X-Odoo-Partial-Navigation";

const HEAD_SELECTORS = [
    'link[rel="canonical"]',
    'link[rel="alternate"][hreflang]',
    'meta[name="description"]',
    'meta[name="robots"]',
    'meta[property^="og:"]',
    'meta[name^="twitter:"]',
].join(", ");

const OUT_OF_BAND = "[data-fragment][data-partial-navigation-oob]";

/**
 * @param {ParentNode} root
 * @param {Element[]} regions
 * @returns {Map<string, HTMLElement[]>}
 */
function outOfBandByKey(root, regions) {
    const byKey = new Map();
    for (const el of /** @type {NodeListOf<HTMLElement>} */ (
        root.querySelectorAll(OUT_OF_BAND)
    )) {
        if (!regions.some((region) => region.contains(el))) {
            const key = el.dataset.fragment;
            byKey.set(key, [...(byKey.get(key) || []), el]);
        }
    }
    return byKey;
}

/**
 * @param {Element} current
 * @param {Element} next
 * @param {string[]} names
 */
function syncAttributes(current, next, names) {
    for (const name of names) {
        const value = next.getAttribute(name);
        if (value === null) {
            current.removeAttribute(name);
        } else {
            current.setAttribute(name, value);
        }
    }
}

/**
 * @param {Element} current
 * @param {Element} next
 */
function syncPageAttributes(current, next) {
    const isPageAttribute = (/** @type {string} */ name) =>
        name.startsWith("data-") || name === "lang" || name === "dir";
    for (const { name } of [...current.attributes]) {
        if (isPageAttribute(name) && !next.hasAttribute(name)) {
            current.removeAttribute(name);
        }
    }
    for (const { name, value } of next.attributes) {
        if (isPageAttribute(name)) {
            current.setAttribute(name, value);
        }
    }
}

/**
 * @param {Document} page
 * @param {Element[]} regions
 * @param {Element[]} nextRegions
 * @param {InteractionService} interactions
 */
function swapOutOfBand(page, regions, nextRegions, interactions) {
    const next = outOfBandByKey(page, nextRegions);
    for (const [key, elements] of outOfBandByKey(document, regions)) {
        const counterparts = next.get(key) || [];
        const attributes = elements[0].dataset.partialNavigationOob;
        if (attributes) {
            if (counterparts[0]) {
                for (const el of elements) {
                    syncAttributes(el, counterparts[0], attributes.split(/\s*,\s*/));
                }
            }
            continue;
        }
        elements.forEach((el, index) => {
            const counterpart = counterparts[index];
            if (counterpart) {
                swapFragment(el, counterpart.outerHTML, "morph", interactions);
            } else {
                el.hidden = true;
            }
        });
    }
}

/** @param {Document} page */
export function swapHead(page) {
    const title = page.querySelector("title")?.textContent;
    if (title) {
        document.title = title;
    }
    for (const el of document.head.querySelectorAll(HEAD_SELECTORS)) {
        el.remove();
    }
    document.head.append(
        ...[...page.head.querySelectorAll(HEAD_SELECTORS)].map((el) =>
            document.importNode(el, true),
        ),
    );
    syncPageAttributes(document.documentElement, page.documentElement);
}

/**
 * @param {Document} page
 * @param {HTMLElement[]} regions
 * @returns {HTMLElement[] | null}
 */
function nextRegionsOf(page, regions) {
    const nextRegions = regions.map((region) =>
        page.querySelector(`[data-fragment="${CSS.escape(region.dataset.fragment)}"]`),
    );
    return nextRegions.some((region) => !region)
        ? null
        : /** @type {HTMLElement[]} */ (nextRegions);
}

/**
 * @param {Document} page
 * @param {HTMLElement[]} regions
 * @param {InteractionService} interactions
 * @returns {boolean}
 */
export function swapRegions(page, regions, interactions) {
    const nextRegions = nextRegionsOf(page, regions);
    if (!nextRegions) {
        return false;
    }
    const swapped = regions.map((region, index) =>
        swapFragment(region, nextRegions[index].outerHTML, "morph", interactions),
    );
    swapOutOfBand(page, swapped, nextRegions, interactions);
    return true;
}

/**
 * @param {Document} page
 * @param {HTMLElement[]} regions
 * @param {InteractionService} interactions
 * @returns {boolean}
 */
export function swapPage(page, regions, interactions) {
    if (!nextRegionsOf(page, regions)) {
        return false;
    }
    swapHead(page);
    return swapRegions(page, regions, interactions);
}

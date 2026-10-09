// @ts-check
/** @odoo-module native */

import { swapFragment } from "@web/public/fragments";

/** @typedef {import("@web/public/interaction_service").InteractionService} InteractionService */

// http_routing's PARTIAL_NAVIGATION_HEADER: the server leaves out the header
// and footer, which a page swapped in place keeps
export const PARTIAL_NAVIGATION_HEADER = "X-Odoo-Partial-Navigation";

// what a page says about itself in <head>, kept in step with the page shown
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
 * The out-of-band elements of `root` outside every region, by key, in
 * document order.
 *
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
 * The page metadata <html> carries (main object, view, website, lang).
 *
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
 * Elements outside the regions that the server renders for the URL follow
 * the page (htmx's hx-swap-oob), found in the next page by their
 * `data-fragment` key:
 * - `data-partial-navigation-oob=""` (the breadcrumbs): each is morphed from
 *   its counterpart, paired by document order, and hidden when the next page
 *   has none. It must live in the page's content, which a page asked for in
 *   place still renders.
 * - `data-partial-navigation-oob="href"` (the language links, in the header
 *   and footer a page asked for in place leaves out): every element of the
 *   key takes the listed attributes from the first counterpart, which the
 *   server also renders, hidden, in that case.
 *
 * @param {Document} page
 * @param {Element[]} regions the regions on this page
 * @param {Element[]} nextRegions their counterparts in `page`
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

/**
 * Brings this page in step with `page`, a fetched page for the URL shown: its
 * title, what its <head> and <html> say about it, each of `regions` morphed
 * from its same-keyed counterpart, and the out-of-band elements. Changes
 * nothing and answers false when `page` lacks one of the regions: the caller
 * then loads it in full.
 *
 * @param {Document} page
 * @param {HTMLElement[]} regions elements of this page carrying `data-fragment`
 * @param {InteractionService} interactions
 * @returns {boolean}
 */
export function swapPage(page, regions, interactions) {
    const nextRegions = regions.map((region) =>
        page.querySelector(`[data-fragment="${CSS.escape(region.dataset.fragment)}"]`),
    );
    if (nextRegions.some((region) => !region)) {
        return false;
    }
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
    const swapped = regions.map((region, index) =>
        swapFragment(region, nextRegions[index].outerHTML, "morph", interactions),
    );
    swapOutOfBand(page, swapped, nextRegions, interactions);
    return true;
}

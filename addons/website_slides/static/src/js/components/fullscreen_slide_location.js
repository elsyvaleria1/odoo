/** @odoo-module native */

export function isFullscreenSlide({ pathname, search }) {
    return pathname.includes("slides") && search.includes("fullscreen=1");
}

export function lessonLocation({ pathname, search, hash }) {
    return {
        pathname,
        search: search.replace(/fullscreen=1/, "fullscreen=0"),
        hash,
    };
}

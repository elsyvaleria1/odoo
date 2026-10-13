/** @odoo-module native */
/**
 * @param {string} imageUrl
 * @private
 */
export async function preloadBackground(imageUrl) {
    let resolvePreload;

    const preloadPromise = new Promise(function (resolve, reject) {
        resolvePreload = resolve;
    });
    const background = new Image();
    background.addEventListener("load", () => resolvePreload(imageUrl), { once: true });
    background.src = imageUrl;

    return preloadPromise;
}

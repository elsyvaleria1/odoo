/** @odoo-module native */
import { loadEmoji } from "@web/components/emoji_picker";

const iconsBlocklist = ["💩", "💀", "☠️", "🤮", "🖕", "🤢", "😒"];

/** @returns {String} */
export async function getRandomIcon() {
    const { emojis } = await loadEmoji();
    const randomEmojis = emojis.filter(
        (emoji) => !iconsBlocklist.includes(emoji.codepoints),
    );
    return randomEmojis[Math.floor(Math.random() * randomEmojis.length)].codepoints;
}

/**
 * @param {HTMLElement} element
 * @param {Function} callback
 * @returns {IntersectionObserver}
 */
export function setIntersectionObserver(element, callback) {
    const options = {
        root: null,
        rootMargin: "0px",
    };
    const observer = new window.IntersectionObserver((entries) => {
        const entry = entries[0];
        if (entry.isIntersecting) {
            observer.unobserve(entry.target);
            callback();
        }
    }, options);
    observer.observe(element);
    return observer;
}

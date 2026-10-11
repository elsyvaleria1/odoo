// @ts-check
/** @odoo-module native */

/** @type {number} */
const COOKIE_TTL = 24 * 60 * 60 * 365;

const UNSAFE_VALUE_CHARS = /[^!#$&'()*+\-./0-9:<=>?@A-Z[\]^_`a-z{|}~]+/gu;
// eslint-disable-next-line no-control-regex
const UNSAFE_KEY_CHARS = /[%;=,\s()<>@:\\"/[\]?{}\x00-\x1f\x7f]/g;
const LEGACY_QUOTED_VALUE = /^"(?:[^\\"]|\\.)*"$/;
const LEGACY_SLASH_ESCAPE = /\\([0-3][0-7]{2}|.)/g;

/**
 * @param {string} str
 * @returns {string}
 */
function escapeCookieKey(str) {
    return String(str).replace(UNSAFE_KEY_CHARS, (c) => encodeURIComponent(c));
}

/**
 * @param {string} str
 * @returns {string}
 */
export function encodeCookieValue(str) {
    return String(str)
        .toWellFormed()
        .replace(UNSAFE_VALUE_CHARS, (run) => encodeURIComponent(run));
}

/**
 * @param {string} str
 * @returns {string}
 */
function decodePercentEscapes(str) {
    try {
        return decodeURIComponent(str);
    } catch {
        return str;
    }
}

/**
 * @param {string} quoted
 * @returns {string}
 */
function decodeLegacyQuotedValue(quoted) {
    const encoder = new TextEncoder();
    const inner = quoted.slice(1, -1);
    /** @type {number[]} */
    const bytes = [];
    let last = 0;
    for (const match of inner.matchAll(LEGACY_SLASH_ESCAPE)) {
        bytes.push(...encoder.encode(inner.slice(last, match.index)));
        const escaped = match[1];
        if (escaped.length === 3) {
            bytes.push(parseInt(escaped, 8));
        } else {
            bytes.push(...encoder.encode(escaped));
        }
        last = match.index + match[0].length;
    }
    bytes.push(...encoder.encode(inner.slice(last)));
    return new TextDecoder().decode(new Uint8Array(bytes));
}

/**
 * @param {string} str
 * @returns {string}
 */
export function decodeCookieValue(str) {
    if (LEGACY_QUOTED_VALUE.test(str)) {
        return decodeLegacyQuotedValue(str);
    }
    return decodePercentEscapes(str);
}

export const cookie = {
    /** @returns {string} */
    get _cookieMonster() {
        return document.cookie;
    },
    /** @param {string} value */
    set _cookieMonster(value) {
        document.cookie = value;
    },
    /**
     * @param {string} str
     * @returns {string | undefined}
     */
    get(str) {
        const parts = this._cookieMonster.split("; ");
        for (const part of parts) {
            const [rawKey, value] = part.split(/=(.*)/);
            const key = decodePercentEscapes(rawKey);
            if (key === str) {
                return value ? decodeCookieValue(value) : "";
            }
        }
    },
    /**
     * @param {string} key
     * @param {string | undefined} value
     * @param {number} [ttl]
     */
    set(key, value, ttl = COOKIE_TTL) {
        if (value === undefined) {
            this.delete(key);
            return;
        }
        const parts = [
            `${escapeCookieKey(key)}=${encodeCookieValue(value)}`,
            "path=/",
            `max-age=${Math.floor(ttl)}`,
            "SameSite=Lax",
        ];
        this._cookieMonster = parts.join("; ");
    },
    /** @param {string} key */
    delete(key) {
        this.set(key, "", 0);
    },
};

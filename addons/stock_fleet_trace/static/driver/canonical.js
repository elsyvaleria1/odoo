const HASHED_FIELDS = [
    "client_uuid",
    "event_type",
    "picking_id",
    "captured_at",
    "latitude",
    "longitude",
    "payload",
    "prev_hash",
];

/**
 * Compare two strings by Unicode code point, as Python sorts dict keys.
 * JavaScript's default sort compares UTF-16 code units, which differs for
 * characters outside the Basic Multilingual Plane.
 *
 * @param {string} a
 * @param {string} b
 * @returns {number}
 */
function compareCodePoints(a, b) {
    const left = Array.from(a);
    const right = Array.from(b);
    const length = Math.min(left.length, right.length);
    for (let i = 0; i < length; i++) {
        const diff = left[i].codePointAt(0) - right[i].codePointAt(0);
        if (diff) {
            return diff;
        }
    }
    return left.length - right.length;
}

/**
 * A number as Python's json.dumps writes the value it parsed from the number
 * JSON.stringify sent: integral values arrive as int ("5", never "5.0"), the
 * rest as float, written with repr (shortest round-trip digits, exponent below
 * 1e-4 as "1e-05").
 *
 * @param {number} value
 * @returns {string}
 */
function pythonNumber(value) {
    if (!Number.isFinite(value)) {
        throw new Error(`Cannot hash the non-finite number ${value}`);
    }
    const absolute = Math.abs(value);
    if (Number.isInteger(value) || absolute >= 1e-4) {
        return JSON.stringify(value);
    }
    const [mantissa, exponent] = value.toExponential().split("e");
    const sign = exponent.startsWith("-") ? "-" : "+";
    const digits = exponent.replace(/^[+-]/, "").padStart(2, "0");
    return `${mantissa}e${sign}${digits}`;
}

/**
 * Serialize ``value`` as the server's canonical JSON: sorted keys, compact
 * separators, non-ASCII written as is. String escaping is JSON.stringify's,
 * which matches Python's ensure_ascii=False (quote, backslash, \b \f \n \r \t,
 * other control characters as lowercase \u00xx).
 *
 * @param {*} value
 * @returns {string}
 */
export function canonicalJson(value) {
    if (value === null || value === undefined) {
        return "null";
    }
    if (typeof value === "number") {
        return pythonNumber(value);
    }
    if (typeof value === "boolean" || typeof value === "string") {
        return JSON.stringify(value);
    }
    if (Array.isArray(value)) {
        return `[${value.map((item) => canonicalJson(item === undefined ? null : item)).join(",")}]`;
    }
    if (typeof value === "object") {
        const keys = Object.keys(value)
            .filter((key) => value[key] !== undefined)
            .sort(compareCodePoints);
        return `{${keys.map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
    }
    throw new Error(`Cannot hash a value of type ${typeof value}`);
}

/**
 * The fields of an event that the hash covers, with the server's defaults.
 *
 * @param {Object} event
 * @returns {Object}
 */
export function hashedFields(event) {
    const fields = {};
    for (const name of HASHED_FIELDS) {
        fields[name] = event[name] === undefined ? null : event[name];
    }
    const payload = event.payload;
    fields.payload = payload && Object.keys(payload).length ? payload : {};
    fields.prev_hash = event.prev_hash || "";
    return fields;
}

/**
 * Hex SHA-256 of a string encoded as UTF-8.
 *
 * @param {string} text
 * @returns {Promise<string>}
 */
export async function sha256Hex(text) {
    const digest = await globalThis.crypto.subtle.digest(
        "SHA-256",
        new TextEncoder().encode(text),
    );
    return Array.from(new Uint8Array(digest), (byte) =>
        byte.toString(16).padStart(2, "0"),
    ).join("");
}

/**
 * The event_hash the server expects for ``event``.
 *
 * @param {Object} event
 * @returns {Promise<string>}
 */
export function hashEvent(event) {
    return sha256Hex(canonicalJson(hashedFields(event)));
}

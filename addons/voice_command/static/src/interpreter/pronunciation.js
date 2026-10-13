// @ts-check
/** @odoo-module native */

import { normalize } from "@web/core/l10n/utils";

const LETTER_NAMES = {
    a: "a",
    b: "be",
    c: "ce",
    d: "de",
    e: "e",
    f: "efe",
    g: "ge",
    h: "hache",
    i: "i",
    j: "jota",
    k: "ka",
    l: "ele",
    m: "eme",
    n: "ene",
    ñ: "eñe",
    o: "o",
    p: "pe",
    q: "cu",
    r: "erre",
    s: "ese",
    t: "te",
    u: "u",
    v: "ve",
    w: "doble u",
    x: "equis",
    y: "ye",
    z: "zeta",
};

/** @type {[RegExp, string][]} */
const RULES = [
    [/^s(?=[bcdfgklmnpqtvw])/, "es"],
    [/^wh?/, "gu"],
    [/^up/, "ap"],
    [/tion$/, "shon"],
    [/ph/g, "f"],
    [/th/g, "t"],
    [/ck/g, "k"],
    [/j/g, "y"],
    [/ce$/, "se"],
    [/oa/g, "o"],
    [/oo/g, "u"],
    [/e[ea]/g, "i"],
    [/a[iy]/g, "ei"],
    [/(?<![aeiou])([aeiou])([bcdfgklmnprstvz])e$/, "$1$2E"],
    [/a([bcdfgklmnprstvz])E$/, "ei$1"],
    [/e([bcdfgklmnprstvz])E$/, "i$1"],
    [/i([bcdfgklmnprstvz])E$/, "ai$1"],
    [/o([bcdfgklmnprstvz])E$/, "ou$1"],
    [/u([bcdfgklmnprstvz])E$/, "iu$1"],
    [/E$/, ""],
    [/([^aeiou])y$/, "$1i"],
    [/([bcdfgklmnprstvz])\1/g, "$1"],
    [/r[dt]$/, "r"],
    [/ft$/, "f"],
    [/nd$/, "n"],
];

/**
 * @param {string} phrase
 * @returns {string[]}
 */
function wordsOf(phrase) {
    return normalize(phrase).match(/[\p{L}\p{N}]+/gu) || [];
}

/**
 * @param {string} word
 * @returns {string}
 */
function renderWord(word) {
    if (/\d/.test(word) || word.length < 3) {
        return word;
    }
    let rendered = word;
    for (const [pattern, replacement] of RULES) {
        rendered = rendered.replace(pattern, replacement);
    }
    return rendered;
}

/**
 * @param {string} phrase
 * @returns {string | null}
 */
export function mexicanRendering(phrase) {
    const words = wordsOf(phrase);
    const rendered = words.map(renderWord).join(" ");
    return rendered && rendered !== words.join(" ") ? rendered : null;
}

/**
 * @param {string} acronym
 * @returns {string | null}
 */
export function spelledOut(acronym) {
    const letters = [...wordsOf(acronym).join("")];
    if (!letters.length || letters.some((letter) => !(letter in LETTER_NAMES))) {
        return null;
    }
    return letters
        .map(
            (letter) => LETTER_NAMES[/** @type {keyof typeof LETTER_NAMES} */ (letter)],
        )
        .join(" ");
}

/**
 * @param {string} phrase
 * @param {string} kind
 * @returns {string[]}
 */
export function pronunciations(phrase, kind) {
    const said =
        kind === "acronym"
            ? spelledOut(phrase)
            : kind === "word"
              ? mexicanRendering(phrase)
              : null;
    return said ? [said] : [];
}

/**
 * @param {string} label
 * @returns {string | null}
 */
export function otherNumber(label) {
    const match = label.match(/^(.*?)(\p{L}+)$/u);
    if (!match || match[2].length < 3) {
        return null;
    }
    const [, head, word] = match;
    const lower = word.toLowerCase();
    if (lower.endsWith("ss") || lower.endsWith("us")) {
        return null;
    }
    if (/(s|x|ch|sh)es$/.test(lower)) {
        return head + word.slice(0, -2);
    }
    if (/[^aeiou]ies$/.test(lower)) {
        return head + word.slice(0, -3) + "y";
    }
    if (lower.endsWith("s")) {
        return head + word.slice(0, -1);
    }
    if (/(s|x|ch|sh)$/.test(lower)) {
        return head + word + "es";
    }
    if (/[^aeiou]y$/.test(lower)) {
        return head + word.slice(0, -1) + "ies";
    }
    return head + word + "s";
}

/**
 * @param {string} lang
 * @param {string[]} labels
 * @returns {string[]}
 */
export function saidInLanguage(lang, labels) {
    if (!lang.startsWith("en")) {
        return labels;
    }
    return [
        ...new Set(
            labels.flatMap((label) => {
                const numbers = [label, otherNumber(label)].filter(
                    /** @returns {said is string} */ (said) => Boolean(said),
                );
                return numbers.flatMap((said) => [
                    said,
                    ...pronunciations(said, "word"),
                ]);
            }),
        ),
    ];
}

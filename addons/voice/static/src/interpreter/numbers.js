// @ts-check
/** @odoo-module native */

import { normalize } from "@web/core/l10n/utils";

/** @type {Record<string, number>} */
const UNITS = {
    cero: 0,
    zero: 0,
    un: 1,
    uno: 1,
    una: 1,
    one: 1,
    a: 1,
    dos: 2,
    two: 2,
    tres: 3,
    three: 3,
    cuatro: 4,
    four: 4,
    cinco: 5,
    five: 5,
    seis: 6,
    six: 6,
    siete: 7,
    seven: 7,
    ocho: 8,
    eight: 8,
    nueve: 9,
    nine: 9,
    diez: 10,
    ten: 10,
    once: 11,
    eleven: 11,
    doce: 12,
    twelve: 12,
    trece: 13,
    thirteen: 13,
    catorce: 14,
    fourteen: 14,
    quince: 15,
    fifteen: 15,
    dieciseis: 16,
    sixteen: 16,
    diecisiete: 17,
    seventeen: 17,
    dieciocho: 18,
    eighteen: 18,
    diecinueve: 19,
    nineteen: 19,
    veinte: 20,
    twenty: 20,
    veintiun: 21,
    veintiuno: 21,
    veintiuna: 21,
    veintidos: 22,
    veintitres: 23,
    veinticuatro: 24,
    veinticinco: 25,
    veintiseis: 26,
    veintisiete: 27,
    veintiocho: 28,
    veintinueve: 29,
    treinta: 30,
    thirty: 30,
    cuarenta: 40,
    forty: 40,
    cincuenta: 50,
    fifty: 50,
    sesenta: 60,
    sixty: 60,
    setenta: 70,
    seventy: 70,
    ochenta: 80,
    eighty: 80,
    noventa: 90,
    ninety: 90,
    cien: 100,
    ciento: 100,
    doscientos: 200,
    doscientas: 200,
    trescientos: 300,
    trescientas: 300,
    cuatrocientos: 400,
    cuatrocientas: 400,
    quinientos: 500,
    quinientas: 500,
    seiscientos: 600,
    seiscientas: 600,
    setecientos: 700,
    setecientas: 700,
    ochocientos: 800,
    ochocientas: 800,
    novecientos: 900,
    novecientas: 900,
};

/** The words a number is said with, for matching what a recogniser misheard. */
export const NUMBER_WORDS_SPOKEN = Object.freeze([
    ...Object.keys(UNITS).filter((word) => word.length > 2),
    "mil",
    "punto",
]);

const HUNDRED = new Set(["hundred", "hundreds"]);
const THOUSAND = new Set(["mil", "thousand", "thousands"]);
const MILLION = new Set(["millon", "millones", "million", "millions"]);
const JOINERS = new Set(["y", "and"]);
const MINUS = new Set(["menos", "minus", "negativo", "negative"]);
const POINT = new Set(["punto", "coma", "point", "dot"]);

/**
 * @param {string[]} words normalized
 * @returns {number | null}
 */
function parseInteger(words) {
    // "dos y" is a number cut off, not two: a recogniser writes it for "doce"
    if (words.length && JOINERS.has(words[words.length - 1])) {
        return null;
    }
    let total = 0;
    let current = 0;
    let seen = false;
    for (const word of words) {
        if (/^\d+$/.test(word)) {
            current += Number(word);
        } else if (word in UNITS) {
            current += UNITS[word];
        } else if (HUNDRED.has(word)) {
            current = (current || 1) * 100;
        } else if (THOUSAND.has(word)) {
            total += (current || 1) * 1000;
            current = 0;
        } else if (MILLION.has(word)) {
            total += (current || 1) * 1_000_000;
            current = 0;
        } else if (JOINERS.has(word) && seen) {
            continue;
        } else {
            return null;
        }
        seen = true;
    }
    return seen ? total + current : null;
}

/** @param {string} word normalized */
function isNumberWord(word) {
    return (
        (word in UNITS && word !== "a") ||
        HUNDRED.has(word) ||
        THOUSAND.has(word) ||
        MILLION.has(word)
    );
}

/**
 * A code read aloud, its numbers written as digits: "L dos mil veintiséis
 * guion cero cero cuarenta y dos" becomes "L 2026 guion 0042". Leading
 * "cero"s are the zeros of a code; every other word stays as it was heard.
 *
 * @param {string} text
 * @returns {string}
 */
export function spokenDigits(text) {
    const words = text.split(/\s+/).filter(Boolean);
    const plain = words.map((word) => normalize(word).replace(/[^\p{L}\p{N}]/gu, ""));
    /** @type {string[]} */
    const out = [];
    let index = 0;
    while (index < words.length) {
        let end = index;
        while (
            end < words.length &&
            (isNumberWord(plain[end]) ||
                (JOINERS.has(plain[end]) &&
                    end > index &&
                    isNumberWord(plain[end + 1] || "")))
        ) {
            end++;
        }
        if (end === index) {
            out.push(words[index++]);
            continue;
        }
        let zeros = "";
        let start = index;
        while (start < end - 1 && ["cero", "zero"].includes(plain[start])) {
            zeros += "0";
            start++;
        }
        const value = parseInteger(plain.slice(start, end));
        out.push(
            value === null ? words.slice(index, end).join(" ") : `${zeros}${value}`,
        );
        index = end;
    }
    return out.join(" ");
}

/**
 * "cinco", "treinta y cinco", "dos mil quinientos", "five point five",
 * "12.5", "-3": what a speech recogniser writes for a number.
 *
 * @param {string} text
 * @returns {number | null}
 */
export function parseSpokenNumber(text) {
    const compact = text
        .trim()
        .replace(/[.,;:!?]+$/u, "")
        .replace(/\s+/g, "");
    // "3,200" is how a recogniser writes three thousand two hundred in Mexico;
    // only a comma not followed by three digits is a decimal one ("12,5")
    if (/^-?\d{1,3}(,\d{3})+(\.\d+)?$/.test(compact)) {
        return Number(compact.replaceAll(",", ""));
    }
    if (/^-?\d+([.,]\d+)?$/.test(compact)) {
        return Number(compact.replace(",", "."));
    }
    const words = normalize(text)
        .split(/[^\p{L}\p{N}]+/u)
        .filter(Boolean);
    let sign = 1;
    if (words.length && MINUS.has(words[0])) {
        sign = -1;
        words.shift();
    }
    const pointIndex = words.findIndex((word) => POINT.has(word));
    if (pointIndex === -1) {
        const integer = parseInteger(words);
        return integer === null ? null : sign * integer;
    }
    const integer = pointIndex ? parseInteger(words.slice(0, pointIndex)) : 0;
    const fractionWords = words.slice(pointIndex + 1);
    if (integer === null || !fractionWords.length) {
        return null;
    }
    let digits = "";
    for (const word of fractionWords) {
        const value = /^\d+$/.test(word) ? Number(word) : UNITS[word];
        if (value === undefined || value > 99) {
            return null;
        }
        digits += String(value);
    }
    return sign * Number(`${integer}.${digits}`);
}

// @ts-check
/** @odoo-module native */

import { normalize } from "@web/core/l10n/utils";

import { pronunciations } from "./pronunciation.js";

/**
 * @typedef {{ phrases: string[], means: string, kind: string }} SpokenTerm
 * @typedef {{ words: string[], means: string }} TermPhrase
 */

/**
 * @param {SpokenTerm[]} terms
 * @returns {TermPhrase[]}
 */
export function termPhrases(terms) {
    return terms
        .flatMap(({ phrases, means, kind }) =>
            [
                ...new Set(
                    phrases.flatMap((phrase) => [
                        phrase,
                        ...pronunciations(phrase, kind),
                    ]),
                ),
            ].map((phrase) => ({
                words: normalize(phrase).match(/[\p{L}\p{N}]+/gu) || [],
                means,
            })),
        )
        .filter(({ words }) => words.length)
        .sort((a, b) => b.words.length - a.words.length);
}

/**
 * @param {string} text
 * @param {TermPhrase[]} phrases
 * @returns {string | null}
 */
export function rewriteTerms(text, phrases) {
    const spans = [...text.matchAll(/[\p{L}\p{N}]+/gu)];
    const words = spans.map((span) => normalize(span[0]));
    let rewritten = "";
    let copied = 0;
    let index = 0;
    while (index < spans.length) {
        const found = phrases.find(({ words: said }) =>
            said.every((word, offset) => words[index + offset] === word),
        );
        if (!found) {
            index++;
            continue;
        }
        const first = spans[index];
        const last = spans[index + found.words.length - 1];
        rewritten += text.slice(copied, first.index) + found.means;
        copied = /** @type {number} */ (last.index) + last[0].length;
        index += found.words.length;
    }
    return copied ? rewritten + text.slice(copied) : null;
}

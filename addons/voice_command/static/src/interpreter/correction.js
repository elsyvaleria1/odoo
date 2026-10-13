// @ts-check
/** @odoo-module native */

import { normalize } from "@web/core/l10n/utils";

import {
    BUTTON_VERBS,
    COMMAND_PHRASES,
    COMMAND_WORDS,
    CONNECTORS,
    DICTATE_VERBS,
    EXPORT_VERBS,
    FILTER_TRIGGERS,
    GROUP_BY_TRIGGERS,
    MESSAGE_PHRASES,
    NOTE_PHRASES,
    NUMBER_WORDS,
    OPEN_VERBS,
    PRINT_VERBS,
    SEND_VERBS,
    SET_VERBS,
    VIEW_TRIGGERS,
    VIEW_WORDS,
} from "./lexicon.js";
import { NUMBER_WORDS_SPOKEN, spokenDigits } from "./numbers.js";

/**
 * @typedef {import("./interpreter.js").Interpretation} Interpretation
 * @typedef {{ phrase: string, meaning: string }} InventoryTerm
 * @typedef {{ text: string, heard: string, as: string, distance: number }} Correction
 */

const MAX_HEAD_WORDS = 3;
const MAX_CANDIDATES = 12;

const CONFUSABLE = ["dt", "rl", "pt", "bm", "bd", "kg", "sf"].map(
    (pair) => new Set(pair),
);

/** @param {string} word */
function wordSound(word) {
    return word
        .replaceAll("ch", "C")
        .replaceAll("h", "")
        .replace(/qu([ei])/g, "k$1")
        .replace(/c([ei])/g, "s$1")
        .replace(/g([ei])/g, "j$1")
        .replaceAll("ll", "y")
        .replaceAll("v", "b")
        .replaceAll("z", "s")
        .replaceAll("c", "k")
        .replaceAll("x", "ks")
        .replaceAll("w", "gu");
}

/**
 * @param {string} text
 * @returns {string[]}
 */
function soundWords(text) {
    return normalize(text).match(/[\p{L}\p{N}]+/gu) || [];
}

/**
 * @param {string} text
 * @returns {string}
 */
export function soundKey(text) {
    return soundWords(text)
        .map(wordSound)
        .join("")
        .replace(/(.)\1+/g, "$1");
}

/**
 * @param {string} a
 * @param {string} b
 * @returns {number}
 */
export function soundDistance(a, b) {
    let previous = Array.from({ length: b.length + 1 }, (_, index) => index);
    for (let row = 1; row <= a.length; row++) {
        const current = [row];
        for (let column = 1; column <= b.length; column++) {
            const x = a[row - 1];
            const y = b[column - 1];
            const swap =
                x === y
                    ? 0
                    : CONFUSABLE.some((pair) => pair.has(x) && pair.has(y))
                      ? 0.5
                      : 1;
            current.push(
                Math.min(
                    previous[column] + 1,
                    current[column - 1] + 1,
                    previous[column - 1] + swap,
                ),
            );
        }
        previous = current;
    }
    return previous[b.length];
}

/**
 * @param {string} key
 * @returns {number}
 */
function allowedDistance(key) {
    if (key.length <= 3) {
        return 0.5;
    }
    if (key.length <= 6) {
        return 1;
    }
    return key.length <= 10 ? 1.5 : 2;
}

/**
 * @param {Iterable<string> | string[][]} phrases
 * @param {string} meaning
 * @returns {InventoryTerm[]}
 */
function terms(phrases, meaning) {
    return [...phrases].map((phrase) => ({
        phrase: Array.isArray(phrase) ? phrase.join(" ") : phrase,
        meaning,
    }));
}

/**
 * @param {import("./vocabulary.js").Vocabulary | null} vocabulary
 * @param {string[]} [screenWords]
 * @returns {InventoryTerm[]}
 */
export function correctionInventory(vocabulary, screenWords = []) {
    const inventory = screenInventory(vocabulary, screenWords);
    const meanings = new Map(
        inventory.map(({ phrase, meaning }) => [soundWords(phrase).join(" "), meaning]),
    );
    for (const { words, means } of vocabulary?.terms || []) {
        const phrase = words.join(" ");
        if (!meanings.has(phrase)) {
            inventory.push({
                phrase,
                meaning: meanings.get(soundWords(means).join(" ")) || `term:${means}`,
            });
        }
    }
    return inventory;
}

/**
 * @param {import("./vocabulary.js").Vocabulary | null} vocabulary
 * @param {string[]} screenWords
 * @returns {InventoryTerm[]}
 */
function screenInventory(vocabulary, screenWords) {
    /** @type {InventoryTerm[]} */
    const inventory = [
        ...Object.entries(COMMAND_PHRASES).flatMap(([kind, phrases]) =>
            terms(phrases, `command:${kind}`),
        ),
        ...terms(OPEN_VERBS, "open"),
        ...terms(SET_VERBS, "set"),
        ...terms(BUTTON_VERBS, "press"),
        ...terms(DICTATE_VERBS, "dictate"),
        ...terms(PRINT_VERBS, "print"),
        ...terms(EXPORT_VERBS, "export"),
        ...terms(SEND_VERBS, "send"),
        ...terms(NOTE_PHRASES, "note"),
        ...terms(MESSAGE_PHRASES, "message"),
        ...terms(GROUP_BY_TRIGGERS, "group_by"),
        ...terms(FILTER_TRIGGERS, "filter_by"),
        ...terms(VIEW_TRIGGERS, "view"),
        ...terms(NUMBER_WORDS, "number"),
        ...terms(COMMAND_WORDS, "palette"),
        ...Object.entries(VIEW_WORDS).flatMap(([word, type]) =>
            [word, `vista ${word}`, `vista de ${word}`, `view ${word}`].map(
                (phrase) => ({
                    phrase,
                    meaning: `view:${type}`,
                }),
            ),
        ),
        ...terms(screenWords, "screen"),
    ];
    if (!vocabulary) {
        return inventory;
    }
    for (const menu of vocabulary.menus) {
        inventory.push(...terms(menu.phrases, `menu:${menu.label}:${menu.appLabel}`));
    }
    for (const command of vocabulary.commands) {
        inventory.push({
            phrase: command.name,
            meaning: `command_palette:${command.name}`,
        });
    }
    for (const target of vocabulary.targets || []) {
        if (target.label) {
            inventory.push({ phrase: target.label, meaning: `target:${target.label}` });
        }
    }
    const view = vocabulary.view;
    if (!view) {
        return inventory;
    }
    /**
     * @param {{ label: string, alternates?: string[] }} term
     * @param {string} meaning
     */
    const named = (term, meaning) =>
        [term.label, ...(term.alternates || [])].map((phrase) => ({ phrase, meaning }));
    inventory.push(
        ...view.filters.flatMap((f) => named(f, `filter:${f.name}`)),
        ...view.dateFilters.flatMap((f) => named(f, `date:${f.name}`)),
        ...view.groupBys.flatMap((g) => named(g, `group_by:${g.fieldName}`)),
        ...view.searchFields.flatMap((s) => named(s, `search:${s.fieldName}`)),
    );
    if (view.form) {
        inventory.push(
            ...view.form.fields.flatMap((f) => named(f, `field:${f.name}`)),
            ...view.form.buttons.flatMap((b) =>
                [b.label, ...(b.alternates || []), ...(b.spoken || [])].map(
                    (phrase) => ({
                        phrase,
                        meaning: `button:${b.label}`,
                    }),
                ),
            ),
        );
        if (
            view.form.fields.some((f) =>
                ["integer", "float", "monetary"].includes(f.type),
            )
        ) {
            inventory.push(...terms(NUMBER_WORDS_SPOKEN, "number_word"));
        }
    }
    return inventory;
}

/**
 * @param {string} text
 * @param {InventoryTerm[]} inventory
 * @returns {Correction[]}
 */
export function correctionCandidates(text, inventory) {
    const spans = [...text.matchAll(/[\p{L}\p{N}]+/gu)];
    if (!spans.length) {
        return [];
    }
    const words = spans.map((span) => normalize(span[0]));
    /** @param {number} length */
    const rest = (length) =>
        length < spans.length
            ? text.slice(/** @type {number} */ (spans[length].index))
            : "";
    /** @type {Map<string, InventoryTerm[]>} */
    const byKey = new Map();
    for (const term of inventory) {
        const key = soundKey(term.phrase);
        if (key.length >= 2) {
            byKey.set(key, [...(byKey.get(key) || []), term]);
        }
    }
    /** @type {Correction[]} */
    const found = [];
    /**
     * @param {string} phrase
     * @param {number} length
     * @param {number} distance
     */
    const propose = (phrase, length, distance) => {
        const heard = text.slice(
            0,
            spans[length - 1].index + spans[length - 1][0].length,
        );
        found.push({
            text: `${phrase} ${rest(length)}`.trim(),
            heard,
            as: phrase,
            distance,
        });
    };
    for (let length = Math.min(MAX_HEAD_WORDS, words.length); length >= 1; length--) {
        const head = words.slice(0, length);
        if (
            head.some((word) => /\d/.test(word)) ||
            (length === 1 && CONNECTORS.has(head[0]))
        ) {
            continue;
        }
        const key = soundKey(head.join(" "));
        const same = byKey.get(key);
        if (same) {
            const phrase = same[0].phrase;
            if (normalize(phrase) !== head.join(" ")) {
                propose(phrase, length, 0);
            }
            break;
        }
        if (length === 1) {
            for (let cut = 1; cut < key.length; cut++) {
                const verb = byKey.get(key.slice(0, cut));
                const tail = key.slice(cut);
                if (
                    verb &&
                    [...CONNECTORS].some((connector) => soundKey(connector) === tail)
                ) {
                    propose(`${verb[0].phrase} ${tail}`, 1, 0.5);
                }
            }
        }
        for (const [termKey, termsOfKey] of byKey) {
            const distance = soundDistance(key, termKey);
            if (distance > 0 && distance <= allowedDistance(termKey)) {
                propose(termsOfKey[0].phrase, length, distance);
            }
        }
    }
    return found.sort((a, b) => a.distance - b.distance).slice(0, MAX_CANDIDATES);
}

/**
 * @param {InventoryTerm[]} inventory
 * @returns {{ a: string, b: string, distance: number }[]}
 */
export function soundCollisions(inventory) {
    /** @type {Map<string, InventoryTerm>} */
    const byPhrase = new Map();
    for (const term of inventory) {
        const plain = normalize(term.phrase);
        if (soundKey(plain).length >= 3 && !byPhrase.has(plain)) {
            byPhrase.set(plain, term);
        }
    }
    const terms = [...byPhrase.entries()].map(([plain, term]) => ({
        plain,
        meaning: term.meaning,
        key: soundKey(plain),
    }));
    /** @type {{ a: string, b: string, distance: number }[]} */
    const collisions = [];
    for (let i = 0; i < terms.length; i++) {
        for (let j = i + 1; j < terms.length; j++) {
            const [x, y] = [terms[i], terms[j]];
            if (x.meaning === y.meaning) {
                continue;
            }
            const distance = soundDistance(x.key, y.key);
            if (distance <= 1) {
                collisions.push({ a: x.plain, b: y.plain, distance });
            }
        }
    }
    return collisions;
}

const SPOKEN_MARKS = new Set(["guion", "diagonal", "bajo", "slash", "dash", "hyphen"]);

/**
 * @param {string} value
 * @returns {string[]}
 */
export function recordSearchWords(value) {
    return (spokenDigits(value).match(/[\p{L}\p{N}]+/gu) || []).filter((word) => {
        const plain = normalize(word);
        return plain.length >= 3 && !CONNECTORS.has(plain) && !SPOKEN_MARKS.has(plain);
    });
}

/**
 * @template {{ display_name: string }} R
 * @param {string} value
 * @param {R[]} records
 * @returns {R[]}
 */
export function recordsSoundingLike(value, records) {
    const said = soundKey(
        soundWords(spokenDigits(value))
            .filter((word) => !SPOKEN_MARKS.has(word))
            .join(" "),
    );
    if (said.length < 3) {
        return [];
    }
    return records
        .map((record) => {
            const name = soundKey(record.display_name);
            const distance = Math.min(
                soundDistance(said, name),
                soundDistance(said, name.slice(0, said.length)),
            );
            return { record, distance };
        })
        .filter(({ distance }) => distance <= allowedDistance(said))
        .sort((a, b) => a.distance - b.distance)
        .map(({ record }) => record);
}

/** @param {Interpretation} interpretation */
export function isUnderstood({ proposals, candidates, blocked }) {
    return Boolean(proposals.length || candidates.length || blocked);
}

/**
 * @param {Interpretation} interpretation
 * @returns {string}
 */
function readingOf({ proposals, candidates, blocked }) {
    return JSON.stringify(
        [...proposals, ...candidates, ...(blocked ? [blocked] : [])].map(
            (p) => `${p.kind}:${p.description}`,
        ),
    );
}

/**
 * @param {string} text
 * @param {InventoryTerm[]} inventory
 * @param {(text: string) => Interpretation} understand
 * @returns {{ interpretation: Interpretation, correction: Correction } | null}
 */
export function understandCorrected(text, inventory, understand) {
    /** @type {{ interpretation: Interpretation, correction: Correction }[]} */
    const understood = [];
    for (const correction of correctionCandidates(text, inventory)) {
        if (
            understood.length &&
            correction.distance > understood[0].correction.distance
        ) {
            break;
        }
        const interpretation = understand(correction.text);
        if (isUnderstood(interpretation)) {
            understood.push({ interpretation, correction });
        }
    }
    if (!understood.length) {
        return null;
    }
    const readings = new Map(understood.map((u) => [readingOf(u.interpretation), u]));
    if (readings.size === 1) {
        return understood[0];
    }
    const choices = [...readings.values()];
    return {
        correction: choices[0].correction,
        interpretation: {
            text,
            proposals: [],
            candidates: choices.flatMap(({ interpretation, correction }) =>
                interpretation.proposals.slice(0, 1).map((proposal) =>
                    Object.assign(proposal, {
                        corrected: { heard: correction.heard, as: correction.as },
                    }),
                ),
            ),
            blocked: null,
        },
    };
}

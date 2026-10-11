// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { ANGLICISMS_2026_09_26 } from "@voice/../tests/corpus/anglicisms_2026_09_26";
import { HEARD_IN_ENGLISH } from "@voice/../tests/corpus/english_pass_2026_09_26";
import { LMMG_2026_09_26 } from "@voice/../tests/corpus/lmmg_2026_09_26";
import { LMMG_WORDS_2026_09_26 } from "@voice/../tests/corpus/lmmg_words_2026_09_26";
import { corpusVocabulary } from "@voice/../tests/corpus/screens";
import {
    correctionInventory,
    isUnderstood,
    soundCollisions,
    understandCorrected,
} from "@voice/interpreter/correction";
import { interpret } from "@voice/interpreter/interpreter";

describe.current.tags("headless");

/**
 * @typedef {{ file: string, screen: string, said: string, small: string, turbo: string, expected: string | null }} Line
 * @typedef {{
 *   name: string,
 *   lines: Line[],
 *   understood: number,
 *   succeeded: { small: number, turbo: number },
 *   corrected: { small: number, turbo: number },
 *   rescued: Record<string, string>,
 *   english: { rescued: number, misled: number, unasked: number },
 * }} Corpus
 */

/** @type {Corpus[]} */
const CORPORA = [
    {
        name: "LMMG 2026-09-26, 100 commands",
        lines: LMMG_2026_09_26,
        understood: 64,
        succeeded: { small: 53, turbo: 51 },
        corrected: { small: 60, turbo: 56 },
        rescued: {
            "c037.wav small": "set_field: Precio unitario: 185.5",
            "c045.wav said": "click_button: Validar on S00042",
            "c045.wav small": "click_button: Validar on S00042",
            "c045.wav turbo": "click_button: Validar on S00042",
        },
        english: { rescued: 0, misled: 0, unasked: 0 },
    },
    {
        name: "LMMG 2026-09-26, word choice",
        lines: LMMG_WORDS_2026_09_26,
        understood: 50,
        succeeded: { small: 45, turbo: 39 },
        corrected: { small: 49, turbo: 40 },
        rescued: {},
        english: { rescued: 0, misled: 0, unasked: 1 },
    },
];

const COLLISIONS = {
    bills: 14,
    invoices: 14,
    order: 25,
    order_numbers: 25,
    pickings: 18,
    sales: 14,
};

const WORDS_ARE_DICTATION = new Set(["log_note", "compose_message", "dictate"]);
const MODELS = /** @type {const} */ (["small", "turbo"]);

/**
 * @param {import("@voice/interpreter/interpreter").Interpretation} interpretation
 * @returns {string | null}
 */
function summary({ proposals, candidates, blocked }) {
    if (blocked) {
        return `blocked ${blocked.kind}: ${blocked.description}`;
    }
    if (candidates.length) {
        return `pick: ${candidates.map((c) => c.description).join(" | ")}`;
    }
    if (!proposals.length) {
        return null;
    }
    return proposals.map((p) => `${p.kind}: ${p.description}`).join(" + ");
}

/**
 * The command a summary stands for: a relation's name is searched without
 * regard to case, and a note's words are dictation, scored by speech_measure.
 *
 * @param {string | null} described
 */
function command(described) {
    if (described === null) {
        return null;
    }
    const kind = described.split(":")[0];
    return WORDS_ARE_DICTATION.has(kind) ? kind : described.toLowerCase();
}

/**
 * @param {string} text
 * @param {string} screen
 */
function read(text, screen) {
    return summary(interpret(text, corpusVocabulary(screen)));
}

/**
 * @param {string} text
 * @param {string} screen
 */
function readCorrected(text, screen) {
    const vocabulary = corpusVocabulary(screen);
    const interpretation = interpret(text, vocabulary);
    if (isUnderstood(interpretation)) {
        return summary(interpretation);
    }
    const corrected = understandCorrected(
        text,
        correctionInventory(vocabulary),
        (reading) => interpret(reading, vocabulary),
    );
    return corrected ? summary(corrected.interpretation) : null;
}

/**
 * @param {Line[]} lines
 * @param {(text: string, screen: string) => string | null} reader
 */
function successes(lines, reader) {
    /** @type {Record<string, number>} */
    const succeeded = { small: 0, turbo: 0 };
    /** @type {string[]} */
    const missed = [];
    for (const line of lines) {
        if (line.expected === null) {
            continue;
        }
        for (const model of MODELS) {
            const heard = reader(line[model], line.screen);
            if (command(heard) === command(line.expected)) {
                succeeded[model]++;
            } else {
                missed.push(`${model} ${line.file}: "${line[model]}" -> ${heard}`);
            }
        }
    }
    return { succeeded, missed };
}

for (const corpus of CORPORA) {
    describe(corpus.name, () => {
        test("the grammar reads each written sentence as it was meant", () => {
            for (const line of corpus.lines) {
                expect(read(line.said, line.screen)).toBe(line.expected, {
                    message: `${line.file}: ${line.said}`,
                });
            }
            expect(corpus.lines.filter((line) => line.expected !== null)).toHaveLength(
                corpus.understood,
            );
        });

        test("the commands still run from what each local model heard", () => {
            const { succeeded, missed } = successes(corpus.lines, read);
            expect(succeeded).toEqual(corpus.succeeded, { message: missed.join("\n") });
        });

        test("context correction recovers what each model misheard, and nothing else", () => {
            const { succeeded, missed } = successes(corpus.lines, readCorrected);
            expect(succeeded).toEqual(corpus.corrected, { message: missed.join("\n") });
            /** @type {Record<string, string>} */
            const rescued = {};
            for (const line of corpus.lines.filter((l) => l.expected === null)) {
                for (const source of /** @type {const} */ (["said", ...MODELS])) {
                    const heard = readCorrected(line[source], line.screen);
                    if (heard !== null) {
                        rescued[`${line.file} ${source}`] = heard;
                    }
                }
            }
            expect(rescued).toEqual(corpus.rescued);
        });

        test("heard again in English, a missed command is rescued or misled", () => {
            const outcome = { rescued: 0, misled: 0, unasked: 0 };
            /** @type {string[]} */
            const readings = [];
            for (const line of corpus.lines) {
                const english = HEARD_IN_ENGLISH[line.file]?.small;
                if (!english || readCorrected(line.small, line.screen) !== null) {
                    continue;
                }
                const second = read(english, line.screen);
                if (second === null) {
                    continue;
                }
                const verdict =
                    line.expected === null
                        ? "unasked"
                        : command(second) === command(line.expected)
                          ? "rescued"
                          : "misled";
                outcome[verdict]++;
                readings.push(
                    `${verdict} ${line.file}: "${line.small}" -> "${english}" -> ${second}`,
                );
            }
            expect(outcome).toEqual(corpus.english, { message: readings.join("\n") });
        });
    });
}

const ANGLICISMS_UNDERSTOOD = { withoutTerms: 35, withTerms: 36 };

describe("anglicisms, as written", () => {
    test("each sentence keeps its reading", () => {
        for (const line of ANGLICISMS_2026_09_26) {
            expect(read(line.said, line.screen)).toBe(line.expected, {
                message: `${line.file}: ${line.said}`,
            });
        }
    });

    test("the terms add what the labels alone do not understand", () => {
        const understood = { withoutTerms: 0, withTerms: 0 };
        /** @type {string[]} */
        const readings = [];
        for (const line of ANGLICISMS_2026_09_26) {
            const plain = summary(
                interpret(line.said, corpusVocabulary(line.screen, { terms: [] })),
            );
            const withTerms = read(line.said, line.screen);
            understood.withoutTerms += plain === null ? 0 : 1;
            understood.withTerms += withTerms === null ? 0 : 1;
            readings.push(`${line.file} ${line.said}: ${plain} -> ${withTerms}`);
        }
        expect(understood).toEqual(ANGLICISMS_UNDERSTOOD, {
            message: readings.join("\n"),
        });
    });
});

test("the words of each screen stay apart by sound", () => {
    /** @type {Record<string, number>} */
    const counted = {};
    /** @type {string[]} */
    const pairs = [];
    for (const screen of new Set(LMMG_2026_09_26.map((line) => line.screen))) {
        const collisions = soundCollisions(
            correctionInventory(corpusVocabulary(screen)),
        );
        counted[screen] = collisions.length;
        pairs.push(...collisions.map(({ a, b }) => `${screen}: ${a} ~ ${b}`));
    }
    expect(counted).toEqual(COLLISIONS, { message: pairs.join("\n") });
});

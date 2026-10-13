// @ts-check
/** @odoo-module native */

import { termPhrases } from "./interpreter/terms.js";

export class VoiceTerms {
    /** @param {any} orm */
    constructor(orm) {
        this.orm = orm;
        /** @type {import("./interpreter/terms.js").TermPhrase[]} */
        this.phrases = [];
        /** @type {import("./interpreter/terms.js").SpokenTerm[]} */
        this.terms = [];
        /** @type {Promise<void> | null} */
        this.loaded = null;
    }

    ensure() {
        if (!this.loaded) {
            this.loaded = this.orm.silent
                .call("speech.vocabulary.form", "spoken_terms", [])
                .then(
                    (
                        /** @type {import("./interpreter/terms.js").SpokenTerm[]} */ terms,
                    ) => {
                        this.terms = terms || [];
                        this.phrases = termPhrases(this.terms);
                    },
                )
                .catch(() => {});
        }
        return this.loaded;
    }
}

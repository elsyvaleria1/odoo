// @ts-check
/** @odoo-module native */

import { proxy, toRaw } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { now } from "@web/core/l10n/dates";
import { normalize } from "@web/core/l10n/utils";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";

import { AlternateLabels } from "./alternates.js";
import { firstAvailableEngine } from "./engines/voice_engines.js";
import { execute, targetView, voiceExecutorRegistry } from "./executor.js";
import {
    correctionInventory,
    isUnderstood,
    recordSearchWords,
    recordsSoundingLike,
    understandCorrected,
} from "./interpreter/correction.js";
import {
    guardNegation,
    interpret,
    isNegated,
    RISK,
} from "./interpreter/interpreter.js";
import { compileVocabulary } from "./interpreter/vocabulary.js";
import { collectTargets } from "./numbers/targets.js";
import { VoiceScreens } from "./screens.js";
import { VoiceTerms } from "./voice_terms.js";

const MAX_DONE = 5;

export const voiceFallbackRegistry = registry.category("voice_fallbacks");
const MAX_NAME_SEARCH = 8;

/**
 * @typedef {import("./interpreter/interpreter.js").Proposal} Proposal
 * @typedef {import("./interpreter/interpreter.js").Interpretation} Interpretation
 * @typedef {{ description: string, undo: import("./executor.js").Undo, fromModel: boolean }} Done
 */

/** @returns {string} */
function speechLang() {
    return (user.lang || "en_US").replace("_", "-");
}

export class VoiceService {
    /**
     * @param {Record<string, any>} services
     * @param {Record<string, any>} allServices for what a registered executor needs
     */
    constructor(services, allServices) {
        this.services = services;
        this.allServices = allServices;
        this.state = proxy({
            open: false,
            listening: false,
            busy: false,
            heard: "",
            interim: "",
            message: "",
            help: false,
            notice: "",
            /** @type {Done[]} */
            done: [],
            /** @type {Proposal | null} */
            pending: null,
            /** @type {Proposal[]} */
            candidates: [],
            /** @type {Proposal | null} */
            blocked: null,
            /** @type {{ n: number, top: number, left: number }[]} */
            numbers: [],
            /** @type {{ label: string, stopping: boolean } | null} */
            session: null,
            /** @type {{ heard: string, as: string } | null} */
            correction: null,
        });
        /** @type {(() => Promise<any>) | null} */
        this.stopCurrentSession = null;
        /** @type {import("./numbers/targets.js").Target[]} */
        this.targets = [];
        this.hideNumbers = this.hideNumbers.bind(this);
        /** @type {AbortController | null} */
        this.abort = null;
        /** @type {{ vocabulary: any, target: any, targets: import("./numbers/targets.js").Target[] }} */
        this.lastSaid = { vocabulary: null, target: null, targets: [] };
        /** @type {((value: boolean) => void) | null} */
        this.acknowledge = null;
        this.screens = new VoiceScreens(services.ui);
        this.alternates = new AlternateLabels(services.orm);
        this.terms = new VoiceTerms(services.orm);
    }

    async prepare() {
        const menuIds = this.services.menu
            .getAll()
            .map((/** @type {any} */ menu) => menu.id)
            .filter((/** @type {any} */ id) => typeof id === "number");
        await Promise.all([
            this.alternates.ensure(this.services.active_view.current, menuIds),
            this.terms.ensure(),
        ]);
    }

    /**
     * Each proposal keeps the view it was said to: a palette or a dialog
     * opened since takes the active element, not the user's intent.
     *
     * @param {string} text
     * @param {{ withTargets?: boolean }} [options] the palette is a dialog of
     *   its own, whose items are not what the user means by "click"
     * @returns {Interpretation}
     */
    interpret(text, { withTargets = true } = {}) {
        const screen = this.screens.current;
        const understood = screen?.parse(text);
        if (screen && understood?.length) {
            this.lastSaid = { vocabulary: null, target: null, targets: [] };
            for (const proposal of understood) {
                proposal.screen = screen;
            }
            return guardNegation(
                { text, proposals: understood, candidates: [], blocked: null },
                isNegated(text),
            );
        }
        const target = this.services.active_view.current;
        const vocabulary = this.vocabulary(target);
        const targets = withTargets ? this.currentTargets() : [];
        vocabulary.targets = targets.map(({ label, risk }) => ({ label, risk }));
        vocabulary.numbersShown = withTargets && this.state.numbers.length > 0;
        vocabulary.extensions = voiceExecutorRegistry
            .getEntries()
            .map(([kind]) => kind);
        this.lastSaid = { vocabulary, target, targets };
        return this.bind(interpret(text, vocabulary));
    }

    /**
     * @param {Interpretation} interpretation
     * @returns {Interpretation}
     */
    bind(interpretation) {
        const { target, targets } = this.lastSaid;
        const { proposals, candidates, blocked } = interpretation;
        for (const proposal of [
            ...proposals,
            ...candidates,
            ...(blocked ? [blocked] : []),
        ]) {
            proposal.target = target;
            if (proposal.kind === "click_target") {
                proposal.element = targets[proposal.index].el;
            }
        }
        return interpretation;
    }

    /**
     * @param {string} text
     * @returns {Promise<Interpretation | null>}
     */
    async fallback(text) {
        for (const ask of voiceFallbackRegistry.getAll()) {
            this.state.busy = true;
            try {
                const proposals = await ask({
                    text,
                    vocabulary: this.lastSaid.vocabulary,
                });
                if (proposals?.length) {
                    for (const proposal of proposals) {
                        proposal.fromModel = true;
                    }
                    return this.bind(
                        guardNegation(
                            { text, proposals, candidates: [], blocked: null },
                            isNegated(text),
                        ),
                    );
                }
            } catch {
                continue;
            } finally {
                this.state.busy = false;
            }
        }
        return null;
    }

    /** @param {import("@web/views/active_view").ActiveView | null} [target] */
    vocabulary(target = this.services.active_view.current) {
        const { menu, home_menu, command, ui } = this.services;
        const commands = command
            .getCommands(ui.activeElement)
            .filter((/** @type {any} */ c) => !c.isAvailable || c.isAvailable())
            .map((/** @type {any} */ c) => ({
                name: c.name,
                category: c.category,
                action: c.action,
            }));
        return compileVocabulary({
            menu,
            activeView: target,
            homeMenu: home_menu,
            commands,
            today: now(),
            alternates: this.alternates.of(target),
            terms: this.terms.phrases,
        });
    }

    /**
     * The names worth biasing a recogniser towards, most specific first.
     *
     * @returns {string[]}
     */
    phrases() {
        const vocabulary = this.vocabulary();
        const view = vocabulary.view;
        return [
            ...(this.screens.current?.phrases?.() || []),
            ...(view?.form?.buttons.map((button) => button.label) || []),
            ...(view?.form?.fields.map((field) => field.label) || []),
            ...(view?.filters.map((filter) => filter.label) || []),
            ...(view?.groupBys.map((groupBy) => groupBy.label) || []),
            ...vocabulary.menus.filter((term) => term.isApp).map((term) => term.label),
        ];
    }

    clear() {
        Object.assign(this.state, {
            message: "",
            help: false,
            pending: null,
            candidates: [],
            blocked: null,
            correction: null,
        });
    }

    close() {
        this.stop();
        this.hideNumbers();
        this.clear();
        Object.assign(this.state, { open: false, heard: "", interim: "", done: [] });
    }

    /**
     * @param {string} text
     * @param {{ spoken?: boolean, again?: ((language: string) => Promise<string>) | null }} [options]
     *   `again` hears the same utterance once more in another language
     */
    async submit(text, { spoken = false, again = null } = {}) {
        this.clear();
        Object.assign(this.state, { open: true, heard: text, interim: "" });
        await this.prepare();
        let interpretation = this.interpret(text);
        /** @type {"grammar" | "correction" | "english" | "model" | "none"} */
        let answeredBy = "grammar";
        if (!isUnderstood(interpretation)) {
            const corrected = this.correct(text);
            if (corrected) {
                const { heard, as } = corrected.correction;
                this.state.correction = { heard, as };
                interpretation = corrected.interpretation;
                answeredBy = "correction";
            } else {
                const english = await this.hearInEnglish(again);
                if (english) {
                    this.state.correction = { heard: text, as: english.text };
                    interpretation = english.interpretation;
                    answeredBy = "english";
                } else {
                    const fallback = await this.fallback(text);
                    answeredBy = fallback ? "model" : "none";
                    interpretation = fallback || interpretation;
                }
            }
        }
        this.share(text, answeredBy, spoken);
        await this.handle(interpretation);
    }

    /**
     * A command said in English inside a Spanish session is often transcribed
     * as Spanish nonsense; decoded again in English, the grammar may read it.
     * Only as a second pass: an English first pass translates Spanish.
     *
     * @param {((language: string) => Promise<string>) | null} again
     * @returns {Promise<{ text: string, interpretation: Interpretation } | null>}
     */
    async hearInEnglish(again) {
        if (!again || speechLang().startsWith("en")) {
            return null;
        }
        this.state.busy = true;
        try {
            const text = (await again("en")).trim();
            if (!text) {
                return null;
            }
            const interpretation = this.interpret(text);
            return isUnderstood(interpretation) ? { text, interpretation } : null;
        } catch {
            return null;
        } finally {
            this.state.busy = false;
        }
    }

    /**
     * What the recogniser most likely misheard, read against what this screen
     * offers; the grammar stays exact and decides which reading holds.
     *
     * @param {string} text
     */
    correct(text) {
        const inventory = correctionInventory(
            this.lastSaid.vocabulary,
            this.screens.current?.words?.() || [],
        );
        return understandCorrected(text, inventory, (reading) =>
            this.interpret(reading),
        );
    }

    /**
     * Said aloud on this device, by the browser's own synthesiser: nothing
     * leaves it.
     *
     * @param {string} text
     * @returns {boolean} whether there was a voice to say it
     */
    speak(text) {
        const synthesis = /** @type {any} */ (browser).speechSynthesis;
        const Utterance = /** @type {any} */ (browser).SpeechSynthesisUtterance;
        if (!text || !synthesis || !Utterance) {
            return false;
        }
        synthesis.cancel();
        const utterance = new Utterance(text);
        utterance.lang = speechLang();
        synthesis.speak(utterance);
        return true;
    }

    /** @returns {boolean} */
    get sharing() {
        return Boolean(user.settings?.voice_share_sentences);
    }

    /** @param {boolean} sharing */
    setSharing(sharing) {
        return user.setUserSettings("voice_share_sentences", sharing);
    }

    /**
     * @param {string} text
     * @param {"grammar" | "correction" | "english" | "model" | "none"} answeredBy
     * @param {boolean} spoken
     */
    share(text, answeredBy, spoken) {
        if (!this.sharing) {
            return;
        }
        const target = this.lastSaid.target;
        this.services.orm.silent
            .call("voice.sentence", "record", [answeredBy, text], {
                spoken,
                res_model: target?.searchModel.resModel || "",
                view_type: target?.config.viewType || "",
            })
            .catch(() => {});
    }

    /**
     * @param {string} text
     * @param {Proposal} proposal one the user already chose, from the palette
     */
    async accept(text, proposal) {
        this.clear();
        Object.assign(this.state, { open: true, heard: text, interim: "" });
        await this.propose(proposal);
    }

    /** @param {Interpretation} interpretation */
    async handle(interpretation) {
        if (interpretation.blocked) {
            this.state.blocked = interpretation.blocked;
            this.state.message = _t(
                "That sounded like a “no”: %s was not done.",
                interpretation.blocked.description,
            );
            return;
        }
        if (interpretation.candidates.length) {
            this.state.candidates = interpretation.candidates;
            return;
        }
        if (!interpretation.proposals.length) {
            this.state.message = _t("I did not understand “%s”.", interpretation.text);
            this.state.help = true;
            return;
        }
        for (const proposal of interpretation.proposals) {
            await this.propose(proposal);
        }
    }

    /** @param {Proposal} proposal */
    async propose(proposal) {
        const { resolved, choose } = await this.resolve(proposal);
        if (choose || resolved.length !== 1) {
            this.state.candidates = resolved;
            if (!resolved.length) {
                this.state.message = _t("Nothing matches “%s”.", proposal.query);
            }
            return;
        }
        if (resolved[0].risk === RISK.COMMIT) {
            this.state.pending = resolved[0];
            return;
        }
        await this.run(resolved[0]);
    }

    /**
     * A relation named by a word becomes the record of that name, or a
     * choice when several records answer to it, or when only records that
     * sound like it do.
     *
     * @param {Proposal} proposal
     * @returns {Promise<{ resolved: Proposal[], choose: boolean }>}
     */
    async resolve(proposal) {
        if (proposal.kind === "search") {
            return this.resolveSearch(proposal);
        }
        if (proposal.kind !== "set_field" || proposal.query === undefined) {
            return { resolved: [proposal], choose: false };
        }
        const records = await this.nameSearch(proposal.relation, proposal.query);
        const exact = records.filter(
            (record) => normalize(record.display_name) === normalize(proposal.query),
        );
        let chosen = exact.length === 1 ? exact : records;
        let choose = false;
        if (!records.length) {
            chosen = await this.recordsSoundingLike(proposal.relation, proposal.query);
            choose = true;
        }
        const { query, ...rest } = proposal;
        return {
            resolved: chosen.map((record) => ({
                ...rest,
                value: record,
                description: proposal.description.replace(query, record.display_name),
            })),
            choose,
        };
    }

    /**
     * A search by a relation keeps what was heard as text when records answer
     * to it; when none does, the records that sound like it are offered, and
     * the one chosen is searched for itself.
     *
     * @param {Proposal} proposal
     * @returns {Promise<{ resolved: Proposal[], choose: boolean }>}
     */
    async resolveSearch(proposal) {
        const searches = proposal.spec.fieldSearches;
        for (const [index, search] of searches.entries()) {
            if (!search.relation) {
                continue;
            }
            const value = String(search.value);
            if ((await this.nameSearch(search.relation, value)).length) {
                continue;
            }
            const records = await this.recordsSoundingLike(search.relation, value);
            if (!records.length) {
                continue;
            }
            const resolved = records.map((record) => ({
                ...proposal,
                spec: {
                    ...proposal.spec,
                    fieldSearches: searches.map((other, at) =>
                        at === index
                            ? {
                                  fieldName: search.fieldName,
                                  value: record.id,
                                  label: record.display_name,
                                  operator: "=",
                              }
                            : other,
                    ),
                },
                description: proposal.description.replace(value, record.display_name),
            }));
            return { resolved, choose: true };
        }
        return { resolved: [proposal], choose: false };
    }

    /**
     * @param {string} relation
     * @param {string} name
     * @returns {Promise<{ id: number, display_name: string }[]>}
     */
    async nameSearch(relation, name) {
        const found = await this.services.orm.call(relation, "name_search", [], {
            name,
            limit: MAX_NAME_SEARCH,
        });
        return found.map((/** @type {[number, string]} */ [id, displayName]) => ({
            id,
            display_name: displayName,
        }));
    }

    /**
     * Nothing is named as it was heard: the records named by any of its words
     * that sound like the whole of it, offered as a choice, never taken.
     *
     * @param {string} relation
     * @param {string} value
     */
    async recordsSoundingLike(relation, value) {
        const lists = await Promise.all(
            recordSearchWords(value).map((word) => this.nameSearch(relation, word)),
        );
        const byId = new Map(lists.flat().map((record) => [record.id, record]));
        return recordsSoundingLike(value, [...byId.values()]).slice(0, MAX_NAME_SEARCH);
    }

    /** @returns {import("./numbers/targets.js").Target[]} */
    currentTargets() {
        return this.state.numbers.length
            ? this.targets
            : collectTargets(this.services.ui.activeElement);
    }

    showNumbers() {
        this.hideNumbers();
        this.targets = collectTargets(this.services.ui.activeElement);
        this.state.numbers = this.targets.map(({ el }, index) => {
            const rect = el.getBoundingClientRect();
            return { n: index + 1, top: rect.top, left: rect.left };
        });
        window.addEventListener("scroll", this.hideNumbers, {
            capture: true,
            once: true,
        });
        window.addEventListener("resize", this.hideNumbers, { once: true });
    }

    hideNumbers() {
        window.removeEventListener("scroll", this.hideNumbers, { capture: true });
        window.removeEventListener("resize", this.hideNumbers);
        this.targets = [];
        this.state.numbers = [];
    }

    /** @param {Proposal} proposal */
    async run(proposal) {
        this.state.busy = true;
        try {
            const undo = await execute(proposal, {
                services: this.services,
                submit: (text) => this.submit(text),
                undo: () => this.undo(),
                showHelp: () => {
                    this.state.help = true;
                },
                showNumbers: () => this.showNumbers(),
                hideNumbers: () => this.hideNumbers(),
                targetView: (target) => targetView(this.services, target),
                getService: (name) => this.allServices[name],
                startSession: (session) => this.startSession(session),
                report: (message) => {
                    this.state.message = message;
                },
            });
            if (proposal.kind !== "show_numbers") {
                this.hideNumbers();
            }
            if (proposal.kind !== "undo" && proposal.kind !== "help") {
                this.state.done = [
                    {
                        description: proposal.description,
                        undo,
                        fromModel: Boolean(proposal.fromModel),
                    },
                    ...this.state.done,
                ].slice(0, MAX_DONE);
            }
        } catch (error) {
            this.state.message = /** @type {Error} */ (error).message;
        } finally {
            this.state.busy = false;
        }
    }

    async confirm() {
        const proposal = toRaw(this.state.pending);
        this.state.pending = null;
        if (proposal) {
            await this.run(proposal);
        }
    }

    /** @param {number} index */
    async pick(index) {
        const proposal = toRaw(this.state.candidates[index]);
        this.state.candidates = [];
        if (proposal) {
            this.learn(proposal.corrected);
            await this.propose(proposal);
        }
    }

    /**
     * A reading the user chose among several is kept, for someone who shares
     * what they say, as a term an administrator may approve.
     *
     * @param {{ heard: string, as: string } | undefined} corrected
     */
    learn(corrected) {
        if (!corrected || !this.sharing) {
            return;
        }
        this.services.orm.silent
            .call("speech.vocabulary.form", "learn", [corrected.heard, corrected.as])
            .catch(() => {});
    }

    async undo() {
        const index = this.state.done.findIndex((done) => done.undo);
        if (index === -1) {
            this.state.message = _t("There is nothing to undo.");
            return;
        }
        const [done] = this.state.done.splice(index, 1);
        await done.undo?.();
    }

    /** @param {{ label: string, stop: () => Promise<any> }} session */
    startSession({ label, stop }) {
        this.stopCurrentSession = stop;
        this.state.session = { label, stopping: false };
    }

    async stopSession() {
        const stop = this.stopCurrentSession;
        if (!stop || !this.state.session) {
            return;
        }
        this.state.session.stopping = true;
        try {
            await stop();
        } finally {
            this.stopCurrentSession = null;
            this.state.session = null;
        }
    }

    async listen() {
        if (this.state.session) {
            await this.stopSession();
            return;
        }
        if (this.state.listening) {
            this.stop();
            return;
        }
        this.clear();
        this.state.open = true;
        const lang = speechLang();
        const engine = await firstAvailableEngine(lang);
        if (!engine) {
            this.state.message = _t(
                "No speech engine is available here. You can still type what you would say in the command palette, after “>”.",
            );
            return;
        }
        if (!(await this.acknowledged(engine.privacy()))) {
            return;
        }
        this.abort = new AbortController();
        Object.assign(this.state, { listening: true, heard: "", interim: "" });
        let text = "";
        try {
            text = await engine.listen({
                lang,
                phrases: this.phrases(),
                onInterim: (interim) => {
                    this.state.interim = interim;
                },
                signal: this.abort.signal,
            });
        } catch (error) {
            this.state.message = /** @type {Error} */ (error).message;
        } finally {
            this.state.listening = false;
            this.abort = null;
        }
        if (text.trim()) {
            const hearAgain = engine.hearAgain;
            await this.submit(text, {
                spoken: true,
                again: hearAgain
                    ? (language) => hearAgain.call(engine, language)
                    : null,
            });
        } else if (!this.state.message) {
            this.state.message = _t("Nothing was heard.");
        }
    }

    stop() {
        this.abort?.abort();
    }

    /**
     * @param {string} privacy
     * @returns {Promise<boolean>}
     */
    acknowledged(privacy) {
        if (user.settings?.voice_notice_acknowledged) {
            return Promise.resolve(true);
        }
        this.state.notice = privacy;
        return new Promise((resolve) => {
            this.acknowledge = (accepted) => {
                this.state.notice = "";
                this.acknowledge = null;
                if (accepted) {
                    user.setUserSettings("voice_notice_acknowledged", true);
                }
                resolve(accepted);
            };
        });
    }
}

export const voiceService = {
    dependencies: [
        "action",
        "active_view",
        "command",
        "home_menu",
        "hotkey",
        "menu",
        "orm",
        "ui",
    ],
    /**
     * @param {import("@web/env").OdooEnv} env
     * @param {Record<string, any>} services
     */
    start(env, services) {
        return new VoiceService(services, env.services);
    },
};

registry.category("services").add("voice", voiceService);

/** @odoo-module */

import { Component, proxy, t, useProps, xml } from "@odoo/owl";

import { Suite } from "../core/suite.js";
import { createUrlFromId } from "../core/url.js";
import {
    elementRef,
    lookup,
    onWillRender,
    parseQuery,
    useLayoutEffect,
    useRender,
} from "../hoot_utils.js";
import { useHootEnv } from "./hoot_env_plugin.js";
import { HootJobButtons } from "./hoot_job_buttons.js";

/**
 * @typedef {{
 *  multi?: number;
 *  name: string;
 *  hasSuites: boolean;
 *  reporting: import("../hoot_utils").Reporting;
 *  selected: boolean;
 *  unfolded: boolean;
 * }} HootSideBarSuiteProps
 * @typedef {{
 *  reporting: import("../hoot_utils").Reporting;
 *  statusFilter: import("./setup_hoot_ui").StatusFilter | null;
 * }} HootSideBarCounterProps
 * @typedef {{
 * }} HootSideBarProps
 */

const { location: actualLocation } = globalThis;

const SUITE_CLASSNAME = "hoot-sidebar-suite";

/** @extends {Component<HootSideBarSuiteProps, import("../hoot").Environment>} */
export class HootSideBarSuite extends Component {
    static props = {
        multi: t.number().optional(),
        name: t.string(),
        hasSuites: t.boolean(),
        reporting: t.object(),
        selected: t.boolean(),
        unfolded: t.boolean(),
    };
    props = useProps(this.constructor.props);

    static template = xml`
        <t t-if="this.props.hasSuites">
            <i
                class="fa-solid fa-chevron-right text-xs transition"
                t-att-class="{
                    'rotate-90': this.props.unfolded,
                    'opacity-25': !this.props.reporting.failed and !this.props.reporting.tests
                }"
            />
        </t>
        <span t-ref="this.rootRef" t-att-class="this.getClassName()" t-out="this.props.name" />
        <t t-if="this.props.multi">
            <strong class="text-amber whitespace-nowrap me-1">
                x<t t-out="this.props.multi" />
            </strong>
        </t>
    `;

    setup() {
        this.rootRef = elementRef();
        let wasSelected = false;
        useLayoutEffect(
            (selected) => {
                if (selected && !wasSelected) {
                    this.rootRef.el.scrollIntoView({
                        behavior: "smooth",
                        block: "center",
                    });
                }
                wasSelected = selected;
            },
            () => [this.props.selected],
        );
    }

    getClassName() {
        const { reporting, selected } = this.props;
        let className = "truncate transition";
        if (reporting.failed) {
            className += " text-rose";
        } else if (!reporting.tests) {
            className += " opacity-25";
        }
        if (selected) {
            className += " font-bold";
        }
        return className;
    }
}

/** @extends {Component<HootSideBarCounterProps, import("../hoot").Environment>} */
export class HootSideBarCounter extends Component {
    static props = {
        reporting: t.object(),
        statusFilter: t.or([t.string(), t.literal(null)]),
    };
    props = useProps(this.constructor.props);

    static template = xml`
        <t t-set="info" t-value="this.getCounterInfo()" />
        <span
            t-attf-class="${HootSideBarCounter.name} {{ info[1] ? info[0] : 'text-gray' }} {{ info[1] ? 'font-bold' : '' }}"
            t-out="info[1]"
        />
    `;

    getCounterInfo() {
        const { reporting, statusFilter } = this.props;
        switch (statusFilter) {
            case "failed":
                return ["text-rose", reporting.failed];
            case "passed":
                return ["text-emerald", reporting.passed];
            case "skipped":
                return ["text-cyan", reporting.skipped];
            case "todo":
                return ["text-purple", reporting.todo];
            default:
                return ["text-primary", reporting.tests];
        }
    }
}

/** @extends {Component<HootSideBarProps, import("../hoot").Environment>} */
export class HootSideBar extends Component {
    static components = { HootJobButtons, HootSideBarSuite, HootSideBarCounter };

    static props = {};
    props = useProps(this.constructor.props);
    env = useHootEnv();
    render = useRender();

    static template = xml`
        <div
            class="${HootSideBar.name} flex-col w-64 h-full resize-x shadow bg-gray-200 dark:bg-gray-800 z-1 hidden md:flex"
            t-on-click.stop="this.onClick"
        >
            <form class="flex p-2 items-center gap-1">
                <div class="hoot-search-bar border rounded bg-base w-full">
                    <input
                        class="w-full rounded px-2 py-1 outline-none"
                        type="search"
                        placeholder="Search suites"
                        t-ref="this.searchInputRef"
                        t-model.proxy="this.state.filter"
                        t-on-keydown="this.onSearchInputKeydown"
                    />
                </div>
                <t t-if="this.env.runner.hasFilter">
                    <button
                        type="button"
                        class="text-primary p-1 transition-colors"
                        t-att-title="this.state.hideEmpty ? 'Show all suites' : 'Hide other suites'"
                        t-on-click.stop="this.toggleHideEmpty"
                    >
                        <i t-attf-class="fa-solid fa-{{ this.state.hideEmpty ? 'eye' : 'eye-slash' }}" />
                    </button>
                </t>
                <t t-set="expanded" t-value="this.unfoldedIds.size === this.env.runner.suites.size" />
                <button
                    type="button"
                    class="text-primary p-1 transition-colors"
                    t-attf-title="{{ expanded ? 'Collapse' : 'Expand' }} all"
                    t-on-click.stop="() => this.toggleExpand(expanded)"
                >
                    <i t-attf-class="fa-solid fa-{{ expanded ? 'compress' : 'expand' }}" />
                </button>
            </form>
            <ul class="overflow-x-hidden overflow-y-auto" t-ref="this.suitesListRef">
                <t t-foreach="this.filteredSuites" t-as="suite" t-key="suite.id">
                    <li class="flex items-center h-7 animate-slide-down">
                        <button
                            class="${SUITE_CLASSNAME} flex items-center w-full h-full gap-1 px-2 overflow-hidden hover:bg-gray-300 dark:hover:bg-gray-700"
                            t-att-class="{ 'bg-gray-300 dark:bg-gray-700': this.uiState.selectedSuiteId === suite.id }"
                            t-attf-style="margin-left: {{ (suite.path.length - 1) + 'rem' }};"
                            t-attf-title="{{ suite.fullName }}\n- {{ suite.totalTestCount }} tests\n- {{ suite.totalSuiteCount }} suites"
                            t-on-click.stop="(ev) => this.toggleItem(suite)"
                            t-on-keydown="(ev) => this.onSuiteKeydown(ev, suite)"
                        >
                            <div class="flex items-center truncate gap-1 flex-1">
                                <HootSideBarSuite
                                    multi="suite.config.multi"
                                    name="suite.name"
                                    hasSuites="this.hasSuites(suite)"
                                    reporting="suite.reporting"
                                    selected="this.uiState.selectedSuiteId === suite.id"
                                    unfolded="this.unfoldedIds.has(suite.id)"
                                />
                                <span class="text-gray">
                                    (<t t-out="suite.totalTestCount" />)
                                </span>
                            </div>
                            <HootJobButtons hidden="true" job="suite" />
                            <t t-if="this.env.runner.state.suites.includes(suite)">
                                <HootSideBarCounter
                                    reporting="suite.reporting"
                                    statusFilter="this.uiState.statusFilter"
                                />
                            </t>
                        </button>
                    </li>
                </t>
            </ul>
        </div>
    `;

    filteredSuites = [];
    runningSuites = new Set();
    unfoldedIds = new Set();

    setup() {
        const { runner, ui } = this.env;

        this.searchInputRef = elementRef();
        this.suitesListRef = elementRef();
        this.uiState = proxy(ui);
        this.state = proxy({
            filter: "",
            hideEmpty: false,
            suites: [],
            /** @type {Set<string>} */
            unfoldedIds: new Set(),
        });

        runner.beforeAll(() => {
            const singleRootSuite = runner.rootSuites.filter(
                (suite) => suite.currentJobs.length,
            );
            if (singleRootSuite.length === 1) {
                this.unfoldAndSelect(singleRootSuite[0]);
            } else {
                this.render();
            }
        });

        onWillRender(() => {
            [this.filteredSuites, this.unfoldedIds] = this.getFilteredVisibleSuites();
        });
    }

    getFilteredVisibleSuites() {
        const { runner } = this.env;
        const { hideEmpty } = this.state;
        const allSuites = runner.suites.values();
        let allowedIds;
        let unfoldedIds;
        let rootSuites;

        const parsedQuery = parseQuery(this.state.filter);
        if (parsedQuery.length) {
            allowedIds = new Set();
            unfoldedIds = new Set(this.state.unfoldedIds);
            rootSuites = new Set();
            for (const matchingSuite of lookup(parsedQuery, allSuites, "name")) {
                for (const suite of matchingSuite.path) {
                    allowedIds.add(suite.id);
                    unfoldedIds.add(suite.id);
                    if (!suite.parent) {
                        rootSuites.add(suite);
                    }
                }
            }
        } else {
            unfoldedIds = this.state.unfoldedIds;
            rootSuites = runner.rootSuites;
        }

        /** @param {Suite} suite */
        function addSuite(suite) {
            if (
                !(suite instanceof Suite) ||
                (allowedIds && !allowedIds.has(suite.id)) ||
                (hideEmpty && !(suite.reporting.tests || suite.currentJobs.length))
            ) {
                return;
            }
            unfoldedSuites.push(suite);
            if (!unfoldedIds.has(suite.id)) {
                return;
            }
            for (const child of suite.jobs) {
                addSuite(child);
            }
        }

        const unfoldedSuites = [];
        for (const suite of rootSuites) {
            addSuite(suite);
        }

        return [unfoldedSuites, unfoldedIds];
    }

    getSuiteElements() {
        return this.suitesListRef.el
            ? [...this.suitesListRef.el.getElementsByClassName(SUITE_CLASSNAME)]
            : [];
    }

    /** @param {import("../core/job").Job} job */
    hasSuites(job) {
        return job.jobs.some((subJob) => subJob instanceof Suite);
    }

    onClick() {
        this.uiState.selectedSuiteId = null;
        this.uiState.resultsPage = 0;
    }

    /** @param {KeyboardEvent & { currentTarget: HTMLInputElement }} ev */
    onSearchInputKeydown(ev) {
        switch (ev.key) {
            case "ArrowDown": {
                if (ev.currentTarget.selectionEnd === ev.currentTarget.value.length) {
                    const suiteElements = this.getSuiteElements();
                    suiteElements[0]?.focus();
                }
            }
        }
    }

    /**
     * @param {KeyboardEvent & { currentTarget: HTMLButtonElement }} ev
     * @param {Suite} suite
     */
    onSuiteKeydown(ev, suite) {
        const { currentTarget, key } = ev;
        switch (key) {
            case "ArrowDown": {
                return this.selectElementAt(currentTarget, +1);
            }
            case "ArrowLeft": {
                if (this.state.unfoldedIds.has(suite.id)) {
                    return this.toggleItem(suite, false);
                } else {
                    return this.selectElementAt(currentTarget, -1);
                }
            }
            case "ArrowRight": {
                if (this.state.unfoldedIds.has(suite.id)) {
                    return this.selectElementAt(currentTarget, +1);
                } else {
                    return this.toggleItem(suite, true);
                }
            }
            case "ArrowUp": {
                return this.selectElementAt(currentTarget, -1);
            }
            case "Enter": {
                ev.preventDefault();
                actualLocation.href = createUrlFromId({ id: suite.id });
            }
        }
    }

    /**
     * @param {HTMLElement} target
     * @param {number} delta
     */
    selectElementAt(target, delta) {
        const suiteElements = this.getSuiteElements();
        const nextIndex = suiteElements.indexOf(target) + delta;
        if (nextIndex < 0) {
            this.searchInputRef.el?.focus();
        } else if (nextIndex >= suiteElements.length) {
            suiteElements[0].focus();
        } else {
            suiteElements[nextIndex].focus();
        }
    }

    /** @param {boolean} expanded */
    toggleExpand(expanded) {
        if (expanded) {
            this.state.unfoldedIds.clear();
        } else {
            for (const { id } of this.env.runner.suites.values()) {
                this.state.unfoldedIds.add(id);
            }
        }
    }

    toggleHideEmpty() {
        this.state.hideEmpty = !this.state.hideEmpty;
    }

    /**
     * @param {Suite} suite
     * @param {boolean} [forceAdd]
     */
    toggleItem(suite, forceAdd) {
        if (this.uiState.selectedSuiteId !== suite.id) {
            this.uiState.selectedSuiteId = suite.id;
            this.uiState.resultsPage = 0;

            if (this.state.unfoldedIds.has(suite.id)) {
                return;
            }
        }

        if (forceAdd ?? !this.state.unfoldedIds.has(suite.id)) {
            this.unfoldAndSelect(suite);
        } else {
            this.state.unfoldedIds.delete(suite.id);
        }
    }

    /** @param {Suite} suite */
    unfoldAndSelect(suite) {
        this.state.unfoldedIds.add(suite.id);

        while (suite.currentJobs.length === 1) {
            suite = suite.currentJobs[0];
            if (!(suite instanceof Suite)) {
                break;
            }
            this.state.unfoldedIds.add(suite.id);
            this.uiState.selectedSuiteId = suite.id;
            this.uiState.resultsPage = 0;
        }
    }
}

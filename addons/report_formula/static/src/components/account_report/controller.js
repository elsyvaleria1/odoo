/** @odoo-module native */

import { markRaw, markup } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { makeLogger } from "@web/core/debug/debug_logger";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";

const log = makeLogger("report.formula");

export class AccountReportController {
    constructor(action) {
        this.action = action;
        this.actionService = useService("action");
        this.dialog = useService("dialog");
        this.orm = useService("orm");
        this.ui = useService("ui");
        this.setup();
    }

    setup() {}

    async load(env) {
        this.env = env;
        log.lifecycle("load", () => ({
            action: this.action.id,
            context: this.action.context,
        }));
        this.reportOptionsMap = markRaw({});
        this.reportInformationMap = {};
        this.lastOpenedSectionByReport = {};
        this.loadingCallNumberByCacheKey = markRaw(
            new Proxy(
                {},
                {
                    get(target, name) {
                        return name in target ? target[name] : 0;
                    },
                    set(target, name, newValue) {
                        target[name] = newValue;
                        return true;
                    },
                },
            ),
        );
        this.actionReportId = this.action.context.report_id;
        const isOpeningReport = !this.action?.restored_from_breadcrumb;
        const mainReportOptions = await this.loadReportOptions(
            this.actionReportId,
            false,
            this.action.params?.ignore_session,
            isOpeningReport,
        );
        const cacheKey = this.getCacheKey(
            mainReportOptions["sections_source_id"],
            mainReportOptions["report_id"],
        );

        this.options = mainReportOptions;
        this.reportOptionsMap[cacheKey] = mainReportOptions;
        this.incrementCallNumber(cacheKey);
        this.options["loading_call_number"] =
            this.loadingCallNumberByCacheKey[cacheKey];
        this.cachedFilterOptions = this.options;
        this.saveSessionOptions(mainReportOptions);

        this.reportLoadingPromise = this.displayReport(mainReportOptions["report_id"]);
        this.preLoadClosedSections();
        this.onLoaded();
    }

    onLoaded() {}

    onReportDisplayed() {}

    onLinesUnfolded() {}

    getCacheKey(sectionsSourceId, reportId) {
        return `${sectionsSourceId}_${reportId}`;
    }

    incrementCallNumber(cacheKey = null) {
        if (!cacheKey) {
            cacheKey = this.getCacheKey(
                this.options["sections_source_id"],
                this.options["report_id"],
            );
        }
        this.loadingCallNumberByCacheKey[cacheKey] += 1;
    }

    async displayReport(reportId) {
        const endDisplay = log.perf(`displayReport ${reportId}`);
        const cacheKey = await this.loadReport(reportId);
        const options = await this.reportOptionsMap[cacheKey];
        if (this.serverCallResultCanBeSetAsActive(options, options, cacheKey)) {
            this.cachedFilterOptions = options;
        }

        const result = await this.loadInformationMap(options, cacheKey);
        endDisplay({ cacheKey, lines: this.lines?.length });
        return result;
    }

    serverCallResultCanBeSetAsActive(callResult, options, cacheKey) {
        return (
            callResult !== undefined &&
            this.loadingCallNumberByCacheKey[cacheKey] ===
                options["loading_call_number"] &&
            (Object.keys(this.lastOpenedSectionByReport).length === 0 ||
                this.lastOpenedSectionByReport[options["selected_variant_id"]] ===
                    options["selected_section_id"])
        );
    }

    async loadInformationMap(options, cacheKey) {
        this.loadingData = true;
        this.displayLoadingSymbolWhenTakingTooLong(
            options["report_id"] === this.options["report_id"],
        );

        const informationMap = await this.reportInformationMap[cacheKey];

        if (this.serverCallResultCanBeSetAsActive(informationMap, options, cacheKey)) {
            this.loadingData = false;
            this.options = options;
            this.data = informationMap;
            this.displayReportAsyncLoadingWarning();

            if (this.areLinesOrdered()) {
                await this.sortLines();
            }
            this.setLineVisibility(this.lines);
            this.onReportDisplayed();
            this.saveSessionOptions(this.options);
        }
    }

    async displayLoadingSymbolWhenTakingTooLong(longWaitBeforeLoadAnimation) {
        const waitingTime = longWaitBeforeLoadAnimation ? 500 : 200;
        await new Promise((resolve) => setTimeout(resolve, waitingTime));

        if (this.loadingData) {
            this.data = undefined;
        }
    }

    async displayReportAsyncLoadingWarning() {
        await new Promise((resolve) => setTimeout(resolve, 200));

        if (this.asyncDataLoading) {
            this.data.warnings["report_formula.report_info_being_loaded"] = {
                alert_type: "warning",
            };
        }
    }

    async reload(optionPath, newOptions) {
        const rootOptionKey = optionPath ? optionPath.split(".")[0] : "";
        log.pipeline("reload", () => ({
            optionPath,
            rootOptionKey,
            cached: Object.keys(this.reportOptionsMap).length,
        }));

        for (const [cacheKey, cachedOptionsPromise] of Object.entries(
            this.reportOptionsMap,
        )) {
            const cachedOptions = await cachedOptionsPromise;

            if (rootOptionKey === "" || Object.hasOwn(cachedOptions, rootOptionKey)) {
                delete this.reportOptionsMap[cacheKey];
                delete this.reportInformationMap[cacheKey];
            }
        }

        this.saveSessionOptions(newOptions);
        await this.displayReport(newOptions["report_id"]);

        this.preLoadClosedSections();
    }

    async preLoadClosedSections() {
        if (this.destroyed) {
            return;
        }

        let pendingSection = null;
        for (const section of this.options["sections"]) {
            const cacheKey = this.getCacheKey(
                this.options["sections_source_id"],
                section.id,
            );
            if (
                section.id !== this.options["report_id"] &&
                !this.reportInformationMap[cacheKey]
            ) {
                pendingSection = section;
                break;
            }
        }

        if (!pendingSection) {
            return;
        }

        const reportCacheKey = await this.loadReport(pendingSection.id, true);
        await this.reportInformationMap[reportCacheKey];

        if (this.destroyed) {
            return;
        }
        setTimeout(() => this.preLoadClosedSections(), 100);
    }

    async loadReport(reportId, preloading = false) {
        const options = await this.loadReportOptions(reportId, preloading, false);
        const reportToDisplayId = options["report_id"];

        const cacheKey = this.getCacheKey(
            options["sections_source_id"],
            reportToDisplayId,
        );
        log.pipeline("loadReport", () => ({
            reportId,
            reportToDisplayId,
            cacheKey,
            preloading,
            cached: Boolean(this.reportInformationMap[cacheKey]),
            readonly: options.readonly_query,
        }));
        if (!this.reportInformationMap[cacheKey]) {
            this.asyncDataLoading = true;
            this.reportInformationMap[cacheKey] = this.orm
                .cache({
                    type: "disk",
                    update: "always",
                    callback: (result, hasChanged) => {
                        this.asyncDataLoading = false;
                        delete this.data?.warnings?.[
                            "report_formula.report_info_being_loaded"
                        ];
                        if (hasChanged) {
                            this.reportInformationMap[cacheKey] =
                                Promise.resolve(result);
                            this.loadInformationMap(options, cacheKey);
                        }
                    },
                })
                .call(
                    "report.formula",
                    options.readonly_query
                        ? "get_report_information_readonly"
                        : "get_report_information",
                    [reportToDisplayId, options],
                    {
                        context: this.action.context,
                    },
                );
        }

        if (!preloading) {
            if (options["sections"].length) {
                this.lastOpenedSectionByReport[options["sections_source_id"]] =
                    options["selected_section_id"];
            }
        }

        return cacheKey;
    }

    async loadReportOptions(
        reportId,
        preloading = false,
        ignore_session = false,
        isOpeningReport = false,
    ) {
        const loadOptions =
            ignore_session || !this.hasSessionOptions()
                ? this.action.params?.options || {}
                : this.sessionOptions();
        const cacheKey = this.getCacheKey(
            loadOptions["sections_source_id"] || reportId,
            reportId,
        );

        if (!(cacheKey in this.loadingCallNumberByCacheKey)) {
            this.incrementCallNumber(cacheKey);
        }
        loadOptions["loading_call_number"] = this.loadingCallNumberByCacheKey[cacheKey];

        loadOptions["is_opening_report"] = isOpeningReport;

        if (!this.reportOptionsMap[cacheKey]) {
            if (preloading) {
                loadOptions["selected_section_id"] = reportId;
            } else {
                if (this.lastOpenedSectionByReport[reportId]) {
                    loadOptions["selected_section_id"] =
                        this.lastOpenedSectionByReport[reportId];
                }
            }

            this.reportOptionsMap[cacheKey] = this.orm.call(
                "report.formula",
                "get_options",
                [reportId, loadOptions],
                {
                    context: this.action.context,
                },
            );

            const reportOptions = await this.reportOptionsMap[cacheKey];

            const loadedOptionsCacheKey = this.getCacheKey(
                reportOptions["sections_source_id"],
                reportOptions["report_id"],
            );
            if (loadedOptionsCacheKey !== cacheKey) {
                delete this.reportOptionsMap[cacheKey];
                this.reportOptionsMap[loadedOptionsCacheKey] = reportOptions;

                this.loadingCallNumberByCacheKey[loadedOptionsCacheKey] = 1;
                delete this.loadingCallNumberByCacheKey[cacheKey];
                return reportOptions;
            }
        }

        return this.reportOptionsMap[cacheKey];
    }

    get buttons() {
        return this.cachedFilterOptions.buttons;
    }

    get caretOptions() {
        return this.data.caret_options;
    }

    get columnHeadersRenderData() {
        return this.data.column_headers_render_data;
    }

    get columnGroupsTotals() {
        return this.data.column_groups_totals;
    }

    get context() {
        return this.data.context;
    }

    get filters() {
        return this.cachedFilterOptions.filters;
    }

    get userGroups() {
        return this.options.user_groups;
    }

    get cachedUserGroups() {
        return this.cachedFilterOptions.user_groups;
    }

    get lines() {
        return this.data.lines;
    }

    get warnings() {
        return this.data.warnings;
    }

    get linesOrder() {
        return this.data.lines_order;
    }

    get report() {
        return this.data.report;
    }

    set columnGroupsTotals(value) {
        this.data.column_groups_totals = value;
    }

    set lines(value) {
        this.data.lines = value;
        this.setLineVisibility(this.lines);
    }

    set linesOrder(value) {
        this.data.lines_order = value;
    }

    get needsColumnPercentComparison() {
        return this.options.column_percent_comparison === "growth";
    }

    get needsAnalyticCoverageColumn() {
        return this.options.column_percent_comparison === "analytic_coverage";
    }

    get hasCustomSubheaders() {
        return this.columnHeadersRenderData.custom_subheaders.length > 0;
    }

    get hasDebugColumn() {
        return Boolean(this.options.show_debug_column);
    }

    async _updateOption(
        operationType,
        optionPath,
        optionValue = null,
        reloadUI = false,
    ) {
        const optionKeys = optionPath.split(".");
        log.logic("updateOption", () => ({
            operationType,
            optionPath,
            optionValue,
            reloadUI,
        }));

        let currentOptionKey;
        let option = this.cachedFilterOptions;

        while (optionKeys.length > 1) {
            currentOptionKey = optionKeys.shift();
            option = option[currentOptionKey];

            if (option === undefined) {
                throw new Error(
                    `Invalid option key in _updateOption(): ${currentOptionKey} (${optionPath})`,
                );
            }
        }

        switch (operationType) {
            case "update":
                option[optionKeys[0]] = optionValue;
                break;
            case "delete":
                delete option[optionKeys[0]];
                break;
            case "toggle":
                option[optionKeys[0]] = !option[optionKeys[0]];
                break;
            default:
                throw new Error(
                    `Invalid operation type in _updateOption(): ${operationType}`,
                );
        }

        if (reloadUI) {
            this.incrementCallNumber();
            await this.reload(optionPath, this.cachedFilterOptions);
        }
    }

    async updateOption(optionPath, optionValue, reloadUI = false) {
        await this._updateOption("update", optionPath, optionValue, reloadUI);
    }

    async deleteOption(optionPath, reloadUI = false) {
        await this._updateOption("delete", optionPath, null, reloadUI);
    }

    async toggleOption(optionPath, reloadUI = false) {
        await this._updateOption("toggle", optionPath, null, reloadUI);
    }

    async switchToSection(reportId) {
        log.logic("switchToSection", () => ({ reportId }));
        this.saveSessionOptions({
            ...this.cachedFilterOptions,
            selected_section_id: reportId,
        });
        this.displayReport(reportId);
    }

    sessionOptionsID() {
        return `report.formula:${this.actionReportId}:${user.defaultCompany.id}`;
    }

    hasSessionOptions() {
        return Boolean(browser.sessionStorage.getItem(this.sessionOptionsID()));
    }

    saveSessionOptions(options) {
        browser.sessionStorage.setItem(
            this.sessionOptionsID(),
            JSON.stringify(options),
        );
    }

    sessionOptions() {
        return JSON.parse(browser.sessionStorage.getItem(this.sessionOptionsID()));
    }

    lineHasDebugData(lineIndex) {
        return "debug_popup_data" in this.lines[lineIndex];
    }

    lineHasGrowthComparisonData(lineIndex) {
        return Boolean(this.lines[lineIndex].column_percent_comparison_data);
    }

    isLineAncestorOf(ancestorLineId, lineId) {
        return lineId.startsWith(`${ancestorLineId}|`);
    }

    isLineChildOf(childLineId, lineId) {
        return childLineId.startsWith(`${lineId}|`);
    }

    isLineRelatedTo(relatedLineId, lineId) {
        return (
            this.isLineAncestorOf(relatedLineId, lineId) ||
            this.isLineChildOf(relatedLineId, lineId)
        );
    }

    isNextLineChild(index, lineId) {
        return (
            index < this.lines.length && this.lines[index].id.startsWith(`${lineId}|`)
        );
    }

    isNextLineDirectChild(index, lineId) {
        return index < this.lines.length && this.lines[index].parent_id === lineId;
    }

    isTotalLine(lineIndex) {
        return this.lines[lineIndex].id.includes("|total~~");
    }

    isLoadMoreLine(lineIndex) {
        return this.lines[lineIndex].id.includes("|load_more~~");
    }

    isLoadedLine(lineIndex) {
        const lineID = this.lines[lineIndex].id;
        const nextLineIndex = lineIndex + 1;

        return (
            this.isNextLineChild(nextLineIndex, lineID) &&
            !this.isTotalLine(nextLineIndex) &&
            !this.isLoadMoreLine(nextLineIndex)
        );
    }

    async replaceLineWith(replaceIndex, newLines) {
        await this.insertLines(replaceIndex, 1, newLines);
    }

    async insertLinesAfter(insertIndex, newLines) {
        await this.insertLines(insertIndex + 1, 0, newLines);
    }

    async insertLines(lineIndex, deleteCount, newLines) {
        this.lines.splice(lineIndex, deleteCount, ...newLines);
    }

    updateLines(lineIds, key, value) {
        for (const lineId of lineIds) {
            const lineIndex = this.lines.findIndex((line) => line.id === lineId);
            this.lines.splice(lineIndex, 1, { ...this.lines[lineIndex], [key]: value });
        }
    }

    async unfoldLoadedLine(lineIndex) {
        const lineId = this.lines[lineIndex].id;
        let nextLineIndex = lineIndex + 1;

        while (this.isNextLineChild(nextLineIndex, lineId)) {
            if (this.isNextLineDirectChild(nextLineIndex, lineId)) {
                const nextLine = this.lines[nextLineIndex];
                nextLine.visible = true;
                if (
                    !nextLine.unfoldable &&
                    this.isNextLineChild(nextLineIndex + 1, nextLine.id)
                ) {
                    await this.unfoldLine(nextLineIndex);
                }
            }
            nextLineIndex += 1;
        }
        return nextLineIndex;
    }

    async unfoldNewLine(lineIndex) {
        const applyNewLines = (newLines) => {
            if (this.areLinesOrdered()) {
                this.updateLinesOrderIndexes(lineIndex, newLines, false);
            }

            this.insertLinesAfter(lineIndex, newLines);

            const totalIndex = lineIndex + newLines.length + 1;

            if (
                this.filters.show_totals &&
                this.lines[totalIndex] &&
                this.isTotalLine(totalIndex)
            ) {
                this.lines[totalIndex].visible = true;
            }

            this.options.unfolded_lines.push(
                ...newLines.filter((line) => line.unfolded).map(({ id }) => id),
            );

            this.saveSessionOptions(this.options);
            return totalIndex;
        };

        const options = await this.options;
        const newLines = await this.orm
            .cache({
                type: "disk",
                update: "always",
                callback: (result, hasChanged) => {
                    if (hasChanged) {
                        let nextIndex = lineIndex + 1;
                        while (
                            this.isNextLineChild(nextIndex, this.lines[lineIndex].id)
                        ) {
                            nextIndex += 1;
                        }
                        if (this.isTotalLine(nextIndex - 1)) {
                            nextIndex -= 1;
                        }
                        const numberOfChildren = nextIndex - lineIndex - 1;
                        this.lines.splice(lineIndex + 1, numberOfChildren);

                        const lastLineIndex = applyNewLines(result);
                        this.onLinesUnfolded(lineIndex + 1, lastLineIndex);
                        this.setLineVisibility(
                            this.lines.slice(lineIndex + 1, lastLineIndex),
                        );
                    }
                },
            })
            .call(
                "report.formula",
                options.readonly_query
                    ? "get_expanded_lines_readonly"
                    : "get_expanded_lines",
                [
                    this.options["report_id"],
                    this.options,
                    this.lines[lineIndex].id,
                    this.lines[lineIndex].groupby,
                    this.lines[lineIndex].expand_function,
                    this.lines[lineIndex].progress,
                    0,
                    this.lines[lineIndex].horizontal_split_side,
                ],
            );

        const totalIndex = applyNewLines(newLines);

        return totalIndex;
    }

    /**
     * @param {Integer} lineIndex
     * @param {Array} newLines
     * @param {Boolean} replaceLine
     */
    updateLinesOrderIndexes(lineIndex, newLines, replaceLine) {
        let unfoldedLineIndex;
        const offset = replaceLine ? 0 : 1;
        for (const [lineOrderIndex, lineOrderValue] of Object.entries(
            this.linesOrder,
        )) {
            if (lineOrderValue > lineIndex) {
                this.linesOrder[lineOrderIndex] += newLines.length - replaceLine;
            }
            if (lineOrderValue === lineIndex) {
                unfoldedLineIndex = parseInt(lineOrderIndex);
            }
        }

        const arrayOfNewIndex = Array.from(
            { length: newLines.length },
            (dummy, index) => this.linesOrder[unfoldedLineIndex] + index + offset,
        );
        this.linesOrder.splice(
            unfoldedLineIndex + offset,
            replaceLine,
            ...arrayOfNewIndex,
        );
    }

    async unfoldLine(lineIndex) {
        const targetLine = this.lines[lineIndex];
        log.logic("unfoldLine", () => ({
            lineIndex,
            id: targetLine?.id,
            loaded: this.isLoadedLine(lineIndex),
        }));
        let lastLineIndex = lineIndex + 1;

        const isLoadedLine = this.isLoadedLine(lineIndex);
        if (isLoadedLine) {
            lastLineIndex = await this.unfoldLoadedLine(lineIndex);
        } else if (targetLine.expand_function) {
            lastLineIndex = await this.unfoldNewLine(lineIndex);
            this.onLinesUnfolded(lineIndex + 1, lastLineIndex);
        }

        this.setLineVisibility(this.lines.slice(lineIndex + 1, lastLineIndex));
        targetLine.unfolded = true;

        if (!this.options.unfolded_lines.includes(targetLine.id)) {
            this.options.unfolded_lines.push(targetLine.id);
        }

        this.saveSessionOptions(this.options);
    }

    foldLine(lineIndex) {
        const targetLine = this.lines[lineIndex];

        const foldedLinesIDs = new Set([targetLine.id]);
        let nextLineIndex = lineIndex + 1;

        while (this.isNextLineChild(nextLineIndex, targetLine.id)) {
            this.lines[nextLineIndex].unfolded = false;
            this.lines[nextLineIndex].visible = false;

            foldedLinesIDs.add(this.lines[nextLineIndex].id);

            nextLineIndex += 1;
        }

        targetLine.unfolded = false;

        this.options.unfolded_lines = this.options.unfolded_lines.filter(
            (unfoldedLineID) => !foldedLinesIDs.has(unfoldedLineID),
        );

        this.saveSessionOptions(this.options);
    }

    linesCurrentOrderByColumn(columnIndex) {
        if (this.areLinesOrderedByColumn(columnIndex)) {
            return this.options.order_column.direction;
        }

        return "default";
    }

    areLinesOrdered() {
        return this.linesOrder != null && this.options.order_column != null;
    }

    areLinesOrderedByColumn(columnIndex) {
        return (
            this.areLinesOrdered() &&
            this.options.order_column.expression_label ===
                this.options.columns[columnIndex].expression_label
        );
    }

    async sortLinesByColumnAsc(columnIndex) {
        this.options.order_column = {
            expression_label: this.options.columns[columnIndex].expression_label,
            direction: "ASC",
        };

        await this.sortLines();
        this.saveSessionOptions(this.options);
    }

    async sortLinesByColumnDesc(columnIndex) {
        this.options.order_column = {
            expression_label: this.options.columns[columnIndex].expression_label,
            direction: "DESC",
        };

        await this.sortLines();
        this.saveSessionOptions(this.options);
    }

    sortLinesByDefault() {
        delete this.options.order_column;
        delete this.data.lines_order;

        this.saveSessionOptions(this.options);
    }

    async sortLines() {
        this.linesOrder = await this.orm.call(
            "report.formula",
            "sort_lines",
            [this.lines, this.options, true],
            {
                context: this.action.context,
            },
        );
    }

    /** @param {Array} linesToAssign */
    setLineVisibility(linesToAssign) {
        const needHidingChildren = new Set();

        linesToAssign.forEach((line) => {
            line.visible = !needHidingChildren.has(line.parent_id);

            if (!line.visible || line.unfoldable & !line.unfolded) {
                needHidingChildren.add(line.id);
            }
        });

        if (this.options.hide_0_lines) {
            this.hideZeroLines(linesToAssign);
        }
    }

    /** @param {Array} lines */
    hideZeroLines(lines) {
        const hasVisibleChildren = new Set();
        const reversed_lines = [...lines].reverse();

        const number_figure_types = ["integer", "float", "monetary", "percentage"];
        reversed_lines.forEach((line) => {
            const isLoadMoreLine = line.id.includes("|load_more~~");
            const isZero =
                !isLoadMoreLine &&
                line.columns.every(
                    (column) =>
                        Object.keys(column).length &&
                        (!number_figure_types.includes(column.figure_type) ||
                            column.is_zero),
                );

            if (!hasVisibleChildren.has(line.id) && isZero) {
                line.visible = false;
            }

            if (line.parent_id && line.visible) {
                hasVisibleChildren.add(line.parent_id);
            }
        });
    }

    buttonAction(ev, button) {
        log.logic("buttonAction", () => ({
            name: button.name,
            action: button.action,
            param: button.action_param,
        }));
        this.reportAction(
            ev,
            button.error_action || button.action,
            button.action_param,
            true,
        );
    }

    async reportAction(
        ev,
        action,
        actionParam = null,
        callOnSectionsSource = false,
        actionContext = null,
    ) {
        ev?.preventDefault();
        ev?.stopPropagation();

        let actionOptions = this.cachedFilterOptions;
        if (callOnSectionsSource) {
            const allUnfoldedLines = this.cachedFilterOptions.sections.length
                ? []
                : [...this.cachedFilterOptions["unfolded_lines"]];

            for (const sectionData of this.cachedFilterOptions["sections"]) {
                const cacheKey = this.getCacheKey(
                    this.cachedFilterOptions["sections_source_id"],
                    sectionData["id"],
                );
                const sectionOptions = await this.reportOptionsMap[cacheKey];
                if (sectionOptions) {
                    allUnfoldedLines.push(...sectionOptions["unfolded_lines"]);
                }
            }

            actionOptions = {
                ...this.cachedFilterOptions,
                unfolded_lines: allUnfoldedLines,
            };
        }

        const dispatchReportAction = await this.orm.call(
            "report.formula",
            "dispatch_report_action",
            [
                this.cachedFilterOptions["report_id"],
                actionOptions,
                action,
                actionParam,
                callOnSectionsSource,
            ],
            {
                context: Object.assign({}, this.action.context, actionContext),
            },
        );
        if (dispatchReportAction?.help) {
            dispatchReportAction.help = markup(dispatchReportAction.help);
        }

        return dispatchReportAction
            ? this.actionService.doAction(dispatchReportAction)
            : null;
    }
}

/** @odoo-module native */
import { getActiveHotkey } from "@web/core/browser/hotkeys";
import { registry } from "@web/core/registry";
import { redirect } from "@web/core/utils/urls";
import { Interaction } from "@web/public/interaction";

export class SurveyResult extends Interaction {
    static selector = ".o_survey_result";

    dynamicContent = {
        ".o_survey_results_topbar_clear_filters": {
            "t-on-click": this.onClearFiltersClick,
        },
        ".o_survey_results_data_tab:not(.active)": { "t-on-click": this.updateContent },
        ".filter-add-answer": { "t-on-click": this.onFilterAddAnswerClick },
        "i.filter-remove-answer": { "t-on-click": this.onFilterRemoveAnswerClick },
        "a.filter-finished-or-not": { "t-on-click": this.onFilterFinishedOrNotClick },
        "a.filter-finished": { "t-on-click": this.onFilterFinishedClick },
        "a.filter-failed": { "t-on-click": this.onFilterFailedClick },
        "a.filter-passed": { "t-on-click": this.onFilterPassedClick },
        "a.filter-passed-and-failed": {
            "t-on-click": this.onFilterPassedAndFailedClick,
        },
        ".o_survey_answer_image": { "t-on-click.prevent": this.onAnswerImageClick },
        ".o_survey_results_print": { "t-on-click": this.onPrintResultsClick },
        _document: {
            "t-on-keydown": this.onKeydown,
        },
    };

    /** @param {Event} ev */
    onFilterAddAnswerClick(ev) {
        const params = new URLSearchParams(window.location.search);
        params.set(
            "filters",
            this.prepareAnswersFilters(params.get("filters"), "add", ev),
        );
        redirect(window.location.pathname + "?" + params.toString());
    }

    /** @param {Event} ev */
    onFilterRemoveAnswerClick(ev) {
        const params = new URLSearchParams(window.location.search);
        const filters = this.prepareAnswersFilters(params.get("filters"), "remove", ev);
        if (filters) {
            params.set("filters", filters);
        } else {
            params.delete("filters");
        }
        redirect(window.location.pathname + "?" + params.toString());
    }

    onClearFiltersClick() {
        const params = new URLSearchParams(window.location.search);
        params.delete("filters");
        params.delete("finished");
        params.delete("failed");
        params.delete("passed");
        redirect(window.location.pathname + "?" + params.toString());
    }

    onFilterFinishedOrNotClick() {
        const params = new URLSearchParams(window.location.search);
        params.delete("finished");
        redirect(window.location.pathname + "?" + params.toString());
    }

    onFilterFinishedClick() {
        const params = new URLSearchParams(window.location.search);
        params.set("finished", "true");
        redirect(window.location.pathname + "?" + params.toString());
    }

    onFilterFailedClick() {
        const params = new URLSearchParams(window.location.search);
        params.set("failed", "true");
        params.delete("passed");
        redirect(window.location.pathname + "?" + params.toString());
    }

    onFilterPassedClick() {
        const params = new URLSearchParams(window.location.search);
        params.set("passed", "true");
        params.delete("failed");
        redirect(window.location.pathname + "?" + params.toString());
    }

    onFilterPassedAndFailedClick() {
        const params = new URLSearchParams(window.location.search);
        params.delete("failed");
        params.delete("passed");
        redirect(window.location.pathname + "?" + params.toString());
    }

    /** @param {Event} ev */
    onAnswerImageClick(ev) {
        this.renderAt(
            "survey.survey_image_zoomer",
            { sourceImage: ev.currentTarget.src },
            document.body,
        );
    }

    onPrintResultsClick() {
        for (const paginatorEl of document.querySelectorAll(
            ".survey_table_with_pagination",
        )) {
            paginatorEl.dispatchEvent(new Event("save_state_and_show_all"));
        }
        window.print();
        for (const paginatorEl of document.querySelectorAll(
            ".survey_table_with_pagination",
        )) {
            paginatorEl.dispatchEvent(new Event("restore_state"));
        }
    }

    /** @param {Event} ev */
    onKeydown(ev) {
        if (getActiveHotkey(ev) === "control+p") {
            ev.preventDefault();
            ev.stopImmediatePropagation();
            this.onPrintResultsClick();
        }
    }

    /**
     * @param {String} filters
     * @param {"add" | "remove"} operation
     * @param {Event} ev
     * @returns {String}
     */
    prepareAnswersFilters(filters, operation, ev) {
        const cellDataset = ev.currentTarget.dataset;
        const filter = `${cellDataset.modelShortKey},${cellDataset.rowId || 0},${cellDataset.recordId}`;

        if (operation === "add") {
            if (filters) {
                filters = !filters.split("|").includes(filter)
                    ? `${filters}|${filter}`
                    : filters;
            } else {
                filters = filter;
            }
        } else if (operation === "remove") {
            filters = filters
                .split("|")
                .filter((filterItem) => filterItem !== filter)
                .join("|");
        } else {
            throw new Error(
                '`operation` parameter for `prepareAnswersFilters` must be either "add" or "remove".',
            );
        }
        return filters;
    }
}

registry.category("public.interactions").add("survey.SurveyResult", SurveyResult);

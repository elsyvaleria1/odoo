/** @odoo-module native */
import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/translation";
import { KeepLast, Race } from "@web/core/utils/concurrency";
import { Model } from "@web/model/model";
import { computeReportMeasures, processMeasure } from "@web/views/view_measurements";

export const MODES = ["retention", "churn"];
export const TIMELINES = ["forward", "backward"];
export const INTERVALS = {
    day: _t("Day"),
    week: _t("Week"),
    month: _t("Month"),
    quarter: _t("Quarter"),
    year: _t("Year"),
};

/**
 * @typedef {import("@web/search/search_model").SearchParams} SearchParams
 */

export class CohortModel extends Model {
    /**
     * @override
     */
    setup(params) {
        // concurrency management
        this.keepLast = new KeepLast();
        this.race = new Race();
        const _load = this._load.bind(this);
        this._load = (...args) => this.race.add(_load(...args));

        // a copy: the view's modelParams are its props, and a reactive model
        // writing into them would re-render the view and reload
        this.metaData = { ...params };
        this.data = null;
        this.searchParams = null;
        this.intervals = INTERVALS;

        const activeInterval =
            browser.localStorage.getItem(this.storageKey) || params.interval;
        if (Object.keys(this.intervals).includes(activeInterval)) {
            this.metaData.interval = activeInterval;
        }
    }

    /**
     * @param {SearchParams} searchParams
     */
    load(searchParams) {
        const { context, domain } = searchParams;
        this.searchParams = { context, domain };
        const { cohort_interval, cohort_measure } = searchParams.context;
        const metaData = { ...this.metaData };
        metaData.interval = cohort_interval || metaData.interval;
        metaData.measure = processMeasure(cohort_measure) || metaData.measure;
        metaData.measures = computeReportMeasures(
            metaData.fields,
            metaData.fieldAttrs,
            [metaData.measure],
            { sumAggregatorOnly: true },
        );
        return this._load(metaData);
    }

    get storageKey() {
        return `scaleOf-viewId-${this.viewContext.config.viewId}`;
    }

    /**
     * @override
     */
    hasData() {
        return this.data.rows.length > 0;
    }

    /**
     * @param {Object} params
     */
    async updateMetaData(params) {
        const metaData = { ...this.metaData, ...params };
        browser.localStorage.setItem(this.storageKey, metaData.interval);
        await this._load(metaData);
        this.notify();
    }

    //--------------------------------------------------------------------------
    // Protected
    //--------------------------------------------------------------------------

    /**
     * Publishes metaData together with the data fetched for it, so a view
     * never shows a measure or an interval over the previous one's rows.
     *
     * @protected
     * @param {Object} metaData
     */
    async _load(metaData) {
        const data = await this.keepLast.add(this._fetchData(metaData));
        for (const row of data.rows) {
            row.columns = row.columns.filter((col) => col.percentage !== "");
        }
        this.data = data;
        this.metaData = metaData;
    }

    /**
     * @protected
     * @param {Object} metaData
     */
    async _fetchData(metaData) {
        const { context, domain } = this.searchParams;
        return this.orm.call(metaData.resModel, "get_cohort_data", [], {
            date_start: metaData.dateStart,
            date_stop: metaData.dateStop,
            measure: metaData.measure,
            interval: metaData.interval,
            domain,
            mode: metaData.mode,
            timeline: metaData.timeline,
            context,
        });
    }
}

// @ts-check
/** @odoo-module native */
import { makeLogger } from "@web/core/debug/debug_logger";
import { RelationalModel } from "@web/model/relational_model";

const log = makeLogger("mail.activity.view");
export class ActivityModel extends RelationalModel {
    static DEFAULT_LIMIT = 100;

    /** @param {Object} [params={}] */
    async load(params = {}) {
        this.originalDomain = params.domain ? [...params.domain] : [];
        params.domain = [
            ...(params.domain || []),
            ["activity_ids.active", "in", [true, false]],
        ];
        if (params && "groupBy" in params) {
            params.groupBy = [];
        }
        delete params.limit;
        const endLoad = log.perf("load");
        await super.load(params);
        endLoad({
            resModel: this.config.resModel,
            records: this.root?.records?.length,
        });
    }

    /**
     * The rows come from the activity data and the pager from the root: the
     * activity data is fetched with the root's and applied when the root is,
     * so no render shows the records of one page with the rows of another.
     *
     * @override
     * @param {import("@web/model/relational_model/relational_model").RelationalModelConfig} config
     * @param {Object} [cache]
     * @param {AbortSignal} [signal]
     */
    async _loadData(config, cache, signal) {
        if (!config.isRoot) {
            return super._loadData(config, cache, signal);
        }
        const [activityData, data] = await Promise.all([
            this._fetchActivityData(config),
            super._loadData(config, cache, signal),
        ]);
        // a page past the end reloads from offset 0, with its own activity data
        data.activityData ??= activityData;
        return data;
    }

    /**
     * @override
     * @param {import("@web/model/relational_model/relational_model").RelationalModelConfig} config
     * @param {Object} data
     * @param {Object} [options]
     */
    _createRoot(config, data, options) {
        this._applyActivityData(data);
        return super._createRoot(config, data, options);
    }

    /**
     * @override
     * @param {import("@web/model/relational_model/relational_model").RelationalModelConfig} config
     * @param {Object} patch
     * @param {{commit?: (data: Record<string, unknown>) => unknown}} [options]
     */
    async reloadWithConfig(config, patch, options = {}) {
        if (!config.isRoot) {
            return super.reloadWithConfig(config, patch, options);
        }
        return super.reloadWithConfig(config, patch, {
            ...options,
            commit: (data) => {
                this._applyActivityData(data);
                return options.commit?.(data);
            },
        });
    }

    /** @param {{activityData?: Object}} [data] */
    _applyActivityData(data) {
        if (data?.activityData) {
            this.activityData = data.activityData;
        }
    }

    /**
     * @param {import("@web/model/relational_model/relational_model").RelationalModelConfig} config
     */
    async _fetchActivityData(config) {
        const endFetch = log.perf("get_activity_data");
        const activityData = await this.orm.call(
            "mail.activity",
            "get_activity_data",
            [],
            {
                res_model: config.resModel,
                context: config.context,
                domain: config.domain,
                limit: config.limit || this.initialLimit,
                offset: config.offset || 0,
                fetch_done: false,
            },
        );
        endFetch({
            activityTypes: activityData?.activity_types?.length,
            records: Object.keys(activityData?.grouped_activities ?? {}).length,
        });
        return activityData;
    }
}

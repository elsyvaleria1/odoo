// @ts-check
/** @odoo-module native */

import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { formatFloat } from "@web/core/utils/format/numbers";
import { useService } from "@web/core/utils/hooks";

import { homeTileRegistry } from "./home_tiles.js";

const log = makeLogger("web.home_tiles.metric");

const SPARK_WIDTH = 100;
const SPARK_HEIGHT = 24;

/**
 * @typedef {{ name: string, label: string }} MetricMeasure
 * @typedef {{ id: number, name: string, model_name: string, measures: MetricMeasure[] }} MetricChoice
 */

export class MetricTile extends Component {
    static template = "web.MetricTile";
    static props = {
        data: t.object({ configured: t.boolean() }),
        size: t.string(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
    }

    get data() {
        return /** @type {any} */ (this.props.data);
    }

    get value() {
        return formatFloat(this.data.value, { humanReadable: true, decimals: 1 });
    }

    get sparkPoints() {
        /** @type {number[]} */
        const spark = this.data.spark;
        const low = Math.min(...spark, 0);
        const range = Math.max(...spark, 0) - low;
        const step = SPARK_WIDTH / Math.max(spark.length - 1, 1);
        return spark
            .map((value, index) => {
                const y = range
                    ? SPARK_HEIGHT - ((value - low) / range) * SPARK_HEIGHT
                    : SPARK_HEIGHT;
                return `${Math.round(index * step)},${Math.round(y)}`;
            })
            .join(" ");
    }

    open() {
        return this.action.doAction({
            type: "ir.actions.act_window",
            name: this.data.name,
            res_model: this.data.model,
            domain: this.data.domain,
            views: [
                [false, "list"],
                [false, "form"],
            ],
        });
    }
}

export class MetricSettings extends Component {
    static template = "web.MetricSettings";
    static props = {
        settings: t.object(),
        onSave: t.function(),
        onCancel: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        this.state = proxy({
            /** @type {MetricChoice[]} */
            choices: [],
            /** @type {number | null} */
            filterId: this.props.settings.filter_id ?? null,
            measure: this.props.settings.measure ?? "__count",
            failed: false,
        });
        onWillStart(async () => {
            try {
                this.state.choices = await this.orm.silent.call(
                    "home.tile",
                    "get_metric_choices",
                    [],
                );
            } catch (error) {
                log.logic("choices_failed", () => ({ error: String(error) }));
                this.state.failed = true;
                return;
            }
            // the saved favourite may be gone or out of reach
            if (!this.choice) {
                this.state.filterId = this.state.choices[0]?.id ?? null;
            }
            this.keepMeasure();
        });
    }

    get choice() {
        return this.state.choices.find((choice) => choice.id === this.state.filterId);
    }

    /** @param {Event & { target: HTMLSelectElement }} ev */
    onFilterChange(ev) {
        this.state.filterId = Number(ev.target.value);
        this.keepMeasure();
    }

    keepMeasure() {
        if (
            !this.choice?.measures.some(
                (measure) => measure.name === this.state.measure,
            )
        ) {
            this.state.measure = "__count";
        }
    }

    /** @param {Event & { target: HTMLSelectElement }} ev */
    onMeasureChange(ev) {
        this.state.measure = ev.target.value;
    }

    save() {
        this.props.onSave({
            filter_id: this.state.filterId,
            measure: this.state.measure,
        });
    }
}

homeTileRegistry.add("metric", {
    Component: MetricTile,
    Settings: MetricSettings,
    title: (/** @type {any} */ data) => (data.configured ? data.name : null),
});

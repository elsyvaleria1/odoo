/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { formatPercentage } from "@web/core/formatters";
import { download } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { ReportViewMeasures } from "@web/views/view_components";
import { ViewScaleSelector } from "@web/views/view_components";

const formatters = registry.category("formatters");

export class CohortRenderer extends Component {
    static components = {
        Dropdown,
        DropdownItem,
        ViewScaleSelector,
        ReportViewMeasures,
    };
    static template = "web_cohort.CohortRenderer";
    static props = { class: t.any(), model: t.any(), onRowClicked: t.any() };
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        this.model = this.props.model;
    }

    range(n) {
        return Array.from({ length: n }, (_, i) => i);
    }

    getFormattedValue(value) {
        const fieldName = this.model.metaData.measure;
        const field = this.model.metaData.measures[fieldName];
        let formatType = this.model.metaData.widgets[fieldName];
        if (!formatType) {
            const fieldType = field.type;
            formatType = ["many2one", "reference"].includes(fieldType)
                ? "integer"
                : fieldType;
        }
        const formatter = formatters.get(formatType);
        return formatter(value, field);
    }

    formatPercentage(value) {
        return formatPercentage(value, { digits: [false, 1] });
    }

    getCellTitle(period, measure, count) {
        return _t("Period: %(period)s\n%(measure)s: %(count)s", {
            period,
            measure,
            count,
        });
    }

    get scales() {
        return Object.fromEntries(
            Object.entries(this.model.intervals).map(([s, d]) => [
                s,
                { description: d },
            ]),
        );
    }

    /**
     * @param {String} scale
     */
    setScale(scale) {
        this.model.updateMetaData({
            interval: scale,
        });
    }

    /**
     * @param {Object} param0
     * @param {string} param0.measure
     */
    onMeasureSelected({ measure }) {
        this.model.updateMetaData({ measure });
    }

    /**
     * Export cohort data in Excel file
     */
    async downloadExcel() {
        const {
            title,
            resModel,
            interval,
            measure,
            measures,
            dateStartString,
            dateStopString,
            timeline,
        } = this.model.metaData;
        const data = {
            title: title,
            model: resModel,
            interval_string: this.model.intervals[interval].toString(), // intervals are lazy-translated
            measure_string: measures[measure].string,
            date_start_string: dateStartString,
            date_stop_string: dateStopString,
            timeline: timeline,
            report: this.model.data,
        };
        this.ui.block();
        try {
            await download({
                url: "/web/cohort/export",
                data: {
                    data: new Blob([JSON.stringify(data)], {
                        type: "application/json",
                    }),
                },
            });
        } finally {
            this.ui.unblock();
        }
    }
}

/** @odoo-module native */
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { useDateTimePicker } from "@web/components/datetime";
import { getPaletteColor, PLC_CHART_COLORS } from "@web/core/colors/colors";
import { serializeDate, toISODate } from "@web/core/l10n/dates";
import { Chart, loadChartJS } from "@web/core/lib/chartjs";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { usePopover } from "@web/ui/popover";
import { standardActionServiceProps } from "@web/webclient/actions";

import { PlcDatePopover } from "./plc_date_popover.js";

class PlcDashboard extends Component {
    static template = "device_machines.PlcDashboard";
    static props = { ...standardActionServiceProps };
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        this.chartRef = elementRef();
        this.hourlyRef = elementRef();
        this.charts = {};
        this.state = proxy({ loading: true, data: {}, period: "window", days: false });
        this.productiveDays = new Set();
        this.periods = [
            { key: "day", label: _t("Today") },
            { key: "week", label: _t("This week") },
            { key: "month", label: _t("This month") },
            { key: "window", label: _t("Recent") },
        ];

        const state = this.state;
        const component = this;
        this.endDateRef = elementRef();
        this.startDateRef = elementRef();
        this.dayPickerBtnRef = elementRef();
        this.dayPicker = useDateTimePicker({
            endDateRef: this.endDateRef,
            startDateRef: this.startDateRef,
            target: this.dayPickerBtnRef,
            createPopover: (_component, options) => usePopover(PlcDatePopover, options),
            onApply: (date) => this.onDayChange(date),
            get pickerProps() {
                return {
                    type: "date",
                    range: true,
                    value: state.days || [false, false],
                    dayCellClass: (date) =>
                        component.productiveDays.has(toISODate(date))
                            ? "plc_day_produced"
                            : "",
                };
            },
        });

        this.workorderId = this.props.action?.context?.plc_workorder_id || null;

        onWillStart(async () => {
            await loadChartJS();
            await this.load();
        });

        useLayoutEffect(
            () => {
                this.renderChart("chart", this.chartRef, this.state.data.chart);
                this.renderChart("hourly", this.hourlyRef, this.state.data.hourly);
                return () => this.destroyCharts();
            },
            () => [this.state.data.chart, this.state.data.hourly],
        );
    }

    async load() {
        this.state.loading = true;
        const payload = await this.orm.call(
            "device.machine.workorder",
            "get_dashboard_data",
            [this.workorderId, this.state.period, ...this.serializedDays],
        );
        this.productiveDays = new Set(payload.productive_days || []);
        this.state.data = payload;
        this.state.loading = false;
    }

    async onRefresh() {
        await this.load();
    }

    async onPeriodChange(period) {
        if (period === this.state.period && !this.state.days) {
            return;
        }
        this.state.period = period;
        this.state.days = false;
        await this.load();
    }

    get serializedDays() {
        const [from, to] = this.state.days || [];
        return [from ? serializeDate(from) : null, to ? serializeDate(to) : null];
    }

    async onDayChange(value) {
        const [from, to] = Array.isArray(value) ? value : [value, false];
        this.state.days = from ? [from, to || false] : false;
        await this.load();
    }

    destroyCharts() {
        for (const chart of Object.values(this.charts)) {
            chart?.destroy();
        }
        this.charts = {};
    }

    renderChart(key, ref, chart) {
        if (!ref.el || !chart || !chart.labels?.length) {
            return;
        }
        this.charts[key] = new Chart(ref.el, {
            type: "bar",
            data: {
                labels: chart.labels,
                datasets: chart.datasets.map((ds, i) => ({
                    label: ds.label,
                    data: ds.data,
                    backgroundColor: getPaletteColor(i, PLC_CHART_COLORS),
                    borderRadius: 6,
                    maxBarThickness: 56,
                })),
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "bottom" } },
                scales: {
                    x: { grid: { display: false } },
                    y: { beginAtZero: true, ticks: { precision: 0 } },
                },
            },
        });
    }
}

registry.category("actions").add("plc_dashboard", PlcDashboard);

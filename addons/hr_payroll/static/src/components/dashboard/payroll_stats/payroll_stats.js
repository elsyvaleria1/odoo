/** @odoo-module native */
import { Component, onWillStart, onWillUnmount, proxy, t, useProps } from "@odoo/owl";
import { useColorSchemeEffect } from "@web/core/color_scheme";
import { getColor, getCustomColor } from "@web/core/colors/colors";
import { loadChartJS } from "@web/core/lib/chartjs";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

const graphGridColor = () => getCustomColor("#d8dadd", "#3C3E4B");
const graphLabelColor = () => getCustomColor("#111827", "#E4E4E4");
export class PayrollDashboardStats extends Component {
    static template = "hr_payroll.DashboardStats";
    static props = {
        title: t.string(),
        help: t.string().optional(),
        id: t.string().optional(),
        actions: t.array(),
        type: t.string(),
        data: t.object(),
        is_sample: t.boolean(),
        label: t.string(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.actionService = useService("action");
        this.canvasRef = elementRef();
        this.state = proxy({ monthly: true });
        onWillStart(async () => {
            const Chart = await loadChartJS();
            this.Chart = Chart;
        });
        useLayoutEffect(() => this.renderChart());
        useColorSchemeEffect(() => this.renderChart());
        onWillUnmount(() => {
            if (this.chart) {
                this.chart.destroy();
            }
        });
    }

    /**
     * @returns {string}
     */
    get tooltipInfo() {
        return JSON.stringify({
            help: this.props.help,
        });
    }

    toggle() {
        this.state.monthly = !this.state.monthly;
    }

    /**
     * @returns {object} The current chart data to be used depending on the state
     */
    get graphData() {
        return this.props.data[this.state.monthly ? "monthly" : "yearly"];
    }

    /**
     * Creates and binds the chart on `canvasRef`.
     */
    renderChart() {
        if (this.chart) {
            this.chart.destroy();
        }
        const ctx = this.canvasRef.el.getContext("2d");
        this.chart = new this.Chart(ctx, this.getChartConfig());
    }

    /**
     * @returns {object} Chart config for the current data
     */
    getChartConfig() {
        const type = this.props.type;
        if (type === "line") {
            return this.getLineChartConfig();
        } else if (type === "bar") {
            return this.getBarChartConfig();
        } else if (type === "stacked_bar") {
            return this.getStackedBarChartConfig();
        }
        return {};
    }

    /**
     * @returns {object} Chart config of type 'line'
     */
    getLineChartConfig() {
        const data = this.graphData;
        const labels = data.map(function (pt) {
            return pt.x;
        });
        const borderColor = this.props.is_sample ? "#dddddd" : "#875a7b";
        const backgroundColor = this.props.is_sample ? "#ebebeb" : "#dcd0d9";
        return {
            type: "line",
            data: {
                labels: labels,
                datasets: [
                    {
                        data: data,
                        fill: "start",
                        label: this.props.label,
                        backgroundColor: backgroundColor,
                        borderColor: borderColor,
                        borderWidth: 2,
                    },
                ],
            },
            options: {
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        intersect: false,
                        position: "nearest",
                        caretSize: 0,
                    },
                },
                scales: {
                    y: {
                        display: false,
                        beginAtZero: true,
                    },
                    x: {
                        display: false,
                    },
                },
                maintainAspectRatio: false,
                elements: {
                    line: {
                        tension: 0.000001,
                    },
                },
            },
        };
    }

    /**
     * @returns {object} Chart config of type 'bar'
     */
    getBarChartConfig() {
        const data = [];
        const labels = [];
        const backgroundColors = [];
        const color19 = getColor(1, "odoo");
        this.graphData.forEach((pt) => {
            data.push(pt.value);
            labels.push(pt.label);
            let color;
            if (this.props.is_sample) {
                color = "#ebebeb";
            } else if (pt.type === "past") {
                color = "#ccbdc8";
            } else if (pt.type === "future") {
                color = "#a5d8d7";
            } else {
                color = color19;
            }
            backgroundColors.push(color);
        });

        return {
            type: "bar",
            data: {
                labels: labels,
                datasets: [
                    {
                        data: data,
                        fill: "start",
                        label: this.props.label,
                        backgroundColor: backgroundColors,
                    },
                ],
            },
            options: {
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        intersect: false,
                        position: "nearest",
                        caretSize: 0,
                    },
                },
                scales: {
                    y: {
                        grid: {
                            color: graphGridColor(),
                        },
                        ticks: {
                            color: graphLabelColor(),
                        },
                    },
                    x: {
                        grid: {
                            color: graphGridColor(),
                        },
                        ticks: {
                            color: graphLabelColor(),
                        },
                    },
                },
                maintainAspectRatio: false,
                elements: {
                    line: {
                        tension: 0.000001,
                    },
                },
            },
        };
    }

    /**
     * @returns {object} Chart config of type 'stacked bar'
     */
    getStackedBarChartConfig() {
        const labels = [];
        const datasets = [];
        const datasets_labels = [];
        let colors;
        if (this.props.is_sample) {
            colors = ["#e7e7e7", "#dddddd", "#f0f0f0", "#fafafa"];
        } else {
            colors = [getColor(14, "odoo"), "#a5d8d7", "#ebebeb", "#ebebeb"];
        }

        Object.entries(this.graphData).forEach(([code, graphData]) => {
            datasets_labels.push(code);
            const dataset_data = [];
            const formatted_data = [];
            graphData.forEach(function (pt) {
                if (!labels.includes(pt.label)) {
                    labels.push(pt.label);
                }
                formatted_data.push(`${code}: ${pt.formatted_value || pt.value}`);
                dataset_data.push(pt.value);
            });
            datasets.push({
                data: dataset_data,
                label: code,
                backgroundColor: colors[datasets_labels.length - 1],
                formatted_data: formatted_data,
            });
        });

        return {
            type: "bar",
            data: {
                labels: labels,
                datasets: datasets,
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        intersect: false,
                        position: "nearest",
                        caretSize: 0,
                        callbacks: {
                            label: (tooltipItem) => {
                                const { datasetIndex, index } = tooltipItem;
                                return datasets[datasetIndex].formatted_data[index];
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        stacked: true,
                        grid: {
                            color: graphGridColor(),
                        },
                        ticks: {
                            color: graphLabelColor(),
                        },
                        border: {
                            color: graphGridColor(),
                        },
                    },
                    y: {
                        display: false,
                        stacked: true,
                        beginAtZero: true,
                        grid: {
                            color: graphGridColor(),
                        },
                    },
                },
                maintainAspectRatio: false,
                elements: {
                    line: {
                        tension: 0.000001,
                    },
                },
            },
        };
    }
}

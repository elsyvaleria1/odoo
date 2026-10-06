/** @odoo-module native */
import { Component, onWillStart, onWillUnmount, useProps } from "@odoo/owl";
import { colorScheme, useColorSchemeEffect } from "@web/core/color_scheme";
import { withOpacity } from "@web/core/colors/colors";
import { loadChartJS } from "@web/core/lib/chartjs";
import { registry } from "@web/core/registry";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { standardFieldProps } from "@web/fields/standard_field_props";
const fieldRegistry = registry.category("fields");

/**
 * Inspired from the GraphView
 */
export class MarketingActivityGraph extends Component {
    static template = "marketing_automation.MarketingActivityGraph";
    static props = { ...standardFieldProps };
    props = useProps(this.constructor.props);

    setup() {
        this.chart = null;
        this.canvasRef = elementRef();

        onWillStart(async () => {
            const Chart = await loadChartJS();
            this.Chart = Chart;
        });
        useLayoutEffect(() => this.renderChart());
        useColorSchemeEffect(() => this.renderChart());
        onWillUnmount(this.onWillUnmount);
    }

    onWillUnmount() {
        if (this.chart) {
            this.chart.destroy();
        }
    }

    //--------------------------------------------------------------------------
    // Business
    //--------------------------------------------------------------------------

    /**
     * Instantiates a Chart (Chart.js lib) to render the graph according to
     * the current config.
     */
    renderChart() {
        if (this.chart) {
            this.chart.destroy();
        }
        const config = this.getChartConfig();
        this.chart = new this.Chart(this.canvasRef.el, config);
    }

    getChartConfig() {
        const chartData = JSON.parse(this.props.record.data[this.props.name]);
        if (colorScheme.isDark) {
            chartData[0].color = "#6afb81"; // Success
            chartData[1].color = "#fb6a6a"; // Danger
        }

        const datasets = chartData.map((group) => {
            const borderColor = group.color;
            const fillColor = withOpacity(group.color, 0.6);
            return {
                label: group.label,
                data: group.points,
                fill: "origin",
                backgroundColor: fillColor,
                borderColor: borderColor,
                borderWidth: 2,
                pointBackgroundColor: "rgba(0, 0, 0, 0)",
                pointBorderColor: borderColor,
            };
        });

        const labels = chartData[0].points.map((point) => point.x);

        return {
            type: "line",
            data: {
                labels: labels,
                datasets: datasets,
            },
            options: {
                elements: {
                    line: {
                        tension: 0,
                    },
                },
                animation: false,
                layout: {
                    padding: { left: 25, right: 20, top: 5, bottom: 20 },
                },
                plugins: {
                    legend: {
                        display: false,
                    },
                    tooltip: {
                        mode: "index",
                        intersect: false,
                        bodyColor: "rgba(0,0,0,1)",
                        titleFont: {
                            size: 13,
                        },
                        titleColor: "rgba(0,0,0,1)",
                        backgroundColor: "rgba(255,255,255,0.6)",
                        borderColor: "rgba(0,0,0,0.2)",
                        borderWidth: 2,
                        callbacks: {
                            labelColor: (tooltipItem) => {
                                const dataset = tooltipItem.dataset;
                                return {
                                    borderColor: "rgba(255,255,255,0.6)",
                                    backgroundColor: dataset.backgroundColor,
                                };
                            },
                        },
                    },
                },
                maintainAspectRatio: false,
                scales: {
                    y: {
                        type: "linear",
                        display: false,
                        beginAtZero: true,
                    },
                    x: {
                        ticks: {
                            maxRotation: 0,
                        },
                    },
                },
            },
        };
    }
}

export const marketingActivityGraph = {
    component: MarketingActivityGraph,
};

fieldRegistry.add("marketing_activity_graph", marketingActivityGraph);

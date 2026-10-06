/** @odoo-module native */
import { Component, onWillStart, onWillUnmount, t, useProps } from "@odoo/owl";
import { formatMonetary, formatPercentage } from "@web/core/formatters";
import { loadChartJS } from "@web/core/lib/chartjs";
import { registry } from "@web/core/registry";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

export class ValuationChart extends Component {
    static template = "equity.ValuationChart";
    static props = {
        labels: t.array(),
        data: t.object(),
        stats: t.object().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.canvasRef = elementRef();
        onWillStart(async () => {
            const Chart = await loadChartJS();
            this.Chart = Chart;
        });
        useLayoutEffect(() => this.renderChart());
        onWillUnmount(this.destroyChart);
    }

    destroyChart() {
        if (this.chart) {
            this.chart.destroy();
        }
    }

    renderChart() {
        this.destroyChart();
        const ctx = this.canvasRef.el.getContext("2d");
        this.chart = new this.Chart(ctx, this.getChartConfig());
    }

    getChartConfig() {
        const chartData = this.props.data;

        return {
            type: "line",
            data: {
                labels: Object.keys(chartData),
                datasets: this.props.labels.map((label, index) => ({
                    label,
                    data: Object.values(chartData).map((tuple) => tuple[index]),
                    borderWidth: 2,
                })),
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { display: true, position: "top" },
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: "Valuation",
                            font: { size: 21 },
                        },
                    },
                    x: {
                        title: {
                            display: true,
                            text: "Date",
                            font: { size: 21 },
                        },
                    },
                },
            },
        };
    }

    get totalValuation() {
        return formatMonetary(this.props.stats.valuation, {
            currencyId: this.props.stats.currencyId,
            humanReadable: true,
        });
    }

    get yourValuation() {
        return formatMonetary(this.props.stats.yourValuation, {
            currencyId: this.props.stats.currencyId,
            humanReadable: true,
        });
    }

    get ownership() {
        return formatPercentage(this.props.stats.ownership);
    }

    get votingRights() {
        return formatPercentage(this.props.stats.votingRights);
    }
}

registry.category("public_components").add("equity.ValuationChart", ValuationChart);

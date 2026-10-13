/** @odoo-module native */
import { Component, onWillStart, useProps } from "@odoo/owl";
import { useColorSchemeEffect } from "@web/core/color_scheme";
import { getColor } from "@web/core/colors/colors";
import { loadChartJS } from "@web/core/lib/chartjs";
import { registry } from "@web/core/registry";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { standardFieldProps } from "@web/fields/standard_field_props";

export class CommissionGraphField extends Component {
    static template = "sale_commission.GraphField";
    static props = { ...standardFieldProps };
    props = useProps(this.constructor.props);

    setup() {
        this.chart = null;
        this.canvasRef = elementRef();
        this.data = JSON.parse(this.props.record.data[this.props.name]);

        onWillStart(async () => {
            const Chart = await loadChartJS();
            this.Chart = Chart;
        });

        useColorSchemeEffect(() => this.renderChart());
        useLayoutEffect(() => {
            this.renderChart();
            return () => {
                if (this.chart) {
                    this.chart.destroy();
                }
            };
        });
    }

    renderChart() {
        if (this.chart) {
            this.chart.destroy();
        }
        this.data = JSON.parse(this.props.record.data[this.props.name]);
        this.chart = new this.Chart(this.canvasRef.el, this.getLineChartConfig());
    }

    /**
     * @param {*} a
     * @param {*} b
     * @returns
     */
    GCD(a, b) {
        a = Math.abs(a);
        b = Math.abs(b);
        if (a < b) {
            return this.GCD(b, a);
        }
        if (b === 0) {
            return a;
        }
        return this.GCD(b, a % b);
    }

    getLineChartConfig() {
        const labels = this.data.values.map(function (pt) {
            return pt.x;
        });

        let gcd = 0;
        this.data.values.forEach((v) => {
            gcd = this.GCD(v.x, gcd);
        });

        const color10 = getColor(3, "odoo");
        const currency = this.data.currency;
        return {
            type: "line",
            data: {
                labels,
                datasets: [
                    {
                        color10,
                        data: this.data.values,
                        fill: "start",
                        borderWidth: 2,
                    },
                ],
            },
            options: {
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        enabled: true,
                        intersect: false,
                        position: "nearest",
                        caretSize: 0,
                    },
                },
                scales: {
                    x: {
                        type: "linear",
                        ticks: {
                            stepSize: gcd,
                            callback: function (value) {
                                return value + "%";
                            },
                        },
                    },
                    y: {
                        type: "linear",
                        ticks: {
                            callback: function (value) {
                                return value + currency;
                            },
                        },
                    },
                },
                elements: {
                    line: {
                        tension: 0.000001,
                    },
                },
            },
        };
    }
}

export const commissionGraphField = {
    component: CommissionGraphField,
    supportedTypes: ["text"],
};

registry.category("fields").add("commission_graph", commissionGraphField);

/** @odoo-module native */
import {
    Component,
    onMounted,
    onWillStart,
    onWillUnmount,
    t,
    useProps,
} from "@odoo/owl";
import { useColorSchemeEffect } from "@web/core/color_scheme";
import {
    darkenColor,
    getBorderWhite,
    getColor,
    getCustomColor,
    lightenColor,
} from "@web/core/colors/colors";
import { loadChartJS } from "@web/core/lib/chartjs";
import { elementRef } from "@web/core/utils/element_ref";

const graphLabelColor = () => getCustomColor("#111827", "#E4E4E4");

export class EsgGraphDashboard extends Component {
    static template = "esg.GraphDashboard";
    static props = { config: t.object() };
    props = useProps(this.constructor.props);

    setup() {
        this.canvasRef = elementRef();
        onWillStart(async () => {
            const Chart = await loadChartJS();
            this.Chart = Chart;
        });
        onMounted(() => {
            this.renderChart();
        });
        useColorSchemeEffect(() => this.renderChart());
        onWillUnmount(() => {
            if (this.chart) {
                this.chart.destroy();
            }
        });
    }

    get config() {
        const config = { ...this.props.config };
        const data = config.data;
        if (config.type === "pie") {
            const colors = data.labels.map((_, index) =>
                getColor(index, data.labels.length),
            );
            const borderColor = getBorderWhite();
            for (const dataset of data.datasets) {
                dataset.backgroundColor = colors;
                dataset.hoverBackgroundColor = colors;
                dataset.borderColor = borderColor;
            }
        } else {
            for (let index = 0; index < data.datasets.length; index++) {
                const dataset = data.datasets[index];
                const itemColor = getColor(index, data.datasets.length);
                if (config.type === "line") {
                    dataset.backgroundColor = getCustomColor(
                        lightenColor(itemColor, 0.5),
                        darkenColor(itemColor, 0.5),
                    );
                    dataset.cubicInterpolationMode = "monotone";
                    dataset.borderColor = itemColor;
                    dataset.borderWidth = 2;
                    dataset.hoverBackgroundColor = dataset.borderColor;
                    dataset.pointRadius = 3;
                    dataset.pointHoverRadius = 6;
                    dataset.pointBackgroundColor = dataset.borderColor;
                } else {
                    dataset.backgroundColor = itemColor;
                    dataset.borderRadius = 4;
                }
            }
        }
        const options = config.options || {};
        if (config.type !== "pie") {
            const scales = options.scales || {};
            const xAxe = scales.x || {};
            if (!xAxe.ticks) {
                xAxe.ticks = {};
            }
            xAxe.ticks.color = graphLabelColor();

            const yAxe = scales.y || {};
            if (!yAxe.ticks) {
                yAxe.ticks = {};
            }
            yAxe.ticks.color = graphLabelColor();
            scales.x = xAxe;
            scales.y = yAxe;
            options.scales = scales;
            if (options.plugins?.title) {
                options.plugins.title.color = graphLabelColor();
            }
        }
        return {
            ...config,
            options,
        };
    }

    renderChart() {
        if (this.chart) {
            this.chart.destroy();
        }
        this.chart = new this.Chart(this.canvasRef.el, this.config);
    }
}

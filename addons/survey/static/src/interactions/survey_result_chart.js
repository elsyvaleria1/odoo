/** @odoo-module native */
import { getPaletteColor, SURVEY_CHART_COLORS } from "@web/core/colors/colors";
import { Chart, loadChartJS } from "@web/core/lib/chartjs";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { Interaction } from "@web/public/interaction";

export class SurveyResultChart extends Interaction {
    static selector = ".survey_graph";

    start() {
        this.graphData = JSON.parse(this.el.dataset.graphData);
        this.rightAnswers = this.el.dataset.rightAnswers || [];
        if (this.graphData && this.graphData.length !== 0) {
            switch (this.el.dataset.graphType) {
                case "multi_bar":
                    this.chartConfig = this.getMultibarChartConfig();
                    break;
                case "bar":
                    this.chartConfig = this.getBarChartConfig();
                    break;
                case "pie":
                    this.chartConfig = this.getPieChartConfig();
                    break;
                case "doughnut":
                    this.chartConfig = this.getDoughnutChartConfig();
                    break;
                case "by_section":
                    this.chartConfig = this.getSectionResultsChartConfig();
                    break;
            }
            this.chart = this.loadChart();
            this.registerCleanup(() => this.chart?.destroy());
        }
    }

    async willStart() {
        await loadChartJS();
    }

    getMultibarChartConfig() {
        return {
            type: "bar",
            data: {
                labels: this.graphData[0].values.map(this.markIfCorrect, this),
                datasets: this.graphData.map(function (group, index) {
                    const data = group.values.map(function (value) {
                        return value.count;
                    });
                    return {
                        label: group.key,
                        data: data,
                        backgroundColor: getPaletteColor(index, SURVEY_CHART_COLORS),
                    };
                }),
            },
            options: {
                scales: {
                    x: {
                        ticks: {
                            callback: function (val, index) {
                                const value = this.getLabelForValue(val);
                                const tickLimit = 25;
                                return value?.length > tickLimit
                                    ? `${value.slice(0, tickLimit)}...`
                                    : value;
                            },
                        },
                    },
                    y: {
                        ticks: {
                            precision: 0,
                        },
                        beginAtZero: true,
                    },
                },
                plugins: {
                    tooltip: {
                        callbacks: {
                            title: function (tooltipItem) {
                                return tooltipItem.label;
                            },
                        },
                    },
                },
            },
        };
    }

    getBarChartConfig() {
        return {
            type: "bar",
            data: {
                labels: this.graphData[0].values.map(this.markIfCorrect, this),
                datasets: this.graphData.map(function (group) {
                    const data = group.values.map(function (value) {
                        return value.count;
                    });
                    return {
                        label: group.key,
                        data: data,
                        backgroundColor: data.map(function (val, index) {
                            return getPaletteColor(index, SURVEY_CHART_COLORS);
                        }),
                    };
                }),
            },
            options: {
                plugins: {
                    legend: {
                        display: false,
                    },
                    tooltip: {
                        enabled: false,
                    },
                },
                scales: {
                    x: {
                        ticks: {
                            callback: function (val, index) {
                                const value = this.getLabelForValue(val);
                                const tickLimit = 35;
                                return value?.length > tickLimit
                                    ? `${value.slice(0, tickLimit)}...`
                                    : value;
                            },
                        },
                    },
                    y: {
                        ticks: {
                            precision: 0,
                        },
                        beginAtZero: true,
                    },
                },
            },
        };
    }

    getPieChartConfig() {
        const counts = this.graphData.map(function (point) {
            return point.count;
        });

        return {
            type: "pie",
            data: {
                labels: this.graphData.map(this.markIfCorrect, this),
                datasets: [
                    {
                        label: "",
                        data: counts,
                        backgroundColor: counts.map(function (val, index) {
                            return getPaletteColor(index, SURVEY_CHART_COLORS);
                        }),
                    },
                ],
            },
            options: {
                aspectRatio: 2,
            },
        };
    }

    getDoughnutChartConfig() {
        const totalsGraphData = this.graphData.totals;
        const counts = totalsGraphData.map(function (point) {
            return point.count;
        });

        return {
            type: "doughnut",
            data: {
                labels: totalsGraphData.map(this.markIfCorrect, this),
                datasets: [
                    {
                        label: "",
                        data: counts,
                        backgroundColor: counts.map(function (val, index) {
                            return getPaletteColor(index, SURVEY_CHART_COLORS);
                        }),
                        borderColor: "rgba(0, 0, 0, 0.1)",
                    },
                ],
            },
            options: {
                plugins: {
                    title: {
                        display: true,
                        text: _t("Overall Performance"),
                    },
                },
                aspectRatio: 2,
            },
        };
    }

    getSectionResultsChartConfig() {
        const sectionGraphData = this.graphData.by_section;

        const resultKeys = {
            correct: _t("Correct"),
            partial: _t("Partially"),
            incorrect: _t("Incorrect"),
            skipped: _t("Unanswered"),
        };
        let resultColorIndex = 0;
        const datasets = [];
        for (const resultKey in resultKeys) {
            const data = [];
            for (const section in sectionGraphData) {
                data.push(
                    (sectionGraphData[section][resultKey] /
                        sectionGraphData[section]["question_count"]) *
                        100,
                );
            }
            datasets.push({
                label: resultKeys[resultKey],
                data: data,
                backgroundColor: getPaletteColor(resultColorIndex, SURVEY_CHART_COLORS),
            });
            resultColorIndex++;
        }

        return {
            type: "bar",
            data: {
                labels: Object.keys(sectionGraphData),
                datasets: datasets,
            },
            options: {
                plugins: {
                    title: {
                        display: true,
                        text: _t("Performance by Section"),
                    },
                    legend: {
                        display: true,
                    },
                    tooltip: {
                        callbacks: {
                            label: (tooltipItem) => {
                                const xLabel = tooltipItem.label;
                                const roundedValue =
                                    Math.round(tooltipItem.parsed.y * 100) / 100;
                                return `${xLabel}: ${roundedValue}%`;
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        ticks: {
                            callback: function (val, index) {
                                const value = this.getLabelForValue(val);
                                const tickLimit = 20;
                                return value?.length > tickLimit
                                    ? `${value.slice(0, tickLimit)}...`
                                    : value;
                            },
                        },
                    },
                    y: {
                        gridLines: {
                            display: false,
                        },
                        ticks: {
                            precision: 0,
                            callback: function (label) {
                                return label + "%";
                            },
                            maxTicksLimit: 5,
                            stepSize: 25,
                        },
                        beginAtZero: true,
                        suggestedMin: 0,
                        suggestedMax: 100,
                    },
                },
            },
        };
    }

    /**
     * Adds a unicode 'check' mark if the answer's text is among the question's right answers.
     *
     * @param  value
     * @param  value.text The original text of the answer
     */
    markIfCorrect(value) {
        return (
            value.text + (this.rightAnswers.indexOf(value.text) >= 0 ? " \u2713" : "")
        );
    }

    loadChart() {
        this.el.style.position = "relative";
        const canvas = this.el.querySelector("canvas");
        const ctx = canvas.getContext("2d");
        return new Chart(ctx, this.chartConfig);
    }
}

registry
    .category("public.interactions")
    .add("survey.survey_result_chart", SurveyResultChart);

/** @odoo-module native */

import SESSION_CHART_COLORS from "@survey/interactions/survey_session_colors";
import { getPaletteColor } from "@web/core/colors/colors";
import { Chart, loadChartJS } from "@web/core/lib/chartjs";
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

import ChartDataLabels from "chartjs-plugin-datalabels";

export class SurveySessionChart extends Interaction {
    static selector = ".o_survey_session_chart";
    dynamicContent = {
        _root: {
            "t-on-updateState": this.updateState,
            "t-att-class": () => ({ chart_is_ready: !!this.chart }),
        },
    };
    setup() {
        const sessionManageEl = this.el.closest(".o_survey_session_manage");
        this.questionType = sessionManageEl.dataset.questionType;
        this.answersValidity = JSON.parse(sessionManageEl.dataset.answersValidity);
        this.hasCorrectAnswers = sessionManageEl.dataset.hasCorrectAnswers;
        this.questionStatistics = this.processQuestionStatistics(
            JSON.parse(sessionManageEl.dataset.questionStatistics),
        );
        this.showAnswers = false;
        this.showInputs = false;
    }

    async willStart() {
        await loadChartJS();
    }

    start() {
        const canvas = this.el.querySelector("canvas");
        const ctx = canvas.getContext("2d");
        this.chart = new Chart(ctx, this.buildChartConfiguration());
        this.registerCleanup(() => this.chart.destroy());
        this.env.bus.trigger("SURVEY:CHART_INTERACTION_STARTED");
    }

    /** @param {CustomEvent} ev */
    updateState(ev) {
        if ("showInputs" in ev.detail) {
            this.showInputs = ev.detail.showInputs;
        }
        if ("showAnswers" in ev.detail) {
            this.showAnswers = ev.detail.showAnswers;
        }
        this.updateChart(ev.detail.questionStatistics);
    }

    /** @param {Object} questionStatistics */
    updateChart(questionStatistics) {
        if (questionStatistics) {
            this.questionStatistics =
                this.processQuestionStatistics(questionStatistics);
        }
        if (this.chart) {
            const chartData = this.chart.data.datasets[0].data;
            for (let i = 0; i < chartData.length; i++) {
                const value = this.showInputs ? this.questionStatistics[i].count : 0;
                this.chart.data.datasets[0].data[i] = value;
            }
            this.chart.update();
        }
    }

    /** @private */
    buildChartConfiguration() {
        return {
            type: "bar",
            data: {
                labels: this.extractChartLabels(),
                datasets: [
                    {
                        backgroundColor: this.getBackgroundColor.bind(this),
                        data: this.extractChartData(),
                    },
                ],
            },
            options: {
                maintainAspectRatio: false,
                plugins: {
                    datalabels: {
                        color: this.getLabelColor.bind(this),
                        font: {
                            size: "50",
                            weight: "bold",
                        },
                        anchor: "end",
                        align: "top",
                    },
                    legend: {
                        display: false,
                    },
                    tooltip: {
                        enabled: false,
                    },
                },
                scales: {
                    y: {
                        ticks: {
                            display: false,
                        },
                        grid: {
                            display: false,
                        },
                    },
                    x: {
                        ticks: {
                            minRotation: 20,
                            maxRotation: 90,
                            font: {
                                size: "35",
                                weight: "bold",
                            },
                            color: "#212529",
                            autoSkip: false,
                        },
                        grid: {
                            drawOnChartArea: false,
                            color: "rgba(0, 0, 0, 0.2)",
                        },
                    },
                },
                layout: {
                    padding: {
                        left: 0,
                        right: 0,
                        top: 70,
                        bottom: 0,
                    },
                },
            },
            plugins: [
                ChartDataLabels,
                {
                    /** @param {Object} chart */
                    beforeInit: function (chart) {
                        const nbrCol = chart.data.labels.length;
                        const minRatio = 0.4;
                        const charPerLineBreakpoints = [
                            [1, 2, 35, minRatio],
                            [3, 4, 30, minRatio],
                            [5, 6, 30, 0.45],
                            [7, 8, 30, 0.65],
                            [9, null, 30, 0.7],
                        ];

                        let charPerLine;
                        let fontRatio;
                        charPerLineBreakpoints.forEach(
                            ([lowerBound, upperBound, value, ratio]) => {
                                if (
                                    nbrCol >= lowerBound &&
                                    (upperBound === null || nbrCol <= upperBound)
                                ) {
                                    charPerLine = value;
                                    fontRatio = ratio;
                                }
                            },
                        );

                        if (charPerLine < 35) {
                            const allWords = chart.data.labels.reduce(
                                (accumulator, words) =>
                                    accumulator.concat(" ".concat(words)),
                            );
                            const maxWordLength = Math.max(
                                ...allWords.split(" ").map((word) => word.length),
                            );
                            fontRatio =
                                maxWordLength > charPerLine ? minRatio : fontRatio;
                            chart.options.scales.x.ticks.font.size = Math.min(
                                parseInt(chart.options.scales.x.ticks.font.size),
                                (chart.width * fontRatio) / nbrCol,
                            );
                        }

                        chart.data.labels.forEach(function (label, index, labelsList) {
                            const words = label.split(" ");
                            const resultLines = [];
                            let currentLine = [];
                            for (let i = 0; i < words.length; i++) {
                                let word = words[i];
                                while (word.length > charPerLine) {
                                    resultLines.push(
                                        word.slice(0, charPerLine - 1) + "-",
                                    );
                                    word = word.slice(charPerLine - 1);
                                }
                                currentLine.push(word);

                                const nextWord =
                                    i + 1 < words.length ? words[i + 1] : null;
                                if (nextWord) {
                                    const nextLength =
                                        currentLine.join(" ").length + nextWord.length;
                                    if (nextLength <= charPerLine) {
                                        continue;
                                    }
                                }
                                const newLabelLine = currentLine.join(" ");
                                resultLines.push(newLabelLine);
                                currentLine = [];
                            }
                            labelsList[index] = resultLines;
                        });
                    },
                },
            ],
        };
    }

    extractChartLabels() {
        return this.questionStatistics.map((point) => point.text);
    }

    extractChartData() {
        return Array(this.questionStatistics.length).fill(0);
    }

    /**
     * @param {Object} metaData
     * @param {Integer} metaData.dataIndex
     */
    getBackgroundColor(metaData) {
        const opacity =
            this.showAnswers &&
            this.hasCorrectAnswers &&
            !this.isValidAnswer(metaData.dataIndex)
                ? "0.2"
                : "0.8";
        const rgb = getPaletteColor(metaData.dataIndex, SESSION_CHART_COLORS);
        return `rgba(${rgb},${opacity})`;
    }

    /**
     * @param {Object} metaData
     * @param {Integer} metaData.dataIndex
     */
    getLabelColor(metaData) {
        let color = "#212529";
        if (this.showAnswers && this.hasCorrectAnswers) {
            color = this.isValidAnswer(metaData.dataIndex) ? "#2CBB70" : "#D9534F";
        }
        return color;
    }

    /** @param {Integer} answerIndex */
    isValidAnswer(answerIndex) {
        return this.answersValidity[answerIndex];
    }

    /** @param {Object} rawStatistics */
    processQuestionStatistics(rawStatistics) {
        if (["multiple_choice", "scale"].includes(this.questionType)) {
            return rawStatistics[0].values;
        }
        return rawStatistics;
    }
}

registry
    .category("public.interactions")
    .add("survey.survey_session_chart", SurveySessionChart);

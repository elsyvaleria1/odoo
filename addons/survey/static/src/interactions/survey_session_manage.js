/** @odoo-module native */
import { preloadBackground } from "@survey/js/survey_preload_image_mixin";
import { fadeIn, fadeOut } from "@survey/utils";
import { browser } from "@web/core/browser/browser";
import { getActiveHotkey } from "@web/core/browser/hotkeys";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { Popover, Tooltip } from "@web/libs/bootstrap";
import { Interaction } from "@web/public/interaction";

const nextPageTooltips = {
    closingWords: _t("End of Survey"),
    leaderboard: _t("Show Leaderboard"),
    leaderboardFinal: _t("Show Final Leaderboard"),
    nextQuestion: _t("Next"),
    results: _t("Show Correct Answer(s)"),
    startScreen: _t("Start"),
    userInputs: _t("Show Results"),
};

export class SurveySessionManage extends Interaction {
    static selector = ".o_survey_session_manage";

    dynamicContent = {
        _document: {
            "t-on-keydown": this.onKeyDown,
        },
        ".o_survey_session_copy": {
            "t-on-click.prevent": this.onCopySessionLink,
        },
        ".o_survey_session_navigation_next": {
            "t-on-click.prevent": this.onNext,
            "t-att-class": () => ({
                "d-none":
                    this.isSessionClosed ||
                    (this.isLastQuestion && this.currentScreen === "leaderboardFinal"),
            }),
        },
        ".o_survey_session_navigation_previous": {
            "t-on-click.prevent": this.onBack,
            "t-att-class": () => ({
                "d-none": this.isFirstQuestion || this.isSessionClosed,
            }),
        },
        ".o_survey_session_close": {
            "t-on-click.prevent": this.onEndSessionClick,
        },
        ".o_survey_session_attendees_count": {
            "t-out": () => this.sessionAttendeesCountText,
        },
        ".o_survey_session_navigation_next_label": {
            "t-out": () => this.sessionNavigationNextLabel,
        },
        ".o_survey_session_results": {
            "t-att-class": () => ({
                "d-none":
                    this.isSessionClosed ||
                    this.leaderboardIsFadingOut ||
                    this.hideResults,
            }),
            "t-on-setDisplayNone": () => {
                this.hideResults = true;
            },
        },
        ".o_survey_session_description_done": {
            "t-att-class": () => ({ "d-none": !this.isSessionClosed }),
        },
    };

    setup() {
        if (this.el.dataset.isSessionClosed) {
            this.isSessionClosed = true;
            this.el.classList.remove("invisible");
            return;
        }
        this.fadeInOutTime = 500;
        this.answersRefreshDelay = 2000;
        this.isSessionClosed = false;
        this.leaderboardIsFadingOut = false;
        this.hideResults = false;
        this.chartEl = this.el.querySelector(".o_survey_session_chart");
        this.leaderboardEl = this.el.querySelector(".o_survey_session_leaderboard");
        this.timerEl = this.el.querySelector(
            ".o_survey_timer_container .o_survey_timer",
        );
        this.textAnswersEl = this.el.querySelector(
            ".o_survey_session_text_answers_container",
        );
        this.surveyId = parseInt(this.el.dataset.surveyId);
        this.attendeesCount = this.el.dataset.attendeesCount
            ? parseInt(this.el.dataset.attendeesCount, 10)
            : 0;
        this.surveyHasConditionalQuestions =
            this.el.dataset.surveyHasConditionalQuestions;
        this.surveyAccessToken = this.el.dataset.surveyAccessToken;
        this.isStartScreen = this.el.dataset.isStartScreen;
        this.isFirstQuestion = this.el.dataset.isFirstQuestion;
        this.isLastQuestion = this.el.dataset.isLastQuestion;
        this.surveyLastTriggeringAnswers = JSON.parse(
            this.el.dataset.surveyLastTriggeringAnswers || "[]",
        );
        this.isScoredQuestion = this.el.dataset.isScoredQuestion;
        this.sessionShowLeaderboard = this.el.dataset.sessionShowLeaderboard;
        this.hasCorrectAnswers = this.el.dataset.hasCorrectAnswers;
        this.showBarChart = this.el.dataset.showBarChart;
        this.showTextAnswers = this.el.dataset.showTextAnswers;
        this.stopNextQuestion = false;
        this.refreshBackground = this.el.dataset.refreshBackground;
        this.copyBtnTooltip = Tooltip.getOrCreateInstance(
            this.el.querySelector(".o_survey_session_copy"),
            {
                title: _t("Click to copy link"),
                placement: "right",
                container: "body",
                trigger: "hover",
                offset: "0, 3",
                delay: 0,
            },
        );
        this.registerCleanup(() => {
            this.copyBtnPopover?.dispose();
            this.copyBtnTooltip?.dispose();
        });
        this.sessionAttendeesCountText = "";
        this.sessionNavigationNextLabel = "";
        this.el.classList.remove("invisible");
        this.setupIntervals();
        this.registerCleanup(() => {
            clearInterval(this.attendeesRefreshInterval);
            clearInterval(this.resultsRefreshInterval);
        });
    }

    async willStart() {
        if (this.chartEl && !this.chartEl.classList.contains("chart_is_ready")) {
            let resolveChartPromise;
            const chartPromise = new Promise(function (resolve) {
                resolveChartPromise = resolve;
            });
            this.env.bus.addEventListener(
                "SURVEY:CHART_INTERACTION_STARTED",
                resolveChartPromise,
            );
            await chartPromise;
        }
    }

    start() {
        if (this.el.dataset.isRpcCall) {
            fadeIn(this.el, this.fadeInOutTime);
        }
        this.setupCurrentScreen();
        this.startTimer();
        if (this.el.dataset.goingBack) {
            this.chartUpdateState({ showInputs: true, showAnswers: true });
            if (this.sessionShowLeaderboard && this.isScoredQuestion) {
                this.currentScreen = "leaderboard";
                this.leaderboardEl.dispatchEvent(
                    new CustomEvent("showLeaderboard", {
                        detail: {
                            fadeOut: false,
                            isScoredQuestion: this.isScoredQuestion,
                        },
                    }),
                );
            } else {
                this.currentScreen = "results";
            }
            this.refreshResults();
        }
    }

    /** @param {MouseEvent} ev */
    async onCopySessionLink(ev) {
        const copyBtnTooltipHideDelay = 800;
        this.copyBtnTooltip?.dispose();
        delete this.copyBtnTooltip;
        this.copyBtnPopover = Popover.getOrCreateInstance(ev.currentTarget, {
            content: _t("Copied!"),
            trigger: "manual",
            placement: "right",
            container: "body",
            offset: "0, 3",
        });
        await this.waitFor(
            browser.navigator.clipboard.writeText(ev.currentTarget.innerText.trim()),
        );
        this.bindDeferred(() => {
            this.copyBtnPopover.show();
            this.waitForTimeout(
                () => this.copyBtnPopover.hide(),
                copyBtnTooltipHideDelay,
            );
        })();
    }

    /** @param {Event} ev */
    onNext(ev) {
        const screenToDisplay = this.getNextScreen();
        switch (screenToDisplay) {
            case "userInputs":
                this.chartUpdateState({ showInputs: true });
                break;
            case "results":
                this.chartUpdateState({ showAnswers: true });
                clearInterval(this.resultsRefreshInterval);
                delete this.resultsRefreshInterval;
                break;
            case "leaderboard":
            case "leaderboardFinal":
                if (!this.currentScreen.startsWith("leaderboard")) {
                    this.leaderboardEl.dispatchEvent(
                        new CustomEvent("showLeaderboard", {
                            detail: {
                                fadeOut: true,
                                isScoredQuestion: this.isScoredQuestion,
                            },
                        }),
                    );
                }
                break;
            default:
                if (!this.isLastQuestion || !this.sessionShowLeaderboard) {
                    this.goToNextQuestion();
                }
                break;
        }
        this.currentScreen = screenToDisplay;
        if (!["question", "nextQuestion"].includes(screenToDisplay)) {
            this.updateNextScreenTooltip();
        }
    }

    /** @param {Event} ev */
    onBack(ev) {
        const screenToDisplay = this.getPreviousScreen();
        switch (screenToDisplay) {
            case "question":
                this.chartUpdateState({ showInputs: false });
                break;
            case "userInputs":
                this.chartUpdateState({ showAnswers: false });
                if (!this.resultsRefreshInterval) {
                    this.resultsRefreshInterval = setInterval(
                        this.refreshResults.bind(this),
                        this.answersRefreshDelay,
                    );
                }
                break;
            case "results":
                if (this.isScoredQuestion || this.isLastQuestion) {
                    this.leaderboardEl.dispatchEvent(new Event("hideLeaderboard"));
                }
                clearInterval(this.resultsRefreshInterval);
                delete this.resultsRefreshInterval;
                break;
            case "previousQuestion":
                if (this.isFirstQuestion) {
                    return;
                }
                this.goToNextQuestion(true);
                break;
        }
        this.currentScreen = screenToDisplay;
        if (!["question", "nextQuestion"].includes(screenToDisplay)) {
            this.updateNextScreenTooltip();
        }
    }

    getNextScreen() {
        if (this.currentScreen === "question" && this.isScoredQuestion) {
            return "userInputs";
        } else if (
            this.hasCorrectAnswers &&
            ["question", "userInputs"].includes(this.currentScreen)
        ) {
            return "results";
        } else if (this.sessionShowLeaderboard) {
            if (this.isLastQuestion) {
                return "leaderboardFinal";
            } else if (
                ["question", "userInputs", "results"].includes(this.currentScreen) &&
                this.isScoredQuestion
            ) {
                return "leaderboard";
            }
        }
        return "nextQuestion";
    }

    /** @param {Event} ev */
    getPreviousScreen() {
        if (this.currentScreen === "userInputs" && this.isScoredQuestion) {
            return "question";
        } else if (
            (this.currentScreen === "results" && this.isScoredQuestion) ||
            (this.currentScreen === "leaderboard" && !this.isScoredQuestion) ||
            (this.currentScreen === "leaderboardFinal" && this.isScoredQuestion)
        ) {
            return "userInputs";
        } else if (
            (this.currentScreen === "leaderboard" && this.isScoredQuestion) ||
            (this.currentScreen === "leaderboardFinal" && !this.isScoredQuestion)
        ) {
            return "results";
        }
        return "previousQuestion";
    }

    /**
     * @param {MouseEvent} ev
     * @private
     */
    async goToNextQuestion(goBack) {
        if (this.stopNextQuestion) {
            return;
        }
        this.stopNextQuestion = true;
        this.leaderboardIsFadingOut = true;
        this.isStartScreen = false;
        let resolveFadeOut;
        const fadeOutPromise = new Promise(function (resolve) {
            resolveFadeOut = resolve;
        });
        fadeOut(this.el, this.fadeInOutTime, () => {
            this.leaderboardIsFadingOut = false;
            resolveFadeOut();
        });
        if (this.refreshBackground) {
            document
                .querySelector("div.o_survey_background")
                .classList.add("o_survey_background_transition");
        }
        if (this.resultsRefreshInterval) {
            clearInterval(this.resultsRefreshInterval);
            delete this.resultsRefreshInterval;
        }
        this.nextQuestion = await this.waitFor(
            rpc(`/survey/session/next_question/${this.surveyAccessToken}`, {
                go_back: goBack,
            }),
        );
        const backgroundImageUrl = this.nextQuestion.data.background_image_url;
        let preloadBgPromise;
        if (this.refreshBackground && backgroundImageUrl) {
            preloadBgPromise = preloadBackground(backgroundImageUrl);
        } else {
            preloadBgPromise = Promise.resolve();
        }
        await this.waitFor(Promise.all([fadeOutPromise, preloadBgPromise]));
        this.bindDeferred(() => this.onNextQuestionDone())();
    }

    onNextQuestionDone() {
        if (this.nextQuestion.data.ended) {
            this.isSessionClosed = true;
            this.onEndSessionClick();
            return;
        }
        const surveyBackground = document.querySelector("div.o_survey_background");
        if (this.refreshBackground && surveyBackground) {
            const url = this.nextQuestion.data.background_image_url;
            if (url) {
                surveyBackground.style.backgroundImage = `url(${url})`;
            }
            surveyBackground.classList.remove("o_survey_background_transition");
        }
        this.swapFragments(this.nextQuestion);
    }

    /** @private */
    async onEndSessionClick(ev) {
        const showResults = ev?.currentTarget?.dataset?.showResults;
        await this.waitFor(
            this.services.orm.call("survey.survey", "action_end_session", [
                [this.surveyId],
            ]),
        );
        this.bindDeferred(() => {
            if (showResults) {
                window.location.href = `/survey/results/${encodeURIComponent(this.surveyId)}`;
            } else {
                window.location.reload();
            }
        })();
    }

    /** @param {KeyboardEvent} ev */
    onKeyDown(ev) {
        const hotkey = getActiveHotkey(ev);
        if (hotkey === "arrowright" || hotkey === "space") {
            this.onNext(ev);
        } else if (hotkey === "arrowleft") {
            this.onBack(ev);
        }
    }

    setupCurrentScreen() {
        if (this.isStartScreen) {
            this.currentScreen = "startScreen";
        } else if (!this.isScoredQuestion && this.showBarChart) {
            this.currentScreen = "userInputs";
        } else {
            this.currentScreen = "question";
        }
        this.chartUpdateState({ showInputs: this.currentScreen === "userInputs" });
        this.updateNextScreenTooltip();
    }

    chartUpdateState(options) {
        this.chartEl?.dispatchEvent(
            new CustomEvent("updateState", {
                detail: options,
            }),
        );
    }

    updateNextScreenTooltip() {
        let tooltip;
        if (this.currentScreen === "startScreen") {
            tooltip = nextPageTooltips.startScreen;
        } else if (
            this.isLastQuestion &&
            !this.surveyHasConditionalQuestions &&
            !this.isScoredQuestion &&
            !this.sessionShowLeaderboard
        ) {
            tooltip = nextPageTooltips.closingWords;
        } else {
            const nextScreen = this.getNextScreen();
            tooltip = nextPageTooltips[nextScreen];
        }
        const sessionNavigationNextEl = this.el.querySelector(
            ".o_survey_session_navigation_next_label",
        );
        if (sessionNavigationNextEl && tooltip) {
            this.sessionNavigationNextLabel = tooltip;
            this.updateContent();
        }
    }

    setupIntervals() {
        if (this.isStartScreen) {
            this.attendeesRefreshInterval = setInterval(
                this.refreshAttendeesCount.bind(this),
                this.answersRefreshDelay,
            );
        } else {
            if (this.attendeesRefreshInterval) {
                clearInterval(this.attendeesRefreshInterval);
            }
            if (!this.resultsRefreshInterval) {
                this.resultsRefreshInterval = setInterval(
                    this.refreshResults.bind(this),
                    this.answersRefreshDelay,
                );
            }
        }
    }

    startTimer(el) {
        const surveyManagerEl = el || this.el;
        const timerData = surveyManagerEl.dataset;
        const questionTimeLimitReached = !!timerData.questionTimeLimitReached;
        const timeLimitMinutes = Number(timerData.timeLimitMinutes);
        const hasAnswered = !!timerData.hasAnswered;
        if (
            this.timerEl &&
            !questionTimeLimitReached &&
            !hasAnswered &&
            timeLimitMinutes
        ) {
            this.addListener(surveyManagerEl, "time_up", async () => {
                if (this.currentScreen === "question" && this.isScoredQuestion) {
                    this.onNext();
                }
            });
            this.timerEl.dispatchEvent(
                new CustomEvent("start_timer", {
                    detail: {
                        timeLimitMinutes: timeLimitMinutes,
                        timer: timerData.timer,
                    },
                }),
            );
        }
    }

    refreshResults() {
        this.waitFor(rpc(`/survey/session/results/${this.surveyAccessToken}`)).then(
            this.bindDeferred((questionResults) => {
                if (questionResults) {
                    this.attendeesCount = questionResults.attendees_count;

                    if (
                        !this.isStartScreen &&
                        this.showBarChart &&
                        questionResults.question_statistics_graph
                    ) {
                        const parsedStatistics = JSON.parse(
                            questionResults.question_statistics_graph,
                        );
                        if (parsedStatistics.length > 0) {
                            this.chartUpdateState({
                                questionStatistics: parsedStatistics,
                            });
                        }
                    } else if (!this.isStartScreen && this.showTextAnswers) {
                        this.textAnswersEl.dispatchEvent(
                            new CustomEvent("updateTextAnswers", {
                                detail: {
                                    questionType: this.el.dataset.questionType,
                                    inputLineValues: questionResults.input_line_values,
                                },
                            }),
                        );
                    }

                    if (this.surveyLastTriggeringAnswers.length) {
                        this.isLastQuestion =
                            !questionResults.answer_count ||
                            !this.surveyLastTriggeringAnswers.some((answerId) =>
                                questionResults.selected_answers.includes(answerId),
                            );
                        this.updateNextScreenTooltip();
                    }

                    const progressBar = this.el.querySelector(".progress-bar");
                    if (progressBar) {
                        const max = this.attendeesCount > 0 ? this.attendeesCount : 1;
                        const percentage = Math.min(
                            Math.round((questionResults.answer_count / max) * 100),
                            100,
                        );
                        progressBar.style.width = `${percentage}%`;
                    }

                    if (this.attendeesCount && this.attendeesCount > 0) {
                        const answerCount = Math.min(
                            questionResults.answer_count,
                            this.attendeesCount,
                        );
                        const answerCountElement = this.el.querySelector(
                            ".o_survey_session_answer_count",
                        );
                        const progressBarTextElement = this.el.querySelector(
                            ".progress-bar.o_survey_session_progress_small span",
                        );
                        if (answerCountElement) {
                            answerCountElement.textContent = answerCount;
                        }
                        if (progressBarTextElement) {
                            progressBarTextElement.textContent = `${answerCount} / ${this.attendeesCount}`;
                        }
                    }
                }
            }),
            this.bindDeferred(() => {
                clearInterval(this.resultsRefreshInterval);
                delete this.resultsRefreshInterval;
            }),
        );
    }

    refreshAttendeesCount() {
        this.waitFor(
            this.services.orm.read(
                "survey.survey",
                [this.surveyId],
                ["session_answer_count"],
            ),
        ).then(
            this.bindDeferred((result) => {
                if (result && result.length === 1) {
                    this.sessionAttendeesCountText = String(
                        result[0].session_answer_count,
                    );
                }
            }),
            this.bindDeferred((err) => {
                clearInterval(this.attendeesRefreshInterval);
                console.error(err);
            }),
        );
    }
}

registry
    .category("public.interactions")
    .add("survey.survey_session_manage", SurveySessionManage);

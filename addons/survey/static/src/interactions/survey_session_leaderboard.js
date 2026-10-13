/** @odoo-module native */
import SESSION_CHART_COLORS from "@survey/interactions/survey_session_colors";
import { fadeIn, fadeOut } from "@survey/utils";
import { getPaletteColor } from "@web/core/colors/colors";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

export class SurveySessionLeaderboard extends Interaction {
    static selector = ".o_survey_session_manage .o_survey_session_leaderboard";
    dynamicContent = {
        _root: {
            "t-on-showLeaderboard": this.showLeaderboard,
            "t-on-hideLeaderboard": this.hideLeaderboard,
        },
        ".o_survey_session_leaderboard_bar": {
            "t-att-style": this.getBarStyle,
        },
        ".o_survey_session_leaderboard_bar_question": {
            "t-att-style": this.getBarQuestionStyle,
        },
    };

    getBarStyle(barEl) {
        if (this.leaderboardAnimationPhase === "prepareScores") {
            const currentScore = parseInt(
                barEl.closest(".o_survey_session_leaderboard_item").dataset
                    .currentScore,
            );
            if (currentScore && currentScore !== 0) {
                return {
                    transition: "width 1s cubic-bezier(.4,0,.4,1)",
                    width: this.BAR_MIN_WIDTH,
                };
            }
        } else if (this.leaderboardAnimationPhase === "sumScores") {
            const { baseRatio, questionRatio } = this.getBarRatios(barEl);
            const updatedScoreRatio = 1 - questionRatio;
            const updatedScoreWidth = `calc(calc(100% - ${this.BAR_WIDTH}) * ${
                updatedScoreRatio * baseRatio
            })`;
            return {
                transition: "width ease .5s cubic-bezier(.5,0,.66,1.11)",
                width: updatedScoreWidth,
                minWidth: "0px",
            };
        }
        return {};
    }

    getBarQuestionStyle(barEl) {
        if (this.leaderboardAnimationPhase === "showQuestionScores") {
            return {
                transition: "width 1s ease-out",
                width: `calc(calc(100% - ${this.BAR_WIDTH}) * ${barEl.dataset.widthRatio} + ${this.BAR_MIN_WIDTH})`,
            };
        } else if (this.leaderboardAnimationPhase === "sumScores") {
            const { baseRatio, questionRatio } = this.getBarRatios(barEl);
            const questionWidth = `calc(calc(calc(100% - ${this.BAR_WIDTH}) * ${
                questionRatio * baseRatio
            }) + ${this.BAR_MIN_WIDTH})`;
            return {
                transition: "width ease .5s cubic-bezier(.5,0,.66,1.11)",
                width: questionWidth,
            };
        }
        return {};
    }

    getBarRatios(barEl) {
        const item = barEl.closest(".o_survey_session_leaderboard_item");
        const updatedScore = parseInt(item.dataset.updatedScore);
        const questionScore = parseInt(item.dataset.questionScore);
        const maxUpdatedScore = parseInt(item.dataset.maxUpdatedScore);
        const baseRatio = maxUpdatedScore ? updatedScore / maxUpdatedScore : 1;
        const questionRatio = questionScore / (updatedScore || 1);
        return { baseRatio, questionRatio };
    }

    setup() {
        this.fadeInOutTime = 400;
        this.BAR_MIN_WIDTH = "3rem";
        this.BAR_WIDTH = "24rem";
        this.BAR_HEIGHT = "3.8rem";
        this.surveyAccessToken = this.el.closest(
            ".o_survey_session_manage",
        ).dataset.surveyAccessToken;
        this.sessionResults = this.el.parentElement.querySelector(
            ".o_survey_session_results",
        );
    }

    /** @param {CustomEvent} ev */
    showLeaderboard(ev) {
        let resolveFadeOut;
        let fadeOutPromise;
        const resultsEl = this.el.parentElement.querySelector(
            ".o_survey_session_results",
        );
        if (ev.detail.fadeOut) {
            fadeOutPromise = new Promise((resolve, reject) => {
                resolveFadeOut = resolve;
            });
            fadeOut(resultsEl, this.fadeInOutTime, () => {
                resultsEl.dispatchEvent(new CustomEvent("setDisplayNone"));
                resolveFadeOut();
            });
        } else {
            fadeOutPromise = Promise.resolve();
            resultsEl.dispatchEvent(new CustomEvent("setDisplayNone"));
            this.removeChildren(
                this.el.querySelector(".o_survey_session_leaderboard_container"),
            );
        }

        const leaderboardPromise = rpc(
            `/survey/session/leaderboard/${this.surveyAccessToken}`,
        );
        this.waitFor(Promise.all([fadeOutPromise, leaderboardPromise])).then(
            this.bindDeferred((results) => {
                this.swapFragments(results[1]);
                this.el
                    .querySelectorAll(".o_survey_session_leaderboard_item")
                    .forEach((item, index) => {
                        const rgb = getPaletteColor(
                            index,
                            SESSION_CHART_COLORS.slice(0, 10),
                        );
                        item.querySelector(
                            ".o_survey_session_leaderboard_bar",
                        ).style.backgroundColor = `rgba(${rgb},1)`;
                        item.querySelector(
                            ".o_survey_session_leaderboard_bar_question",
                        ).style.backgroundColor = `rgba(${rgb},0.4)`;
                    });
                fadeIn(this.el, this.fadeInOutTime, async () => {
                    if (ev.detail.isScoredQuestion) {
                        await this.waitFor(this.prepareScores());
                        await this.waitFor(this.showQuestionScores());
                        await this.waitFor(this.sumScores());
                        await this.waitFor(this.reorderScores());
                        this.leaderboardAnimationPhase = null;
                    }
                });
            }),
        );
    }

    hideLeaderboard() {
        fadeOut(this.el, this.fadeInOutTime, () => {
            this.removeChildren(
                this.el.querySelector(".o_survey_session_leaderboard_container"),
            );
            fadeIn(this.sessionResults, this.fadeInOutTime);
        });
    }

    /**
     * @param {Element} scoreEl
     * @param {Integer} currentScore
     * @param {Integer} totalScore
     * @param {Integer} increment
     * @param {Boolean} plusSign
     * @private
     */
    animateScoreCounter(scoreEl, currentScore, totalScore, increment, plusSign) {
        this.waitForTimeout(() => {
            const nextScore = Math.min(totalScore, currentScore + increment);
            scoreEl.textContent = `${plusSign ? "+ " : ""}${Math.round(nextScore)} p`;
            if (nextScore < totalScore) {
                this.animateScoreCounter(
                    scoreEl,
                    nextScore,
                    totalScore,
                    increment,
                    plusSign,
                );
            }
        }, 25);
    }

    /**
     * @param {Element} scoreEl
     * @param {Integer} position
     * @param {Integer} offset
     * @param {Integer} timeout
     */
    animateMoveTo(scoreEl, position, offset, timeout) {
        let animationDone;
        const animationPromise = new Promise(function (resolve) {
            animationDone = resolve;
        });
        scoreEl.style.top = `calc(calc(${this.BAR_HEIGHT} * ${position}) + ${offset}rem)`;
        this.waitForTimeout(animationDone, timeout);
        return animationPromise;
    }

    /** @private */
    async prepareScores() {
        let animationDone;
        const animationPromise = new Promise(function (resolve) {
            animationDone = resolve;
        });
        this.waitForTimeout(() => {
            this.leaderboardAnimationPhase = "prepareScores";
            this.waitForTimeout(animationDone, 1000);
        }, 300);
        return animationPromise;
    }

    /** @private */
    async reorderScores() {
        let animationDone;
        const animationPromise = new Promise(function (resolve) {
            animationDone = resolve;
        });
        this.waitForTimeout(() => {
            this.leaderboardAnimationPhase = "reorderScores";
            this.el
                .querySelectorAll(".o_survey_session_leaderboard_item")
                .forEach(async (item) => {
                    const currentPosition = parseInt(item.dataset.currentPosition);
                    const newPosition = parseInt(item.dataset.newPosition);
                    if (currentPosition !== newPosition) {
                        const offset = newPosition > currentPosition ? 2 : -2;
                        await this.waitFor(
                            this.animateMoveTo(item, newPosition, offset, 300),
                        );
                        item.style.transition = "top ease-in-out .1s";
                        await this.waitFor(
                            this.animateMoveTo(item, newPosition, offset * -0.3, 100),
                        );
                        await this.waitFor(this.animateMoveTo(item, newPosition, 0, 0));
                        animationDone();
                    }
                });
        }, 1800);
        return animationPromise;
    }

    /** @private */
    async showQuestionScores() {
        let animationDone;
        const animationPromise = new Promise(function (resolve) {
            animationDone = resolve;
        });
        this.waitForTimeout(() => {
            this.leaderboardAnimationPhase = "showQuestionScores";
            this.el
                .querySelectorAll(".o_survey_session_leaderboard_bar_question")
                .forEach((barEl) => {
                    const scoreEl = barEl.querySelector(
                        ".o_survey_session_leaderboard_bar_question_score",
                    );
                    scoreEl.textContent = "0 p";
                    const questionScore = parseInt(barEl.dataset.questionScore);
                    if (questionScore && questionScore > 0) {
                        let increment = parseInt(barEl.dataset.maxQuestionScore / 40);
                        if (!increment || increment === 0) {
                            increment = 1;
                        }
                        scoreEl.textContent = "+ 0 p";
                        this.waitForTimeout(() => {
                            this.animateScoreCounter(
                                scoreEl,
                                0,
                                questionScore,
                                increment,
                                true,
                            );
                        }, 400);
                    }
                    this.waitForTimeout(animationDone, 1400);
                });
        }, 300);
        return animationPromise;
    }

    /** @private */
    async sumScores() {
        let animationDone;
        const animationPromise = new Promise(function (resolve) {
            animationDone = resolve;
        });
        this.waitForTimeout(() => {
            this.leaderboardAnimationPhase = "sumScores";
            this.el
                .querySelectorAll(".o_survey_session_leaderboard_item")
                .forEach((item) => {
                    const currentScore = parseInt(item.dataset.currentScore);
                    const updatedScore = parseInt(item.dataset.updatedScore);
                    let increment = parseInt(item.dataset.maxQuestionScore / 40);
                    if (!increment || increment === 0) {
                        increment = 1;
                    }
                    this.animateScoreCounter(
                        item.querySelector(".o_survey_session_leaderboard_score"),
                        currentScore,
                        updatedScore,
                        increment,
                        false,
                    );
                    this.waitForTimeout(animationDone, 500);
                });
        }, 1400);

        return animationPromise;
    }
}

registry
    .category("public.interactions")
    .add("survey.survey_session_leaderboard", SurveySessionLeaderboard);

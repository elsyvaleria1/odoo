/** @odoo-module native */
import { preloadBackground } from "@survey/js/survey_preload_image_mixin";
import { fadeIn, fadeOut } from "@survey/utils";
import { cookie } from "@web/core/browser/cookie";
import { inputModality } from "@web/core/input_modality";
import { formatWithTokens } from "@web/core/l10n/date_format";
import {
    compareDates,
    dateSettings,
    deserializeDate,
    deserializeDateTime,
    now,
    parseDate,
    parseDateTime,
    serializeDate,
    serializeDateTime,
} from "@web/core/l10n/dates";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { resizeTextArea } from "@web/core/utils/dom/autoresize";
import { scrollTo } from "@web/core/utils/dom/scrolling";
import { redirect } from "@web/core/utils/urls";
import { Interaction } from "@web/public/interaction";
import { ConfirmationDialog } from "@web/ui/dialog";

function bound(raw) {
    if (raw === undefined || raw === "") {
        return null;
    }
    const value = Number(raw);
    return Number.isNaN(value) ? null : value;
}

function outOfBounds(value, min, max) {
    if (Number.isNaN(value)) {
        return false;
    }
    return (min !== null && value < min) || (max !== null && value > max);
}

function isBlank(value) {
    return value === undefined || value === null || String(value).trim() === "";
}

export class SurveyForm extends Interaction {
    static selector = ".o_survey_form";
    dynamicSelectors = {
        ...this.dynamicSelectors,
        _background: () => document.querySelector("div.o_survey_background"),
    };
    dynamicContent = {
        _document: {
            "t-on-keydown": (ev) => {
                if (this.listenOnKeydown) {
                    this.onKeyDown(ev);
                }
            },
        },
        ".o_survey_lang_selector": { "t-on-change": this.onLanguageChange },
        ".o_survey_form_choice_item": { "t-on-change": this.onChoiceItemChange },
        ".o_survey_dropdown_select": { "t-on-change": this.onDropdownChange },
        ".o_survey_matrix_btn": { "t-on-click": this.onMatrixButtonClick },
        ".o_survey_question_slider": { "t-on-input.withTarget": this.onSliderInput },
        "input[type='radio']": { "t-on-click": this.onRadioChoiceClick },
        "button[type='submit']": { "t-on-click": this.onSubmit },
        ".o_survey_choice_img img": { "t-on-click": this.onChoiceImageClick },
        ".o_survey_save_later": { "t-on-click.prevent": this.onSaveLaterClick },
        ".o_survey_breadcrumb_container .breadcrumb-item a": {
            "t-on-click.prevent": this.onBreadcrumbClick,
        },
        ".o_survey_breadcrumb_container": {
            "t-att-class": () => ({ "d-none": !this.showBreadcrumb }),
        },
        _background: {
            "t-att-class": () => ({
                o_survey_background_transition: this.background.transition,
            }),
            "t-att-style": () => {
                if (this.background.shouldUpdate) {
                    return {
                        "background-image": `url("${this.background.image}")`,
                    };
                }
                return {};
            },
        },
    };

    setup() {
        this.dialog = this.services.dialog;
        this.fadeInOutDelay = 400;
        this.formEl = this.el.querySelector("form.o_survey-fill-form");
        const optionsData = this.el.querySelector("form.o_survey-fill-form").dataset;
        this.options = {
            scoringType: optionsData.scoringType,
            answerToken: optionsData.answerToken,
            surveyToken: optionsData.surveyToken,
            usersCanGoBack: !!optionsData.usersCanGoBack,
            sessionInProgress: !!optionsData.sessionInProgress,
            sessionBusChannel: optionsData.sessionBusChannel,
            isStartScreen: !!optionsData.isStartScreen,
            readonly: !!optionsData.readonly,
            hasAnswered: !!optionsData.hasAnswered,
            isPageDescription: !!optionsData.isPageDescription,
            questionsLayout: optionsData.questionsLayout,
            triggeredQuestionsByAnswer: JSON.parse(
                optionsData.triggeredQuestionsByAnswer,
            ),
            triggeringAnswersByQuestion: JSON.parse(
                optionsData.triggeringAnswersByQuestion,
            ),
            selectedAnswers: JSON.parse(optionsData.selectedAnswers),
            refreshBackground: !!optionsData.refreshBackground,
        };
        this.readonly = this.options.readonly;
        this.selectedAnswers = this.options.selectedAnswers;
        this.imgZoomerEl = null;
        this.listenOnKeydown = !this.readonly;
        this.nextScreenResult = undefined;
        this.showBreadcrumb = false;
        this.notificationDestructors = [];
        this.background = {
            transition: false,
            image: "",
            shouldUpdate: false,
        };

        const url = new URL(window.location.href);
        const languageChanged = url.searchParams.has("language-changed");
        if (languageChanged) {
            url.searchParams.delete("language-changed");
            window.history.replaceState({}, "", url.href);
        }
        const backgroundUrl = document
            .querySelector("div.o_survey_background")
            .style.backgroundImage?.slice(4, -1)
            .replace(/['"]/g, "");
        const language = document.querySelector(
            ".o_survey_lang_selector option[selected]",
        )?.value;
        if (languageChanged && backgroundUrl && language) {
            this.background.shouldUpdate = true;
            this.background.image = `/${language}/${backgroundUrl}`;
        }

        this.submitting = false;
        this.breadcrumbData = null;
        if (!cookie.get(`survey_${this.options.surveyToken}`)) {
            cookie.set(
                `survey_${this.options.surveyToken}`,
                this.options.answerToken,
                60 * 60 * 24,
                "optional",
            );
        }
        if (
            this.options.sessionInProgress &&
            (this.options.isStartScreen ||
                this.options.hasAnswered ||
                this.options.isPageDescription)
        ) {
            this.preventEnterSubmit = true;
        }
    }

    async willStart() {
        const busService = this.services.bus_service;
        if (this.options.sessionBusChannel && this.options.sessionInProgress) {
            this.registerCleanup(busService.addChannel(this.options.sessionBusChannel));
            await this.checkIsOnMainTab();
            this.registerCleanup(
                busService.subscribe(
                    "next_question",
                    this.onNextQuestionNotification.bind(this),
                ),
            );
            this.registerCleanup(
                busService.subscribe(
                    "end_session",
                    this.onEndSessionNotification.bind(this),
                ),
            );
        }
        this.initChoiceItems();
        this.initTextArea();
        this.enableSubmitButtons();
        this.focusOnFirstInput();
    }

    start() {
        this.surveyProgressEl = document.querySelector(".o_survey_progress_wrapper");
        this.surveyNavigationEl = document.querySelector(
            ".o_survey_navigation_wrapper",
        );
        if (!this.options.isStartScreen && !this.readonly) {
            this.initTimer();
            this.initBreadcrumb();
        }
        this.updateNavigationListeners();
        this.updateContent();
    }

    onKeyDown(ev) {
        const ctrlKeyClicked = ev.ctrlKey || ev.metaKey;
        const inputFocused =
            document.activeElement.tagName.toLowerCase() === "input" &&
            document.hasFocus();

        if (
            ["one_page", "page_per_section"].includes(this.options.questionsLayout) &&
            !this.options.isStartScreen
        ) {
            if (inputFocused && ev.key === "Enter") {
                ev.preventDefault();
            }
            if (!ctrlKeyClicked || ev.key !== "Enter") {
                return;
            }
        }

        if (this.el.querySelector("fieldset[disabled='disabled']")) {
            return;
        }
        if (this.imgZoomerEl && this.imgZoomerEl.isConnected && ev.key !== "Escape") {
            return;
        }

        const textareaFocused =
            document.activeElement.tagName.toLowerCase() === "textarea" &&
            document.hasFocus();

        if (
            (textareaFocused || inputFocused) &&
            (!ctrlKeyClicked || ev.key !== "Enter")
        ) {
            return;
        }

        if (ev.key === "Enter" || ev.key === "ArrowRight") {
            ev.preventDefault();
            if (this.showingCorrectAnswers) {
                this.showingCorrectAnswers = false;
                this.nextScreen(this.nextScreenPromise, this.nextScreenOptions);
                return;
            }
            if (this.preventEnterSubmit) {
                return;
            }
            this.submitForm({
                isFinish: !!this.el.querySelector("button[value='finish']"),
                nextSkipped: this.el.querySelector("button[value='next_skipped']")
                    ? ev.key === "Enter"
                    : false,
            });
            return;
        }
        if (ev.key === "ArrowLeft") {
            if (this.showingCorrectAnswers) {
                return;
            }
            document
                .querySelector(".o_survey_navigation_submit[value='previous']")
                ?.click();
            return;
        }
        if (this.showingCorrectAnswers || !ev.key.match(/[a-z]/i)) {
            return;
        }
        const choiceInputEl = this.el.querySelector(
            `input[data-selection-key=${ev.key.toUpperCase()}]`,
        );
        if (choiceInputEl) {
            choiceInputEl.checked = !choiceInputEl.checked;
            this.triggerEvent(choiceInputEl, "change");
            ev.preventDefault();
        }
    }

    /**
     * Handle visibility of comment area and conditional questions
     * The form (page) is then automatically submitted if:
     * - Survey is configured with one page per question and participants are allowed to go back,
     * - It is not the last question of the survey,
     * - The question is not waiting for a comment (with "Other" answer),
     *
     * @param {Event} ev
     */
    async onChoiceItemChange(ev) {
        const targetEl = ev.currentTarget;
        let questionEl = targetEl.closest(".o_survey_form_choice");
        if (!questionEl) {
            questionEl = targetEl.closest(".o_survey_question_matrix");
            if (!questionEl) {
                return;
            }
        }

        const surveyLastTriggeringAnswers = this.el.querySelector(
            ".o_survey_form_content_data",
        ).dataset.surveyLastTriggeringAnswers;
        if (surveyLastTriggeringAnswers) {
            const checkedAnswers = Array.from(
                this.el.querySelectorAll(`
                .o_survey_form_choice[data-question-type='simple_choice_radio'] input:checked,
                .o_survey_form_choice[data-question-type='multiple_choice'] input:checked
            `),
            ).map((input) => parseInt(input.value));
            const dropdownAnswers = Array.from(
                this.el.querySelectorAll(
                    ".o_survey_form_choice[data-question-type='dropdown'] select",
                ),
            )
                .filter((sel) => sel.value)
                .map((sel) => parseInt(sel.value));
            const currentSelectedAnswers = [...checkedAnswers, ...dropdownAnswers];
            const submitButton = this.el.querySelector("button[type=submit]");
            if (
                currentSelectedAnswers.some((answerId) =>
                    surveyLastTriggeringAnswers.includes(answerId),
                )
            ) {
                submitButton.value = "next";
                submitButton.textContent = _t("Continue");
                submitButton.classList.replace("btn-secondary", "btn-primary");
            } else {
                submitButton.value = "finish";
                submitButton.textContent = _t("Submit");
                submitButton.classList.replace("btn-primary", "btn-secondary");
            }
        }
        this.applyCommentAreaVisibility(questionEl);
        const isQuestionComplete = this.checkConditionalQuestionsConfiguration(
            targetEl,
            questionEl,
        );

        if (!isQuestionComplete || !this.options.usersCanGoBack) {
            return;
        }
        const isLastQuestion = !!this.el.querySelector("button[value='finish']");
        if (isLastQuestion) {
            return;
        }
        const questionHasComment =
            targetEl.classList.contains("o_survey_js_form_other_comment") ||
            targetEl.closest(".js_question-wrapper").querySelector(".o_survey_comment");
        if (!questionHasComment) {
            await this.submitForm({
                nextSkipped: !!questionEl.dataset.isSkippedQuestion,
            });
        }
    }

    /**
     * Handle dropdown select change — propagates conditional question visibility
     * and auto-advances in page_per_question layout.
     *
     * @param {Event} ev
     */
    async onDropdownChange(ev) {
        const selectEl = ev.currentTarget;
        const questionEl = selectEl.closest(".o_survey_form_choice");
        if (!questionEl) {
            return;
        }

        const previousValue = selectEl.dataset.previousValue || "";
        const newValue = selectEl.value;
        selectEl.dataset.previousValue = newValue;

        if (this.options.questionsLayout !== "page_per_question") {
            if (previousValue) {
                const idx = this.selectedAnswers.indexOf(parseInt(previousValue));
                if (idx !== -1) {
                    this.selectedAnswers.splice(idx, 1);
                }
            }
            if (newValue) {
                this.selectedAnswers.push(parseInt(newValue));
            }
            const toRecompute = (
                this.options.triggeredQuestionsByAnswer[previousValue] || []
            ).concat(this.options.triggeredQuestionsByAnswer[newValue] || []);
            if (toRecompute.length) {
                this.applyConditionalQuestionsVisibility(new Set(toRecompute));
            }
        }

        if (
            newValue &&
            this.options.questionsLayout === "page_per_question" &&
            this.options.usersCanGoBack
        ) {
            const isLastQuestion = !!this.el.querySelector("button[value='finish']");
            if (!isLastQuestion) {
                await this.submitForm({
                    nextSkipped: !!questionEl.dataset.isSkippedQuestion,
                });
            }
        }
    }

    /**
     * Called when an image on an answer in multi-answers question is clicked.
     * @param {Event} ev
     */
    onChoiceImageClick(ev) {
        if (!inputModality.isTouch) {
            ev.preventDefault();
        }
        const [zoomerEl] = this.renderAt(
            "survey.survey_image_zoomer",
            { sourceImage: ev.currentTarget.src },
            document.body,
        );
        this.imgZoomerEl = zoomerEl;
    }

    async onSaveLaterClick(ev) {
        const linkEl = ev.currentTarget;
        const surveyToken = linkEl.dataset.surveyToken;
        const answerToken = linkEl.dataset.answerToken;
        try {
            const result = await rpc(
                `/survey/save_later/${surveyToken}/${answerToken}`,
            );
            if (result.success) {
                linkEl.innerHTML = `<i class="fa-solid fa-check me-1"></i>Link sent to ${result.email}`;
                linkEl.classList.replace("text-muted", "text-success");
            } else {
                linkEl.textContent =
                    result.error === "no_email"
                        ? "No email address on file"
                        : "Could not send link";
                linkEl.classList.replace("text-muted", "text-danger");
            }
        } catch {
            linkEl.textContent = "Failed to send link";
            linkEl.classList.replace("text-muted", "text-danger");
        }
    }

    removeTimer() {
        if (this.timerEl) {
            this.services["public.interactions"].stopInteractions(this.timerEl);
            this.timerEl.remove();
        }
    }

    /**
     * @param {Event} ev
     * @param {HTMLInputElement} sliderEl
     */
    onSliderInput(ev, sliderEl) {
        const valueEl = sliderEl
            .closest(".o_survey_answer_wrapper")
            ?.querySelector(".o_survey_slider_value");
        if (valueEl) {
            valueEl.textContent = sliderEl.value;
        }
    }

    onMatrixButtonClick(ev) {
        if (this.readonly) {
            return;
        }
        const targetEl = ev.currentTarget;
        const inputEl = targetEl.querySelector("input");
        inputEl.checked = !inputEl.checked;
        this.triggerEvent(inputEl, "change");
    }

    onRadioChoiceClick(ev) {
        const targetEl = ev.currentTarget;
        if (targetEl.classList.contains("o_survey_form_choice_item_selected")) {
            targetEl.checked = false;
            targetEl.classList.remove("o_survey_form_choice_item_selected");
            this.triggerEvent(targetEl, "change");
        } else {
            this.el
                .querySelector(
                    `input[type="radio"][name="${targetEl.getAttribute(
                        "name",
                    )}"].o_survey_form_choice_item_selected`,
                )
                ?.classList.remove("o_survey_form_choice_item_selected");
            targetEl.classList.add("o_survey_form_choice_item_selected");
        }
    }

    onSubmit(ev) {
        ev.preventDefault();
        const targetEl = ev.currentTarget;
        if (targetEl.value === "previous") {
            this.submitForm({
                previousPageId: parseInt(targetEl.dataset.previousPageId),
            });
        } else if (targetEl.value === "next_skipped") {
            this.submitForm({ nextSkipped: true });
        } else if (targetEl.value === "finish" && !this.options.sessionInProgress) {
            this.dialog.add(ConfirmationDialog, {
                title: _t("Submit confirmation"),
                body: _t("Are you sure you want to submit the survey?"),
                confirmLabel: _t("Submit"),
                confirm: () => {
                    this.waitForTimeout(() => this.submitForm({ isFinish: true }), 0);
                },
                cancel: () => {},
            });
        } else {
            this.submitForm();
        }
    }

    onBreadcrumbClick(ev) {
        const previousPageId = Number(
            ev.currentTarget.closest(".breadcrumb-item").dataset.pageId,
        );
        this.submitForm({ previousPageId });
    }

    /**
     * Handle some extra computation to find a suitable "fadeInOutDelay" based
     * on the delay between the time of the question change by the host and the
     * time of reception of the event. This will allow us to account for a
     * little bit of server lag (up to 1 second) while giving everyone a fair
     * experience on the quiz.
     *
     * e.g 1:
     * - The host switches the question
     * - We receive the event 200 ms later due to server lag
     * - -> The fadeInOutDelay will be 400 ms (200ms delay + 400ms * 2 fade in fade out)
     *
     * e.g 2:
     * - The host switches the question
     * - We receive the event 600 ms later due to bigger server lag
     * - -> The fadeInOutDelay will be 200ms (600ms delay + 200ms * 2 fade in fade out)
     *
     * @param {object} notification notification of type `next_question` as
     * specified by the bus.
     */
    onNextQuestionNotification(notification) {
        let serverDelayMS =
            (now().epochMilliseconds / 1000 - notification.question_start) * 1000;
        if (serverDelayMS < 0) {
            serverDelayMS = 0;
        } else if (serverDelayMS > 1000) {
            serverDelayMS = 1000;
        }
        this.fadeInOutDelay = (1000 - serverDelayMS) / 2;
        this.goToNextPage();
    }

    onEndSessionNotification() {
        if (this.options.isStartScreen) {
            return;
        }
        this.fadeInOutDelay = 400;
        this.goToNextPage(true);
    }

    onLanguageChange() {
        const languageCode = this.el.querySelector(
            ".o_survey_lang_selector[name='lang_code']",
        ).value;
        const pathName = document.location.pathname;
        const indexOfSurvey = pathName.indexOf("/survey/");
        if (indexOfSurvey >= 0) {
            const url = new URL(window.location.href);
            url.pathname = `/${languageCode}${pathName.substring(indexOfSurvey)}`;
            url.searchParams.set("language-changed", true);
            redirect(url.href);
        }
    }

    /**
     * Go to the next page of the survey.
     *
     * @param {boolean} isFinish Whether the survey is done or not
     */
    goToNextPage(isFinish = false) {
        fadeOut(
            this.el.querySelectorAll(".o_survey_main_title, .o_lang_selector"),
            400,
        );
        this.preventEnterSubmit = false;
        this.readonly = false;
        this.nextScreen(
            rpc(
                `/survey/next_question/${this.options.surveyToken}/${this.options.answerToken}`,
            ),
            {
                initTimer: true,
                isFinish,
            },
        );
    }

    /**
     * This function will send a json rpc call to the server to
     * - start the survey (if we are on start screen)
     * - submit the answers of the current page
     * Before submitting the answers, they are first validated to avoid latency from the server
     * and allow a fade out/fade in transition of the next question.
     *
     * @param {Array} [options]
     * @param {Integer} [options.previousPageId] navigates to page id
     * @param {Boolean} [options.nextSkipped] navigates to next skipped page or question
     * @param {Boolean} [options.skipValidation] skips JS validation
     * @param {Boolean} [options.initTime] will force the re-init of the timer after next
     *   screen transition
     * @param {Boolean} [options.isFinish] fades out breadcrumb and timer
     */
    async submitForm(options = {}) {
        if (this.submitting) {
            return;
        }
        this.submitting = true;
        const params = {};
        if (options.previousPageId) {
            params.previous_page_id = options.previousPageId;
        }
        if (options.nextSkipped) {
            params.next_skipped_page_or_question = true;
        }
        let route = "/survey/submit";
        if (this.options.isStartScreen) {
            params.lang_code = this.el.querySelector(
                ".o_survey_lang_selector[name='lang_code']",
            ).value;
            route = "/survey/begin";
            if (this.options.questionsLayout === "page_per_question") {
                fadeOut(this.el.querySelector(".o_survey_main_title"), 400);
            }
            fadeOut(this.el.querySelector(".o_survey_lang_selector"), 400);
        } else {
            const formData = new FormData(this.formEl);
            if (!options.skipValidation) {
                if (!this.validateForm(this.formEl, formData)) {
                    this.submitting = false;
                    return;
                }
            }
            this.prepareSubmitValues(formData, params);
        }

        if (this.options.sessionInProgress) {
            this.fadeInOutDelay = 400;
            this.readonly = true;
        }

        const submitPromise = rpc(
            `${route}/${this.options.surveyToken}/${this.options.answerToken}`,
            params,
        );

        try {
            if (
                !this.options.isStartScreen &&
                this.options.scoringType === "scoring_with_answers_after_page"
            ) {
                const [correctAnswers] = await this.waitFor(submitPromise);
                if (
                    Object.keys(correctAnswers).length &&
                    this.el.querySelector(".js_question-wrapper")
                ) {
                    this.showCorrectAnswers(correctAnswers, submitPromise, options);
                    return;
                }
            }
            await this.nextScreen(submitPromise, options);
        } finally {
            this.submitting = false;
            if (this.options.sessionInProgress) {
                this.readonly = false;
            }
        }
    }

    /**
     * Will fade out / fade in the next screen based on passed promise and options.
     *
     * @param {Promise} nextScreenPromise
     * @param {Object} options see 'submitForm' for details
     */
    async nextScreen(nextScreenPromise, options) {
        const selectorsToFadeout = [".o_survey_form_content"];
        if (options.isFinish && !this.nextScreenResult?.data?.has_skipped_questions) {
            document
                .querySelector(".o_survey_main_title_fade")
                ?.classList.replace("opacity-100", "opacity-0");

            selectorsToFadeout.push(".breadcrumb", ".o_survey_timer");
            cookie.delete(`survey_${this.options.surveyToken}`);
        }
        const fadeOutPromise = this.waitFor(
            fadeOut(
                this.el.querySelectorAll(selectorsToFadeout.join(",")),
                this.fadeInOutDelay,
            ),
        );
        if (this.options.refreshBackground) {
            this.background.transition = true;
        }

        const nextScreenWithBackgroundPromise = (async () => {
            const [, result] = await nextScreenPromise;
            this.nextScreenResult = result;
            if (this.options.refreshBackground && result.data?.background_image_url) {
                return preloadBackground(result.data.background_image_url);
            } else {
                return Promise.resolve();
            }
        })();

        await this.waitFor(
            Promise.all([fadeOutPromise, nextScreenWithBackgroundPromise]),
        );
        return this.onNextScreenDone(options);
    }

    /**
     * Handle server side validation and display eventual error messages.
     *
     * @param {Object} options see 'submitForm' for details
     */
    onNextScreenDone(options) {
        const result = this.nextScreenResult;
        const data = result?.data || {};
        if (
            (!(options && options.isFinish) || data.has_skipped_questions) &&
            !this.options.sessionInProgress
        ) {
            this.preventEnterSubmit = false;
        }
        if (data.fields && data.error === "validation") {
            fadeIn(this.el.querySelector(".o_survey_form_content"), 0);
            this.showErrors(data.fields);
            return;
        }
        if (!result || data.error) {
            this.notificationDestructors.push(
                this.services.notification.add(
                    _t("There was an error during the validation of the survey."),
                    { type: "danger", sticky: true },
                ),
            );
            return;
        }
        if (data.redirect_url) {
            redirect(data.redirect_url);
            return;
        }
        this.swapFragments(result);
        const formContentEl = this.el.querySelector(".o_survey_form_content");
        this.surveyProgressEl = document.querySelector(".o_survey_progress_wrapper");
        this.surveyNavigationEl = document.querySelector(
            ".o_survey_navigation_wrapper",
        );
        if (this.surveyNavigationEl) {
            this.updateNavigationListeners();
        }

        if (
            this.options.questionsLayout === "page_per_question" &&
            this.el.querySelector(".o_survey_finished")
        ) {
            options.isFinish = true;
        }

        if (
            this.options.isStartScreen &&
            this.options.questionsLayout !== "page_per_question"
        ) {
            document
                .querySelector(".o_survey_main_title_fade")
                ?.classList.replace("opacity-0", "opacity-100");
        }

        if (this.options.isStartScreen || (options && options.initTimer)) {
            this.initTimer();
            this.options.isStartScreen = false;
        } else {
            if (this.options.sessionInProgress) {
                this.removeTimer();
            }
        }
        if (options && options.isFinish && !data.has_skipped_questions) {
            if (this.breadcrumbEl) {
                this.showBreadcrumb = false;
                this.breadcrumbEl.replaceChildren();
            }
            this.removeTimer();
        } else {
            this.updateBreadcrumb();
        }
        this.initChoiceItems();
        this.initTextArea();

        if (this.options.sessionInProgress && this.options.isPageDescription) {
            this.preventEnterSubmit = true;
        }
        if (this.options.refreshBackground) {
            this.background.transition = false;
            this.background.image = data.background_image_url;
            this.background.shouldUpdate = true;
        }
        fadeIn(formContentEl, this.fadeInOutDelay);
        this.enableSubmitButtons();
        this.focusOnFirstInput();
        this.scrollTop();
        this.scrollToFirstError();
    }

    validateForm(formEl, formData) {
        const errors = {};
        const validationEmailMsg = _t("This answer must be an email address.");
        const validationDateMsg = _t("This is not a date");
        this.resetErrors();
        const data = {};
        for (const [key, value] of formData.entries()) {
            data[key] = value;
        }
        const inactiveQuestionIds = this.options.sessionInProgress
            ? []
            : this.getInactiveConditionalQuestionIds();
        for (const inputEl of formEl.querySelectorAll("[data-question-type]")) {
            const questionWrapperEl = inputEl.closest(".js_question-wrapper");
            const questionId = questionWrapperEl.id;
            if (inactiveQuestionIds.includes(parseInt(questionId))) {
                continue;
            }
            const questionRequired = questionWrapperEl.hasAttribute("data-required");
            const constrErrorMsg = questionWrapperEl.dataset.constrErrorMsg || "";
            const validationErrorMsg =
                questionWrapperEl.dataset.validationErrorMsg || "";
            const inputData = {
                questionType: inputEl.dataset.questionType,
                validationLengthMin: bound(inputEl.dataset.validationLengthMin),
                validationLengthMax: bound(inputEl.dataset.validationLengthMax),
                validationFloatMin: bound(inputEl.dataset.validationFloatMin),
                validationFloatMax: bound(inputEl.dataset.validationFloatMax),
                minDate: inputEl.dataset.minDate,
                maxDate: inputEl.dataset.maxDate,
            };
            switch (inputData.questionType) {
                case "char_box":
                    if (questionRequired && !inputEl.value) {
                        errors[questionId] = constrErrorMsg;
                    } else if (
                        inputEl.value &&
                        inputEl.type === "email" &&
                        !this.validateEmail(inputEl.value)
                    ) {
                        errors[questionId] = validationEmailMsg;
                    } else {
                        const lengthMin = inputData.validationLengthMin;
                        const lengthMax = inputData.validationLengthMax;
                        const length = inputEl.value.length;
                        if (outOfBounds(length, lengthMin, lengthMax)) {
                            errors[questionId] = validationErrorMsg;
                        }
                    }
                    break;
                case "text_box":
                    if (questionRequired && !inputEl.value) {
                        errors[questionId] = constrErrorMsg;
                    }
                    break;
                case "numerical_box":
                    if (questionRequired && isBlank(data[questionId])) {
                        errors[questionId] = constrErrorMsg;
                    } else {
                        const floatMin = inputData.validationFloatMin;
                        const floatMax = inputData.validationFloatMax;
                        const value = parseFloat(inputEl.value);
                        if (outOfBounds(value, floatMin, floatMax)) {
                            errors[questionId] = validationErrorMsg;
                        }
                    }
                    break;
                case "date":
                case "datetime":
                    if (questionRequired && isBlank(data[questionId])) {
                        errors[questionId] = constrErrorMsg;
                    } else if (data[questionId]) {
                        const [parse, deserialize] =
                            inputData.questionType === "date"
                                ? [parseDate, deserializeDate]
                                : [parseDateTime, deserializeDateTime];
                        const date = parse(inputEl.value);
                        if (!date) {
                            errors[questionId] = validationDateMsg;
                        } else {
                            const maxDate =
                                inputData.maxDate && deserialize(inputData.maxDate);
                            const minDate =
                                inputData.minDate && deserialize(inputData.minDate);
                            if (
                                (maxDate && compareDates(date, maxDate) > 0) ||
                                (minDate && compareDates(date, minDate) < 0)
                            ) {
                                errors[questionId] = validationErrorMsg;
                            }
                        }
                    }
                    break;
                case "scale":
                    if (questionRequired && isBlank(data[questionId])) {
                        errors[questionId] = constrErrorMsg;
                    }
                    break;
                case "simple_choice_radio":
                case "multiple_choice":
                    if (questionRequired) {
                        const textareaEl = questionWrapperEl.querySelector("textarea");
                        if (!data[questionId]) {
                            errors[questionId] = constrErrorMsg;
                        } else if (data[questionId] === "-1" && !textareaEl.value) {
                            errors[questionId] = constrErrorMsg;
                        }
                    }
                    break;
                case "matrix":
                    if (questionRequired) {
                        const subQuestionsIds = JSON.parse(
                            inputEl.dataset.subQuestions,
                        );
                        const questionBodySelector = `div[id="${questionId}"] > .o_survey_question_matrix > tbody`;
                        for (const subQuestionId of subQuestionsIds) {
                            if (!(`${questionId}_${subQuestionId}` in data)) {
                                errors[questionId] = constrErrorMsg;
                                this.el
                                    .querySelector(
                                        `${questionBodySelector} > tr[id="${subQuestionId}"] > th`,
                                    )
                                    .classList.add("bg-danger");
                            }
                        }
                    }
                    break;
            }
        }
        if (Object.keys(errors).length > 0) {
            this.showErrors(errors);
            return false;
        }
        return true;
    }

    validateEmail(email) {
        const emailParts = email.split("@");
        return emailParts.length === 2 && emailParts[0] && emailParts[1];
    }

    /**
     * For each type of question, extract the answer from inputs or textarea (comment or answer)
     * @param {FormData} formData
     * @param {Object} params
     */
    prepareSubmitValues(formData, params) {
        for (const [key, value] of formData) {
            if (["csrf_token", "page_id", "question_id", "token"].includes(key)) {
                params[key] = value;
            }
        }

        for (const el of this.el.querySelectorAll("[data-question-type]")) {
            switch (el.dataset.questionType) {
                case "text_box":
                case "char_box":
                    params[el.name] = el.value;
                    break;
                case "numerical_box":
                    params[el.name] = el.value;
                    break;
                case "date":
                case "datetime": {
                    const [parse, serialize] =
                        el.dataset.questionType === "date"
                            ? [parseDate, serializeDate]
                            : [parseDateTime, serializeDateTime];
                    const date = parse(el.value);
                    params[el.name] = date ? serialize(date) : "";
                    break;
                }
                case "scale":
                case "simple_choice_radio":
                case "multiple_choice":
                    params = this.prepareSubmitChoices(params, el, el.dataset.name);
                    break;
                case "dropdown": {
                    const selectEl = el.querySelector("select");
                    if (selectEl && selectEl.value) {
                        params = this.prepareSubmitAnswer(
                            params,
                            el.dataset.name,
                            selectEl.value,
                        );
                    }
                    params = this.prepareSubmitComment(
                        params,
                        el,
                        el.dataset.name,
                        false,
                    );
                    break;
                }
                case "matrix":
                    params = this.prepareSubmitAnswersMatrix(params, el);
                    break;
                case "ranking":
                case "constant_sum":
                    params = this.prepareSubmitPerAnswerValues(params, el);
                    break;
                case "file_upload":
                    params = this.prepareSubmitFileUpload(params, el);
                    break;
            }
        }
    }

    prepareSubmitPerAnswerValues(params, wrapperEl) {
        const values = {};
        for (const inputEl of wrapperEl.querySelectorAll("[data-answer-id]")) {
            const answerId = inputEl.dataset.answerId;
            const raw =
                inputEl.tagName === "INPUT"
                    ? inputEl.value
                    : inputEl.querySelector("input")?.value;
            if (raw !== undefined && raw !== "") {
                values[answerId] = Number(raw);
            }
        }
        if (Object.keys(values).length) {
            params[wrapperEl.dataset.name] = values;
        }
        return params;
    }

    prepareSubmitFileUpload(params, wrapperEl) {
        const attachmentId = wrapperEl.dataset.attachmentId;
        if (attachmentId) {
            params[wrapperEl.dataset.name] = Number(attachmentId);
        }
        return params;
    }

    prepareSubmitChoices(params, parentEl, questionId) {
        for (const el of parentEl.querySelectorAll("input:checked")) {
            if (el.value !== "-1") {
                params = this.prepareSubmitAnswer(params, questionId, el.value);
            }
        }
        params = this.prepareSubmitComment(params, parentEl, questionId, false);
        return params;
    }

    prepareSubmitAnswersMatrix(params, matrixTable) {
        for (const el of matrixTable.querySelectorAll("input:checked")) {
            params = this.prepareSubmitAnswerMatrix(
                params,
                matrixTable.dataset.name,
                Number(el.dataset.rowId),
                el.value,
            );
        }
        params = this.prepareSubmitComment(
            params,
            matrixTable.closest(".js_question-wrapper"),
            matrixTable.dataset.name,
            true,
        );
        return params;
    }

    prepareSubmitAnswerMatrix(params, questionId, rowId, colId, isComment) {
        const value = questionId in params ? params[questionId] : {};
        if (isComment) {
            value["comment"] = colId;
        } else {
            if (rowId in value) {
                value[rowId].push(colId);
            } else {
                value[rowId] = [colId];
            }
        }
        params[questionId] = value;
        return params;
    }

    prepareSubmitAnswer(params, questionId, value) {
        if (questionId in params) {
            if (params[questionId].constructor === Array) {
                params[questionId].push(value);
            } else {
                params[questionId] = [params[questionId], value];
            }
        } else {
            params[questionId] = value;
        }
        return params;
    }

    prepareSubmitComment(params, parentEl, questionId, isMatrix) {
        for (const el of parentEl.querySelectorAll("textarea")) {
            if (el.value) {
                const value = { comment: el.value };
                if (isMatrix) {
                    params = this.prepareSubmitAnswerMatrix(
                        params,
                        questionId,
                        el.name,
                        el.value,
                        true,
                    );
                } else {
                    params = this.prepareSubmitAnswer(params, questionId, value);
                }
            }
        }
        return params;
    }

    initTextArea() {
        for (const el of this.el.querySelectorAll("textarea")) {
            resizeTextArea(el);
        }
    }

    initChoiceItems() {
        for (const el of this.el.querySelectorAll(
            "input[type='radio'],input[type='checkbox']",
        )) {
            const matrixButtonEl = el.closest(".o_survey_matrix_btn");
            if (el.checked) {
                const targetEl = matrixButtonEl ? matrixButtonEl : el.closest("label");
                targetEl.classList.add("o_survey_selected");
            }
        }
    }

    initBreadcrumb() {
        this.breadcrumbEl = this.el.querySelector(".o_survey_breadcrumb_container");
        if (!this.breadcrumbEl) {
            return;
        }
        const data = this.breadcrumbEl.dataset;
        this.breadcrumbData = {
            surveyCanGoBack: !!data.canGoBack,
            pages: JSON.parse(data.pages),
        };
        this.showBreadcrumb = true;
        this.updateBreadcrumb();
    }

    updateBreadcrumb() {
        if (!this.breadcrumbEl) {
            this.initBreadcrumb();
        } else {
            const pageId = this.el.querySelector("input[name='page_id']")?.value;
            if (pageId) {
                this.breadcrumbEl.replaceChildren();
                this.renderAt(
                    "survey.survey_breadcrumb_template",
                    {
                        currentPageId: parseInt(pageId),
                        ...this.breadcrumbData,
                    },
                    this.breadcrumbEl,
                );
            } else {
                this.showBreadcrumb = false;
            }
        }
    }

    initTimer() {
        this.removeTimer();
        const timerDataEl = this.el.querySelector(".o_survey_form_content_data");
        if (!timerDataEl) {
            return;
        }
        const timerData = timerDataEl.dataset;
        const questionTimeLimitReached = !!timerData.questionTimeLimitReached;
        const timeLimitMinutes = Number(timerData.timeLimitMinutes);
        const hasAnswered = !!timerData.hasAnswered;
        if (!questionTimeLimitReached && !hasAnswered && timeLimitMinutes) {
            this.timerEl = document.createElement("span");
            this.timerEl.classList.add("o_survey_timer");
            this.insert(
                this.timerEl,
                this.el.querySelector(".o_survey_timer_container"),
            );
            this.addListener(this.timerEl, "time_up", async () => {
                if (this.showingCorrectAnswers) {
                    await this.nextScreen(
                        this.nextScreenPromise,
                        this.nextScreenOptions,
                    );
                }
                this.submitForm({
                    skipValidation: true,
                    isFinish: !this.options.sessionInProgress,
                });
            });
        }
    }

    /**
     * Checks, if the 'other' choice is checked. Applies only if the comment count as answer.
     *   If not checked : Clear the comment textarea, hide and disable it
     *   If checked : enable the comment textarea, show and focus on it
     *
     * @param {HTMLElement} choiceItemGroupEl
     */
    applyCommentAreaVisibility(choiceItemGroupEl) {
        if (!choiceItemGroupEl) {
            return;
        }
        const otherItemEl = choiceItemGroupEl.querySelector(
            ".o_survey_js_form_other_comment",
        );
        const commentInputEl = choiceItemGroupEl.querySelector("textarea[type='text']");
        if (!commentInputEl) {
            return;
        }
        if (
            otherItemEl?.checked ||
            commentInputEl.classList.contains("o_survey_comment")
        ) {
            commentInputEl.disabled = false;
            commentInputEl
                .closest(".o_survey_comment_container")
                .classList.remove("d-none");
            if (otherItemEl?.checked) {
                commentInputEl.focus();
            }
        } else {
            commentInputEl.value = "";
            commentInputEl
                .closest(".o_survey_comment_container")
                .classList.add("d-none");
            commentInputEl.disabled = true;
        }
    }

    focusOnFirstInput() {
        const inputEls =
            this.el
                .querySelector(".js_question-wrapper")
                ?.querySelectorAll(
                    "input[type='text'],input[type='number'],textarea",
                ) || [];
        let firstTextInputEl = null;
        for (const inputEl of inputEls) {
            if (
                inputEl.classList.contains("form-control") &&
                !inputEl.classList.contains("o_survey_comment")
            ) {
                firstTextInputEl = inputEl;
                break;
            }
        }
        if (firstTextInputEl && !inputModality.isTouch) {
            firstTextInputEl.focus();
        }
    }

    async checkIsOnMainTab() {
        const check = async (shouldReloadMasterTab) => {
            if (await this.services.multi_tab.isOnMainTab()) {
                if (shouldReloadMasterTab) {
                    window.location.reload();
                }
                return;
            }
            const checkAgain = () => this.waitForTimeout(() => check(true), 1000);
            this.dialog.add(ConfirmationDialog, {
                title: _t("A problem has occurred"),
                body: _t(
                    "To take this survey, please close all other tabs on %(hostname)s",
                    { hostname: window.location.hostname },
                ),
                confirmLabel: _t("Continue here"),
                confirm: checkAgain,
                dismiss: checkAgain,
            });
        };
        return check(false);
    }

    /**
     * For single and multiple choice questions, propagate questions visibility
     * based on conditional questions and (de)selected triggers
     *
     * @param {HTMLInputElement} targetEl
     * @param {HTMLElement} choiceItemGroupEl
     * @returns {boolean} Whether the question is considered completed
     */
    checkConditionalQuestionsConfiguration(targetEl, choiceItemGroupEl) {
        let isQuestionComplete = false;
        const matrixButtonEl = targetEl.closest(".o_survey_matrix_btn");
        if (targetEl.type === "radio") {
            if (matrixButtonEl) {
                for (const el of matrixButtonEl.closest("tr")?.querySelectorAll("td") ||
                    []) {
                    el.classList.remove("o_survey_selected");
                }
                if (targetEl.checked) {
                    matrixButtonEl.classList.add("o_survey_selected");
                }
                if (this.options.questionsLayout === "page_per_question") {
                    const subQuestionsIds = JSON.parse(
                        matrixButtonEl.closest("table").dataset.subQuestions,
                    );
                    const completedQuestions = [];
                    for (const id of subQuestionsIds) {
                        if (this.el.querySelector(`tr[id="${id}"] input:checked`)) {
                            completedQuestions.push(id);
                        }
                    }
                    isQuestionComplete =
                        completedQuestions.length === subQuestionsIds.length;
                }
            } else {
                const previouslySelectedAnswerEl = choiceItemGroupEl.querySelector(
                    "label.o_survey_selected",
                );
                previouslySelectedAnswerEl?.classList.remove("o_survey_selected");
                const previouslySelectedAnswerId =
                    previouslySelectedAnswerEl?.querySelector("input").value;
                if (
                    previouslySelectedAnswerId &&
                    this.options.questionsLayout !== "page_per_question"
                ) {
                    this.selectedAnswers.splice(
                        this.selectedAnswers.indexOf(
                            parseInt(previouslySelectedAnswerId),
                        ),
                        1,
                    );
                }

                const newlySelectedAnswerEl = targetEl.closest("label");
                const newlySelectedAnswerId = targetEl.value;
                const isNewSelection =
                    newlySelectedAnswerId !== previouslySelectedAnswerId;
                if (isNewSelection) {
                    newlySelectedAnswerEl.classList.add("o_survey_selected");
                    isQuestionComplete =
                        this.options.questionsLayout === "page_per_question";
                    if (!isQuestionComplete) {
                        this.selectedAnswers.push(parseInt(newlySelectedAnswerId));
                    }
                }

                if (this.options.questionsLayout !== "page_per_question") {
                    const toRecompute = (
                        this.options.triggeredQuestionsByAnswer[
                            previouslySelectedAnswerId
                        ] || []
                    ).concat(
                        this.options.triggeredQuestionsByAnswer[
                            newlySelectedAnswerId
                        ] || [],
                    );
                    const conditionalQuestionsToRecomputeVisibility = new Set(
                        toRecompute,
                    );
                    this.applyConditionalQuestionsVisibility(
                        conditionalQuestionsToRecomputeVisibility,
                    );
                }
            }
        } else {
            if (matrixButtonEl) {
                matrixButtonEl.classList.toggle("o_survey_selected");
            } else {
                const labelEl = targetEl.closest("label");
                labelEl.classList.toggle("o_survey_selected");
                const answerId = targetEl.value;

                if (this.options.questionsLayout !== "page_per_question") {
                    if (labelEl.classList.contains("o_survey_selected")) {
                        this.selectedAnswers.push(parseInt(answerId));
                    } else {
                        this.selectedAnswers.splice(
                            this.selectedAnswers.indexOf(parseInt(answerId)),
                            1,
                        );
                    }
                    this.applyConditionalQuestionsVisibility(
                        this.options.triggeredQuestionsByAnswer[answerId],
                    );
                }
            }
        }
        return isQuestionComplete;
    }

    /**
     * Apply visibility rules of conditional questions.
     * When layout is "one_page", hide the empty sections (the ones without description and
     * which don't have any question to be displayed because of conditional questions).
     *
     * @param {Number[] | String[] | Set | undefined} questionIds Conditional questions ids
     */
    applyConditionalQuestionsVisibility(questionIds) {
        if (!questionIds || (!questionIds.length && !questionIds.size)) {
            return;
        }
        for (const questionId of questionIds) {
            const dependingQuestionEl = this.el.querySelector(
                `.js_question-wrapper[id="${questionId}"]`,
            );
            if (!dependingQuestionEl) {
                continue;
            }
            const hasNoSelectedTriggers = !this.options.triggeringAnswersByQuestion[
                questionId
            ].some((answerId) => this.selectedAnswers.includes(parseInt(answerId)));
            dependingQuestionEl.classList.toggle("d-none", hasNoSelectedTriggers);
            if (hasNoSelectedTriggers) {
                for (const el of dependingQuestionEl.querySelectorAll("input")) {
                    if (el.type === "text" || el.type === "number") {
                        el.value = "";
                    } else if (el.checked) {
                        el.checked = false;
                        this.triggerEvent(el, "change");
                    }
                }
                for (const el of dependingQuestionEl.querySelectorAll("textarea")) {
                    el.value = "";
                }
            }
        }
        if (this.options.questionsLayout === "one_page") {
            const sections = this.el.querySelectorAll(".js_section_wrapper");
            for (const section of sections) {
                if (!section.querySelector(".o_survey_description")) {
                    const hasVisibleQuestions = !!section.querySelector(
                        ".js_question-wrapper:not(.d-none)",
                    );
                    section.classList.toggle("d-none", !hasVisibleQuestions);
                }
            }
        }
    }

    getInactiveConditionalQuestionIds() {
        const inactiveQuestionIds = [];
        for (const [questionId, answerIds] of Object.entries(
            this.options.triggeringAnswersByQuestion || {},
        )) {
            if (
                !answerIds.some((answerId) =>
                    this.selectedAnswers.includes(parseInt(answerId)),
                )
            ) {
                inactiveQuestionIds.push(parseInt(questionId));
            }
        }
        return inactiveQuestionIds;
    }

    showCorrectAnswers(correctAnswers, submitPromise, options) {
        for (const questionId of Object.keys(correctAnswers)) {
            this.showQuestionAnswer(correctAnswers, questionId);
        }
        const formEl = document.querySelector("form");
        for (const el of formEl.querySelectorAll("input, textarea, label, td")) {
            el.blur();
            el.classList.add("pe-none");
        }

        this.nextScreenPromise = submitPromise;
        this.nextScreenOptions = options;
        this.showingCorrectAnswers = true;

        formEl.querySelector("button[type='submit']").classList.add("d-none");
        const nextPageButtonEl = formEl.querySelector("button[id='next_page']");
        nextPageButtonEl.classList.remove("d-none");
        this.addListener(nextPageButtonEl, "click", async (ev) => {
            ev.preventDefault();
            this.showingCorrectAnswers = false;
            return this.nextScreen(submitPromise, options);
        });
    }

    showQuestionAnswer(correctAnswers, questionId) {
        const correctAnswer = correctAnswers[questionId];
        const questionWrapperEl = this.el.querySelector(
            `.js_question-wrapper[id="${questionId}"]`,
        );
        const answerWrapperEl = questionWrapperEl.querySelector(
            ".o_survey_answer_wrapper",
        );
        const questionType =
            questionWrapperEl.querySelector("[data-question-type]").dataset
                .questionType;

        if (["numerical_box", "date", "datetime"].includes(questionType)) {
            const inputEl = answerWrapperEl.querySelector("input");
            let isCorrect;
            if (questionType === "numerical_box") {
                isCorrect = inputEl.valueAsNumber === correctAnswer;
            } else if (questionType === "datetime") {
                const datetime = parseDateTime(inputEl.value);
                const value = datetime
                    ? formatWithTokens(
                          datetime.withTimeZone("UTC"),
                          "MM/dd/yyyy HH:mm:ss",
                          { locale: dateSettings.locale, numberingSystem: "latn" },
                      )
                    : "";
                isCorrect = value === correctAnswer;
            } else {
                isCorrect = inputEl.value === correctAnswer;
            }
            answerWrapperEl.classList.add(`bg-${isCorrect ? "success" : "danger"}`);
        } else if (
            ["simple_choice_radio", "dropdown", "multiple_choice"].includes(
                questionType,
            )
        ) {
            for (const buttonEl of answerWrapperEl.querySelectorAll(
                ".o_survey_choice_btn",
            )) {
                const answerId = buttonEl.querySelector("input").value;
                const isCorrect = correctAnswer.includes(parseInt(answerId));
                buttonEl.classList.add(
                    `bg-${isCorrect ? "success" : "danger"}`,
                    "text-white",
                );
                if (!isCorrect && buttonEl.classList.contains("o_survey_selected")) {
                    let fromIcon = "fa-check-circle";
                    let toIcon = "fa-times-circle";
                    if (questionType === "multiple_choice") {
                        fromIcon = "fa-check-square";
                        toIcon = "fa-times-rectangle";
                    }
                    buttonEl
                        .querySelector(`i.${fromIcon}`)
                        ?.classList.replace(fromIcon, toIcon);
                }
            }
        }
    }

    showErrors(errors) {
        const errorKeys = Object.keys(errors || {});
        for (const key of errorKeys) {
            this.el
                .querySelector(`[id="${key}"] > .o_survey_question_error`)
                .replaceChildren();
        }
        for (const key of errorKeys) {
            const errorEl = this.el.querySelector(
                `[id="${key}"] > .o_survey_question_error`,
            );
            const textEl = document.createElement("span");
            textEl.textContent = errors[key];
            this.insert(textEl, errorEl);
            errorEl.classList.add("slide_in");
            if (errorKeys[0] === key) {
                scrollTo(this.el.querySelector(`.js_question-wrapper[id="${key}"]`), {
                    behavior: "smooth",
                });
            }
        }
    }

    scrollToFirstError() {
        const errorEl = this.el.querySelector(".o_survey_question_error :not(:empty)");
        errorEl?.scrollIntoView();
    }

    resetErrors() {
        for (const el of this.el.querySelectorAll(".o_survey_question_error")) {
            el.replaceChildren();
            el.classList.remove("slide_in");
        }
        for (const notificationDestructor of this.notificationDestructors) {
            notificationDestructor();
        }
        this.notificationDestructors = [];
        for (const rowEl of this.el.querySelectorAll(
            ".o_survey_question_matrix th.bg-danger",
        )) {
            rowEl.classList.remove("bg-danger");
        }
    }

    triggerEvent(el, ev) {
        el.dispatchEvent(new Event(ev, { bubbles: true }));
    }

    scrollTop() {
        document.querySelector("#wrapwrap").scrollTo({ top: 0, behavior: "smooth" });
    }

    enableSubmitButtons() {
        for (const submitButtonEl of this.el.querySelectorAll(
            "button[type='submit']",
        )) {
            submitButtonEl.classList.remove("disabled");
        }
    }

    updateNavigationListeners() {
        this.addListener(
            this.surveyNavigationEl.querySelectorAll(".o_survey_navigation_submit"),
            "click",
            this.onSubmit,
        );
    }
}

registry.category("public.interactions").add("survey.SurveyForm", SurveyForm);

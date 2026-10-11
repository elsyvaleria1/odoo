/** @odoo-module native */
import { makeLogger } from "@web/core/debug/debug_logger";
import { rpc } from "@web/core/network";
import { renderToElement } from "@web/core/utils/render";
import { Interaction } from "@web/public/interaction";
import { session } from "@web/session";
import { parseSlideBoolean } from "@website_slides/js/public/slides_course_utils";

const log = makeLogger("website_slides.course_page");

export class CoursePage extends Interaction {
    pendingCompletion = new Set();

    dynamicContent = {
        "button.o_wslides_button_complete": {
            "t-on-click.stop.prevent": this.onClickComplete,
        },
        _root: {
            "t-on-slide_completed": (ev) => this.onSlideCompleted(ev.detail),
            "t-on-slide_mark_completed": (ev) => this.onSlideMarkCompleted(ev.detail),
        },
    };

    /**
     * @param {Integer} nextCategoryId
     */
    collapseNextCategory(nextCategoryId) {
        const categorySectionEl = document.getElementById(
            `category-collapse-${nextCategoryId}`,
        );
        if (categorySectionEl?.getAttribute("aria-expanded") === "false") {
            categorySectionEl.setAttribute("aria-expanded", true);
            document
                .querySelector(`ul[id=collapse-${nextCategoryId}]`)
                .classList.add("show");
        }
    }

    /**
     * @param {Object} slideData
     * @param {Boolean} completed
     */
    toggleCompletionButton(slideData, completed = true) {
        const buttonEl = this.el.querySelector(
            `.o_wslides_sidebar_done_button[data-id="${slideData.id}"]`,
        );

        if (!buttonEl) {
            return;
        }

        const newButtonEl = renderToElement("website.slides.sidebar.done.button", {
            slideId: slideData.id,
            uncompletedIcon: buttonEl.dataset.uncompletedIcon ?? "fa-regular fa-circle",
            slideCompleted: completed ? 1 : 0,
            canSelfMarkUncompleted: parseSlideBoolean(slideData.canSelfMarkUncompleted),
            canSelfMarkCompleted: parseSlideBoolean(slideData.canSelfMarkCompleted),
            isMember: parseSlideBoolean(slideData.isMember),
        });
        buttonEl.replaceWith(newButtonEl);
    }

    /**
     * @param {Integer} channelCompletion
     */
    updateProgressbar(channelCompletion) {
        const completion = Math.min(100, channelCompletion);
        const isCompleted = completion === 100;

        for (const el of document.querySelectorAll(
            ".o_wslides_channel_completion_completed",
        )) {
            el.classList.toggle("d-none", !isCompleted);
        }
        for (const el of document.querySelectorAll(
            ".o_wslides_channel_completion_progressbar",
        )) {
            el.classList.toggle("d-none", isCompleted);
            el.classList.toggle("d-flex", !isCompleted);
            const progressBarEl = el.querySelector(".progress-bar");
            if (progressBarEl) {
                progressBarEl.style.width = `${completion}%`;
            }
            const percentageEl = el.querySelector(".o_wslides_progress_percentage");
            if (percentageEl) {
                percentageEl.textContent = completion;
            }
        }
    }

    /**
     * @param {Object} slideData
     * @param {Boolean} completed
     * @returns {Promise<boolean>}
     */
    async toggleSlideCompleted(slideData, completed = true) {
        if (this.pendingCompletion.has(Number(slideData.id))) {
            log.logic("toggle: already in flight, dropped", () => ({
                slideId: slideData.id,
                completed,
            }));
            return false;
        }
        const canToggle = completed
            ? slideData.canSelfMarkCompleted
            : slideData.canSelfMarkUncompleted;
        if (
            parseSlideBoolean(slideData.completed) === !!completed ||
            !parseSlideBoolean(slideData.isMember) ||
            !parseSlideBoolean(canToggle)
        ) {
            log.logic("toggle: refused", () => ({
                slideId: slideData.id,
                completed,
                isCompleted: slideData.completed,
                isMember: slideData.isMember,
                canToggle,
            }));
            return false;
        }
        const slideId = Number(slideData.id);
        this.pendingCompletion.add(slideId);
        let data;
        try {
            data = await this.waitFor(
                rpc(
                    `/slides/slide/${completed ? "set_completed" : "set_uncompleted"}`,
                    {
                        slide_id: slideData.id,
                    },
                ),
            );
        } finally {
            this.pendingCompletion.delete(slideId);
        }
        if (data.error) {
            log.logic("toggle: server refused", () => ({
                slideId: slideData.id,
                completed,
                error: data.error,
            }));
            return false;
        }
        this.toggleCompletionButton(slideData, completed);
        this.updateProgressbar(data.channel_completion);
        if (data.next_category_id) {
            this.collapseNextCategory(data.next_category_id);
        }
        return true;
    }

    /**
     * @param {Integer} slideId
     * @returns {DOMStringMap|undefined}
     */
    getSlide(slideId) {
        const el = document.querySelector(
            `.o_wslides_sidebar_done_button[data-id="${slideId}"]`,
        );
        return el ? el.dataset : undefined;
    }

    /**
     * @param {MouseEvent} ev
     */
    onClickComplete(ev) {
        const buttonEl = ev.currentTarget.closest(".o_wslides_sidebar_done_button");
        const slideData = buttonEl.dataset;
        const isCompleted = parseSlideBoolean(slideData.completed);
        this.toggleSlideCompleted(slideData, !isCompleted);
    }

    /**
     * @param {Object} detail
     * @param {Integer} detail.slideId
     * @param {Boolean} detail.completed
     * @param {Integer} detail.channelCompletion
     */
    onSlideCompleted({ slideId, completed, channelCompletion }) {
        const slideData = this.getSlide(slideId);
        if (slideData) {
            this.toggleCompletionButton(slideData, completed);
        }
        this.updateProgressbar(channelCompletion);
    }

    /**
     * @param {Object} detail
     * @param {Integer} detail.id
     */
    onSlideMarkCompleted(detail) {
        if (session.is_website_user) {
            return;
        }
        const slideData = this.getSlide(detail.id);
        if (!slideData) {
            log.logic("markCompleted: no done button for slide, dropped", () => ({
                slideId: detail.id,
            }));
            return;
        }
        this.toggleSlideCompleted(slideData, true);
    }
}

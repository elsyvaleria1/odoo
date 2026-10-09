/** @odoo-module native */
import { closestScrollable, scrollTo } from "@html_builder/utils/scrolling";
import { markup } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { browser } from "@web/core/browser/browser";
import { cookie } from "@web/core/browser/cookie";
import { isMobileOS } from "@web/core/browser/feature_detection";
import { parseSQL, toRelative } from "@web/core/l10n/dates";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { htmlJoin } from "@web/core/utils/dom/html";
import { Interaction } from "@web/public/interaction";
import { session } from "@web/session";

import { FlagMarkAsOffensiveDialog } from "../components/flag_mark_as_offensive/flag_mark_as_offensive.js";
import { WebsiteForumTagsWrapper } from "../components/website_forum_tags_wrapper.js";

const FORUM_WYSIWYG = "website_forum.WebsiteForumWysiwyg";

export class WebsiteForum extends Interaction {
    static selector = ".website_forum";
    dynamicContent = {
        ".karma_required": {
            "t-on-click.withTarget": this.onKarmaRequiredClick,
        },
        ".o_js_forum_tag_follow": {
            "t-on-click.withTarget": this.onTagFollowClick,
        },
        ".o_wforum_flag:not(.karma_required)": {
            "t-on-click.prevent.withTarget": this.onFlagClick,
        },
        ".o_wforum_flag_validator": {
            "t-on-click.prevent.withTarget": this.onFlagValidatorClick,
        },
        ".o_wforum_flag_mark_as_offensive": {
            "t-on-click.prevent.withTarget": this.onFlagMarkAsOffensiveClick,
        },
        ".o_wforum_validation_queue a[href*='/validate']": {
            "t-on-click.prevent.withTarget": this.onValidationQueueClick,
        },
        ".o_wforum_favorite_toggle": {
            "t-on-click.prevent.withTarget": this.onToggleFavoriteClick,
        },
        ".js_close_intro": {
            "t-on-click.prevent": this.onCloseIntroClick,
        },
        ".answer_collapse": {
            "t-on-click.withTarget": this.onExpandAnswerClick,
        },
        ".js_wforum_submit_form:has(.o_wforum_submit_post:not(.karma_required))": {
            "t-on-submit.withTarget": this.onFormSubmit,
        },
        "#post_reply": {
            "t-on-shown.bs.collapse.withTarget": this.onCollapseShown,
        },
        "span[data-oe-model='forum.post'][data-oe-field='content'] img.float-start": {
            "t-att-class": () => ({ "float-start": false }),
        },
        ".o_wforum_relative_datetime": {
            "t-out": (el) => this.relativeLastActivity(el),
        },
        ".forum_register_url": {
            "t-att-href": () =>
                `${browser.location.origin}/odoo?redirect=${encodeURIComponent(browser.location.href)}`,
        },
    };

    setup() {
        this.lastsearch = [];

        const selectMenuWrapperEl = document.querySelector(
            "div.js_select_menu_wrapper",
        );
        if (selectMenuWrapperEl) {
            const isReadOnly = Boolean(selectMenuWrapperEl.dataset.readonly);
            const defaulValue = JSON.parse(
                selectMenuWrapperEl.dataset.initValue || "[]",
            ).map((x) => x.id);

            this.mountComponent(selectMenuWrapperEl, WebsiteForumTagsWrapper, {
                defaulValue: defaulValue,
                isReadOnly: isReadOnly,
            });
        }

        this.wysiwygTextareaEls = [
            ...this.el.querySelectorAll("textarea.o_wysiwyg_loader"),
        ];
    }

    /** @param {HTMLElement} el */
    relativeLastActivity(el) {
        const post = /** @type {HTMLElement | null} */ (
            el.closest(
                ".o_wforum_question, .o_wforum_answer, .o_wforum_post_comment, .o_wforum_last_activity",
            )
        );
        const lastActivity = post && parseSQL(post.dataset.lastActivity, "UTC");
        return lastActivity ? toRelative(lastActivity) : "";
    }

    async willStart() {
        if (
            this.wysiwygTextareaEls.length &&
            !registry.category("lazy_components").contains(FORUM_WYSIWYG)
        ) {
            await loadBundle("website_forum.assets_forum_editor");
        }
    }

    start() {
        if (!this.wysiwygTextareaEls.length) {
            return;
        }
        const WebsiteForumWysiwyg = registry
            .category("lazy_components")
            .get(FORUM_WYSIWYG);
        for (const textareaEl of this.wysiwygTextareaEls) {
            const editorKarma = parseInt(textareaEl.dataset.karma || 0);
            const hasFullEdit =
                parseInt(this.el.querySelector("#karma").value) >= editorKarma;
            const isReply = !!textareaEl.closest("#post_reply");
            const props = {
                textareaEl,
                fullEdit: hasFullEdit,
                getRecordInfo: () => ({
                    context: this.services.website_page.context,
                    resModel: "forum.post",
                    resId: +browser.location.pathname
                        .split("-")
                        .slice(-1)[0]
                        .split("/")[0],
                }),
                ...(!isReply && {
                    resizable: !isMobileOS(),
                    height: "350px",
                }),
            };
            const wysiwygWrapper = textareaEl.closest(".o_wysiwyg_textarea_wrapper");
            textareaEl.style.display = "none";
            wysiwygWrapper.after(textareaEl);
            wysiwygWrapper.replaceChildren();

            this.mountComponent(wysiwygWrapper, WebsiteForumWysiwyg, props);
        }
    }

    /**
     * @returns {boolean}
     */
    warnIfPublicUser() {
        if (session.is_website_user) {
            this.displayAccessDeniedNotification(
                markup`<a href='/web/login'>${_t(
                    "Oh no! Please sign in to perform this action",
                )}</a>`,
            );
            return true;
        }
        return false;
    }

    /**
     * @param {string} message
     */
    displayAccessDeniedNotification(message) {
        this.services.notification.add(message, {
            title: _t("Access Denied"),
            sticky: false,
            type: "warning",
        });
    }

    /**
     * @param {SubmitEvent} ev
     * @param {HTMLElement} currentTargetEl
     */
    onFormSubmit(ev, currentTargetEl) {
        let validForm = true;
        const titleEl = currentTargetEl.querySelector("input[name=post_name]");
        const textareaEl = currentTargetEl.querySelector("textarea[name=content]");

        if (titleEl?.required) {
            titleEl.classList.toggle("is-invalid", !titleEl.value);
            validForm = !!titleEl.value;
        }

        if (textareaEl?.required) {
            const textareaContainerEl = currentTargetEl.querySelector(
                ".o_wysiwyg_textarea_wrapper",
            );
            const hasContent =
                !!textareaContainerEl.innerText.trim() ||
                !!textareaContainerEl.querySelector("img");
            ["border", "border-danger", "rounded-top"].forEach((cls) => {
                textareaContainerEl.classList.toggle(cls, !hasContent);
            });
            validForm = hasContent;
        }

        if (validForm) {
            if (currentTargetEl.querySelector(".oe_social_share_call")) {
                sessionStorage.setItem(
                    "social_share",
                    JSON.stringify({
                        targetType: currentTargetEl.querySelector(
                            ".o_wforum_submit_post",
                        ).dataset.socialTargetType,
                    }),
                );
            }
        } else {
            ev.preventDefault();
        }
    }

    /**
     * @param {MouseEvent} ev
     * @param {HTMLElement} currentTargetEl
     */
    onExpandAnswerClick(ev, currentTargetEl) {
        if (ev.target.matches(".o_wforum_expand_toggle")) {
            currentTargetEl.classList.toggle("o_expand");
            currentTargetEl.classList.toggle("min-vh-100");
            currentTargetEl.classList.toggle("w-lg-50");
        } else if (ev.target.matches(".o_wforum_discard_btn")) {
            currentTargetEl.classList.remove("o_expand", "min-vh-100");
            currentTargetEl.classList.add("w-lg-50");
        }
    }

    /**
     * @param {MouseEvent} ev
     * @param {HTMLElement} currentTargetEl
     */
    onKarmaRequiredClick(ev, currentTargetEl) {
        const karma = parseInt(currentTargetEl.dataset.karma);
        if (!karma) {
            return;
        }
        ev.preventDefault();
        if (this.warnIfPublicUser()) {
            return;
        }
        const forumId = parseInt(
            this.el.ownerDocument.getElementById("wrapwrap").dataset.forum_id,
        );
        let message = _t("%(score)s karma is required to perform this action.", {
            score: karma,
        });
        if (forumId) {
            message = htmlJoin(
                message,
                _t(
                    "%(link_start)sRead the guidelines to know how to gain karma.%(link_end)s",
                    {
                        link_start: markup`<br><a class="alert-link" href="/forum/${forumId}/faq">`,
                        link_end: markup`</a>`,
                    },
                ),
            );
        }
        this.services.notification.add(message, {
            type: "warning",
            sticky: false,
            title: _t("Karma Error"),
        });
    }

    /**
     * @param {MouseEvent} ev
     * @param {HTMLElement} currentTargetEl
     */
    onTagFollowClick(ev, currentTargetEl) {
        if (ev.target.closest("button")) {
            currentTargetEl
                .querySelector(".o_js_forum_tag_link")
                .classList.toggle("text-muted");
        }
    }

    /**
     * @param {MouseEvent} ev
     * @param {HTMLElement} currentTargetEl
     */
    async onFlagClick(ev, currentTargetEl) {
        if (this.warnIfPublicUser()) {
            return;
        }
        const data = await this.waitFor(
            rpc(
                currentTargetEl.dataset.href ||
                    (currentTargetEl.getAttribute("href") !== "#" &&
                        currentTargetEl.getAttribute("href")) ||
                    currentTargetEl.closest("form").getAttribute("action"),
            ),
        );
        if (data.error) {
            const message =
                data.error === "post_already_flagged"
                    ? _t("This post is already flagged")
                    : data.error === "post_non_flaggable"
                      ? _t("This post can not be flagged")
                      : data.error;
            this.displayAccessDeniedNotification(message);
        } else if (data.success) {
            const child = currentTargetEl.firstElementChild;
            if (data.success === "post_flagged_moderator") {
                const countFlaggedPosts = this.el.querySelector(
                    "#count_posts_queue_flagged",
                );
                currentTargetEl.innerText = _t(" Flagged");
                currentTargetEl.prepend(child);
                if (countFlaggedPosts) {
                    countFlaggedPosts.classList.remove("bg-light", "d-none");
                    countFlaggedPosts.classList.add("text-bg-danger");
                    countFlaggedPosts.innerText =
                        parseInt(countFlaggedPosts.innerText, 10) + 1;
                }
            } else if (data.success === "post_flagged_non_moderator") {
                currentTargetEl.innerText = _t(" Flagged");
                currentTargetEl.prepend(child);
                const forumAnswerEl = currentTargetEl.closest(".o_wforum_answer");
                if (forumAnswerEl) {
                    forumAnswerEl.style.height = getComputedStyle(forumAnswerEl).height;
                    forumAnswerEl.classList.add("overflow-hidden");
                    forumAnswerEl.style.transition = "height 1s, opacity 1s";
                    forumAnswerEl.classList.add("opacity-0", "h-0");
                }
            }
        }
    }

    /**
     * @param {MouseEvent} ev
     * @param {HTMLElement} currentTargetEl
     */
    async onValidationQueueClick(ev, currentTargetEl) {
        const postBeingValidated = currentTargetEl.closest(".post_to_validate");
        if (!postBeingValidated) {
            return;
        }
        postBeingValidated.classList.add("d-none");
        let ok;
        try {
            ok = (await this.waitFor(fetch(currentTargetEl.href))).ok;
        } catch {
            ok = false;
        }
        if (!ok) {
            postBeingValidated.classList.remove("d-none");
            return;
        }
        const nbLeftInQueue = Array.from(
            document.querySelectorAll(".post_to_validate"),
        ).filter((e) => window.getComputedStyle(e).display !== "none").length;
        const queueType = document.querySelector("#queue_type").dataset.queueType;
        const queueCountBadge = document.querySelector(
            `#count_posts_queue_${queueType}`,
        );
        queueCountBadge.innerText = nbLeftInQueue;
        if (!nbLeftInQueue) {
            document.querySelector(".o_caught_up_alert").classList.remove("d-none");
            document
                .querySelector(".o_wforum_btn_filter_tool")
                ?.classList.add("d-none");
            queueCountBadge.classList.add("d-none");
        }
    }

    /**
     * @param {MouseEvent} ev
     * @param {HTMLElement} currentTargetEl
     */
    async onToggleFavoriteClick(ev, currentTargetEl) {
        const data = await this.waitFor(rpc(currentTargetEl.dataset.href));
        currentTargetEl.classList.toggle("opacity-50", !data);
        currentTargetEl.classList.toggle("opacity-100-hover", !data);
        const currentTargetEl_icon = currentTargetEl.querySelector("i");
        currentTargetEl_icon.classList.toggle("fa-regular", !data);
        currentTargetEl_icon.classList.toggle("fa-solid", data);
        currentTargetEl_icon.classList.toggle("o_wforum_gold", data);
    }

    onCloseIntroClick() {
        cookie.set("forum_welcome_message", false, 24 * 60 * 60 * 365, "optional");
        const forumIntroEl = this.el.querySelector(".forum_intro");
        forumIntroEl.style.height = getComputedStyle(forumIntroEl).height;
        forumIntroEl.classList.add("overflow-hidden");
        forumIntroEl.style.transition = "height 1s";
        forumIntroEl.classList.add("h-0");
        return true;
    }

    /**
     * @param {MouseEvent} ev
     * @param {HTMLElement} currentTargetEl
     */
    async onFlagValidatorClick(ev, currentTargetEl) {
        await this.waitFor(
            this.services.orm.call("forum.post", currentTargetEl.dataset.action, [
                parseInt(currentTargetEl.dataset.postId),
            ]),
        );
        currentTargetEl.closest(".o_wforum_flag_alert")?.classList.toggle("d-none");
        const flaggedButton = currentTargetEl.parentElement.firstElementChild,
            child = flaggedButton.firstElementChild,
            countFlaggedPosts = this.el.querySelector("#count_posts_queue_flagged"),
            count = parseInt(countFlaggedPosts.innerText, 10) - 1;

        flaggedButton.innerText = _t(" Flag");
        flaggedButton.prepend(child);
        if (count === 0) {
            countFlaggedPosts.classList.add("bg-light");
        }
        countFlaggedPosts.innerText = count;
    }

    /**
     * @param {MouseEvent} ev
     * @param {HTMLElement} currentTargetEl
     */
    async onFlagMarkAsOffensiveClick(ev, currentTargetEl) {
        if (
            !/^\/forum\/.+?\/ask_for_mark_as_offensive$/.test(
                currentTargetEl.dataset.action,
            )
        ) {
            return;
        }
        const template = await this.waitFor(rpc(currentTargetEl.dataset.action));
        this.services.dialog.add(FlagMarkAsOffensiveDialog, {
            title: _t("Offensive Post"),
            body: markup(template),
        });
    }

    /**
     * @param {Event} ev
     * @param {HTMLElement} currentTargetEl
     */
    onCollapseShown(ev, currentTargetEl) {
        const scrollingElement = closestScrollable(currentTargetEl.parentNode);
        scrollTo(currentTargetEl, {
            forcedOffset: scrollingElement.clientHeight - currentTargetEl.clientHeight,
        });
    }
}

registry
    .category("public.interactions")
    .add("website_forum.website_forum", WebsiteForum);

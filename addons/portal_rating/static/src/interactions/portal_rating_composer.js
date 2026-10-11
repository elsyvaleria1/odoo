/** @odoo-module native */
import { PortalComposer } from "@portal/interactions/portal_composer";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { Interaction } from "@web/public/interaction";

export class RatingPopupComposer extends Interaction {
    static selector = ".o_rating_popup_composer";

    setup() {
        const options = this.el.dataset;
        this.rating_avg = Math.round(options["rating_avg"] * 100) / 100 || 0.0;
        this.rating_count = options["rating_count"] || 0.0;

        this.options = Object.assign(
            {
                token: false,
                res_model: false,
                res_id: false,
                pid: 0,
                display_rating: true,
                csrf_token: odoo.csrf_token,
                user_id: user.userId,
                reloadRatingPopupComposer: this.onReloadRatingPopupComposer.bind(this),
            },
            options,
            {},
        );
        this.env.bus.addEventListener("reload_rating_popup_composer", (ev) =>
            this.onReloadRatingPopupComposer(ev.detail),
        );
    }

    start() {
        this.reloadRatingPopupComposer();
    }

    reloadRatingPopupComposer() {
        const starsEl = this.el.querySelector(".o_rating_popup_composer_stars");
        if (this.options.hide_rating_avg) {
            starsEl.replaceChildren();
        } else {
            starsEl.replaceChildren();
            this.renderAt(
                "portal_rating.rating_stars_static",
                {
                    inline_mode: true,
                    widget: this,
                    val: this.rating_avg,
                },
                starsEl,
            );
        }

        const modalEl = this.el.querySelector(".o_rating_popup_composer_modal");
        modalEl.replaceChildren();
        this.renderAt(
            "portal_rating.PopupComposer",
            {
                inline_mode: true,
                widget: this,
                val: this.rating_avg,
            },
            modalEl,
        );

        if (this.composerEl) {
            this.services["public.interactions"].stopInteractions(this.composerEl);
        }

        const options = PortalComposer.prepareOptions(this.options);
        options.send_button_label = options.default_message_id
            ? _t("Update review")
            : _t("Post review");
        this.env.portalComposerOptions = options;
        const locationEl = this.el.querySelector(
            ".o_rating_popup_composer_modal .o_portal_chatter_composer",
        );
        if (!locationEl) {
            return;
        }
        this.composerEl = this.renderAt(
            "portal.Composer",
            { widget: { options: this.env.portalComposerOptions } },
            locationEl,
            "afterend",
        )[0];
        delete this.env.portalComposerOptions;
        locationEl.remove();
        this.el.querySelector(".o_rating_popup_composer_text").textContent =
            options.is_fullscreen
                ? _t("Review")
                : options.default_message_id
                  ? _t("Edit Review")
                  : _t("Add Review");
    }

    /**
     * @param {Object} data
     */
    onReloadRatingPopupComposer(data) {
        this.rating_avg = data["mixin.mail.thread"][0].rating_avg;
        this.rating_count = data["mixin.mail.thread"][0].rating_count;
        this.rating_value = data["rating.rating"]?.[0].rating;
        this.updateOptions(data);
        this.reloadRatingPopupComposer();
    }

    /**
     * @param {Object} data
     */
    updateOptions(data) {
        const message = data["mail.message"][0];
        if (
            !message.author_id ||
            Number(message.author_id) !== Number(this.options.partner_id)
        ) {
            return;
        }
        const body = message.body[1]?.replace(/<[^>]+>/g, "");
        Object.assign(this.options, {
            default_message: body,
            default_message_id:
                body || message.attachment_ids?.length || message.rating_id
                    ? message.id
                    : undefined,
            default_attachment_ids: data["ir.attachment"],
            default_rating_value: this.rating_value || 4,
        });
    }
}

registry
    .category("public.interactions")
    .add("portal_rating.rating_popup_composer", RatingPopupComposer);

/** @odoo-module native */
import { markup } from "@odoo/owl";
import {
    SocialPostFormatterMixinBase,
    SocialPostFormatterRegex,
} from "@social/js/social_post_formatter_mixin";
import { htmlReplace } from "@web/core/utils/dom/html";
import { patch } from "@web/core/utils/patch";

patch(SocialPostFormatterMixinBase, {
    _formatPost(value) {
        value = super._formatPost(...arguments);
        const mediaType = this._getMediaType();
        if (["facebook", "facebook_preview"].includes(mediaType)) {
            value = htmlReplace(
                value,
                SocialPostFormatterRegex.REGEX_HASHTAG,
                (_, before, hashtag) => {
                    before = markup(before);
                    hashtag = markup(hashtag);
                    return markup`${before}<a href='https://www.facebook.com/hashtag/${hashtag}' target='_blank'>#${hashtag}</a>`;
                },
            );
            const accountId =
                (this.record && this.record.account_id.raw_value) ||
                (this.originalPost && this.originalPost.account_id.raw_value);
            if (accountId) {
                const REGEX_AT_FACEBOOK = /\B@\[([0-9]*)\]\s([\w\dÀ-ÿ-]+)/g;
                value = htmlReplace(value, REGEX_AT_FACEBOOK, (_, id, name) => {
                    id = markup(id);
                    name = markup(name);
                    return markup`<a href='/social_facebook/redirect_to_profile/${encodeURIComponent(
                        accountId,
                    )}/${id}?name=${name}' target='_blank'>${name}</a>`;
                });
            }
        }
        return value;
    },
});

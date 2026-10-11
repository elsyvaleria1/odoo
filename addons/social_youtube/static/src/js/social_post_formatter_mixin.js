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
        if (["youtube", "youtube_preview"].includes(this._getMediaType())) {
            value = htmlReplace(
                value,
                SocialPostFormatterRegex.REGEX_HASHTAG,
                (_, before, hashtag) => {
                    before = markup(before);
                    hashtag = markup(hashtag);
                    return markup`${before}<a href='https://www.youtube.com/results?search_query=%23${encodeURIComponent(
                        hashtag,
                    )}' target='_blank'>#${hashtag}</a>`;
                },
            );
        }
        return value;
    },
});

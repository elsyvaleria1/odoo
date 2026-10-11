/** @odoo-module native */
import { markup } from "@odoo/owl";
import {
    SocialPostFormatterMixinBase,
    SocialPostFormatterRegex,
} from "@social/js/social_post_formatter_mixin";
import { htmlReplace } from "@web/core/utils/dom/html";
import { patch } from "@web/core/utils/patch";

export const LINKEDIN_HASHTAG_REGEX = /{hashtag\|#\|([a-zA-Z\d\-_]+)}/g;

patch(SocialPostFormatterMixinBase, {
    _formatPost(value) {
        value = super._formatPost(...arguments);
        if (this._getMediaType() === "linkedin") {
            value = htmlReplace(
                value,
                SocialPostFormatterRegex.REGEX_HASHTAG,
                (_, before, hashtag) => {
                    before = markup(before);
                    hashtag = markup(hashtag);
                    return markup`${before}<a href='https://www.linkedin.com/feed/hashtag/?keywords=${hashtag}' target='_blank'>#${hashtag}</a>`;
                },
            );
            value = htmlReplace(value, LINKEDIN_HASHTAG_REGEX, (_, name) => {
                name = markup(name);
                return markup`<a href='https://www.linkedin.com/feed/hashtag/?keywords=${name}' target='_blank'>#${name}</a>`;
            });
        }
        return value;
    },
});

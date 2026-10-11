/** @odoo-module native */
import { formatText } from "@mail/utils/web/emojis_mixin";
import { markup } from "@odoo/owl";
import { htmlReplace } from "@web/core/utils/dom/html";

export const SocialPostFormatterRegex = {
    REGEX_AT: /\B@([\w\dÀ-ÿ-.]+)/g,
    REGEX_HASHTAG: /(^|\s|<br>)#([a-zA-Z\d\-_]+)/g,
    REGEX_URL: /http(s)?:\/\/(www\.)?[a-zA-Z0-9@:%_+~#=?&/\-;!.,()'*$]{3,2000}/g,
};

export const SocialPostFormatterMixinBase = {
    /**
     * Add emojis support
     * Wraps links, #hashtag and @tag around anchors
     * Regex from: https://stackoverflow.com/questions/19484370/how-do-i-automatically-wrap-text-urls-in-anchor-tags
     *
     * @param {string|import("@odoo/owl").Markup} value
     * @returns {string|import("@odoo/owl").Markup} value
     * @private
     */
    _formatPost(value) {
        value = formatText(value);
        value = htmlReplace(value, SocialPostFormatterRegex.REGEX_URL, (url) => {
            url = markup(url);
            return markup`<a href='${url}' class='text-truncate' target='_blank' rel='noreferrer noopener'>${url}</a>`;
        });
        return value;
    },

    _getMediaType() {
        return (
            (this.props && this.props.mediaType) ||
            (this.props.record && this.props.record.data.media_type) ||
            (this.originalPost && this.originalPost.media_type.raw_value) ||
            ""
        );
    },
};

export const SocialPostFormatterMixin = (T) =>
    class extends T {
        _formatPost() {
            return SocialPostFormatterMixinBase._formatPost.call(this, ...arguments);
        }
        _getMediaType() {
            return SocialPostFormatterMixinBase._getMediaType.call(this, ...arguments);
        }
    };

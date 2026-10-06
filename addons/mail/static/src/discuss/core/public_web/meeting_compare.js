// @ts-check
/** @odoo-module native */
import { compareFavorites } from "@mail/discuss/core/common/thread_compare_patch";
import { compareChannels } from "@mail/discuss/core/public_web/messaging_menu_tab_model_patch";
import { compareDatetime } from "@mail/utils/common/misc";
import { compareDates, now as currentDateTime } from "@web/core/l10n/dates";

/**
 * Meetings read as an agenda: the one going on or coming next on top, the
 * later ones below, those already over at the bottom with the latest ended
 * first. A meeting whose call is running is going on however late it runs.
 *
 * @param {import("models").DiscussChannel} channel1
 * @param {import("models").DiscussChannel} channel2
 * @returns {number}
 */
export function compareMeetings(channel1, channel2) {
    const favorite = compareFavorites(channel1, channel2);
    if (favorite !== undefined) {
        return favorite;
    }
    const now = currentDateTime();
    /** @param {import("models").DiscussChannel} channel */
    const isOver = (channel) =>
        Boolean(
            !channel.rtc_session_ids?.length &&
            channel.meeting_stop_dt &&
            compareDates(channel.meeting_stop_dt, now) < 0,
        );
    if (isOver(channel1) !== isOver(channel2)) {
        return isOver(channel1) ? 1 : -1;
    }
    const order = isOver(channel1)
        ? compareDatetime(channel2.meeting_stop_dt, channel1.meeting_stop_dt)
        : compareDatetime(channel1.meeting_start_dt, channel2.meeting_start_dt);
    return order || compareChannels(channel1, channel2);
}

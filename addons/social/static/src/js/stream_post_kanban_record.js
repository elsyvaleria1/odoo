/** @odoo-module native */
import { KanbanRecord } from "@web/views/kanban";

export const CANCEL_GLOBAL_CLICK = ["a", ".o_social_subtle_btn", "img"].join(",");
const DEFAULT_COMMENT_COUNT = 20;

export class StreamPostKanbanRecord extends KanbanRecord {
    /**
     * @override
     */
    onGlobalClick(ev) {
        if (ev.target.closest(CANCEL_GLOBAL_CLICK)) {
            return;
        }
        this.rootRef.el.querySelector(".o_social_comments").click();
    }

    async _updateLikesCount(userLikeField, likesCountField, record = null) {
        record = record || this.props.record;
        const userLikes = record.data[userLikeField];
        let likesCount = record.data[likesCountField];
        if (userLikes) {
            if (likesCount > 0) {
                likesCount--;
            }
        } else {
            likesCount++;
        }

        await record.update({
            [userLikeField]: !userLikes,
            [likesCountField]: likesCount,
            ...this._prepareLikeAdditionnalValues(likesCount, !userLikes),
        });
        await record.save();
    }

    _prepareLikeAdditionnalValues() {
        return {};
    }

    get commentCount() {
        return this.props.commentCount || DEFAULT_COMMENT_COUNT;
    }
}

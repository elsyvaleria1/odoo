// @ts-check
/** @odoo-module native */
import { ActivityListPopover } from "@mail/core/web/activity_list_popover";
import { Avatar } from "@mail/views/web/fields/avatar/avatar";
import { Component, t, useProps } from "@odoo/owl";
import { deserializeDate, formatDate } from "@web/core/l10n/dates";
import { formatList } from "@web/core/l10n/utils";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { usePopover } from "@web/ui/popover";
export class ActivityCell extends Component {
    static components = {
        Avatar,
    };
    static props = {
        activityIds: t.array(),
        attachmentsInfo: t.object().optional(),
        activityTypeId: t.number(),
        reportingDate: t.string(),
        countByState: t.object(),
        reloadFunc: t.function(),
        resId: t.number(),
        resModel: t.string(),
        summaries: t.array(),
        userAssignedIds: t.array(),
    };
    static template = "mail.ActivityCell";
    props = useProps(this.constructor.props);

    setup() {
        this.popover = usePopover(ActivityListPopover, { position: "bottom-start" });
        this.contentRef = elementRef();
    }

    get reportingDateFormatted() {
        return formatDate(deserializeDate(this.props.reportingDate));
    }
    get displayedSummaries() {
        const summariesWithContent = this.props.summaries.filter(
            (textContent) => !!textContent,
        );
        const extras = this.props.summaries.length - summariesWithContent.length;
        if (summariesWithContent.length > 0 && extras > 0) {
            summariesWithContent.push(
                _t("%(extraCount)s more", { extraCount: extras }),
            );
        }
        return formatList(summariesWithContent);
    }

    get ongoingActivityCount() {
        return (
            (this.props.countByState?.planned ?? 0) +
            (this.props.countByState?.today ?? 0) +
            (this.props.countByState?.overdue ?? 0)
        );
    }

    get totalActivityCount() {
        return this.ongoingActivityCount + (this.props.countByState?.done ?? 0);
    }

    onClick() {
        if (this.popover.isOpen) {
            this.popover.close();
        } else {
            this.popover.open(this.contentRef.el, {
                activityIds: this.props.activityIds,
                defaultActivityTypeId: this.props.activityTypeId,
                onActivityChanged: () => {
                    this.props.reloadFunc();
                    this.popover.close();
                },
                resId: this.props.resId,
                resModel: this.props.resModel,
            });
        }
    }
}

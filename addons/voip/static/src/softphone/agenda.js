/** @odoo-module native */
import { Component, onMounted, proxy, t, useProps } from "@odoo/owl";
import { tabComponents } from "@voip/softphone/tab";
import { compareDates, DATE_MED, today, toLocaleString } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { ConfirmationDialog } from "@web/ui/dialog";

/**
 * List of "call activities", i.e. activities of type call you were scheduled
 * to handle today.
 */
export class Agenda extends Component {
    static components = tabComponents;
    static props = { extraClass: t.string().optional("") };
    static template = "voip.Agenda";
    props = useProps(this.constructor.props);

    setup() {
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.orm = useService("orm");
        this.userAgent = useService("voip.user_agent");
        this.voip = useService("voip");
        this.ui = useService("ui");
        onMounted(() => this.voip.fetchTodayCallActivities());
        this.state = proxy(this.voip.softphone.agenda);
        this.onInputSearch = useDebounced(
            () => this.voip.fetchTodayCallActivities(),
            300,
        );
    }

    get activitiesByDate() {
        const activities = [...this.voip.softphone.activities];
        activities.sort((a, b) => compareDates(a.date_deadline, b.date_deadline));
        const currentDay = today();
        const yesterday = currentDay.subtract({ days: 1 });
        const tomorrow = currentDay.add({ days: 1 });
        return Map.groupBy(activities, (activity) => {
            const dueDate = activity.date_deadline;
            if (dueDate.equals(currentDay)) {
                return _t("Due: Today");
            }
            if (dueDate.equals(yesterday)) {
                return _t("Due: Yesterday");
            }
            if (dueDate.equals(tomorrow)) {
                return _t("Due: Tomorrow");
            }
            return _t("Due: %(date)s", {
                date: toLocaleString(dueDate, DATE_MED),
            });
        });
    }

    getExtraClass(activity) {
        const currentDay = today();
        if (compareDates(currentDay, activity.date_deadline) > 0) {
            return "border-start border-danger border-2";
        }
        if (currentDay.equals(activity.date_deadline)) {
            return "border-start border-warning border-2";
        }
        return "";
    }

    getSectionStyle(activity) {
        const currentDay = today();
        if (compareDates(currentDay, activity.date_deadline) > 0) {
            return "text-danger";
        }
        if (currentDay.equals(activity.date_deadline)) {
            return "text-warning";
        }
        return "";
    }

    onClickActivity(activity) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: activity.res_model,
            res_id: activity.res_id,
            views: [[false, "form"]],
            target: this.ui.isSmall ? "new" : "current",
        });
    }

    onClickCall(activity) {
        const { partner, phone: phone_number } = activity;
        this.userAgent.makeCall({ activity, partner, phone_number });
    }

    onClickCancel(activity) {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Hold your horses!"),
            body: _t(
                "Are you sure you want to delete this activity? It will be lost forever! (A long time!)",
            ),
            cancel() {},
            confirm: async () => {
                await this.orm.call("mail.activity", "unlink", [[activity.id]]);
                activity.remove();
            },
            confirmLabel: _t("Yes, I know what I'm doing"),
            cancelLabel: _t("Missclicked, sorry"),
        });
    }

    onClickContact(partnerId) {
        if (!partnerId) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "res.partner",
            res_id: partnerId,
            views: [[false, "form"]],
            target: this.ui.isSmall ? "new" : "current",
        });
    }

    async onClickDone(activity) {
        await activity.markAsDone();
        activity.delete();
    }

    onClickEdit(activity) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_id: activity.id,
            res_model: "mail.activity",
            views: [[false, "form"]],
            view_mode: "form",
            target: "new",
            context: {
                default_res_id: activity.res_id,
                default_res_model: activity.res_model,
            },
        });
    }

    openMyActivities() {
        this.action.doAction("mail.mail_activity_action_my", {
            target: this.ui.isSmall ? "new" : "current",
        });
    }
}

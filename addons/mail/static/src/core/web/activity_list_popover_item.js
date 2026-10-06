// @ts-check
/** @odoo-module native */
import { ActivityMailTemplate } from "@mail/core/web/activity_mail_template";
import { ActivityMarkAsDone } from "@mail/core/web/activity_markasdone_popover";
import { computeDelay } from "@mail/utils/common/dates";
import { Component, proxy, t, useProps } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { FileUploader } from "@web/core/file_upload";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";

const log = makeLogger("mail.activity");
/**
 * @typedef {Object} Props
 * @property {import("models").Activity} activity
 * @property {function} [onActivityChanged]
 * @property {function} [onClickDoneAndScheduleNext]
 * @property {function} onClickEditActivityButton
 * @extends {Component<Props, import("@web/env").OdooEnv>}
 */
export class ActivityListPopoverItem extends Component {
    static components = { ActivityMailTemplate, ActivityMarkAsDone, FileUploader };
    static props = {
        activity: t.any(),
        onActivityChanged: t.any().optional(),
        onClickDoneAndScheduleNext: t.any().optional(),
        onClickEditActivityButton: t.any().optional(),
    };
    static template = "mail.ActivityListPopoverItem";
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.state = proxy({ hasMarkDoneView: false });
        this.closeMarkAsDone = this.closeMarkAsDone.bind(this);
    }

    closeMarkAsDone() {
        this.state.hasMarkDoneView = false;
    }

    get delayLabel() {
        const diff = computeDelay(this.props.activity.date_deadline);
        if (diff === 0) {
            return _t("Today");
        } else if (diff === -1) {
            return _t("Yesterday");
        } else if (diff < 0) {
            return _t("%s days overdue", Math.round(Math.abs(diff)));
        } else if (diff === 1) {
            return _t("Tomorrow");
        } else {
            return _t("Due in %s days", Math.round(Math.abs(diff)));
        }
    }

    get hasCancelButton() {
        const activity = this.props.activity;
        return activity.state !== "done" && activity.can_write;
    }

    get hasEditButton() {
        const activity = this.props.activity;
        return activity.state !== "done" && activity.can_write;
    }

    get hasFileUploader() {
        const activity = this.props.activity;
        return (
            activity.state !== "done" && activity.activity_category === "upload_file"
        );
    }

    get hasMarkDoneButton() {
        return this.props.activity.state !== "done" && !this.hasFileUploader;
    }

    onClickEditActivityButton() {
        this.props.onClickEditActivityButton();
        this.props.activity.edit().then(() => this.props.onActivityChanged?.());
    }

    onClickMarkAsDone() {
        this.state.hasMarkDoneView = !this.state.hasMarkDoneView;
    }

    /** @param {{data: string, name: string, type: string}} data */
    async onFileUploaded(data) {
        if (!(await this.props.activity.markAsDoneWithFile(data))) {
            return;
        }
        this.props.onActivityChanged?.();
    }

    async unlink() {
        log.logic("unlink", () => ({ activityId: this.props.activity.id }));
        await this.orm.unlink("mail.activity", [this.props.activity.id]);
        this.props.activity.remove();
        this.props.onActivityChanged?.();
    }
}

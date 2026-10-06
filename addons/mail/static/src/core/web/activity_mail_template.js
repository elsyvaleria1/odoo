// @ts-check
/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";

const log = makeLogger("mail.activity");
/**
 * @typedef {Object} Props
 * @property {import("models").Activity} activity
 * @property {function} [onClickButtons]
 * @property {function} [onActivityChanged]
 * @extends {Component<Props, import("@web/env").OdooEnv>}
 */
export class ActivityMailTemplate extends Component {
    static props = {
        activity: t.any(),
        onClickButtons: t.any().optional(() => () => {}),
        onActivityChanged: t.any().optional(),
    };
    static template = "mail.ActivityMailTemplate";
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.action = useService("action");
        this.orm = useService("orm");
        this.store = useService("mail.store");
    }

    /**
     * @param {MouseEvent} ev
     * @param {Object} mailTemplate
     */
    onClickPreview(ev, mailTemplate) {
        ev.stopPropagation();
        ev.preventDefault();
        log.logic("onClickPreview", () => ({
            activityId: this.props.activity.id,
            templateId: mailTemplate.id,
        }));
        this.props.onClickButtons();
        const action = {
            name: _t("Compose Email"),
            type: "ir.actions.act_window",
            res_model: "wizard.mail.message.send",
            views: [[false, "form"]],
            target: "new",
            context: {
                default_res_ids: [this.props.activity.res_id],
                default_model: this.props.activity.res_model,
                default_subtype_xmlid: "mail.mt_comment",
                default_template_id: mailTemplate.id,
                force_email: true,
            },
        };
        const thread = this.store.Thread.insert({
            model: this.props.activity.res_model,
            id: this.props.activity.res_id,
        });
        this.action.doAction(action, {
            onClose: () => this.props.onActivityChanged?.(thread),
        });
    }

    /**
     * @param {MouseEvent} ev
     * @param {Object} mailTemplate
     */
    async onClickSend(ev, mailTemplate) {
        ev.stopPropagation();
        ev.preventDefault();
        log.logic("onClickSend", () => ({
            activityId: this.props.activity.id,
            templateId: mailTemplate.id,
        }));
        this.props.onClickButtons();
        const thread = this.store.Thread.insert({
            model: this.props.activity.res_model,
            id: this.props.activity.res_id,
        });
        await this.orm.call(this.props.activity.res_model, "activity_send_mail", [
            [this.props.activity.res_id],
            mailTemplate.id,
        ]);
        this.props.onActivityChanged?.(thread);
    }
}

// @ts-check
/** @odoo-module native */
import { Component, onMounted, t, useListener, useProps } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";

const log = makeLogger("mail.activity");

export class ActivityMarkAsDone extends Component {
    static template = "mail.ActivityMarkAsDone";
    static props = {
        activity: t.any(),
        close: t.any().optional(),
        hasHeader: t.any().optional(false),
        onClickDoneAndScheduleNext: t.any().optional(),
        onActivityChanged: t.any(),
    };
    props = useProps(this.constructor.props);

    get isSuggested() {
        return this.props.activity.chaining_type === "suggest";
    }

    setup() {
        super.setup();
        this.store = useService("mail.store");
        this.action = useService("action");
        this.textArea = elementRef();
        onMounted(() => {
            this.textArea.el.focus();
        });
        useListener(window, "keydown", this.onKeydown.bind(this));
    }

    /** @param {KeyboardEvent} ev */
    onKeydown(ev) {
        if (ev.key === "Escape" && this.props.close) {
            this.props.close();
        }
    }

    async onClickDone() {
        const { res_id, res_model } = this.props.activity;
        const thread = this.store.Thread.insert({
            model: res_model,
            id: res_id,
        });
        log.logic("onClickDone", () => ({ activityId: this.props.activity.id }));
        await this.props.activity.markAsDone();
        this.props.onActivityChanged(thread);
        await thread.fetchNewMessages();
    }

    async onClickDoneAndScheduleNext() {
        const { res_id, res_model } = this.props.activity;
        const thread = this.store.Thread.insert({
            model: res_model,
            id: res_id,
        });
        if (this.props.onClickDoneAndScheduleNext) {
            this.props.onClickDoneAndScheduleNext();
        }
        if (this.props.close) {
            this.props.close();
        }
        const action = await this.props.activity.markAsDoneAndScheduleNext();
        log.logic("onClickDoneAndScheduleNext", () => ({
            activityId: this.props.activity.id,
            nextAction: Boolean(action),
        }));
        thread.fetchNewMessages();
        this.props.onActivityChanged(thread);
        if (!action) {
            return;
        }
        await new Promise((resolve) => {
            this.action.doAction(action, {
                onClose: resolve,
            });
        });
        this.props.onActivityChanged(thread);
    }
}

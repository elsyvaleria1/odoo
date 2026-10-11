/** @odoo-module native */
import { Component, proxy, useListener, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/fields/standard_field_props";

export class CallQueueSwitch extends Component {
    static props = standardFieldProps;
    static template = "voip.CallQueueSwitch";
    props = useProps(this.constructor.props);

    _hasPendingRequest = false;

    setup() {
        this.state = proxy({
            isRecordInCallQueue: this.props.record.data[this.props.name],
        });
        this.orm = useService("orm");
        this.voip = useService("voip");
        useListener(
            this.voip.bus,
            "on-call-activity-removed",
            this._onCallActivityRemoved.bind(this),
        );
    }

    /** @returns {string} */
    get iconClasses() {
        return this.state.isRecordInCallQueue
            ? "fa-minus text-danger"
            : "fa-plus text-success";
    }

    /** @returns {string} */
    get titleText() {
        return this.state.isRecordInCallQueue
            ? _t("Remove from Call Queue")
            : _t("Add to Call Queue");
    }

    async addToCallQueue() {
        if (this._hasPendingRequest) {
            return;
        }
        await this._makeRequest(() =>
            this.orm.call(this.props.record.resModel, "create_call_activity", [
                [this.props.record.resId],
            ]),
        );
        this.state.isRecordInCallQueue = true;
        await this.props.record.load();
        this.props.record.model.notify();
    }

    /** @param {MouseEvent} ev */
    onClick(ev) {
        if (this.state.isRecordInCallQueue) {
            this.removeFromCallQueue();
        } else {
            this.addToCallQueue();
        }
    }

    async removeFromCallQueue() {
        if (this._hasPendingRequest) {
            return;
        }
        await this._makeRequest(async () =>
            this.orm.call(this.props.record.resModel, "remove_call_activity", [
                [this.props.record.resId],
            ]),
        );
        this.state.isRecordInCallQueue = false;
        await this.props.record.load();
        this.props.record.model.notify();
    }

    /** @param {function} callback */
    async _makeRequest(callback) {
        this._hasPendingRequest = true;
        await callback();
        this._hasPendingRequest = false;
    }

    /**
     * @param {Object} param0
     * @param {integer} param0.detail The resId of the deleted record.
     */
    _onCallActivityRemoved({ detail: resId }) {
        if (this.props.record.resId !== resId) {
            return;
        }
        this.state.isRecordInCallQueue = false;
    }
}

registry.category("fields").add("call_queue_switch", { component: CallQueueSwitch });

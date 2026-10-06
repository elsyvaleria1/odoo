/** @odoo-module native */
import { now } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";

export class CallService {
    missedCalls = 0;

    constructor(env, services) {
        this.env = env;
        this.orm = services.orm;
        this.store = services["mail.store"];
    }

    async abort(call) {
        this.store.insert(await this.orm.call("phone.call", "abort_call", [[call.id]]));
    }

    async create(data) {
        const { activity, partner } = data;
        delete data.activity;
        delete data.partner;
        data.partner_id = partner?.id;
        const {
            ids: [id],
            store_data,
        } = await this.orm.call("phone.call", "create_and_format", [], data);
        this.store.insert(store_data);
        const call = this.store["phone.call"].insert(id);
        if (activity) {
            call.activity = activity;
        }
        if (!call.partner_id) {
            this.orm
                .call("phone.call", "acquire_contact_info", [[call.id]])
                .then((data) => {
                    if (data) {
                        this.store.insert(data);
                    }
                });
        }
        return call;
    }

    async end(call, { activityDone = true } = {}) {
        let data;
        if (call.activity && activityDone) {
            data = await this.orm.call("phone.call", "end_call", [[call.id]], {
                activity_name: call.activity.res_name,
            });
            await call.activity.markAsDone();
            call.activity.remove();
            call.activity = null;
        } else {
            data = await this.orm.call("phone.call", "end_call", [[call.id]]);
        }
        this.store.insert(data);
        if (call.timer) {
            clearInterval(call.timer.interval);
            call.timer = null;
        }
    }

    async miss(call) {
        this.store.insert(await this.orm.call("phone.call", "miss_call", [[call.id]]));
        ++this.missedCalls;
    }

    async reject(call) {
        this.store.insert(await this.orm.call("phone.call", "reject_call", [[call.id]]));
    }

    async start(call) {
        this.store.insert(await this.orm.call("phone.call", "start_call", [[call.id]]));
        call.timer = {};
        // Use the time from the client (rather than call.start_date) to avoid
        // clock skew with the server.
        const timerStart = now().epochMilliseconds;
        const computeDuration = () => {
            call.timer.time = Math.floor((now().epochMilliseconds - timerStart) / 1000);
        };
        computeDuration();
        call.timer.interval = setInterval(computeDuration, 1000);
    }
}

export const callService = {
    dependencies: ["mail.store", "orm"],
    start(env, services) {
        return new CallService(env, services);
    },
};

registry.category("services").add("voip.call", callService);

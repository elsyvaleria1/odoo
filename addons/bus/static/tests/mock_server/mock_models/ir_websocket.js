import { makeKwArgs, models } from "@web/../tests/web_test_helpers";

export class IrWebSocket extends models.ServerModel {
    _name = "ir.websocket";

    /**
     * @param {number} inactivityPeriod
     */
    _update_presence(inactivityPeriod) {}

    /**
     * @returns {string[]}
     */
    _get_bus_channels(channels = []) {
        /** @type {import("mock_models").ResPartner} */
        const ResPartner = this.env["res.partner"];

        channels = [...channels];
        channels.push("broadcast");
        const authenticatedUserId = this.env.cookie.get("authenticated_user_sid");
        const [authenticatedPartner] = authenticatedUserId
            ? ResPartner.search_read(
                  [["user_ids", "in", [authenticatedUserId]]],
                  makeKwArgs({ context: { active_test: false } }),
              )
            : [];
        if (authenticatedPartner) {
            channels.push(authenticatedPartner);
        }
        return channels;
    }
}

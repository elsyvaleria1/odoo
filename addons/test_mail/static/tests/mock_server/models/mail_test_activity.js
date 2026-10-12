import { models } from "@web/../tests/web_test_helpers";
import { Domain } from "@web/core/domain";

export class MailTestActivity extends models.ServerModel {
    _name = "mail.test.activity";
    _inherit = ["mixin.mail.thread"];

    /**
     * The activity view's `activity_ids.active` condition is dropped, as the
     * mock get_activity_data drops it: the mock cannot evaluate it.
     *
     * @param {Record<string, any>} params
     */
    _search(params) {
        return super._search({
            ...params,
            domain: Domain.removeDomainLeaves(
                new Domain(params.domain ?? []).toList(),
                ["activity_ids.active"],
            ).toList(),
        });
    }
}

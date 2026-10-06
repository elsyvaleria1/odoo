import { defineLivechatModels } from "@im_livechat/../tests/livechat_test_helpers";
import { websiteHelpdeskLivechatModels } from "@website_helpdesk_livechat/../tests/website_helpdesk_livechat_test_helpers";

export function defineTestDiscussFullEnterpriseModels() {
    return defineLivechatModels(testDiscussFullEnterpriseModels);
}

export const testDiscussFullEnterpriseModels = {
    ...websiteHelpdeskLivechatModels,
};

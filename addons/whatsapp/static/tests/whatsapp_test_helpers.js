import "./mock_server/messaging_menu_mock_server.js";

import { mailModels } from "@mail/../tests/mail_test_helpers";
import { registerMailMockRoutes } from "@mail/../tests/mock_server/mail_mock_server";
import { defineModels } from "@web/../tests/web_test_helpers";

import { DiscussChannel } from "./mock_server/mock_models/discuss_channel.js";
import { MailMessage } from "./mock_server/mock_models/mail_message.js";
import { MailThread } from "./mock_server/mock_models/mail_thread.js";
import { WhatsAppAccount } from "./mock_server/mock_models/whatsapp_account.js";
import { WhatsAppComposer } from "./mock_server/mock_models/whatsapp_composer.js";
import { WhatsAppMessage } from "./mock_server/mock_models/whatsapp_message.js";
import { WhatsAppTemplate } from "./mock_server/mock_models/whatsapp_template.js";

export function defineWhatsAppModels() {
    registerMailMockRoutes();
    return defineModels(whatsAppModels);
}

export const whatsAppModels = {
    ...mailModels,
    DiscussChannel,
    MailMessage,
    MailThread,
    WhatsAppAccount,
    WhatsAppComposer,
    WhatsAppMessage,
    WhatsAppTemplate,
};

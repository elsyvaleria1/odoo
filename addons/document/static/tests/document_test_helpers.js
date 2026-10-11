import { DocumentsModels } from "@document/../tests/helpers/data";
import { registerMailMockRoutes } from "@mail/../tests/mock_server/mail_mock_server";
import { registerSessionGroups } from "@web/../tests/_framework/mock_session.hoot";
import { defineModels } from "@web/../tests/web_test_helpers";

registerSessionGroups({
    "document.group_documents_manager": true,
    "document.group_documents_user": true,
});

export const documentsModels = DocumentsModels;

export function defineDocumentsModels() {
    registerMailMockRoutes();
    return defineModels(documentsModels);
}

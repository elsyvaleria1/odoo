import { DocumentsModels } from "@document/../tests/helpers/data";
import { registerMailMockRoutes } from "@mail/../tests/mock_server/mail_mock_server";
import { registerSessionGroups } from "@web/../tests/_framework/mock_session.hoot";
import { defineModels } from "@web/../tests/web_test_helpers";

// document/models/ir_http.py adds these to session_info()["groups"] on every
// database it is installed in; the mock session carries them the same way, so
// document_service.start() reads them from the cache in every suite of the
// bundle instead of asking the mock server.
registerSessionGroups({
    "document.group_documents_manager": true,
    "document.group_documents_user": true,
});

export const documentsModels = DocumentsModels;

export function defineDocumentsModels() {
    registerMailMockRoutes();
    return defineModels(documentsModels);
}

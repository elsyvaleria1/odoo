from odoo.orm.runtime import environment as environment_module
from odoo.tests.common import tagged
from odoo.tools import translate as translate_tools

from .test_document_common import GIF, TransactionCaseDocuments


@tagged("post_install", "-at_install")
class TestDocumentsTrashChatterTranslation(TransactionCaseDocuments):
    def test_transition_messages_resolve_their_module_and_language(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        document = self.env["document.document"].create(
            {
                "type": "binary",
                "name": "translated trash",
                "datas": GIF,
                "folder_id": self.folder_b.id,
                "owner_id": self.doc_user.id,
            }
        )
        self.env.flush_all()

        seen = []

        def make_spy(original):
            def spy(module, lang, source, args=None):
                seen.append((module, lang, source))
                return original(module, lang, source, args)

            return spy

        self.patch(
            translate_tools,
            "get_translation",
            make_spy(translate_tools.get_translation),
        )
        self.patch(
            environment_module,
            "get_translation",
            make_spy(environment_module.get_translation),
        )
        document.with_context(lang="fr_FR").action_archive()

        resolved = {
            (module, lang) for module, lang, source in seen if "sent to trash" in source
        }
        self.assertTrue(resolved, "the trash message must be looked up at all")
        self.assertEqual(
            resolved,
            {("document", "fr_FR")},
            "under ('base', 'en_US') no .po entry of this module could match",
        )


@tagged("post_install", "-at_install", "mail_post")
class TestDocumentsChatterAttachments(TransactionCaseDocuments):
    def _empty_documents(self, count):
        return self.env["document.document"].create(
            [
                {"type": "binary", "name": f"Empty {i}", "folder_id": self.folder_b.id}
                for i in range(count)
            ]
        )

    def test_posted_attachments_never_become_the_file(self):
        single, *batch = self._empty_documents(3)
        batch = single.browse([document.id for document in batch])
        single.message_post(body="See attached", attachments=[("a.txt", b"hello")])
        messages = batch._message_post_values_all(
            {
                document.id: {
                    "body": "See attached",
                    "attachments": [("b.txt", b"hello")],
                }
                for document in batch
            }
        )
        self.assertEqual(len(messages.attachment_ids), 2)
        self.assertFalse((single | batch).attachment_id)

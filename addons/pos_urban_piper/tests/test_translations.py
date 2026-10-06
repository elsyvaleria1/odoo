from odoo.tests import TransactionCase, tagged
from odoo.tools.translate import TranslationModuleReader


@tagged("post_install", "-at_install")
class TestStoreStatusTranslations(TransactionCase):
    def test_the_store_status_notifications_are_extracted_whole(self):
        terms = {
            source
            for _module, _type, name, _res_id, source, *_rest in TranslationModuleReader(
                self.env.cr, ["pos_urban_piper"]
            )
            if name.endswith("/app/services/pos_store.js")
        }
        self.assertLessEqual(
            {
                "%(store)s is online on %(platform)s.",
                "%(store)s is offline on %(platform)s.",
                "Error occurred while updating %s status.",
            },
            terms,
        )

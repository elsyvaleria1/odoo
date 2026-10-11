from types import SimpleNamespace
from unittest.mock import patch

from odoo.db import db_connect
from odoo.service.transaction import retrying
from odoo.tests import TransactionCase, tagged
from odoo.tools import SQL, mute_logger

from odoo.addons.document_product.controllers import document_document
from odoo.addons.document_product.controllers.document_document import (
    ProductDocumentsController,
)


class _File:
    filename = "race.txt"
    content_type = "text/plain"

    def read(self):
        return b"race"


@tagged("post_install", "-at_install")
class TestProductDocumentUploadRaces(TransactionCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(self.drop_committed)

    def cursor(self):
        return db_connect(self.env.cr.dbname).cursor()

    def drop_committed(self):
        with self.cursor() as cr:
            env = self.env(cr=cr, su=True)
            products = env["product.template"].search([("name", "=", "race product")])
            env["document.document"].with_context(active_test=False).search(
                [("res_model", "=", products._name), ("res_id", "in", products.ids)]
            ).unlink()
            products.unlink()
            cr.commit()

    def committed_product(self):
        with self.cursor() as cr:
            product = self.env(cr=cr, su=True)["product.template"].create(
                {"name": "race product"}
            )
            cr.commit()
            return product.id

    def edit_product(self, env, product_id):
        env["product.template"].browse(product_id).description = "edited meanwhile"
        env.flush_all()

    def test_an_upload_that_loses_a_race_reruns_and_lands(self):
        product_id = self.committed_product()
        attempts = []

        def write_the_product(controller, **kwargs):
            request = document_document.request
            request.env.cr.execute(
                SQL("UPDATE product_template SET id = id WHERE id = %s", product_id)
            )
            return {}

        with self.cursor() as cr_upload, self.cursor() as cr_other:
            env = self.env(cr=cr_upload, su=True)

            def upload():
                attempts.append(len(attempts) + 1)
                env["product.template"].browse(product_id).name
                if len(attempts) == 1:
                    self.edit_product(self.env(cr=cr_other, su=True), product_id)
                    cr_other.commit()
                fake = SimpleNamespace(
                    env=env,
                    httprequest=SimpleNamespace(
                        files=SimpleNamespace(getlist=lambda name: [_File()])
                    ),
                    prepare_json_response=lambda result: result,
                )
                with (
                    patch.object(document_document, "request", fake),
                    patch.object(
                        ProductDocumentsController,
                        "_prepare_additional_document_vals",
                        write_the_product,
                    ),
                ):
                    return ProductDocumentsController.upload_document.__wrapped__(
                        ProductDocumentsController(),
                        _File(),
                        "product.template",
                        str(product_id),
                    )

            with mute_logger(
                "odoo.db.cursor",
                "odoo.service.model",
                "odoo.addons.document_product.controllers.document_document",
            ):
                result = retrying(upload, env)
        self.assertEqual(result, {"success": "All files uploaded"})
        self.assertEqual(
            len(attempts), 2, "the upload must fail to serialize, and rerun"
        )

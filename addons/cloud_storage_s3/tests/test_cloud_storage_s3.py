import hashlib
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, quote, urlencode, urlsplit

from botocore.exceptions import ClientError

from odoo import http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import HttpCase, TransactionCase, new_test_user, tagged

from .. import uninstall_hook
from ..tools import s3

CLIENT_FACTORY = "odoo.addons.cloud_storage_s3.tools.s3.boto3.client"


class TestCloudStorageS3Common(TransactionCase):
    def setUp(self):
        super().setUp()
        self.bucket_name = "test-odoo-bucket"
        self.region = "us-east-2"
        self.access_key_id = "AKIAIOSFODNN7EXAMPLE"
        self.secret_access_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

        icp = self.env["ir.config_parameter"]
        icp.set_param("cloud_storage_s3_enabled", "True")
        icp.set_param("cloud_storage_provider", "s3")
        icp.set_param(s3.PARAM_BUCKET, self.bucket_name)
        icp.set_param(s3.PARAM_REGION, self.region)
        s3.store_keys(self.env, self.access_key_id, self.secret_access_key)

        self.mock_s3_client = MagicMock()
        self.mock_s3_client.generate_presigned_url.return_value = (
            "https://presigned.example.com/test"
        )
        self.mock_s3_client.head_object.side_effect = ClientError(
            {"Error": {"Code": "404"}}, "HeadObject"
        )

        self._boto3_patcher = patch(CLIENT_FACTORY, return_value=self.mock_s3_client)
        self._boto3_patcher.start()

    def tearDown(self):
        self._boto3_patcher.stop()
        s3.clear_cache()
        super().tearDown()


class TestCloudStorageS3(TestCloudStorageS3Common):
    def test_generate_cloud_storage_url(self):
        attachment = self.env["ir.attachment"].create(
            [{"name": "test.txt", "mimetype": "text/plain", "datas": b""}]
        )
        attachment._post_add_create(cloud_storage=True)
        self.assertTrue(
            attachment.url.startswith(
                f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/"
            ),
            "URL should use the S3 virtual-hosted style",
        )

    def test_generate_url_with_special_characters(self):
        file_name = "reporte año 2026 (final).pdf"
        attachment = self.env["ir.attachment"].create(
            [{"name": file_name, "mimetype": "application/pdf", "datas": b""}]
        )
        attachment._post_add_create(cloud_storage=True)
        self.assertIn(
            quote(file_name),
            attachment.url,
            "Special characters in filename should be URL-encoded",
        )

    def test_generate_presigned_download_info(self):
        attachment = self.env["ir.attachment"].create(
            [{"name": "test.txt", "mimetype": "text/plain", "datas": b""}]
        )
        attachment._post_add_create(cloud_storage=True)
        info = attachment._generate_cloud_storage_download_info()
        self.assertIn("url", info)
        self.assertIn("time_to_expiry", info)
        self.mock_s3_client.generate_presigned_url.assert_called()

    def test_presigned_download_signs_the_disposition_it_is_given(self):
        attachment = self.env["ir.attachment"].create(
            [{"name": "test.txt", "mimetype": "text/plain", "datas": b""}]
        )
        attachment._post_add_create(cloud_storage=True)
        presign = self.mock_s3_client.generate_presigned_url

        attachment._generate_cloud_storage_download_info()
        self.assertNotIn("ResponseContentDisposition", presign.call_args[1]["Params"])

        attachment._generate_cloud_storage_download_info(
            content_disposition="attachment; filename=test.txt"
        )
        self.assertEqual(
            presign.call_args[1]["Params"]["ResponseContentDisposition"],
            "attachment; filename=test.txt",
        )

    def test_generate_presigned_upload_info(self):
        attachment = self.env["ir.attachment"].create(
            [{"name": "test.txt", "mimetype": "text/plain", "datas": b""}]
        )
        attachment._post_add_create(cloud_storage=True)
        info = attachment._generate_cloud_storage_upload_info()
        self.assertEqual(info["method"], "PUT")
        self.assertEqual(info["response_status"], 200)

    def test_blob_name_structure(self):
        attachment = self.env["ir.attachment"].create(
            [
                {
                    "name": "document.pdf",
                    "mimetype": "application/pdf",
                    "datas": b"",
                    "res_model": "res.partner",
                    "res_id": 1,
                }
            ]
        )
        attachment._post_add_create(cloud_storage=True)
        self.assertIn("res_partner/1/", attachment.url)

    def test_s3_url_validation(self):
        attachment = self.env["ir.attachment"].create(
            [
                {
                    "name": "test.txt",
                    "mimetype": "text/plain",
                    "type": "cloud_storage",
                    "url": f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/res_partner/1/42_abc12345_test.txt",
                }
            ]
        )
        info = attachment._get_s3_info()
        self.assertEqual(info["bucket_name"], self.bucket_name)
        self.assertEqual(info["region"], self.region)
        self.assertEqual(info["blob_name"], "res_partner/1/42_abc12345_test.txt")

    def test_s3_url_validation_invalid(self):
        attachment = self.env["ir.attachment"].create(
            [
                {
                    "name": "test.txt",
                    "mimetype": "text/plain",
                    "type": "cloud_storage",
                    "url": "https://storage.googleapis.com/bucket/blob",
                }
            ]
        )
        with self.assertRaises(ValidationError):
            attachment._get_s3_info()

    def test_unlink_deletes_s3_blobs_batch(self):
        attachments = self.env["ir.attachment"]
        for i in range(3):
            attachments |= self.env["ir.attachment"].create(
                [
                    {
                        "name": f"file_{i}.txt",
                        "mimetype": "text/plain",
                        "type": "cloud_storage",
                        "url": f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/test/{i}_abc_file_{i}.txt",
                    }
                ]
            )
        attachments.unlink()
        self.mock_s3_client.delete_objects.assert_called_once()
        call_args = self.mock_s3_client.delete_objects.call_args
        self.assertEqual(call_args.kwargs["Bucket"], self.bucket_name)
        self.assertEqual(len(call_args.kwargs["Delete"]["Objects"]), 3)

    def test_unlink_non_s3_attachments_ignored(self):
        attachment = self.env["ir.attachment"].create(
            [
                {
                    "name": "local.txt",
                    "mimetype": "text/plain",
                    "datas": b"",
                }
            ]
        )
        attachment.unlink()
        self.mock_s3_client.delete_objects.assert_not_called()

    def test_client_cache_invalidation(self):
        with patch(CLIENT_FACTORY, side_effect=lambda *a, **kw: MagicMock()):
            s3.clear_cache()
            client1 = s3.get_client(self.env)
            client2 = s3.get_client(self.env)
            self.assertIs(client1, client2)

            s3.store_keys(self.env, "NEWKEY", self.secret_access_key)
            client3 = s3.get_client(self.env)
            self.assertIsNot(client1, client3)

    def test_keys_live_in_the_vault_only(self):
        credential = s3.get_credential(self.env)
        self.assertEqual(credential.storage_method, "json")
        self.assertEqual(
            credential.get_credential_dict(),
            {
                "access_key_id": self.access_key_id,
                "secret_access_key": self.secret_access_key,
            },
        )
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT count(*) FROM ir_config_parameter WHERE value LIKE %s",
            (f"%{self.secret_access_key}%",),
        )
        self.assertEqual(self.env.cr.fetchone()[0], 0)

    def test_settings_store_keys_and_clear_the_wizard_row(self):
        settings = self.env["res.config.settings"].create(
            {
                "cloud_storage_s3_access_key_id": "AKIANEWKEY",
                "cloud_storage_s3_secret_access_key": "newsecret",
            }
        )
        with patch.object(
            type(settings), "_setup_cloud_storage_provider", return_value=None
        ):
            settings.set_values()
        self.assertEqual(s3.get_keys(self.env)["access_key_id"], "AKIANEWKEY")
        self.assertFalse(settings.cloud_storage_s3_access_key_id)
        self.assertFalse(settings.cloud_storage_s3_secret_access_key)
        self.assertTrue(settings.cloud_storage_s3_keys_set)
        self.assertTrue(
            self.env["res.config.settings"].get_values()["cloud_storage_s3_keys_set"]
        )

    def test_settings_refuse_half_a_key_pair(self):
        settings = self.env["res.config.settings"].create(
            {"cloud_storage_s3_access_key_id": "AKIANEWKEY"}
        )
        with self.assertRaises(UserError):
            settings.set_values()

    def test_configuration_needs_the_vault_keys(self):
        settings = self.env["res.config.settings"].new({})
        self.assertTrue(settings._get_cloud_storage_configuration())
        s3.get_credential(self.env).active = False
        s3.clear_cache()
        self.assertFalse(settings._get_cloud_storage_configuration())

    def test_is_s3_provider(self):
        attachment = self.env["ir.attachment"].new()
        self.assertTrue(attachment._is_s3_provider())

        self.env["ir.config_parameter"].set_param("cloud_storage_provider", "google")
        self.assertFalse(attachment._is_s3_provider())

    def test_uninstall_fail(self):
        with self.assertRaises(UserError):
            attachment = self.env["ir.attachment"].create(
                [{"name": "test.txt", "mimetype": "text/plain", "datas": b""}]
            )
            attachment._post_add_create(cloud_storage=True)
            attachment.flush_recordset()
            uninstall_hook(self.env)

    def test_uninstall_success(self):
        uninstall_hook(self.env)
        icp = self.env["ir.config_parameter"]
        self.assertFalse(icp.get_param("cloud_storage_provider"))
        self.assertFalse(icp.get_param(s3.PARAM_BUCKET))
        self.assertFalse(icp.get_param(s3.PARAM_REGION))
        self.assertFalse(s3.get_credential(self.env))


class TestCloudStorageS3Endpoint(TestCloudStorageS3Common):
    def setUp(self):
        super().setUp()
        self.region = "bhs"
        self.host = "s3.bhs.io.cloud.ovh.net"
        icp = self.env["ir.config_parameter"]
        icp.set_param(s3.PARAM_REGION, self.region)
        icp.set_param(s3.PARAM_ENDPOINT, f"{self.host}/")
        s3.clear_cache()

    def _cloud_attachment(self, url):
        return self.env["ir.attachment"].create(
            [
                {
                    "name": "test.txt",
                    "mimetype": "text/plain",
                    "type": "cloud_storage",
                    "url": url,
                }
            ]
        )

    def test_client_points_at_the_endpoint(self):
        with patch(CLIENT_FACTORY, return_value=self.mock_s3_client) as factory:
            s3.get_client(self.env)
        self.assertEqual(
            factory.call_args.kwargs["endpoint_url"], f"https://{self.host}"
        )
        self.assertEqual(factory.call_args.kwargs["region_name"], self.region)

    def test_changing_the_endpoint_rebuilds_the_client(self):
        with patch(CLIENT_FACTORY, side_effect=lambda *a, **kw: MagicMock()):
            client1 = s3.get_client(self.env)
            self.env["ir.config_parameter"].set_param(s3.PARAM_ENDPOINT, False)
            client2 = s3.get_client(self.env)
        self.assertIsNot(client1, client2)

    def test_amazon_client_has_no_endpoint(self):
        self.env["ir.config_parameter"].set_param(s3.PARAM_ENDPOINT, False)
        with patch(CLIENT_FACTORY, return_value=self.mock_s3_client) as factory:
            s3.get_client(self.env)
        self.assertIsNone(factory.call_args.kwargs["endpoint_url"])

    def test_generated_url_uses_the_endpoint_host(self):
        attachment = self.env["ir.attachment"].create(
            [{"name": "test.txt", "mimetype": "text/plain", "datas": b""}]
        )
        attachment._post_add_create(cloud_storage=True)
        self.assertTrue(
            attachment.url.startswith(f"https://{self.bucket_name}.{self.host}/")
        )
        info = attachment._get_s3_info()
        self.assertEqual(info["bucket_name"], self.bucket_name)
        self.assertEqual(info["region"], self.region)

    def test_endpoint_url_resolves_bucket_and_key(self):
        attachment = self._cloud_attachment(
            f"https://{self.bucket_name}.{self.host}/res_partner/1/42_a%20b.txt"
        )
        info = attachment._get_s3_info()
        self.assertEqual(info["bucket_name"], self.bucket_name)
        self.assertEqual(info["region"], self.region)
        self.assertEqual(info["blob_name"], "res_partner/1/42_a b.txt")

    def test_amazon_url_still_resolves_with_an_endpoint(self):
        attachment = self._cloud_attachment(
            "https://old-bucket.s3.us-east-2.amazonaws.com/res_partner/1/x.txt"
        )
        info = attachment._get_s3_info()
        self.assertEqual(info["bucket_name"], "old-bucket")
        self.assertEqual(info["region"], "us-east-2")

    def test_url_of_another_host_is_refused(self):
        attachment = self._cloud_attachment(
            f"https://{self.bucket_name}.s3.gra.io.cloud.ovh.net/x.txt"
        )
        with self.assertRaises(ValidationError):
            attachment._get_s3_info()

    def test_unlink_deletes_endpoint_blobs(self):
        self._cloud_attachment(
            f"https://{self.bucket_name}.{self.host}/t/1.txt"
        ).unlink()
        call_args = self.mock_s3_client.delete_objects.call_args
        self.assertEqual(call_args.kwargs["Bucket"], self.bucket_name)
        self.assertEqual(call_args.kwargs["Delete"]["Objects"], [{"Key": "t/1.txt"}])

    def test_uninstall_blocked_by_endpoint_attachment(self):
        self._cloud_attachment(f"https://{self.bucket_name}.{self.host}/t/1.txt")
        self.env.flush_all()
        with self.assertRaises(UserError):
            uninstall_hook(self.env)

    def test_ovh_provider_is_served_by_this_module(self):
        icp = self.env["ir.config_parameter"]
        icp.set_param("cloud_storage_provider", "ovh")
        attachment = self.env["ir.attachment"].new()
        self.assertTrue(attachment._is_s3_provider())
        self.assertTrue(s3.get_config(self.env))
        icp.set_param("cloud_storage_s3_storage_mode", "hybrid")
        self.assertTrue(attachment._is_s3_hybrid())

    def test_switching_to_ovh_keeps_attachments_in_use(self):
        self._cloud_attachment(f"https://{self.bucket_name}.{self.host}/t/1.txt")
        self.env.flush_all()
        settings = self.env["res.config.settings"].create(
            {"cloud_storage_provider": "ovh"}
        )
        settings._check_cloud_storage_uninstallable()
        settings.cloud_storage_provider = False
        with self.assertRaises(UserError):
            settings._check_cloud_storage_uninstallable()

    def test_cloud_only_cors_lets_a_viewer_read_ranges(self):
        self.env["ir.config_parameter"].set_param(
            "cloud_storage_s3_storage_mode", "s3_only"
        )
        self.mock_s3_client.get_object.return_value = {"Body": MagicMock()}
        self.env["res.config.settings"]._setup_cloud_storage_provider()
        rule = self.mock_s3_client.put_bucket_cors.call_args.kwargs[
            "CORSConfiguration"
        ]["CORSRules"][0]
        self.assertIn("Range", rule["AllowedHeaders"])
        self.assertTrue(
            {"Content-Range", "Accept-Ranges"} <= set(rule["ExposeHeaders"])
        )

    def test_ovh_without_endpoint_is_not_configured(self):
        icp = self.env["ir.config_parameter"]
        icp.set_param("cloud_storage_provider", "ovh")
        icp.set_param(s3.PARAM_ENDPOINT, False)
        self.assertFalse(s3.get_config(self.env))
        with self.assertRaises(UserError):
            s3.get_client(self.env)

    def test_uninstall_drops_the_endpoint(self):
        uninstall_hook(self.env)
        self.assertFalse(self.env["ir.config_parameter"].get_param(s3.PARAM_ENDPOINT))


class TestCloudStorageS3Move(TestCloudStorageS3Common):
    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].set_param(
            "cloud_storage_s3_storage_mode", "s3_only"
        )
        self.data = b"%PDF-1.4 agromarin move test"
        self.mock_s3_client.head_object.side_effect = None
        self.mock_s3_client.head_object.return_value = {
            "ContentLength": len(self.data),
            "ETag": f'"{hashlib.md5(self.data, usedforsecurity=False).hexdigest()}"',
        }

    def _local(self, **vals):
        return self.env["ir.attachment"].create(
            [
                {
                    "name": "contrato.pdf",
                    "raw": self.data,
                    "res_model": "res.partner",
                    "res_id": 1,
                    **vals,
                }
            ]
        )

    def test_move_serves_from_the_bucket_and_keeps_metadata(self):
        attachment = self._local()
        before = attachment.read(
            ["checksum", "file_size", "index_content", "mimetype", "store_fname"]
        )[0]
        outcome = attachment._s3_move_to_cloud()
        self.assertEqual(outcome, {"moved": attachment.ids})
        self.assertEqual(attachment.type, "cloud_storage")
        info = attachment._get_s3_info()
        self.assertEqual(info["bucket_name"], self.bucket_name)
        after = attachment.read(list(before) + ["id"])[0]
        for field, value in before.items():
            self.assertEqual(after[field], value, field)
        call = self.mock_s3_client.put_object.call_args.kwargs
        self.assertEqual(call["Key"], info["blob_name"])
        self.assertEqual(call["ContentLength"], len(self.data))
        self.assertEqual(call["ContentType"], "application/pdf")
        self.assertTrue(call["ContentMD5"])

    def test_move_is_undone_by_writing_the_type_back(self):
        attachment = self._local()
        attachment._s3_move_to_cloud()
        attachment.write({"type": "binary", "url": False})
        self.assertEqual(attachment.raw, self.data)

    def test_move_refuses_what_it_cannot_serve(self):
        empty = self._local(name="empty.txt", raw=b"")
        served = self._local(name="sitemap.xml", url="/sitemap-1.xml")
        outcome = (empty | served)._s3_move_to_cloud()
        self.assertEqual(
            outcome, {"not_in_filestore": empty.ids, "served_by_url": served.ids}
        )
        self.assertEqual(served.url, "/sitemap-1.xml")
        self.mock_s3_client.put_object.assert_not_called()

    def test_move_takes_a_field_attachment(self):
        field = self._local(name="image_128", res_field="image_128")
        self.assertEqual(field._s3_move_to_cloud(), {"moved": field.ids})
        self.assertEqual(field.type, "cloud_storage")
        self.assertEqual(field.res_field, "image_128")

    def _age(self, attachments, minutes):
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE ir_attachment SET write_date = now() at time zone 'utc'"
            " - make_interval(mins => %s) WHERE id = ANY(%s)",
            [minutes, attachments.ids],
        )
        attachments.invalidate_recordset()

    def test_cron_moves_and_releases_what_was_stored_here(self):
        old = self._local()
        field = self._local(name="image_128", res_field="image_128")
        fresh = self._local(name="fresh.pdf")
        asset = self._local(name="web.assets.css", url="/web/assets/1/web.css")
        self._age(old | field | asset, 60)
        with (
            patch.object(type(self.env["ir.attachment"]), "_mark_for_gc_multi"),
            patch.object(type(self.env["ir.cron"]), "_commit_progress", return_value=1),
        ):
            self.env["ir.attachment"]._cron_s3_move_local_to_cloud()
        for moved in (old, field):
            self.assertEqual(moved.type, "cloud_storage")
            self.assertFalse(moved.store_fname)
        self.assertEqual(fresh.type, "binary", "a row still being written waits")
        self.assertEqual(asset.type, "binary", "a served URL stays local")

    def test_cron_leaves_hybrid_storage_alone(self):
        self.env["ir.config_parameter"].set_param(
            "cloud_storage_s3_storage_mode", "hybrid"
        )
        old = self._local()
        self._age(old, 60)
        self.env["ir.attachment"]._cron_s3_move_local_to_cloud()
        self.assertEqual(old.type, "binary")
        self.mock_s3_client.put_object.assert_not_called()

    def test_move_keeps_local_when_the_store_disagrees(self):
        attachment = self._local()
        self.mock_s3_client.head_object.return_value = {
            "ContentLength": len(self.data),
            "ETag": '"0000"',
        }
        outcome = attachment._s3_move_to_cloud()
        self.assertEqual(outcome, {"verify_failed": attachment.ids})
        self.assertEqual(attachment.type, "binary")

    def test_move_keeps_local_when_the_upload_fails(self):
        attachment = self._local()
        self.mock_s3_client.put_object.side_effect = ClientError(
            {"Error": {"Code": "BadDigest"}}, "PutObject"
        )
        with self.assertLogs(
            "odoo.addons.cloud_storage_s3.models.ir_attachment", "WARNING"
        ):
            outcome = attachment._s3_move_to_cloud()
        self.assertEqual(outcome, {"error": attachment.ids})
        self.assertEqual(attachment.type, "binary")

    def test_move_refuses_a_truncated_local_file(self):
        attachment = self._local()
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE ir_attachment SET file_size = file_size + 1 WHERE id = %s",
            [attachment.id],
        )
        attachment.invalidate_recordset()
        outcome = attachment._s3_move_to_cloud()
        self.assertEqual(outcome, {"size_mismatch": attachment.ids})
        self.mock_s3_client.put_object.assert_not_called()

    def test_release_drops_the_local_file_and_keeps_metadata(self):
        attachment = self._local()
        attachment._s3_move_to_cloud()
        size, checksum = attachment.file_size, attachment.checksum
        fname = attachment.store_fname
        with patch.object(
            type(self.env["ir.attachment"]), "_mark_for_gc_multi"
        ) as mark:
            outcome = attachment._s3_release_local_files()
        self.assertEqual(outcome, {"released": attachment.ids})
        self.assertFalse(attachment.store_fname)
        self.assertEqual(attachment.file_size, size)
        self.assertEqual(attachment.checksum, checksum)
        mark.assert_called_once_with([fname])

    def test_release_refuses_when_the_object_size_differs(self):
        attachment = self._local()
        attachment._s3_move_to_cloud()
        self.mock_s3_client.head_object.return_value = {"ContentLength": 1}
        outcome = attachment._s3_release_local_files()
        self.assertEqual(outcome, {"verify_failed": attachment.ids})
        self.assertTrue(attachment.store_fname)

    def test_release_refuses_a_local_attachment(self):
        attachment = self._local()
        outcome = attachment._s3_release_local_files()
        self.assertEqual(outcome, {"not_releasable": attachment.ids})

    def test_rewriting_a_cloud_attachment_deletes_its_unused_blob(self):
        attachment = self._local()
        attachment._s3_move_to_cloud()
        key = attachment._get_s3_info()["blob_name"]
        attachment.write({"raw": b"new content"})
        self.assertEqual(attachment.type, "binary")
        self.mock_s3_client.delete_objects.assert_not_called()
        self.env.cr.postcommit.run()
        self.mock_s3_client.delete_objects.assert_called_once()
        objects = self.mock_s3_client.delete_objects.call_args.kwargs["Delete"][
            "Objects"
        ]
        self.assertEqual(objects, [{"Key": key}])

    def test_rewriting_keeps_a_blob_a_copy_still_uses(self):
        attachment = self._local()
        attachment._s3_move_to_cloud()
        copy = attachment.copy()
        copy.write({"raw": b"new content"})
        self.env.cr.postcommit.run()
        self.mock_s3_client.delete_objects.assert_not_called()
        self.assertEqual(attachment.type, "cloud_storage")

    def test_unlink_keeps_a_blob_a_copy_still_uses(self):
        attachment = self._local()
        attachment._s3_move_to_cloud()
        copy = attachment.copy()
        self.assertEqual(copy.url, attachment.url)
        attachment.unlink()
        self.mock_s3_client.delete_objects.assert_not_called()
        copy.unlink()
        self.mock_s3_client.delete_objects.assert_called_once()

    def test_a_user_keeps_a_blob_an_attachment_they_cannot_read_uses(self):
        employee = new_test_user(
            self.env, login="s3_employee", groups="base.group_user"
        )
        parameter = self.env["ir.config_parameter"].search([], limit=1)
        hidden = self._local(res_model="ir.config_parameter", res_id=parameter.id)
        hidden._s3_move_to_cloud()
        own = hidden.copy({"res_model": False, "res_id": False})
        self.env.cr.execute(
            "UPDATE ir_attachment SET create_uid = %s WHERE id = %s",
            (employee.id, own.id),
        )
        self.env.invalidate_all()
        self.assertFalse(
            self.env["ir.attachment"]
            .with_user(employee)
            .search([("id", "=", hidden.id)])
        )
        own.with_user(employee).unlink()
        self.mock_s3_client.delete_objects.assert_not_called()

    def test_an_employee_signs_with_keys_they_cannot_read(self):
        employee = new_test_user(self.env, login="s3_signer", groups="base.group_user")
        attachment = (
            self.env["ir.attachment"]
            .with_user(employee)
            .create([{"name": "nota.txt", "mimetype": "text/plain", "datas": b""}])
        )
        attachment._post_add_create(cloud_storage=True)
        s3.clear_cache()
        info = attachment._generate_cloud_storage_download_info()
        self.assertIn("url", info)
        self.mock_s3_client.generate_presigned_url.assert_called()
        with self.assertRaises(AccessError):
            self.env["credential.credential"].with_user(employee).search_count([])


class TestCloudStorageS3Hybrid(TestCloudStorageS3Common):
    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].set_param(
            "cloud_storage_s3_storage_mode", "hybrid"
        )

    def _make_attachment(self, **vals):
        defaults = {
            "name": "doc.txt",
            "raw": b"hello world",
            "res_model": "res.partner",
            "res_id": 1,
        }
        defaults.update(vals)
        return self.env["ir.attachment"].create([defaults])

    def test_create_flags_business_attachment_pending(self):
        attachment = self._make_attachment()
        self.assertEqual(attachment.type, "binary")
        self.assertTrue(attachment.s3_mirror_pending)

    def test_create_does_not_upload_in_the_request_transaction(self):
        attachment = self._make_attachment()
        self.assertTrue(attachment.s3_mirror_pending)
        self.assertEqual(
            len(self.env.cr.postcommit),
            0,
            "the mirror must not be queued on the request cursor: running it "
            "there uploads to S3 while the main transaction sits idle",
        )
        self.env.cr.postcommit.run()
        self.mock_s3_client.put_object.assert_not_called()
        self.assertTrue(attachment.s3_mirror_pending)

    def test_create_skips_system_assets(self):
        attachment = self.env["ir.attachment"].create(
            [{"name": "bundle.js", "raw": b"console.log(1)"}]
        )
        self.assertFalse(attachment.s3_mirror_pending)

    def test_post_add_create_keeps_local_in_hybrid(self):
        attachment = self._make_attachment()
        attachment._post_add_create(cloud_storage=True)
        self.assertEqual(attachment.type, "binary")
        self.assertFalse(attachment.url)

    def test_mirror_uploads_and_clears_pending(self):
        attachment = self._make_attachment()
        attachment._s3_mirror_to_cloud()
        self.mock_s3_client.put_object.assert_called_once()
        call = self.mock_s3_client.put_object.call_args
        self.assertEqual(call.kwargs["Bucket"], self.bucket_name)
        self.assertEqual(call.kwargs["Body"], b"hello world")
        self.assertFalse(attachment.s3_mirror_pending)
        self.assertTrue(attachment.s3_blob_name)

    def test_mirror_failure_keeps_pending(self):
        self.mock_s3_client.put_object.side_effect = Exception("network down")
        attachment = self._make_attachment()
        attachment._s3_mirror_to_cloud()
        self.assertTrue(attachment.s3_mirror_pending)
        self.assertFalse(attachment.s3_blob_name)

    def test_cron_mirrors_pending(self):
        attachment = self._make_attachment()
        self.env["ir.attachment"]._cron_mirror_pending_to_s3()
        self.mock_s3_client.put_object.assert_called()
        self.assertFalse(attachment.s3_mirror_pending)

    def test_unlink_deletes_hybrid_mirror(self):
        attachment = self._make_attachment()
        attachment._s3_mirror_to_cloud()
        blob_name = attachment.s3_blob_name
        attachment.unlink()
        self.mock_s3_client.delete_objects.assert_called_once()
        call = self.mock_s3_client.delete_objects.call_args
        self.assertEqual(call.kwargs["Bucket"], self.bucket_name)
        self.assertEqual(call.kwargs["Delete"]["Objects"], [{"Key": blob_name}])

    def test_write_flags_late_res_model(self):
        attachment = self.env["ir.attachment"].create(
            [{"name": "late.pdf", "raw": b"pdf-bytes"}]
        )
        self.assertFalse(attachment.s3_mirror_pending)
        attachment.write({"res_model": "document.document", "res_id": 99})
        self.assertTrue(attachment.s3_mirror_pending)

    def test_blob_name_mirrors_filestore(self):
        attachment = self._make_attachment()
        attachment._s3_mirror_to_cloud()
        self.assertEqual(attachment.s3_blob_name, attachment.store_fname)

    def test_unlink_keeps_shared_blob(self):
        a1 = self._make_attachment(name="a.txt")
        a2 = self._make_attachment(name="b.txt")
        a1._s3_mirror_to_cloud()
        a2._s3_mirror_to_cloud()
        self.assertEqual(a1.s3_blob_name, a2.s3_blob_name)
        a1.unlink()
        self.mock_s3_client.delete_objects.assert_not_called()
        a2.unlink()
        self.mock_s3_client.delete_objects.assert_called_once()

    def test_mirror_skips_existing_object(self):
        self.mock_s3_client.head_object.side_effect = None
        self.mock_s3_client.head_object.return_value = {"ContentLength": 11}
        attachment = self._make_attachment()
        attachment._s3_mirror_to_cloud()
        self.mock_s3_client.put_object.assert_not_called()
        self.assertFalse(attachment.s3_mirror_pending)
        self.assertTrue(attachment.s3_blob_name)

    def test_backfill_mirrors_existing(self):
        attachment = self._make_attachment()
        attachment.s3_mirror_pending = False
        self.assertFalse(attachment.s3_blob_name)
        self.env["ir.attachment"]._s3_backfill_to_s3(
            batch_size=1000, commit_each_batch=False
        )
        self.assertTrue(attachment.s3_blob_name)
        self.assertFalse(attachment.s3_mirror_pending)

    def test_backfill_includes_binary_field_attachments(self):
        attachment = self._make_attachment(res_field="image_128")
        attachment.s3_mirror_pending = False
        self.assertFalse(attachment.s3_blob_name)
        self.env["ir.attachment"]._s3_backfill_to_s3(
            batch_size=1000, commit_each_batch=False
        )
        self.assertEqual(attachment.s3_blob_name, attachment.store_fname)
        self.assertFalse(attachment.s3_mirror_pending)

    def test_cron_retries_binary_field_attachments(self):
        attachment = self._make_attachment(res_field="image_128")
        self.assertTrue(attachment.s3_mirror_pending)
        self.env["ir.attachment"]._cron_mirror_pending_to_s3()
        self.assertFalse(attachment.s3_mirror_pending)
        self.assertEqual(attachment.s3_blob_name, attachment.store_fname)

    def test_unlink_keeps_blob_shared_with_binary_field_attachment(self):
        doc = self._make_attachment(name="doc.txt")
        field_att = self._make_attachment(name="field.bin", res_field="image_128")
        doc._s3_mirror_to_cloud()
        field_att._s3_mirror_to_cloud()
        self.assertEqual(doc.s3_blob_name, field_att.s3_blob_name)
        doc.unlink()
        self.mock_s3_client.delete_objects.assert_not_called()

    def test_backfill_ends_when_an_attachment_has_no_content(self):
        attachment = self._make_attachment()
        attachment.s3_mirror_pending = False
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE ir_attachment SET store_fname = 'ab/missing' WHERE id = %s",
            [attachment.id],
        )
        attachment.invalidate_recordset()
        Attachment = self.registry["ir.attachment"]
        mirror = Attachment._s3_mirror_to_cloud
        visits = []

        def record(records):
            if attachment in records:
                visits.append(attachment.id)
                if len(visits) > 3:
                    raise AssertionError("backfill re-reads the same attachment")
            return mirror(records)

        with patch.object(
            Attachment, "_s3_mirror_to_cloud", autospec=True, side_effect=record
        ):
            self.env["ir.attachment"]._s3_backfill_to_s3(commit_each_batch=False)
        self.assertEqual(visits, [attachment.id])
        self.assertFalse(attachment.s3_blob_name)

    def test_disabled_environment_skips_s3(self):
        self.env["ir.config_parameter"].set_param("cloud_storage_s3_enabled", "False")
        attachment = self._make_attachment()
        self.assertFalse(attachment.s3_mirror_pending)
        self.env["ir.attachment"]._cron_mirror_pending_to_s3()
        self.env["ir.attachment"]._s3_backfill_to_s3()
        self.mock_s3_client.put_object.assert_not_called()

    def test_unlink_disabled_skips_s3_delete(self):
        attachment = self._make_attachment()
        attachment._s3_mirror_to_cloud()
        self.assertTrue(attachment.s3_blob_name)
        self.env["ir.config_parameter"].set_param("cloud_storage_s3_enabled", "False")
        attachment.unlink()
        self.mock_s3_client.delete_objects.assert_not_called()

    def test_config_available_when_disabled(self):
        self.env["ir.config_parameter"].set_param("cloud_storage_s3_enabled", "False")
        settings = self.env["res.config.settings"].new({})
        self.assertTrue(settings._get_cloud_storage_configuration())


@tagged("post_install", "-at_install")
class TestDocumentsDirectUpload(HttpCase):
    def setUp(self):
        super().setUp()
        if "document.document" not in self.env:
            self.skipTest("document is not installed")
        icp = self.env["ir.config_parameter"]
        icp.set_param("cloud_storage_s3_enabled", "True")
        icp.set_param("cloud_storage_provider", "s3")
        icp.set_param(s3.PARAM_BUCKET, "test-odoo-bucket")
        icp.set_param(s3.PARAM_REGION, "us-east-2")
        s3.store_keys(self.env, "AKIAIOSFODNN7EXAMPLE", "secret")
        client = MagicMock()
        client.generate_presigned_url.return_value = "https://presigned.example.com/put"
        self._boto3_patcher = patch(CLIENT_FACTORY, return_value=client)
        self._boto3_patcher.start()
        self.uploader = self.env["res.users"].create(
            {
                "name": "Uploader",
                "login": "uploader",
                "password": "uploader_pwd",
                "group_ids": [
                    (6, 0, [self.env.ref("document.group_documents_user").id])
                ],
            }
        )

    def tearDown(self):
        self._boto3_patcher.stop()
        s3.clear_cache()
        super().tearDown()

    def test_upload_route_signs_a_direct_upload(self):
        self.authenticate("uploader", "uploader_pwd")
        response = self.url_open(
            "/documents/upload/",
            data={
                "csrf_token": http.Request.csrf_token(self),
                "user_folder_id": "MY",
                "cloud_storage": "1",
                "file_size": "4096",
            },
            files={"ufile": ("big.bin", b"", "application/octet-stream")},
        )
        response.raise_for_status()
        payload = response.json()
        document = self.env["document.document"].browse(payload["document_ids"])
        self.assertEqual(payload["upload_info"]["method"], "PUT")
        self.assertEqual(
            payload["upload_info"]["url"], "https://presigned.example.com/put"
        )
        attachment = document.attachment_id
        self.assertEqual(attachment.type, "cloud_storage")
        self.assertEqual(attachment.file_size, 4096)
        self.assertEqual(document.file_size, 4096)
        self.assertIn("document_document/", attachment.url)
        self.assertEqual(attachment.res_id, document.id)
        self.assertNotIn(
            "document.document",
            self.env["ir.attachment"]._get_cloud_storage_unsupported_models(),
        )


@tagged("post_install", "-at_install")
class TestS3CredentialSlots(TransactionCase):
    def test_the_category_declares_both_iam_keys(self):
        category = self.env.ref(s3.CREDENTIAL_CATEGORY_XMLID)

        self.assertEqual(
            set(category.field_ids.mapped("code")),
            {"access_key_id", "secret_access_key"},
        )

    def test_a_credential_missing_the_secret_key_is_refused(self):
        with self.assertRaises(ValidationError):
            self.env["credential.credential"].create(
                {
                    "name": "S3 without its secret",
                    "category_id": self.env.ref(s3.CREDENTIAL_CATEGORY_XMLID).id,
                    "credential_data": '{"access_key_id": "AKIA"}',
                }
            )


@tagged("post_install", "-at_install")
class TestCloudStorageS3DownloadName(HttpCase):

    def setUp(self):
        super().setUp()
        icp = self.env["ir.config_parameter"]
        icp.set_param("cloud_storage_s3_enabled", "True")
        icp.set_param("cloud_storage_provider", "s3")
        icp.set_param(s3.PARAM_BUCKET, "test-odoo-bucket")
        icp.set_param(s3.PARAM_REGION, "us-east-2")
        s3.store_keys(self.env, "AKIAIOSFODNN7EXAMPLE", "secret")
        self.client = MagicMock()
        self.client.generate_presigned_url.side_effect = (
            lambda method, Params, ExpiresIn: (
                "https://presigned.example.com/get?"
                + urlencode(
                    {
                        "response-content-disposition": Params.get(
                            "ResponseContentDisposition", ""
                        )
                    }
                )
            )
        )
        self._boto3_patcher = patch(CLIENT_FACTORY, return_value=self.client)
        self._boto3_patcher.start()
        self.authenticate("admin", "admin")

    def tearDown(self):
        self._boto3_patcher.stop()
        s3.clear_cache()
        super().tearDown()

    def _redirect_disposition(self, url):
        response = self.url_open(url, allow_redirects=False)
        self.assertEqual(response.status_code, 302)
        query = parse_qs(urlsplit(response.headers["Location"]).query)
        return query["response-content-disposition"][0]

    def _cloud_attachment(self, name):
        attachment = self.env["ir.attachment"].create(
            [{"name": name, "mimetype": "application/pkix-cert", "datas": b""}]
        )
        attachment._post_add_create(cloud_storage=True)
        return attachment

    def test_web_content_names_the_file_for_download_and_preview(self):
        attachment = self._cloud_attachment("marl640819192.cer")
        self.assertEqual(
            self._redirect_disposition(f"/web/content/{attachment.id}?download=true"),
            "attachment; filename=marl640819192.cer",
        )
        self.assertEqual(
            self._redirect_disposition(f"/web/content/{attachment.id}"),
            "inline; filename=marl640819192.cer",
        )

    def test_non_ascii_name_survives_the_redirect(self):
        attachment = self._cloud_attachment("CSD Marín.cer")
        self.assertEqual(
            self._redirect_disposition(f"/web/content/{attachment.id}?download=true"),
            'attachment; filename="CSD Marin.cer"; '
            "filename*=UTF-8''CSD%20Mar%C3%ADn.cer",
        )

    def test_documents_content_names_the_file(self):
        if "document.document" not in self.env:
            self.skipTest("document is not installed")
        document = self.env["document.document"].create(
            {
                "name": "Claveprivada_FIEL.key",
                "raw": b"",
                "folder_id": self.env["document.document"]
                .create({"name": "Accesos", "type": "folder"})
                .id,
            }
        )
        document.attachment_id._post_add_create(cloud_storage=True)
        self.assertEqual(
            self._redirect_disposition(f"/documents/content/{document.access_token}"),
            "attachment; filename=Claveprivada_FIEL.key",
        )

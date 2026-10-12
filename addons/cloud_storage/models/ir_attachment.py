import logging
import uuid

from odoo import fields, models
from odoo.exceptions import MissingError, UserError, ValidationError
from odoo.http import Stream, prepare_content_disposition_header

from odoo.addons.base.models.ir_binary import STREAM_INLINE_CONTEXT_KEY

_logger = logging.getLogger(__name__)


class CloudStorageStream(Stream):
    def __init__(self, attachment, **kwargs) -> None:
        super().__init__(**kwargs)
        self._attachment = attachment

    def prepare_response(self, as_attachment=None, *args, **kwargs):
        if as_attachment is None:
            as_attachment = self.as_attachment
        if self.download_name:
            self.url = self._attachment._generate_cloud_storage_download_info(
                content_disposition=prepare_content_disposition_header(
                    self.download_name,
                    "attachment" if as_attachment else "inline",
                ),
            )["url"]
        return super().prepare_response(as_attachment, *args, **kwargs)

    def read(self) -> bytes:
        return self._attachment._get_content()


class IrAttachment(models.Model):
    _inherit = "ir.attachment"
    _cloud_storage_upload_url_time_to_expiry = 300
    _cloud_storage_download_url_time_to_expiry = 300

    type = fields.Selection(
        selection_add=[("cloud_storage", "Cloud Storage")],
        ondelete={"cloud_storage": "set url"},
    )

    def _check_cloud_storage_configured(self):
        if not self.env["res.config.settings"]._get_cloud_storage_configuration():
            raise MissingError(
                self.env._(
                    "The content of attachment %(id)s is held by cloud storage, "
                    "which this database has not configured.",
                    id=self.id,
                )
            )

    def _to_http_stream(self):
        if self.type != "cloud_storage":
            return super()._to_http_stream()
        self.check_singleton()
        self._check_cloud_storage_configured()
        if self.env.context.get(STREAM_INLINE_CONTEXT_KEY):
            content = self._get_content()
            return Stream(
                type="data",
                data=content,
                size=len(content),
                mimetype=self.mimetype,
                download_name=self.name,
                etag=self.checksum or True,
                last_modified=self.write_date,
                public=self.public,
            )
        info = self._generate_cloud_storage_download_info()
        stream = CloudStorageStream(
            self,
            type="url",
            url=info["url"],
            mimetype=self.mimetype,
            download_name=self.name,
        )
        if "time_to_expiry" in info:
            stream.max_age = max(info["time_to_expiry"] - 10, 0)
        return stream

    def write(self, vals):
        if ("raw" in vals or "datas" in vals) and "type" not in vals:
            cloud = self.filtered(lambda a: a.type == "cloud_storage")
            if cloud:
                super(IrAttachment, cloud).write(
                    {**vals, "type": "binary", "url": False}
                )
                rest = self - cloud
                return super(IrAttachment, rest).write(vals) if rest else True
        return super().write(vals)

    def _post_add_create(self, **kwargs):
        super()._post_add_create(**kwargs)
        if kwargs.get("cloud_storage"):
            if not self.env.registry.settings.get(
                self.env, "cloud_storage_provider", False
            ):
                raise UserError(self.env._("Cloud Storage is not enabled"))
            for record in self:
                record.write(
                    {
                        "raw": False,
                        "type": "cloud_storage",
                        "url": record._generate_cloud_storage_url(),
                    }
                )

    def _compute_raw(self):
        cloud = self.filtered(
            lambda a: a.type == "cloud_storage" and not a.store_fname and a.file_size
        )
        super(IrAttachment, self - cloud)._compute_raw()
        if not cloud:
            return
        configured = bool(
            self.env["res.config.settings"]._get_cloud_storage_configuration()
        )
        for attach in cloud:
            attach.raw = attach._get_content() if configured else False

    def _get_content(self, size=None):
        if self.type != "cloud_storage":
            return super()._get_content(size)
        self.check_singleton()
        self._check_cloud_storage_configured()
        url = self._generate_cloud_storage_download_info()["url"]
        headers = {"Range": f"bytes=0-{size - 1}"} if size else {}
        response = self.env["ir.egress"].request(
            "GET",
            url,
            purpose="cloud_storage",
            timeout=60,
            headers=headers,
            max_bytes=size,
        )
        response.raise_for_status()
        return response.content

    def _migrate_remote_to_local(self):
        if self.type != "cloud_storage":
            return super()._migrate_remote_to_local()
        self._check_cloud_storage_configured()
        url = self._generate_cloud_storage_download_info()["url"]
        response = self.env["ir.egress"].request(
            "GET", url, purpose="cloud_storage", timeout=10, max_bytes=None
        )
        response.raise_for_status()
        if response.status_code != 200:
            raise ValidationError(
                self.env._(
                    "Failed to download attachment (%(id)s) from cloud: %(code)s - %(reason)s",
                    id=self.id,
                    code=response.status_code,
                    reason=response.reason,
                )
            )
        attachment_data = response.content
        _logger.info(
            "Migrating attachment (%s) with url (%s) from cloud_storage to binary.",
            self.id,
            self.url,
        )
        self.write(
            {
                "type": "binary",
                "url": False,
                "raw": attachment_data,
            }
        )
        return True

    def _generate_cloud_storage_blob_name(self):
        return f"{self.id}/{uuid.uuid4()}/{self.name}"

    def _generate_cloud_storage_url(self):
        raise NotImplementedError

    def _generate_cloud_storage_download_info(self, content_disposition=None):
        raise NotImplementedError

    def _generate_cloud_storage_upload_info(self):
        raise NotImplementedError

    def _get_cloud_storage_unsupported_models(self):
        return list(
            self.env.registry.get_descendants(
                ["mixin.mail.thread.main.attachment"], "_inherit", "_inherits"
            )
        )

    def _get_zip_detached_reader(self):
        if self.type != "cloud_storage":
            return super()._get_zip_detached_reader()
        self._check_cloud_storage_configured()
        url = self._generate_cloud_storage_download_info()["url"]

        def read_blocks(block_size):
            with self.env["ir.egress"].request(
                "GET",
                url,
                purpose="cloud_storage",
                stream=True,
                timeout=30,
                max_bytes=None,
            ) as response:
                response.raise_for_status()
                yield from response.iter_content(block_size)

        return read_blocks

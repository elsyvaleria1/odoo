import base64
import hashlib
import logging
import uuid
from collections import defaultdict
from datetime import timedelta
from itertools import batched
from pathlib import Path
from typing import Self

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import SQL

from ..tools import s3

_logger = logging.getLogger(__name__)


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    s3_blob_name = fields.Char(
        copy=False,
        help="Object key of the copy mirrored to S3 in hybrid mode.",
    )
    s3_mirror_pending = fields.Boolean(
        default=False,
        index=True,
        copy=False,
        help="Set when this attachment still needs to be mirrored to S3 "
        "(hybrid mode). Cleared once the upload succeeds.",
    )

    def _s3_is_enabled(self) -> bool:
        return (
            self.env.registry.settings.get(self.env, "cloud_storage_s3_enabled", False)
            == "True"
        )

    def _is_s3_provider(self) -> bool:
        return (
            self.env.registry.settings.get(self.env, "cloud_storage_provider", False)
            in s3.PROVIDERS
        )

    def _is_s3_hybrid(self) -> bool:
        if not self._s3_is_enabled():
            return False
        settings = self.env.registry.settings
        return (
            settings.get(self.env, "cloud_storage_provider", False) in s3.PROVIDERS
            and settings.get(self.env, "cloud_storage_s3_storage_mode", False)
            == "hybrid"
        )

    def _filtered_s3_mirrorable(self) -> Self:
        return self.filtered(
            lambda a: (
                a.type == "binary" and (a.store_fname or a.db_datas) and a.res_model
            )
        )

    def _s3_queue_mirror(self) -> None:
        # Only flag the rows: the upload is left to
        # ``_cron_mirror_pending_to_s3``. Uploading from a postcommit callback
        # runs it in the request thread, which keeps the main transaction
        # idle-in-transaction for as long as S3 takes to answer.
        to_mirror = self._filtered_s3_mirrorable()
        if to_mirror:
            to_mirror.s3_mirror_pending = True

    @api.model_create_multi
    def create(self, vals_list):
        attachments = super().create(vals_list)
        if attachments and attachments._is_s3_hybrid():
            attachments._s3_queue_mirror()
        return attachments

    _S3_MIRROR_TRIGGER_FIELDS = frozenset(
        {"res_model", "res_id", "raw", "datas", "db_datas", "store_fname", "type"}
    )

    def write(self, vals):
        held = {}
        if vals.keys() & {"type", "url", "raw", "datas"} and self._s3_is_enabled():
            held = {a.id: a.url for a in self if a.type == "cloud_storage" and a.url}
        res = super().write(vals)
        if self._S3_MIRROR_TRIGGER_FIELDS & vals.keys() and self._is_s3_hybrid():
            self.filtered(
                lambda a: not a.s3_blob_name and not a.s3_mirror_pending
            )._s3_queue_mirror()
        if held:
            dropped = [
                url
                for attach_id, url in held.items()
                if (attach := self.browse(attach_id)).type != "cloud_storage"
                or attach.url != url
            ]
            self._s3_delete_unused_blobs(dropped)
        return res

    def _s3_delete_unused_blobs(self, urls) -> None:
        if not urls:
            return
        still_used = self._s3_still_referenced("url", set(urls))
        endpoint = s3.get_endpoint(self.env)
        blobs = defaultdict(list)
        for url in set(urls) - still_used:
            if info := s3.parse_object_url(url, None, endpoint):
                blobs[info["bucket_name"]].append(info["blob_name"])
        if not blobs:
            return
        client = s3.get_client(self.env)

        def delete():
            for bucket, keys in blobs.items():
                try:
                    client.delete_objects(
                        Bucket=bucket,
                        Delete={"Objects": [{"Key": k} for k in keys]},
                    )
                except Exception:
                    _logger.warning(
                        "Failed to delete %d replaced S3 blobs from bucket %s",
                        len(keys),
                        bucket,
                        exc_info=True,
                    )

        # the blob goes only once the row that stopped using it is committed
        self.env.cr.postcommit.add(delete)

    def _post_add_create(self, **kwargs):
        if kwargs.get("cloud_storage") and self._is_s3_hybrid():
            kwargs = {k: v for k, v in kwargs.items() if k != "cloud_storage"}
        return super()._post_add_create(**kwargs)

    def _s3_hybrid_blob_name(self):
        self.check_singleton()
        return self.store_fname or self._generate_cloud_storage_blob_name()

    def _s3_bucket_name(self):
        return self.env.registry.settings.get(self.env, s3.PARAM_BUCKET, False)

    def _s3_mirror_to_cloud(self) -> None:
        if not self or not self._s3_is_enabled():
            return
        bucket = self._s3_bucket_name()
        if not bucket:
            _logger.error("S3 mirror skipped: no bucket configured.")
            return
        client = s3.get_client(self.env)
        for attach in self:
            try:
                blob_name = attach.s3_blob_name or attach._s3_hybrid_blob_name()
                if s3.object_exists(client, bucket, blob_name):
                    attach.write(
                        {"s3_blob_name": blob_name, "s3_mirror_pending": False}
                    )
                    continue
                data = attach.raw
                if not data:
                    attach.write({"s3_mirror_pending": False})
                    continue
                client.put_object(Bucket=bucket, Key=blob_name, Body=data)
                attach.write({"s3_blob_name": blob_name, "s3_mirror_pending": False})
            except Exception:
                _logger.warning(
                    "Failed to mirror attachment %s to S3; will retry on the "
                    "next cron run.",
                    attach.id,
                    exc_info=True,
                )

    @api.model
    def _s3_backfill_to_s3(self, batch_size=500, commit_each_batch=True):
        if not self._is_s3_hybrid():
            _logger.warning("S3 backfill skipped: hybrid storage mode is not active.")
            return 0
        domain = [
            ("type", "=", "binary"),
            ("res_model", "!=", False),
            ("s3_blob_name", "=", False),
            ("s3_mirror_pending", "=", False),
            "|",
            ("store_fname", "!=", False),
            ("db_datas", "!=", False),
        ]
        total = 0
        backfill = self._with_field_rows()
        for batch in backfill.search_iter(domain, batch_size=batch_size):
            batch.s3_mirror_pending = True
            batch._s3_mirror_to_cloud()
            if commit_each_batch:
                self.env["ir.cron"]._commit_progress(len(batch))
            total += len(batch)
            _logger.info("S3 backfill: processed %s attachments so far.", total)
        _logger.info("S3 backfill finished: %s attachments processed.", total)
        return total

    @api.model
    def _cron_mirror_pending_to_s3(self, limit=100) -> None:
        if not self._is_s3_hybrid():
            return
        pending = self._with_field_rows().search(
            [("s3_mirror_pending", "=", True)], limit=limit
        )
        pending._s3_mirror_to_cloud()

    def _parse_s3_url(self):
        return s3.parse_object_url(
            self.url,
            self.env.registry.settings.get(self.env, s3.PARAM_REGION, False),
            s3.get_endpoint(self.env),
        )

    def _get_s3_info(self) -> dict:
        info = self._parse_s3_url()
        if not info:
            raise ValidationError(self.env._("%s is not a valid S3 URL.", self.url))
        return info

    def _generate_s3_url(self, blob_name):
        settings = self.env.registry.settings
        return s3.object_url(
            settings.get(self.env, s3.PARAM_BUCKET, False),
            settings.get(self.env, s3.PARAM_REGION, False),
            blob_name,
            s3.get_endpoint(self.env),
        )

    def _generate_s3_presigned_url(
        self,
        bucket_name,
        blob_name,
        method="get_object",
        expiration=300,
        content_disposition=None,
    ):
        client = s3.get_client(self.env)
        params = {"Bucket": bucket_name, "Key": blob_name}
        if content_disposition:
            params["ResponseContentDisposition"] = content_disposition
        return client.generate_presigned_url(
            method, Params=params, ExpiresIn=expiration
        )

    def _generate_cloud_storage_blob_name(self):
        if not self._is_s3_provider():
            return super()._generate_cloud_storage_blob_name()
        res_model = (self.res_model or "_orphan").replace(".", "_")
        res_id = self.res_id or 0
        short_uuid = uuid.uuid4().hex[:8]
        filename = self.name or "unnamed"
        return f"{res_model}/{res_id}/{self.id}_{short_uuid}_{filename}"

    def _generate_cloud_storage_url(self):
        if not self._is_s3_provider():
            return super()._generate_cloud_storage_url()
        blob_name = self._generate_cloud_storage_blob_name()
        return self._generate_s3_url(blob_name)

    def _generate_cloud_storage_download_info(self, content_disposition=None):
        if not self._is_s3_provider():
            return super()._generate_cloud_storage_download_info(content_disposition)
        info = self._get_s3_info()
        return {
            "url": self._generate_s3_presigned_url(
                info["bucket_name"],
                info["blob_name"],
                method="get_object",
                expiration=self._cloud_storage_download_url_time_to_expiry,
                content_disposition=content_disposition,
            ),
            "time_to_expiry": self._cloud_storage_download_url_time_to_expiry,
        }

    def _generate_cloud_storage_upload_info(self):
        if not self._is_s3_provider():
            return super()._generate_cloud_storage_upload_info()
        info = self._get_s3_info()
        return {
            "url": self._generate_s3_presigned_url(
                info["bucket_name"],
                info["blob_name"],
                method="put_object",
                expiration=self._cloud_storage_upload_url_time_to_expiry,
            ),
            "method": "PUT",
            "response_status": 200,
        }

    def _s3_move_refusal(self) -> str | None:
        self.check_singleton()
        if self.type != "binary":
            return "not_binary"
        if self.url:
            # served at its own URL (a generated asset, a shape, a sitemap):
            # the bucket's URL would replace the path it is answered at
            return "served_by_url"
        if not self.store_fname or "://" in self.store_fname:
            return "not_in_filestore"
        if not self.file_size:
            return "empty"
        return None

    def _s3_move_to_cloud(self) -> dict[str, list[int]]:
        """Upload each filestore attachment to the bucket and serve it from there.

        :return: attachment ids by outcome, ``moved`` or the reason for a skip
        :rtype: dict
        """
        settings = self.env.registry.settings
        bucket = settings.get(self.env, s3.PARAM_BUCKET, False)
        region = settings.get(self.env, s3.PARAM_REGION, False)
        endpoint = s3.get_endpoint(self.env)
        client = s3.get_client(self.env)
        outcome = defaultdict(list)
        for attach in self:
            reason = attach._s3_move_refusal()
            if reason:
                outcome[reason].append(attach.id)
                continue
            try:
                key, reason = attach._s3_upload_verified(client, bucket)
            except Exception:
                _logger.warning(
                    "S3 move: attachment %s was not uploaded", attach.id, exc_info=True
                )
                key, reason = None, "error"
            if reason:
                outcome[reason].append(attach.id)
                continue
            # The local file stays referenced, so writing ``type`` back to
            # ``binary`` undoes the move until _s3_release_local_files runs.
            # Only type and url are written: content values would recompute
            # file_size, checksum and index_content from empty bytes. The
            # context names it a relocation, which a lock on the document's
            # content (a decided approval) lets through.
            try:
                with self.env.cr.savepoint():
                    attach.with_context(attachment_storage_relocation=True).write(
                        {
                            "type": "cloud_storage",
                            "url": s3.object_url(bucket, region, key, endpoint),
                        }
                    )
            except Exception:
                _logger.warning(
                    "S3 move: attachment %s was uploaded but not switched",
                    attach.id,
                    exc_info=True,
                )
                outcome["write_refused"].append(attach.id)
                continue
            outcome["moved"].append(attach.id)
        return dict(outcome)

    def _s3_upload_verified(self, client, bucket) -> tuple[str | None, str | None]:
        """Upload the filestore file and check the stored object against it.

        :return: the object key and ``None``, or ``None`` and the refusal
        :rtype: tuple
        """
        self.check_singleton()
        path = Path(self._get_full_path(self.store_fname))
        digest = hashlib.md5(usedforsecurity=False)
        size = 0
        with path.open("rb") as f:
            while block := f.read(1 << 20):
                digest.update(block)
                size += len(block)
        if size != self.file_size:
            return None, "size_mismatch"
        key = self._generate_cloud_storage_blob_name()
        with path.open("rb") as f:
            client.put_object(
                Bucket=bucket,
                Key=key,
                Body=f,
                ContentLength=size,
                ContentType=self.mimetype or "application/octet-stream",
                # the store rejects a body whose MD5 differs from this one
                ContentMD5=base64.b64encode(digest.digest()).decode(),
            )
        head = client.head_object(Bucket=bucket, Key=key)
        if (
            head["ContentLength"] != size
            or head["ETag"].strip('"') != digest.hexdigest()
        ):
            return None, "verify_failed"
        return key, None

    def _s3_release_local_files(self) -> dict[str, list[int]]:
        """Drop the filestore copy of attachments the bucket already holds.

        :return: attachment ids by outcome, ``released`` or the reason for a skip
        :rtype: dict
        """
        client = s3.get_client(self.env)
        outcome = defaultdict(list)
        fnames = []
        for attach in self:
            info = attach.type == "cloud_storage" and attach._parse_s3_url()
            if not info or not attach.store_fname or "://" in attach.store_fname:
                outcome["not_releasable"].append(attach.id)
                continue
            try:
                head = client.head_object(
                    Bucket=info["bucket_name"], Key=info["blob_name"]
                )
            except Exception:
                _logger.warning(
                    "S3 release: object of attachment %s is not readable",
                    attach.id,
                    exc_info=True,
                )
                outcome["error"].append(attach.id)
                continue
            if head["ContentLength"] != attach.file_size:
                outcome["verify_failed"].append(attach.id)
                continue
            outcome["released"].append(attach.id)
            fnames.append(attach.store_fname)
        released = self.browse(outcome.get("released", []))
        if released:
            # write() drops store_fname from its values, so the column is set
            # here; the garbage collector keeps files other rows still use
            self.flush_model(["store_fname"])
            self.env.cr.execute(
                "UPDATE ir_attachment SET store_fname = NULL WHERE id = ANY(%s)",
                [released.ids],
            )
            released.invalidate_recordset(["store_fname", "raw", "datas"])
            self._remove_stored_file_multi(fnames)
        return dict(outcome)

    @api.model
    def _cron_s3_move_local_to_cloud(self, batch_size=200, min_age_minutes=30):
        """Move what Odoo stored locally since the last run to the bucket.

        In cloud-only mode a server-side write (a report PDF, a thumbnail, an
        image field, a rewritten blob) still lands in the filestore; left
        there, the filestore and every backup grow back. A row waits until it
        is ``min_age_minutes`` old, so the content a transaction is still
        rewriting is not uploaded twice.
        """
        if not self._is_s3_provider() or not self._s3_is_enabled():
            return
        if self._is_s3_hybrid():
            return
        cutoff = fields.Datetime.now() - timedelta(minutes=min_age_minutes)
        attachments = self.sudo()._with_field_rows()
        domain = [
            ("type", "=", "binary"),
            ("store_fname", "!=", False),
            ("url", "=", False),
            ("file_size", ">", 0),
            ("write_date", "<", cutoff),
        ]
        skipped = []
        totals = defaultdict(int)
        while True:
            batch = attachments.search(
                domain + [("id", "not in", skipped)], limit=batch_size, order="id"
            )
            if not batch:
                break
            moved_outcome = batch._s3_move_to_cloud()
            moved = attachments.browse(moved_outcome.pop("moved", []))
            released_outcome = moved._s3_release_local_files() if moved else {}
            for outcome in (moved_outcome, released_outcome):
                for reason, ids in outcome.items():
                    totals[reason] += len(ids)
                    if reason != "released":
                        skipped.extend(ids)
            remaining = attachments.search_count(domain + [("id", "not in", skipped)])
            if not self.env["ir.cron"]._commit_progress(
                len(batch), remaining=remaining
            ):
                break
        if totals:
            _logger.info("S3 move of local attachments: %s", dict(totals))

    def _s3_still_referenced(self, column: str, values) -> set[str]:
        # whoever deletes, an object another attachment still points at stays:
        # the user's reach on ir.attachment would hide the ones they cannot read
        self.flush_model([column])
        rows = self.env.execute_query(
            SQL(
                "SELECT DISTINCT %s FROM ir_attachment WHERE %s = ANY(%s)",
                SQL.identifier(column),
                SQL.identifier(column),
                list(values),
            )
        )
        return {value for (value,) in rows}

    def unlink(self):
        if not self._s3_is_enabled():
            return super().unlink()
        blobs_by_bucket = defaultdict(list)
        hybrid_bucket = self._s3_bucket_name()
        hybrid_candidates = []
        for attach in self:
            info = attach.type == "cloud_storage" and attach._parse_s3_url()
            if info:
                blobs_by_bucket[info["bucket_name"]].append(info["blob_name"])
            elif attach.s3_blob_name and hybrid_bucket:
                hybrid_candidates.append(attach.s3_blob_name)
        cloud_urls = {attach.url for attach in self if attach.type == "cloud_storage"}
        res = super().unlink()
        if cloud_urls:
            # a copied document shares its source's url, and so its blob
            endpoint = s3.get_endpoint(self.env)
            shared_keys = set()
            for url in self._s3_still_referenced("url", cloud_urls):
                if info := s3.parse_object_url(url, None, endpoint):
                    shared_keys.add((info["bucket_name"], info["blob_name"]))
            for bucket, blobs in blobs_by_bucket.items():
                blobs[:] = [b for b in blobs if (bucket, b) not in shared_keys]
        if hybrid_candidates:
            still_used = self._s3_still_referenced("s3_blob_name", hybrid_candidates)
            for blob in set(hybrid_candidates):
                if blob not in still_used:
                    blobs_by_bucket[hybrid_bucket].append(blob)
        if blobs_by_bucket:
            client = s3.get_client(self.env)
            for bucket, blob_names in blobs_by_bucket.items():
                for batch in batched(blob_names, 1000, strict=False):
                    try:
                        client.delete_objects(
                            Bucket=bucket,
                            Delete={"Objects": [{"Key": k} for k in batch]},
                        )
                    except Exception:
                        _logger.warning(
                            "Failed to delete %d S3 blobs from bucket %s",
                            len(batch),
                            bucket,
                            exc_info=True,
                        )
        return res

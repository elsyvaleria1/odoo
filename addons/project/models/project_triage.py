from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict

_debug = DebugLog(__name__)


class ProjectTriage(models.Model):
    _name = "project.triage"
    _description = "Personal Task Triage Bucket"
    _inherit = ["mixin.project.pm"]
    _access_anchors = frozendict(
        {
            "owner": "user_id",
        }
    )

    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Triage Owner",
        default=lambda self: self.env.user,
        index=True,
        required=True,
        ondelete="cascade",
    )

    @_debug.perf.timed
    @api.ondelete(at_uninstall=False)
    def _unlink_if_remaining_triage_buckets(self) -> None:
        _debug.lifecycle("unlink", buckets=self, users=self.user_id)
        remaining_all = self.env["project.triage"]._read_group(
            [
                ("user_id", "in", self.user_id.ids),
                ("id", "not in", self.ids),
            ],
            groupby=["user_id", "sequence", "id"],
            order="user_id,sequence DESC",
        )
        remaining_by_user: dict = defaultdict(list)
        # grouped by "id", _read_group answers the id itself, not a record
        for user, sequence, bucket_id in remaining_all:
            remaining_by_user[user].append({"id": bucket_id, "seq": sequence})

        triage_to_update = self.env["project.task.triage"]._read_group(
            [("triage_id", "in", self.ids)],
            ["triage_id"],
            ["id:recordset"],
        )
        buckets_by_user = self.grouped("user_id")
        for user in self.user_id:
            if not user.active or user.share:
                _debug.logic(
                    "bucket_replacement_skipped",
                    reason="inactive_or_share",
                    user=user.id,
                )
                continue
            user_buckets_to_unlink = buckets_by_user[user]
            user_remaining = remaining_by_user[user]
            _debug.logic(
                "user_buckets_unlinked",
                user=user.id,
                buckets=user_buckets_to_unlink,
                remaining=len(user_remaining),
            )
            if not user_remaining:
                raise UserError(
                    self.env._(
                        "Each user must have at least one triage bucket. "
                        "Create a replacement bucket before deleting the selected ones."
                    )
                )
            user_buckets_to_unlink._update_task_triages_to_replacement(
                user_remaining, triage_to_update
            )

    def _update_task_triages_to_replacement(
        self, remaining_buckets: list[dict], triage_to_update
    ) -> None:
        buckets_to_delete = sorted(
            [{"id": b.id, "seq": b.sequence} for b in self],
            key=lambda b: b["seq"],
        )
        replacement_id = remaining_buckets.pop()["id"]
        next_replacement = remaining_buckets and remaining_buckets.pop()

        triage_by_bucket = {
            bucket.id: task_triages for bucket, task_triages in triage_to_update
        }
        for bucket in buckets_to_delete:
            while next_replacement and next_replacement["seq"] < bucket["seq"]:
                replacement_id = next_replacement["id"]
                next_replacement = remaining_buckets and remaining_buckets.pop()
            if bucket["id"] in triage_by_bucket:
                _debug.pipeline(
                    "task_triages_moved",
                    bucket=bucket["id"],
                    task_triages=len(triage_by_bucket[bucket["id"]]),
                    replacement=replacement_id,
                )
                triage_by_bucket[bucket["id"]].triage_id = replacement_id

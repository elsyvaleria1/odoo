from odoo import api, exceptions, fields, models
from odoo.tools import frozendict


class KnowledgeArticleFavorite(models.Model):
    _name = "knowledge.article.favorite"
    _description = "Favorite Article"
    _order = "sequence ASC, id DESC"
    _rec_name = "article_id"
    _access_anchors = frozendict(
        {
            "owner": "user_id",
        }
    )

    article_id = fields.Many2one(
        comodel_name="knowledge.article",
        index=True,
        required=True,
        ondelete="cascade",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        index=True,
        required=True,
        ondelete="cascade",
    )
    is_article_active = fields.Boolean(
        related="article_id.active",
        string="Is Article Active",
        readonly=True,
    )
    sequence = fields.Integer(default=0)

    _unique_article_user = models.Constraint(
        "unique(article_id, user_id)",
        "User already has this article in favorites.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        """At creation, we need to set the max sequence, if not given, for each favorite to create, in order to keep
        a correct ordering as much as possible. Some sequence could be given in create values, that could lead to
        duplicated sequence per user_id. That is not an issue as they will be resequenced the next time the user reorder
        their favorites."""
        # The sequence orders ONE user's sidebar, so it has to come from the
        # list it will live in -- `vals["user_id"]` -- and not from whoever
        # happens to be creating the row. Taking it from `env.uid` put a
        # favourite created for someone else at a position derived from a
        # stranger's list: with a short list acting on a long one, the new
        # entry landed in the middle of the recipient's sidebar.
        next_sequence_by_user = {}
        for vals in vals_list:
            if vals.get("sequence"):
                continue
            user_id = vals.get("user_id") or self.env.uid
            if user_id not in next_sequence_by_user:
                last_favorite = self.search(
                    [("user_id", "=", user_id)], order="sequence DESC", limit=1
                )
                next_sequence_by_user[user_id] = (
                    last_favorite.sequence + 1 if last_favorite else 1
                )
            vals["sequence"] = next_sequence_by_user[user_id]
            next_sequence_by_user[user_id] += 1
        return super().create(vals_list)

    def write(self, vals):
        """Whatever rights, avoid any attempt at privilege escalation."""
        if ("article_id" in vals or "user_id" in vals) and not self.env.is_admin():
            raise exceptions.AccessError(
                self.env._("Can not update the article or user of a favorite.")
            )
        return super().write(vals)

    def resequence_favorites(self, article_ids) -> None:
        # Some article may not be accessible by the user anymore. Therefore,
        # to prevent an access error, one will only resequence the favorites
        # related to the articles accessible by the user -- the search below
        # still runs as the user, so a favourite they can no longer read
        # simply does not come back.
        favorite_by_article = {
            favorite.article_id.id: favorite
            for favorite in self.search(
                [("article_id", "in", article_ids), ("user_id", "=", self.env.uid)]
            )
        }
        # Keep the same order as in article_ids. `enumerate` is exact here:
        # the previous loop advanced its counter on every article whether or
        # not a favourite was found, so the numbers are the ones it produced.
        for sequence, article_id in enumerate(article_ids):
            favorite = favorite_by_article.get(article_id)
            if favorite:
                favorite.sequence = sequence

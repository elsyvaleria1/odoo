from odoo.exceptions import ValidationError
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCoverProperties(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.blog = cls.env["blog.blog"].create({"name": "cover probe blog"})

    def _post(self, **vals):
        return self.env["blog.post"].create(
            {"name": "cover probe", "blog_id": self.blog.id, **vals}
        )

    def _store_null(self, post):
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE blog_post SET cover_properties = NULL WHERE id = %s", (post.id,)
        )
        post.invalidate_recordset(["cover_properties"])
        self.assertFalse(post.cover_properties)

    def test_a_stored_null_does_not_break_the_background(self):
        post = self._post()
        self._store_null(post)
        self.assertEqual(post._get_background(), "none")

    def test_a_stored_null_does_not_break_a_write(self):
        post = self._post()
        self._store_null(post)
        post.write({"cover_properties": json_dumps({"background-image": "none"})})
        self.assertEqual(
            json_loads(post.cover_properties)["resize_class"],
            "o_half_screen_height",
            "the default resize class stands in for the unreadable stored one",
        )

    def test_unparseable_incoming_properties_are_still_refused(self):
        post = self._post()
        with self.assertRaises(ValidationError):
            post.write({"cover_properties": "not json at all"})

    def test_a_fresh_query_string_carries_no_empty_first_parameter(self):
        post = self._post(
            cover_properties=json_dumps(
                {"background-image": "url(/web/image/1-abc/x.png)"}
            )
        )
        self.assertEqual(
            post._get_background(height=100),
            "url(/web/image/1-abc/x.png?height=100)",
        )

    def test_an_existing_query_string_is_extended_with_an_ampersand(self):
        post = self._post(
            cover_properties=json_dumps(
                {"background-image": "url(/web/image/1-abc/x.png?access_token=zz)"}
            )
        )
        self.assertEqual(
            post._get_background(height=100, width=200),
            "url(/web/image/1-abc/x.png?access_token=zz&height=100&width=200)",
        )

    def test_a_background_with_no_dimensions_is_untouched(self):
        img = "url(/web/image/1-abc/x.png)"
        post = self._post(cover_properties=json_dumps({"background-image": img}))
        self.assertEqual(post._get_background(), img)

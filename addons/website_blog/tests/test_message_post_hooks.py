from odoo.tests import tagged

from odoo.addons.website_blog.tests.common import TestWebsiteBlogCommon


@tagged("mail_post")
class TestBlogMessagePostBatch(TestWebsiteBlogCommon):
    def test_batch_reply_to_publication_is_a_note(self):
        blogs = self.env["blog.blog"].create([{"name": "B1"}, {"name": "B2"}])
        published = self.env.ref("website_blog.mt_blog_blog_published")
        parents = {
            blog.id: blog.message_post(body="Published", subtype_id=published.id).id
            for blog in blogs
        }
        comment = self.env.ref("mail.mt_comment")
        messages = blogs._message_post_values_all(
            {
                blog.id: {
                    "body": "Reply",
                    "message_type": "comment",
                    "parent_id": parents[blog.id],
                    "subtype_id": comment.id,
                }
                for blog in blogs
            }
        )
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages.subtype_id, self.env.ref("mail.mt_note"))

from odoo import exceptions
from odoo.tests.common import tagged, users
from odoo.tools import mute_logger

from odoo.addons.knowledge.tests.common import KnowledgeArticlePermissionsCase
from odoo.addons.mail.tests.common import mail_new_test_user


@tagged("knowledge_acl")
class TestKnowledgeSecurity(KnowledgeArticlePermissionsCase):
    """Tests ACLs and low level access on models. Do not test the internals
    of permission computation as those are done in another test suite. Here
    we rely on them to check the create/read/write/unlink access checks."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.user_erp_manager = mail_new_test_user(
            cls.env,
            company_id=cls.company_admin.id,
            country_id=cls.env.ref("base.be").id,
            groups="base.group_erp_manager",
            login="user_erp_manager",
            name="Emmanuel Erp Manager",
            notification_type="inbox",
            signature="--\nEmmanuel",
        )

    @mute_logger(
        "odoo.addons.base.models.ir_model", "odoo.addons.base.models.ir_access"
    )
    @users("user_public")
    def test_models_as_public(self):
        with self.assertRaises(
            exceptions.AccessError, msg="ACLs: No article access to public"
        ):
            self.env["knowledge.article"].search([])

        with self.assertRaises(
            exceptions.AccessError, msg="ACLs: No favorite access to public"
        ):
            self.env["knowledge.article.favorite"].search([])

        with self.assertRaises(
            exceptions.AccessError, msg="ACLs: No member access to public"
        ):
            self.env["knowledge.article.member"].search([])

        with self.assertRaises(
            exceptions.AccessError, msg="ACLs: no cover access to public"
        ):
            self.env["knowledge.cover"].search([])

    @mute_logger(
        "odoo.addons.base.models.ir_model", "odoo.addons.base.models.ir_access"
    )
    @users("portal_test")
    def test_models_as_portal(self):
        article_root = self.article_roots[0].with_env(self.env)

        with self.assertRaises(
            exceptions.AccessError, msg="ACLs: No access given to portal"
        ):
            article_root.body

        article_shared = self.article_roots[2].with_env(self.env)
        with self.assertRaises(
            exceptions.AccessError,
            msg="ACLs: Internal permission 'none', not for portal",
        ):
            article_shared.body

        article_accessible = self.article_write_contents[2].with_env(self.env)
        self.assertEqual(
            article_accessible.body,
            "<p>Writable Subarticle through inheritance</p>",
            "ACLs: should be accessible due to explicit 'read' member permission",
        )
        self.assertTrue(article_accessible.is_user_favorite)

        new_article = self.env["knowledge.article"].create(
            {
                "article_member_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": self.env.user.partner_id.id,
                            "permission": "write",
                        },
                    ),
                ],
                "name": "New Article",
                "internal_permission": "none",
            }
        )
        self.assertTrue(new_article)

        self.env.ref(
            "knowledge.rule_knowledge_article_users_write_group_portal"
        ).sudo().write({"operation": "u"})
        with self.assertRaises(exceptions.AccessError):
            self.env["knowledge.article"].create(
                {
                    "name": "New Article",
                    "internal_permission": "none",
                }
            )

        favs = self.env["knowledge.article.favorite"].search([])
        self.assertEqual(len(favs), 1)
        self.assertEqual(favs.article_id, article_accessible)
        sudo_favorites = self.article_roots.favorite_ids.with_env(self.env)
        self.assertEqual(len(sudo_favorites), 2)
        with self.assertRaises(
            exceptions.AccessError, msg="ACLs: Breaking rule for portal"
        ):
            sudo_favorites.mapped("user_id")

        my_members = self.env["knowledge.article.member"].search(
            [("partner_id", "!=", False)]
        )
        self.assertEqual(len(my_members), 5)
        self.assertEqual(
            my_members,
            (
                self.article_read_contents[0]
                | self.article_read_contents[1]
                | self.article_write_contents[2]
                | new_article
            ).article_member_ids,
            msg="Portal can read all members from articles he has access to",
        )
        sudo_members = self.article_roots.article_member_ids.with_env(self.env)
        with self.assertRaises(exceptions.AccessError, msg="Breaking rule for portal"):
            sudo_members.mapped("partner_id")

        with self.assertRaises(
            exceptions.AccessError, msg="ACLs: No cover access to portal"
        ):
            self.env["knowledge.cover"].search([])

    @mute_logger("odoo.models.unlink")
    @users("user_erp_manager")
    def test_models_as_erp_manager(self):
        self.assertTrue(self.env.user.has_group("base.group_erp_manager"))
        self.assertFalse(self.env.user.has_group("base.group_system"))

        article_writable = self.article_roots[0].with_env(self.env)
        article_writable.body
        article_readable = self.article_roots[1].with_env(self.env)
        article_readable.body
        self.assertTrue(article_readable.user_has_access)
        self.assertTrue(article_readable.user_can_read)
        self.assertFalse(article_readable.user_has_write_access)
        self.assertFalse(article_readable.user_can_write)

        with self.assertRaises(
            exceptions.AccessError, msg="Erp Managers behave like internal users"
        ):
            _other_private = self.env["knowledge.article"].create(
                {
                    "article_member_ids": [
                        (
                            0,
                            0,
                            {
                                "partner_id": self.partner_employee.id,
                                "permission": "write",
                            },
                        )
                    ],
                    "internal_permission": "none",
                    "name": "Private for Employee",
                }
            )

    @mute_logger("odoo.models.unlink")
    @users("admin")
    def test_models_as_system(self):
        self.assertTrue(self.env.user.has_group("base.group_system"))

        article_roots = self.article_roots.with_env(self.env)
        article_roots.mapped("body")
        article_hidden = self.article_read_contents[3].with_env(self.env)
        article_hidden.body
        article_readable = self.article_roots[1].with_env(self.env)
        article_readable.body
        self.assertTrue(article_readable.user_has_access)
        self.assertTrue(article_readable.user_can_read)
        self.assertFalse(article_readable.user_has_write_access)
        self.assertTrue(article_readable.user_can_write)

        other_private = self.env["knowledge.article"].create(
            {
                "article_member_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": self.partner_employee.id,
                            "permission": "write",
                        },
                    )
                ],
                "internal_permission": "none",
                "name": "Private for Employee",
            }
        )
        self.assertMembers(other_private, "none", {self.partner_employee: "write"})
        self.assertEqual(other_private.category, "private")
        self.assertTrue(
            other_private.user_can_write,
            "Can write ACL-like is True, system can do everything",
        )
        self.assertFalse(
            other_private.user_has_write_access,
            "Can write based on permission is False but can perform write due to ACLs",
        )
        other_private.write({"name": "Admin can do everything"})

        other_private_child = self.env["knowledge.article"].create(
            {
                "name": "Child of Private for Employee",
                "parent_id": other_private.id,
            }
        )
        self.assertMembers(other_private_child, False, {})
        self.assertEqual(
            other_private_child.article_member_ids.partner_id, self.env["res.partner"]
        )
        self.assertEqual(other_private_child.category, "private")
        self.assertTrue(
            other_private_child.user_can_write,
            "Can write ACL-like is True, system can do everything",
        )
        self.assertFalse(
            other_private_child.user_has_write_access,
            "Can write based on permission is False but can perform write due to ACLs",
        )

        other_private.write({"name": "Can Update"})
        other_private_child.write({"name": "Can Also Update"})

        other_private_child.action_toggle_user_favorite()
        self.assertTrue(other_private_child.is_user_favorite)
        favorite_rec = self.env["knowledge.article.favorite"].search(
            [("article_id", "=", other_private_child.id)]
        )
        favorite_rec.unlink()
        self.assertFalse(other_private_child.is_user_favorite)

        members = other_private.article_member_ids
        self.assertEqual(members.partner_id, self.partner_employee)
        new_member = self.env["knowledge.article.member"].create(
            {
                "article_id": other_private.id,
                "partner_id": self.partner_employee2.id,
                "permission": "read",
            }
        )
        members = other_private.article_member_ids
        self.assertEqual(
            members.partner_id, self.partner_employee + self.partner_employee2
        )
        new_member.write({"permission": "write"})
        members.filtered(lambda m: m.partner_id == self.partner_employee).unlink()
        members = other_private.article_member_ids
        self.assertEqual(members, new_member)
        self.assertEqual(members.partner_id, self.partner_employee2)

        cover = self._create_cover()
        cover.write({"attachment_url": "/"})
        self.assertEqual(cover.attachment_url, "/")
        cover.unlink()

    @mute_logger(
        "odoo.addons.base.models.ir_model",
        "odoo.addons.base.models.ir_access",
        "odoo.models.unlink",
    )
    @users("employee")
    def test_models_as_user(self):
        article_roots = self.article_roots.with_env(self.env)

        article_roots.mapped("body")
        article_roots[0].write({"name": "Hacked (or not)"})
        with self.assertRaises(
            exceptions.AccessError, msg="ACLs: 'read' internal permission"
        ):
            article_roots[1].write({"name": "Hacked"})
        with self.assertRaises(
            exceptions.AccessError, msg="ACLs: 'read' member permission"
        ):
            article_roots[2].write({"name": "Hacked"})

        article_hidden = self.article_read_contents[3].with_env(self.env)
        with self.assertRaises(
            exceptions.AccessError, msg="ACLs: 'none' internal permission"
        ):
            article_hidden.body

        new_article = self.env["knowledge.article"].create(
            {
                "article_member_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": self.env.user.partner_id.id,
                            "permission": "write",
                        },
                    ),
                ],
                "name": "New Article",
            }
        )
        self.assertTrue(new_article)

        self.env.ref(
            "knowledge.rule_knowledge_article_users_write_group_user"
        ).sudo().write({"operation": "u"})
        with self.assertRaises(exceptions.AccessError):
            self.env["knowledge.article"].create(
                {
                    "name": "New Article",
                }
            )

        my_favs = self.env["knowledge.article.favorite"].search([])
        self.assertEqual(
            my_favs,
            self.articles_all.favorite_ids.filtered(
                lambda f: f.user_id == self.env.user
            ),
            "Favorites: employee should see its own favorites",
        )
        my_favs.mapped("user_id")
        my_favs.write({"sequence": 0})
        with self.assertRaises(
            exceptions.AccessError,
            msg="ACLs: should not be used to change article/user",
        ):
            my_favs[0].write({"article_id": article_roots[0].id})
        with self.assertRaises(
            exceptions.AccessError,
            msg="ACLs: should not be used to change article/user",
        ):
            my_favs[0].write({"user_id": self.user_portal.id})

        my_members = self.env["knowledge.article.member"].search(
            [("article_id", "in", self.article_roots.ids), ("partner_id", "!=", False)]
        )
        self.assertEqual(len(my_members), 4)
        self.assertEqual(
            my_members,
            self.article_roots.article_member_ids,
            "Members: employee should memberships of visible ",
        )
        self.article_roots[2].article_member_ids.filtered(
            lambda m: m.partner_id == self.partner_employee
        ).unlink()
        my_members = self.env["knowledge.article.member"].search(
            [("article_id", "in", self.article_roots.ids), ("partner_id", "!=", False)]
        )
        self.assertEqual(len(my_members), 2)
        self.assertEqual(
            my_members,
            (self.article_roots[1] + self.article_roots[3]).article_member_ids,
            "Members: employee should see its own memberships",
        )
        my_members.mapped("partner_id")
        with self.assertRaises(
            exceptions.AccessError, msg="ACLs: no ACLs for write for user"
        ):
            my_members.write({"permission": "write"})

        cover = self._create_cover()
        cover.write({"attachment_url": "/"})
        self.assertEqual(cover.attachment_url, "/")
        cover.unlink()

    @mute_logger(
        "odoo.addons.base.models.ir_model", "odoo.addons.base.models.ir_access"
    )
    @users("employee")
    def test_models_as_user_copy(self):
        article_hidden = self.article_read_contents[3].with_env(self.env)
        with self.assertRaises(
            exceptions.AccessError, msg="ACLs: 'none' internal permission"
        ):
            article_hidden.body

        with self.assertRaises(
            exceptions.AccessError,
            msg="ACLs: copy should not allow to access hidden articles",
        ):
            _new_article = article_hidden.copy()

        article_root_readonly = self.article_roots[0].with_env(self.env)
        with self.assertRaises(
            exceptions.AccessError,
            msg="ACLs: copy should not allow to duplicate other people members",
        ):
            _new_article = article_root_readonly.copy()

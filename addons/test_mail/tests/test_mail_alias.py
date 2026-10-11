import random
from ast import literal_eval
from unittest.mock import patch

import psycopg

from odoo import exceptions
from odoo.tests import tagged
from odoo.tests.common import users
from odoo.tools import SQL, formataddr, mute_logger

from odoo.addons.mail.models.mail_alias import dot_atom_text
from odoo.addons.mail.tests.common import MailCommon, mail_new_test_user


class TestMailAliasCommon(MailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.test_alias_mc = cls.env["mail.alias"].create(
            {
                "alias_domain_id": cls.mail_alias_domain.id,
                "alias_model_id": cls.env["ir.model"]._get("mail.test.container.mc").id,
                "alias_name": "test.alias",
            }
        )

        cls.company_no_alias = cls.env["res.company"].create(
            {
                "alias_domain_id": False,
                "country_id": cls.env.ref("base.be").id,
                "currency_id": cls.env.ref("base.EUR").id,
                "email": "company_no_alias@test.example.com",
                "name": "No Alias Company",
            }
        )
        cls.user_erp_manager.write(
            {
                "company_ids": [(4, cls.company_no_alias.id)],
            }
        )


@tagged("mail_gateway", "mail_alias", "multi_company")
class TestMailAlias(TestMailAliasCommon):
    """Test alias model features, constraints and behavior."""

    @users("admin")
    def test_alias_domain_allowed_validation(self):
        for value in [",", ",,", ", ,"]:
            with self.assertRaises(exceptions.ValidationError):
                self.env["ir.config_parameter"].set_param(
                    "mail.catchall.domain.allowed", value
                )

        for value, expected in [
            ("", False),
            ("hello.com", "hello.com"),
            ("hello.com,,", "hello.com"),
            ("hello.com,bonjour.com", "hello.com,bonjour.com"),
            ("hello.COM, BONJOUR.com", "hello.com,bonjour.com"),
        ]:
            self.env["ir.config_parameter"].set_param(
                "mail.catchall.domain.allowed", value
            )
            self.assertEqual(
                self.env["ir.config_parameter"].get_param(
                    "mail.catchall.domain.allowed"
                ),
                expected,
            )

    @users("erp_manager")
    def test_alias_domain_company_check(self):
        misc_alias_domain = self.env["mail.alias.domain"].create({"name": "misc.com"})
        record_mc_c1, record_mc_c2 = self.env["mail.test.container.mc"].create(
            [
                {
                    "alias_name": "Test1",
                    "company_id": self.company_admin.id,
                },
                {
                    "alias_name": "Test2",
                    "company_id": self.company_2.id,
                },
            ]
        )
        alias_mc_c1, alias_mc_c2 = record_mc_c1.alias_id, record_mc_c2.alias_id
        self.assertEqual(
            (alias_mc_c1 + alias_mc_c2).alias_parent_model_id,
            self.env["ir.model"]._get("mail.test.container.mc"),
        )
        self.assertEqual(
            (alias_mc_c1 + alias_mc_c2).mapped("alias_parent_thread_id"),
            (record_mc_c1 + record_mc_c2).ids,
        )
        self.assertEqual(alias_mc_c1.alias_domain_id, self.mail_alias_domain)
        self.assertEqual(alias_mc_c2.alias_domain_id, self.mail_alias_domain_c2)

        with self.assertRaises(exceptions.ValidationError):
            record_mc_c1.alias_domain_id = self.mail_alias_domain_c2
        with self.assertRaises(exceptions.ValidationError):
            alias_mc_c1.sudo().alias_domain_id = self.mail_alias_domain_c2
        record_mc_c1.alias_domain_id = misc_alias_domain

        record_upd_c1, record_upd_c2 = (
            self.env["mail.test.alias.optional"]
            .sudo()
            .create(
                [
                    {
                        "alias_name": "Update C1",
                        "company_id": self.company_admin.id,
                    },
                    {
                        "alias_name": "Update C2",
                        "company_id": self.company_2.id,
                    },
                ]
            )
        )
        alias_update_c1, alias_update_c2 = (
            record_upd_c1.alias_id,
            record_upd_c2.alias_id,
        )
        self.assertEqual(
            (alias_update_c1 + alias_update_c2).mapped("alias_force_thread_id"),
            (record_upd_c1 + record_upd_c2).ids,
        )
        self.assertEqual(alias_update_c1.alias_domain_id, self.mail_alias_domain)
        self.assertEqual(alias_update_c2.alias_domain_id, self.mail_alias_domain_c2)

        with self.assertRaises(exceptions.ValidationError):
            record_upd_c1.alias_domain_id = self.mail_alias_domain_c2
        with self.assertRaises(exceptions.ValidationError):
            alias_update_c1.sudo().alias_domain_id = self.mail_alias_domain_c2
        record_upd_c1.alias_domain_id = misc_alias_domain

    @users("admin")
    def test_alias_name_unique(self):
        mail_alias_domain = self.mail_alias_domain.with_env(self.env)
        mail_alias_domain_c2 = self.mail_alias_domain_c2.with_env(self.env)
        alias_model_id = self.env["ir.model"]._get("mail.test.gateway").id

        new_mail_alias = self.env["mail.alias"].create(
            {
                "alias_model_id": alias_model_id,
                "alias_name": "unused.test.alias",
            }
        )
        other_alias = self.env["mail.alias"].create(
            {
                "alias_model_id": alias_model_id,
                "alias_name": "other.test.alias",
            }
        )
        self.assertEqual(
            (new_mail_alias + other_alias).alias_domain_id, mail_alias_domain
        )

        with self.assertRaises(exceptions.ValidationError):
            self.env["mail.alias"].create(
                {
                    "alias_model_id": alias_model_id,
                    "alias_name": mail_alias_domain.catchall_alias,
                }
            )
        with self.assertRaises(exceptions.ValidationError):
            self.env["mail.alias"].create(
                {
                    "alias_model_id": alias_model_id,
                    "alias_name": mail_alias_domain.bounce_alias,
                }
            )
        with self.assertRaises(exceptions.UserError):
            new_mail_alias.write({"alias_name": mail_alias_domain.catchall_alias})
        with self.assertRaises(exceptions.UserError):
            new_mail_alias.write({"alias_name": mail_alias_domain.bounce_alias})

        new_aliases = self.env["mail.alias"].create(
            [
                {
                    "alias_model_id": alias_model_id,
                    "alias_name": self.alias_catchall_c2,
                },
                {"alias_model_id": alias_model_id, "alias_name": self.alias_bounce_c2},
            ]
        )
        self.assertEqual(new_aliases.alias_domain_id, mail_alias_domain)
        new_aliases.unlink()
        new_mail_alias.write({"alias_name": mail_alias_domain_c2.bounce_alias})
        other_alias.write({"alias_name": mail_alias_domain_c2.catchall_alias})
        with self.assertRaises(exceptions.UserError):
            new_mail_alias.write(
                {
                    "alias_domain_id": mail_alias_domain_c2.id,
                }
            )

        new_mail_alias.write({"alias_name": "unused.test.alias"})
        with self.assertRaises(exceptions.UserError):
            self.env["mail.alias"].create(
                {
                    "alias_model_id": alias_model_id,
                    "alias_name": "unused.test.alias",
                }
            )
        with self.assertRaises(exceptions.UserError):
            self.env["mail.alias"].create(
                [
                    {
                        "alias_model_id": alias_model_id,
                        "alias_name": alias_name,
                    }
                    for alias_name in ("new.alias.1", "new.alias.2", "new.alias.1")
                ]
            )
        with self.assertRaises(exceptions.UserError):
            other_alias.write({"alias_name": "unused.test.alias"})

        nodom_alias = self.env["mail.alias"].create(
            {
                "alias_domain_id": False,
                "alias_model_id": alias_model_id,
                "alias_name": "no.domain",
            }
        )
        self.assertFalse(nodom_alias.alias_domain_id)
        with self.assertRaises(exceptions.UserError):
            self.env["mail.alias"].create(
                {
                    "alias_domain_id": False,
                    "alias_model_id": alias_model_id,
                    "alias_name": "no.domain",
                }
            )
        with self.assertRaises(exceptions.UserError):
            self.env["mail.alias"].create(
                [
                    {
                        "alias_domain_id": False,
                        "alias_model_id": alias_model_id,
                        "alias_name": "dupes.wo.domain",
                    }
                    for _x in range(2)
                ]
            )
        with self.assertRaises(exceptions.UserError):
            other_alias.write(
                {
                    "alias_domain_id": False,
                    "alias_name": "no.domain",
                }
            )

        other_domain_alias = self.env["mail.alias"].create(
            {
                "alias_domain_id": mail_alias_domain_c2.id,
                "alias_model_id": alias_model_id,
                "alias_name": "unused.test.alias",
            }
        )
        self.assertEqual(other_domain_alias.alias_domain_id, mail_alias_domain_c2)
        with self.assertRaises(exceptions.UserError):
            other_domain_alias.write({"alias_domain_id": mail_alias_domain.id})

    @users("admin")
    def test_alias_name_unique_copy(self):
        mail_alias_domain = self.mail_alias_domain.with_env(self.env)
        alias_model_id = self.env["ir.model"]._get("mail.test.gateway").id
        new_mail_alias = self.env["mail.alias"].create(
            {"alias_model_id": alias_model_id, "alias_name": "unused.test.alias"}
        )

        with mute_logger("odoo.db"), self.assertRaises(psycopg.errors.UniqueViolation):
            new_mail_alias.copy({"alias_name": "unused.test.alias"})

        copy_1 = new_mail_alias.copy()
        self.assertFalse(copy_1.alias_name)
        self.assertEqual(copy_1.alias_domain_id, mail_alias_domain)
        copy_2 = new_mail_alias.copy({"alias_name": "test.alias.2.éè#"})
        self.assertEqual(copy_2.alias_name, "test.alias.2.ee#")
        self.assertEqual(copy_2.alias_domain_id, mail_alias_domain)

        with self.assertRaises(exceptions.UserError):
            (copy_1 + copy_2).write({"alias_name": "test.alias.other"})

    @users("admin")
    @mute_logger("odoo.models.unlink")
    def test_alias_name_sanitize(self):
        alias_names = [
            "bidule...inc.",
            "b4r+=*R3wl_#_-$€{}[]()~|\\/!?&%^'\"`~",
            "hélène.prôvâïder",
            "Déboulonneur 😊",
        ]
        expected_names = [
            "bidule.inc",
            "b4r+=*r3wl_#_-${}-~|-/!?&%^'-`~",
            "helene.provaider",
            "deboulonneur-",
        ]
        msgs = [
            "Emails cannot start or end with a dot, there cannot be a sequence of dots.",
            (
                "Disallowed chars should be replaced by hyphens; the euro sign is not "
                "representable in ascii at all, so it is dropped rather than hyphenated"
            ),
            "Email alias should be unaccented",
            "Only a subset of unaccented latin chars are valid, others are replaced",
        ]
        for alias_name, expected, msg in zip(
            alias_names, expected_names, msgs, strict=True
        ):
            with self.subTest(alias_name=alias_name):
                alias = self.env["mail.alias"].create(
                    {
                        "alias_model_id": self.env["ir.model"]
                        ._get("mail.test.container")
                        .id,
                        "alias_name": alias_name,
                    }
                )
                self.assertEqual(alias.alias_name, expected, msg)
                alias.unlink()

        alias = self.env["mail.alias"].create(
            {
                "alias_model_id": self.env["ir.model"]._get("mail.test.container").id,
            }
        )
        for alias_name, expected, msg in zip(
            alias_names, expected_names, msgs, strict=True
        ):
            with self.subTest(alias_name=alias_name):
                alias.write({"alias_name": alias_name})
                self.assertEqual(alias.alias_name, expected, msg)

    @users("admin")
    def test_a_name_with_nothing_latin_left_is_refused_not_cleared(self):
        alias_model = self.env["ir.model"]._get("mail.test.container")
        alias = self.env["mail.alias"].create(
            {"alias_model_id": alias_model.id, "alias_name": "sales"}
        )
        for name in ("продажи", "販売", "...", "😊", "ぁ", "@example.com"):
            with self.subTest(alias_name=name):
                with self.assertRaises(exceptions.ValidationError):
                    alias.write({"alias_name": name})
                self.assertEqual(alias.alias_name, "sales")
                with self.assertRaises(exceptions.ValidationError):
                    self.env["mail.alias"].create(
                        {"alias_model_id": alias_model.id, "alias_name": name}
                    )

    @users("admin")
    def test_alias_name_sanitize_is_always_acceptable(self):
        MailAlias = self.env["mail.alias"]
        explicit = [
            "\u65e5\u672c.jobs",
            "jobs.\u65e5\u672c",
            "\u041e\u041e\u041e.\u0420\u043e\u043c\u0430\u0448\u043a\u0430",
            "info.\u043a\u043e\u043d\u0442\u0430\u043a\u0442.sales",
            "jobs.\U0001f60a.sales",
            "..\u65e5\u672c..",
        ]
        for name in explicit:
            with self.subTest(alias_name=name):
                sanitized = MailAlias._normalize_alias_name(name)
                if sanitized:
                    self.assertRegex(
                        sanitized, dot_atom_text, "must satisfy the constraint"
                    )
                    alias = MailAlias.create(
                        {
                            "alias_model_id": self.env["ir.model"]
                            ._get("mail.test.container")
                            .id,
                            "alias_name": name,
                        }
                    )
                    self.assertEqual(alias.alias_name, sanitized)
                    alias.unlink()

        rng = random.Random(20260817)
        alphabet = list("ab.-_@ ") + [
            "\u4e2d",
            "\u042b",
            "\u00e9",
            "\u3041",
            "!",
            "\u20ac",
        ]
        for _idx in range(3000):
            name = "".join(rng.choice(alphabet) for _c in range(rng.randint(1, 9)))
            sanitized = MailAlias._normalize_alias_name(name)
            if sanitized:
                self.assertRegex(
                    sanitized,
                    dot_atom_text,
                    f"_normalize_alias_name({name!r}) returned a name the constraint rejects",
                )

    @users("admin")
    def test_alias_name_sanitize_email_domain(self):
        MailAlias = self.env["mail.alias"]
        for source, expected, msg in [
            ("jobs@Example.COM", "jobs@example.com", "domain is lowercased"),
            (
                "notifications@\u043f\u043e\u0447\u0442\u0430.\u0440\u0444",
                "notifications@xn--80a1acny.xn--p1ai",
                "non-ascii domains are IDNA-encoded, not carried as raw unicode",
            ),
            ("jobs@exa mple.com", False, "a space is not a domain"),
            ("jobs@a@b.com", False, "two @ is not an address"),
            ("jobs@.example.com", False, "a domain cannot start with a dot"),
            ("jobs@", "jobs", "no domain part at all is still a valid local part"),
        ]:
            with self.subTest(source=source):
                self.assertEqual(
                    MailAlias._normalize_alias_name(source, is_email=True),
                    expected,
                    msg,
                )

    @users("admin")
    def test_alias_status_resets_on_config_change(self):
        record = self.env["mail.test.container"].create({"name": "status host"})
        alias = self.env["mail.alias"].create(
            {
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_model_id": self.env["ir.model"]._get("mail.test.container").id,
                "alias_name": "status.test",
                "alias_contact": "followers",
            }
        )
        for fname, value, expected, msg in [
            ("alias_force_thread_id", record.id, "not_tested", "repairs the config"),
            ("alias_contact", "everyone", "not_tested", "changes who may post"),
            (
                "alias_defaults",
                "{'name': 'x'}",
                "not_tested",
                "changes what is created",
            ),
            ("alias_name", "status.renamed", "invalid", "renaming repairs nothing"),
            (
                "alias_domain_id",
                self.mail_alias_domain_c2.id,
                "invalid",
                "moving domains repairs nothing",
            ),
        ]:
            with self.subTest(field=fname):
                alias.alias_status = "invalid"
                alias.flush_recordset()
                alias.write({fname: value})
                self.assertEqual(alias.alias_status, expected, msg)

    @users("admin")
    def test_alias_create_honours_defaults(self):
        alias = (
            self.env["mail.alias"]
            .with_context(
                default_alias_name="from.the.context",
                default_alias_domain_id=self.mail_alias_domain_c2.id,
            )
            .create(
                {"alias_model_id": self.env["ir.model"]._get("mail.test.container").id}
            )
        )
        self.assertEqual(alias.alias_name, "from.the.context")
        self.assertEqual(alias.alias_domain_id, self.mail_alias_domain_c2)
        alias_2 = (
            self.env["mail.alias"]
            .with_context(default_alias_name="Ctx Déf@ult")
            .create(
                {"alias_model_id": self.env["ir.model"]._get("mail.test.container").id}
            )
        )
        self.assertEqual(alias_2.alias_name, "ctx-def")

    @users("admin")
    def test_alias_name_search(self):
        alias = self.env["mail.alias"].create(
            {
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_model_id": self.env["ir.model"]._get("mail.test.container").id,
                "alias_name": "search.me",
            }
        )
        self.assertEqual(alias.display_name, f"search.me@{self.mail_alias_domain.name}")
        for term in ("search.me", alias.display_name, self.mail_alias_domain.name):
            with self.subTest(term=term):
                found = self.env["mail.alias"].name_search(term)
                self.assertIn(
                    alias.id,
                    [res[0] for res in found],
                    f"name_search({term!r}) should find the alias it describes",
                )

    @users("admin")
    def test_alias_name_sanitize_false(self):
        aliases = self.env["mail.alias"].create(
            [
                {
                    "alias_model_id": self.env["ir.model"]
                    ._get("mail.test.container")
                    .id,
                    "alias_name": falsy_name,
                }
                for falsy_name in [False, None, "", " "]
            ]
        )
        for alias in aliases:
            with self.subTest(alias_name=alias.alias_name):
                self.assertFalse(
                    alias.alias_name, "Void values should resolve to False"
                )

        for idx, alias in enumerate(aliases):
            alias.write({"alias_name": f"unique-{idx}"})
        aliases.write({"alias_name": ""})
        for alias in aliases:
            self.assertEqual(alias.alias_name, False)

    @users("admin")
    def test_search(self):
        existing = self.env["mail.alias"].search([("alias_domain_id", "!=", False)])
        self.assertEqual(existing.alias_domain_id, self.mail_alias_domain)
        existing.write({"alias_name": False})

        mail_alias_domain = self.mail_alias_domain.with_env(self.env)
        mail_alias_domain_c2 = self.mail_alias_domain_c2.with_env(self.env)
        self.assertEqual(mail_alias_domain.name, "test.mycompany.com")
        self.assertEqual(mail_alias_domain_c2.name, "test.mycompany2.com")

        aliases = self.env["mail.alias"].create(
            [
                {
                    "alias_model_id": self.env["ir.model"]
                    ._get("mail.test.container.mc")
                    .id,
                    "alias_name": f"test.search.{idx}",
                    "alias_domain_id": domain.id,
                }
                for idx in range(5)
                for domain in (mail_alias_domain + mail_alias_domain_c2)
            ]
        )
        aliases_d1 = aliases.filtered(lambda a: a.alias_domain_id == mail_alias_domain)
        aliases_d2 = aliases.filtered(
            lambda a: a.alias_domain_id == mail_alias_domain_c2
        )

        self.assertEqual(
            self.env["mail.alias"].search([("alias_name", "ilike", "test.search")]),
            aliases,
        )

        for search_term, expected, msg in [
            (
                "mycompany",
                aliases,
                'Match all aliases on both domains as "mycompany" is contained in those two',
            ),
            (
                mail_alias_domain.name,
                aliases_d1,
                "Exact match on domain 1: should find all aliases in that domain",
            ),
            (
                mail_alias_domain_c2.name,
                aliases_d2,
                "Exact match on domain 2: should find all aliases in that domain",
            ),
            (
                "search.0@test.mycompany",
                aliases.filtered(lambda a: a.alias_name == "test.search.0"),
                "Match in both domains",
            ),
            (
                "search.0@test.mycompany.com",
                aliases.filtered(
                    lambda a: (
                        a.alias_name == "test.search.0"
                        and a.alias_domain_id == mail_alias_domain
                    )
                ),
                "Match only in domain 1",
            ),
            (
                "search@test.mycompany.com",
                self.env["mail.alias"],
                "Does not match even as ilike",
            ),
        ]:
            with self.subTest(search_term=search_term):
                self.assertEqual(
                    self.env["mail.alias"].search(
                        [("alias_full_name", "ilike", search_term)]
                    ),
                    expected,
                    msg,
                )

        for search_term, expected, msg in [
            (
                ["mycompany"],
                self.env["mail.alias"],
                "mycompany is too vague: does not match a left- and right- part (!= ilike)",
            ),
            (
                [mail_alias_domain.name],
                self.env["mail.alias"],
                "Match only right-part of aliases emails",
            ),
        ]:
            with self.subTest(search_term=search_term):
                self.assertEqual(
                    self.env["mail.alias"].search(
                        [("alias_full_name", "in", search_term)]
                    ),
                    expected,
                    msg,
                )

    @users("admin")
    def test_alias_setup(self):
        alias = self.env["mail.alias"].create(
            {
                "alias_model_id": self.env["ir.model"]
                ._get("mail.test.container.mc")
                .id,
                "alias_name": "unused.test.alias",
            }
        )
        self.assertEqual(alias.alias_status, "not_tested")

        with self.assertRaises(exceptions.ValidationError):
            alias.write({"alias_defaults": "{'custom_field': brokendict"})
        alias.write({"alias_defaults": "{'name': 'validdict'}"})
        self.assertEqual(alias._prepare_alias_defaults(), {"name": "validdict"})

        with self.assertRaises(exceptions.ValidationError):
            alias.write({"alias_defaults": "{'custom_field': 'validdict'}"})

        with self.assertRaises(exceptions.ValidationError):
            alias.write({"alias_defaults": "[('name', 'from pairs')]"})
        self.assertEqual(alias._prepare_alias_defaults(), {"name": "validdict"})


@tagged("mail_alias", "multi_company")
class TestAliasCompany(TestMailAliasCommon):
    """Test company / alias domain and configuration synchronization"""

    def test_alias_domain_setup_archived_company(self):

        self.company_archived = self.env["res.company"].create(
            {
                "country_id": self.env.ref("base.be").id,
                "currency_id": self.env.ref("base.EUR").id,
                "email": "company_archived@test.example.com",
                "name": "Company Archived Test",
            }
        )
        self.company_archived.action_archive()

        test_record_archived_company = self.env["mail.test.simple.unfollow"].create(
            {
                "name": "Test record (mixin.mail.thread) specific to archived company",
                "company_id": self.company_archived.id,
            }
        )

        unfollow_model_id = self.env["ir.model"]._get_id("mail.test.simple.unfollow")
        mc_archived_parent = self.env["mail.alias"].create(
            {
                "alias_name": "alias_parent_specific_to_archived_company",
                "alias_parent_model_id": unfollow_model_id,
                "alias_model_id": unfollow_model_id,
                "alias_parent_thread_id": test_record_archived_company.id,
            }
        )

        mc_archived_target = self.env["mail.alias"].create(
            {
                "alias_name": "alias_target_specific_to_archived_company",
                "alias_parent_model_id": unfollow_model_id,
                "alias_model_id": unfollow_model_id,
                "alias_force_thread_id": test_record_archived_company.id,
            }
        )

        all_mail_aliases = self.env["mail.alias"].search([])
        all_mail_aliases.write({"alias_domain_id": False})
        self.env["mail.alias.domain"].search([]).unlink()

        self.assertFalse(
            any(all_mail_aliases.mapped("alias_domain_id")),
            "Mail aliases should have no linked alias domain at this stage",
        )

        mc_alias_domain = self.env["mail.alias.domain"].create(
            {
                "bounce_alias": "bounce.mc.archived",
                "catchall_alias": "catchall.bounce.mc.archived",
                "name": "test.init.mc.archived.com",
            }
        )

        self.assertEqual(
            mc_archived_parent.alias_domain_id.id,
            mc_alias_domain.id,
            "Parent thread has the wrong alias domain",
        )
        self.assertEqual(
            mc_archived_target.alias_domain_id.id,
            mc_alias_domain.id,
            "Target thread has the wrong alias domain",
        )
        self.assertEqual(
            self.company_archived.alias_domain_id.id,
            mc_alias_domain.id,
            "Archived company was attributed wrong alias domain",
        )

    @mute_logger("odoo.models.unlink")
    @users("erp_manager")
    def test_alias_domain_setup(self):
        mail_alias_domain = self.mail_alias_domain.with_env(self.env)
        mail_alias_domain_c2 = self.mail_alias_domain_c2.with_env(self.env)

        self.assertEqual(self.company_admin.alias_domain_id, mail_alias_domain)
        self.assertEqual(self.company_2.alias_domain_id, mail_alias_domain_c2)

        with (
            self.assertRaises(
                (psycopg.errors.ForeignKeyViolation, psycopg.errors.RestrictViolation)
            ),
            mute_logger("odoo.db"),
        ):
            mail_alias_domain.unlink()

        self.env["mail.alias"].sudo().search([]).write({"alias_domain_id": False})
        mail_alias_domain.unlink()
        self.assertFalse(self.company_admin.alias_domain_id)
        self.assertEqual(self.company_2.alias_domain_id, mail_alias_domain_c2)
        self.assertFalse(self.test_alias_mc.alias_domain_id)

        self.env["mail.alias.domain"].search([]).unlink()
        self.assertFalse(self.company_2.alias_domain_id)
        self.assertEqual(self.company_2.bounce_email, "")
        self.assertEqual(self.company_2.bounce_formatted, "")
        self.assertEqual(self.company_2.catchall_email, "")
        self.assertEqual(self.company_2.catchall_formatted, "")
        self.assertFalse(self.company_2.default_from_email, "")
        self.assertFalse(self.company_3.alias_domain_id)

        alias_domain_new = self.env["mail.alias.domain"].create(
            {
                "bounce_alias": "bounce.new",
                "catchall_alias": "catchall.new",
                "name": "test.global.bitnurk.com",
            }
        )
        self.assertEqual(
            self.company_admin.alias_domain_id,
            alias_domain_new,
            "MC Alias: first domain should populate void companies",
        )
        self.assertEqual(
            self.company_2.alias_domain_id,
            alias_domain_new,
            "MC Alias: should take alias domain with lower sequence",
        )
        self.assertEqual(
            self.company_3.alias_domain_id,
            alias_domain_new,
            "MC Alias: should take alias domain with lower sequence",
        )
        self.assertEqual(
            self.test_alias_mc.alias_domain_id,
            alias_domain_new,
            "MC Alias: first domain should populate void aliases",
        )

        self.company_2.alias_domain_id = alias_domain_new.id
        self.assertEqual(self.company_2.alias_domain_id, alias_domain_new)
        self.assertEqual(
            self.company_2.bounce_email, "bounce.new@test.global.bitnurk.com"
        )
        self.assertEqual(
            self.company_2.catchall_email, "catchall.new@test.global.bitnurk.com"
        )

    def test_assert_initial_values(self):
        self.assertEqual(self.test_alias_mc.alias_domain_id, self.mail_alias_domain)
        self.assertFalse(self.company_no_alias.alias_domain_id)

        self.assertEqual(self.company_admin.alias_domain_id, self.mail_alias_domain)
        self.assertEqual(
            self.company_admin.bounce_email, f"{self.alias_bounce}@{self.alias_domain}"
        )
        self.assertEqual(
            self.company_admin.bounce_formatted,
            formataddr(
                (self.company_admin.name, f"{self.alias_bounce}@{self.alias_domain}")
            ),
        )
        self.assertEqual(
            self.company_admin.catchall_email,
            f"{self.alias_catchall}@{self.alias_domain}",
        )
        self.assertEqual(
            self.company_admin.catchall_formatted,
            formataddr(
                (self.company_admin.name, f"{self.alias_catchall}@{self.alias_domain}")
            ),
        )
        self.assertEqual(
            self.company_admin.default_from_email,
            f"{self.default_from}@{self.alias_domain}",
        )

        self.assertEqual(self.company_2.alias_domain_id, self.mail_alias_domain_c2)
        self.assertEqual(
            self.company_2.bounce_email,
            f"{self.alias_bounce_c2}@{self.alias_domain_c2_name}",
        )
        self.assertEqual(
            self.company_2.bounce_formatted,
            formataddr(
                (
                    self.company_2.name,
                    f"{self.alias_bounce_c2}@{self.alias_domain_c2_name}",
                )
            ),
        )
        self.assertEqual(
            self.company_2.catchall_email,
            f"{self.alias_catchall_c2}@{self.alias_domain_c2_name}",
        )
        self.assertEqual(
            self.company_2.catchall_formatted,
            formataddr(
                (
                    self.company_2.name,
                    f"{self.alias_catchall_c2}@{self.alias_domain_c2_name}",
                )
            ),
        )
        self.assertEqual(
            self.company_2.default_from_email,
            f"{self.alias_default_from_c2}@{self.alias_domain_c2_name}",
        )

        self.assertEqual(self.company_3.alias_domain_id, self.mail_alias_domain_c3)
        self.assertEqual(
            self.company_3.bounce_email,
            f"{self.alias_bounce_c3}@{self.alias_domain_c3_name}",
        )
        self.assertEqual(
            self.company_3.bounce_formatted,
            formataddr(
                (
                    self.company_3.name,
                    f"{self.alias_bounce_c3}@{self.alias_domain_c3_name}",
                )
            ),
        )
        self.assertEqual(
            self.company_3.catchall_email,
            f"{self.alias_catchall_c3}@{self.alias_domain_c3_name}",
        )
        self.assertEqual(
            self.company_3.catchall_formatted,
            formataddr(
                (
                    self.company_3.name,
                    f"{self.alias_catchall_c3}@{self.alias_domain_c3_name}",
                )
            ),
        )
        self.assertEqual(
            self.company_3.default_from_email,
            f"{self.alias_default_from_c3}@{self.alias_domain_c3_name}",
        )

    @users("erp_manager")
    def test_res_company_creation_alias_domain(self):
        company = self.env["res.company"].create(
            {
                "email": '"Super Company" <super.company@test3.mycompany.com>',
                "name": "Super Company",
            }
        )
        company.flush_recordset()
        self.assertEqual(
            company.alias_domain_id,
            self.mail_alias_domain,
            "Default alias domain: sequence based",
        )

        company = self.env["res.company"].create(
            {
                "alias_domain_id": self.mail_alias_domain_c2.id,
                "email": '"Yet Another Company" <yet.another.company@test.embed.mycompany.com>',
                "name": "Yet Another Company",
            }
        )
        self.assertEqual(company.alias_domain_id, self.mail_alias_domain_c2)


@tagged("mail_gateway", "mail_alias", "multi_company")
class TestMailAliasBounce(TestMailAliasCommon):
    """Both bounce bodies leave the server addressed to an outside sender."""

    @users("admin")
    def test_bounce_bodies_speak_the_author_language(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        author = self.env["res.partner"].create(
            {"name": "Francais", "email": "fr@test.example.com", "lang": "fr_FR"}
        )
        alias = self.env["mail.alias"].create(
            {
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_model_id": self.env["ir.model"]._get("mail.test.container").id,
                "alias_name": "bounce.lang",
                "alias_contact": "partners",
            }
        )
        message_dict = {
            "author_id": author.id,
            "email_from": author.email,
            "body": "<p>le corps</p>",
        }
        for body, label in [
            (alias._get_alias_bounced_body(message_dict), "security bounce"),
            (alias._get_alias_invalid_body(message_dict), "config bounce"),
        ]:
            with self.subTest(body=label):
                self.assertNotIn(
                    "Dear Sender",
                    body,
                    f"the {label} was rendered in the server language, not the author's",
                )

    @users("admin")
    def test_bounce_contact_description_covers_every_policy(self):
        alias = self.env["mail.alias"].create(
            {
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_model_id": self.env["ir.model"]._get("mail.test.container").id,
                "alias_name": "bounce.desc",
            }
        )
        alias.alias_contact = "everyone"
        fallback = alias._get_alias_contact_description()
        restrictions = [
            value
            for value, _label in alias._fields["alias_contact"].get_description(
                self.env
            )["selection"]
            if value != "everyone"
        ]
        self.assertTrue(restrictions)
        descriptions = set()
        for contact in restrictions:
            with self.subTest(alias_contact=contact):
                alias.alias_contact = contact
                description = alias._get_alias_contact_description()
                self.assertNotEqual(
                    description,
                    fallback,
                    f"'{contact}' falls through to the catch-all wording, which tells "
                    f"the bounced sender nothing about who may write",
                )
                descriptions.add(description)
        self.assertEqual(
            len(descriptions),
            len(restrictions),
            "each policy must describe itself distinctly",
        )


@tagged("mail_gateway", "mail_alias", "multi_company")
class TestMailAliasDomain(TestMailAliasCommon):
    @users("employee")
    def test_the_companies_of_a_domain_are_searched_like_a_relation(self):
        AliasDomain = self.env["mail.alias.domain"]
        used = self.mail_alias_domain.with_env(self.env)
        company = used.sudo().company_ids[:1]
        self.assertTrue(company, "sanity: the main domain is some company's")
        unused = AliasDomain.sudo().create({"name": "unused.example.com"})

        def found(domain):
            return AliasDomain.search(domain) & (used | unused)

        self.assertEqual(found([("company_ids", "in", company.ids)]), used)
        self.assertEqual(found([("company_ids", "not in", company.ids)]), unused)
        self.assertEqual(found([("company_ids", "=", False)]), unused)
        self.assertEqual(found([("company_ids", "!=", False)]), used)
        self.assertEqual(
            found([("company_ids", "in", [company.id, False])]), used | unused
        )
        self.assertEqual(
            found([("company_ids", "any", [("id", "=", company.id)])]), used
        )

    @users("admin")
    def test_alias_domain_config_alias_clash(self):
        alias_domain = self.mail_alias_domain.with_env(self.env)

        for domain_config in ("bounce_alias", "catchall_alias"):
            with self.subTest(domain_config=domain_config):
                with self.assertRaises(exceptions.ValidationError):
                    self.env["mail.alias.domain"].create(
                        {
                            domain_config: self.test_alias_mc.alias_name,
                            "name": self.test_alias_mc.alias_domain_id.name,
                        }
                    )
        self.env["mail.alias.domain"].create(
            {
                domain_config: self.test_alias_mc.alias_name,
                "name": "another.domain.name.com",
            }
        )

        with self.assertRaises(exceptions.UserError):
            alias_domain.write({"bounce_alias": self.test_alias_mc.alias_name})
        with self.assertRaises(exceptions.UserError):
            alias_domain.write({"catchall_alias": self.test_alias_mc.alias_name})

    @users("admin")
    def test_alias_domain_config_unique(self):
        alias_domain = self.mail_alias_domain.with_env(self.env)

        with mute_logger("odoo.db"), self.assertRaises(psycopg.errors.UniqueViolation):
            new_alias_domain = alias_domain.copy()

        new_alias_domain = alias_domain.copy(
            {
                "bounce_alias": "new.bounce",
                "catchall_alias": "new.catchall",
            }
        )
        self.assertEqual(
            new_alias_domain.bounce_email, f"new.bounce@{alias_domain.name}"
        )
        self.assertEqual(
            new_alias_domain.catchall_email, f"new.catchall@{alias_domain.name}"
        )
        self.assertEqual(new_alias_domain.name, alias_domain.name)

        self.env["mail.alias.domain"].create(
            {
                "bounce_alias": "unique.bounce",
                "catchall_alias": "unique.catchall",
                "name": alias_domain.name,
            }
        )
        with mute_logger("odoo.db"), self.assertRaises(psycopg.errors.UniqueViolation):
            self.env["mail.alias.domain"].create(
                {
                    "bounce_alias": alias_domain.bounce_alias,
                    "name": alias_domain.name,
                }
            )
        with mute_logger("odoo.db"), self.assertRaises(psycopg.errors.UniqueViolation):
            self.env["mail.alias.domain"].create(
                {
                    "catchall_alias": alias_domain.catchall_alias,
                    "name": alias_domain.name,
                }
            )

        with self.assertRaises(exceptions.ValidationError):
            new_alias_domain.write({"bounce_alias": alias_domain.bounce_alias})
        with self.assertRaises(exceptions.ValidationError):
            new_alias_domain.write({"catchall_alias": alias_domain.catchall_alias})

    @users("admin")
    def test_alias_domain_parameters_validation(self):
        alias_domain = self.mail_alias_domain.with_env(self.env)

        for failing_name in [
            "outlook.fr, gmail.com",
            "",
            " ",
            "prova ider.com",
        ]:
            with self.subTest(failing_name=failing_name):
                with self.assertRaises(exceptions.ValidationError):
                    _new_domain = self.env["mail.alias.domain"].create(
                        {"name": failing_name}
                    )

                with self.assertRaises(exceptions.ValidationError):
                    alias_domain.write({"name": failing_name})

        for (
            (bounce_alias, catchall_alias, default_from),
            (exp_bounce, exp_catchall, exp_default_from),
            (exp_bounce_email, exp_catchall_email, exp_default_from_email),
        ) in zip(
            [
                (
                    "bounce+b4r=*R3wl_#_-$€{}[]()~|\\/!?&%^'\"`~",
                    "catchall+b4r=*R3wl_#_-$€{}[]()~|\\/!?&%^'\"`~",
                    "notifications+b4r=*R3wl_#_-$€{}[]()~|\\/!?&%^'\"`~",
                ),
                ("bounce+😊", "catchall+😊", "notifications+😊"),
                ("Bouncâïde 😊", "Catchôïee 😊", "Notificâtïons 😊"),
                (
                    "bounce@wrong.complete.com",
                    "catchall@wrong.complete.com",
                    "notifications@valid.complete.com",
                ),
            ],
            [
                (
                    "bounce+b4r=*r3wl_#_-${}-~|-/!?&%^'-`~",
                    "catchall+b4r=*r3wl_#_-${}-~|-/!?&%^'-`~",
                    "notifications+b4r=*r3wl_#_-${}-~|-/!?&%^'-`~",
                ),
                ("bounce+", "catchall+", "notifications+"),
                ("bouncaide-", "catchoiee-", "notifications-"),
                (
                    "bounce",
                    "catchall",
                    "notifications@valid.complete.com",
                ),
            ],
            [
                (
                    f"bounce+b4r=*r3wl_#_-${{}}-~|-/!?&%^'-`~@{alias_domain.name}",
                    f"catchall+b4r=*r3wl_#_-${{}}-~|-/!?&%^'-`~@{alias_domain.name}",
                    f"notifications+b4r=*r3wl_#_-${{}}-~|-/!?&%^'-`~@{alias_domain.name}",
                ),
                (
                    f"bounce+@{alias_domain.name}",
                    f"catchall+@{alias_domain.name}",
                    f"notifications+@{alias_domain.name}",
                ),
                (
                    f"bouncaide-@{alias_domain.name}",
                    f"catchoiee-@{alias_domain.name}",
                    f"notifications-@{alias_domain.name}",
                ),
                (
                    f"bounce@{alias_domain.name}",
                    f"catchall@{alias_domain.name}",
                    "notifications@valid.complete.com",
                ),
            ],
            strict=True,
        ):
            with self.subTest(bounce_alias=bounce_alias):
                alias_domain.write({"bounce_alias": bounce_alias})
                self.assertEqual(alias_domain.bounce_alias, exp_bounce)
                self.assertEqual(alias_domain.bounce_email, exp_bounce_email)
            with self.subTest(catchall_alias=catchall_alias):
                alias_domain.write({"catchall_alias": catchall_alias})
                self.assertEqual(alias_domain.catchall_alias, exp_catchall)
                self.assertEqual(alias_domain.catchall_email, exp_catchall_email)
            with self.subTest(default_from=default_from):
                alias_domain.write({"default_from": default_from})
                self.assertEqual(alias_domain.default_from, exp_default_from)
                self.assertEqual(
                    alias_domain.default_from_email, exp_default_from_email
                )

        for config_value in [False, None, "", " ", "ぁ", "ぁぁ"]:
            with self.subTest(config_value=config_value):
                alias_domain.write({"bounce_alias": config_value})
                self.assertFalse(alias_domain.bounce_alias)
                alias_domain.write({"catchall_alias": config_value})
                self.assertFalse(alias_domain.catchall_alias)
                alias_domain.write({"default_from": config_value})
                self.assertFalse(alias_domain.default_from)

        for _ in range(2):
            alias_domain.write(
                {
                    "bounce_alias": "bounce+double.test",
                    "catchall_alias": "catchall+double.test",
                }
            )
            self.assertEqual(alias_domain.bounce_alias, "bounce+double.test")
            self.assertEqual(alias_domain.catchall_alias, "catchall+double.test")


@tagged("mail_alias", "multi_company")
class TestMailAliasDomainLocalParts(TestMailAliasCommon):
    """`mail.alias.domain` composes addresses out of its three local parts."""

    @users("admin")
    def test_local_parts_are_never_stored_malformed(self):
        alias_domain = self.env["mail.alias.domain"].create(
            {
                "bounce_alias": "bnc",
                "catchall_alias": "cat",
                "default_from": "notif",
                "name": "localparts.example.com",
            }
        )
        for value in [
            "\u0431\u043e\u0443\u043d\u0441.\u044f",
            "bounce.\u65e5\u672c",
            "\u65e5\u672c.bounce",
            "b.\U0001f60a.c",
            "\u3041",
        ]:
            for fname, email_fname in [
                ("bounce_alias", "bounce_email"),
                ("catchall_alias", "catchall_email"),
                ("default_from", "default_from_email"),
            ]:
                with self.subTest(value=value, field=fname):
                    alias_domain.write({fname: value})
                    stored = alias_domain[fname]
                    if stored:
                        self.assertRegex(
                            stored.partition("@")[0],
                            dot_atom_text,
                            f"{fname} stored a local part no MTA accepts",
                        )
                        self.assertTrue(alias_domain[email_fname].isascii())
                    else:
                        self.assertFalse(alias_domain[email_fname])
                    alias_domain.write(
                        {
                            "bounce_alias": "bnc",
                            "catchall_alias": "cat",
                            "default_from": "notif",
                        }
                    )

    @users("admin")
    def test_local_parts_constraint_is_the_backstop(self):
        alias_domain = self.mail_alias_domain.with_env(self.env)
        for fname, value in [
            ("bounce_alias", "bounce."),
            ("catchall_alias", ".catchall"),
            ("default_from", "notifications@exa mple.com"),
        ]:
            with self.subTest(field=fname), self.env.cr.savepoint(flush=False):
                self.env.cr.execute(
                    SQL(
                        "UPDATE mail_alias_domain SET %s = %s WHERE id = %s",
                        SQL.identifier(fname),
                        value,
                        alias_domain.id,
                    )
                )
                alias_domain.invalidate_recordset([fname])
                with self.assertRaises(exceptions.ValidationError):
                    alias_domain._check_local_parts()

    @users("admin")
    def test_default_from_domain_is_validated(self):
        alias_domain = self.mail_alias_domain.with_env(self.env)
        alias_domain.write({"default_from": "notifications@exa mple.com"})
        self.assertFalse(
            alias_domain.default_from,
            "a domain with a space in it is not an address; it used to be stored whole",
        )
        alias_domain.write(
            {
                "default_from": "notifications@\u043f\u043e\u0447\u0442\u0430.\u0440\u0444"
            }
        )
        self.assertEqual(
            alias_domain.default_from, "notifications@xn--80a1acny.xn--p1ai"
        )
        self.assertTrue(alias_domain.default_from_email.isascii())


@tagged("mail_gateway", "mail_alias", "mail_alias_mixin", "multi_company")
class TestMailAliasMixin(TestMailAliasCommon):
    """Test alias mixin implementation, synchronization of alias records
    based on owner records."""

    @users("employee")
    @mute_logger("odoo.addons.base.models.ir_model")
    def test_alias_mixin(self):
        self.assertEqual(self.env.company.alias_domain_id, self.mail_alias_domain)

        record = self.env["mail.test.gateway.groups"].create(
            {
                "name": "Test Record",
                "alias_name": "alias.test",
                "alias_contact": "followers",
            }
        )
        self.assertEqual(record.alias_id.alias_domain_id, self.mail_alias_domain)
        self.assertEqual(
            record.alias_id.alias_model_id,
            self.env["ir.model"]._get("mail.test.gateway.groups"),
        )
        self.assertEqual(record.alias_id.alias_force_thread_id, record.id)
        self.assertEqual(
            record.alias_id.alias_parent_model_id,
            self.env["ir.model"]._get("mail.test.gateway.groups"),
        )
        self.assertEqual(record.alias_id.alias_parent_thread_id, record.id)
        self.assertEqual(record.alias_id.alias_name, "alias.test")
        self.assertEqual(record.alias_id.alias_contact, "followers")

        record.write(
            {
                "alias_domain_id": self.mail_alias_domain_c2.id,
                "alias_name": "better.alias.test",
                "alias_defaults": "{'custom_field': 'defaults'}",
            }
        )
        self.assertEqual(record.alias_domain, self.mail_alias_domain_c2.name)
        self.assertEqual(record.alias_id.alias_name, "better.alias.test")
        self.assertEqual(record.alias_id.alias_defaults, "{'custom_field': 'defaults'}")

        with self.assertRaises(exceptions.AccessError):
            record.write(
                {
                    "alias_force_thread_id": 0,
                }
            )

        with self.assertRaises(exceptions.AccessError):
            record.write(
                {
                    "alias_model_id": self.env["ir.model"]._get("mail.test.gateway").id,
                }
            )

        with self.assertRaises(exceptions.ValidationError):
            record.write({"alias_defaults": "{'custom_field': brokendict"})

        rec = self.env["mail.test.gateway.groups"].create(
            {
                "name": "Test Record2",
                "alias_name": "alias.test",
                "alias_domain_id": self.mail_alias_domain_c2.id,
            }
        )
        self.assertEqual(
            rec.alias_id.alias_domain_id,
            self.mail_alias_domain_c2,
            "Should use the provided alias domain in priority",
        )

    def test_alias_only_writes_need_write_access(self):
        record = self.env["mail.test.alias.optional"].create(
            {"alias_name": "readers.cannot", "name": "Guarded"}
        )
        reader = mail_new_test_user(
            self.env,
            email="alias.reader@test.example.com",
            groups="base.group_portal",
            login="alias_reader",
            name="Alias Reader",
        )
        self.assertTrue(record.with_user(reader).has_access("read"))
        self.assertFalse(record.with_user(reader).has_access("write"))
        with self.assertRaises(exceptions.AccessError):
            record.with_user(reader).write({"alias_name": "renamed"})
        self.assertEqual(record.alias_id.alias_name, "readers.cannot")
        record.with_user(self.user_employee).write({"alias_name": "renamed"})
        self.assertEqual(record.alias_id.alias_name, "renamed")

    @users("erp_manager")
    def test_alias_mixin_alias_email(self):
        Model = self.env["mail.test.container.mc"]
        records = Model.create(
            [
                {
                    "alias_name": f"alias.email.{idx}",
                    "company_id": company.id,
                    "name": f"Test {company.id} {idx}",
                }
                for company in (self.company_admin, self.company_2)
                for idx in range(5)
            ]
        )
        self.assertEqual(
            Model.search([("alias_email", "ilike", "alias.email")]),
            records,
            "Search: partial search: any domain, matching all left parts",
        )
        self.assertEqual(
            Model.search([("alias_email", "ilike", "alias.email.0")]),
            records[0] + records[5],
            "Search: partial search: any domain, matching some left parts",
        )
        self.assertEqual(
            Model.search([("alias_email", "=", self.mail_alias_domain.name)]),
            Model,
            "Search: partial search: does not match any complete email",
        )
        self.assertEqual(
            Model.search(
                [("alias_email", "=", f"alias.email.1@{self.mail_alias_domain.name}")]
            ),
            records[1],
            "Search: both part search: search on name + domain",
        )

    @users("employee")
    @mute_logger("odoo.addons.base.models.ir_model")
    def test_alias_mixin_alias_id_management(self):
        record_wo_alias, record_w_alias = self.env["mail.test.alias.optional"].create(
            [
                {
                    "name": "Test WoAlias Name",
                },
                {
                    "alias_name": "Alias Name",
                    "name": "Test WoAlias Name",
                },
            ]
        )
        self.assertFalse(
            record_wo_alias.alias_id,
            "Alias record not created if not necessary (no alias_name)",
        )
        self.assertFalse(record_wo_alias.alias_id.alias_name)
        self.assertFalse(record_wo_alias.alias_id.alias_defaults)
        self.assertFalse(record_wo_alias.alias_name)
        self.assertTrue(
            record_w_alias.alias_id, "Alias record created as alias_name was given"
        )
        self.assertEqual(
            record_w_alias.alias_id.alias_name,
            "alias-name",
            "Alias name should go through sanitize",
        )
        self.assertEqual(
            literal_eval(record_w_alias.alias_id.alias_defaults),
            {"company_id": self.env.company.id},
        )
        self.assertEqual(
            record_w_alias.alias_name,
            "alias-name",
            "Alias name should go through sanitize",
        )
        self.assertEqual(
            literal_eval(record_w_alias.alias_defaults),
            {"company_id": self.env.company.id},
        )

        record_w_alias.write(
            {"alias_contact": "followers", "alias_name": "Updated Alias Name"}
        )
        self.assertEqual(record_w_alias.alias_id.alias_contact, "followers")
        self.assertEqual(record_w_alias.alias_id.alias_name, "updated-alias-name")
        self.assertEqual(record_w_alias.alias_name, "updated-alias-name")

        record_wo_alias.write({"alias_name": "trying a name"})
        self.assertTrue(
            record_wo_alias.alias_id,
            "Alias record should have been created to store the name",
        )
        self.assertEqual(record_wo_alias.alias_id.alias_name, "trying-a-name")
        self.assertEqual(
            literal_eval(record_wo_alias.alias_id.alias_defaults),
            {"company_id": self.env.company.id},
        )
        self.assertEqual(record_wo_alias.alias_name, "trying-a-name")
        self.assertEqual(
            literal_eval(record_wo_alias.alias_defaults),
            {"company_id": self.env.company.id},
        )

        existing_aliases = record_wo_alias.alias_id + record_w_alias.alias_id
        (record_wo_alias + record_w_alias).write({"alias_name": False})
        self.assertEqual((record_wo_alias + record_w_alias).alias_id, existing_aliases)
        self.assertFalse(list(filter(None, existing_aliases.mapped("alias_name"))))

    @users("employee")
    def test_copy_content(self):
        self.assertFalse(
            self.env.user.has_group("base.group_system"),
            "Test user should not have Administrator access",
        )

        record = self.env["mail.test.gateway.groups"].create(
            {
                "name": "Test Record",
                "alias_name": "test.record",
                "alias_contact": "followers",
                "alias_bounced_content": False,
            }
        )
        record_alias = record.alias_id
        self.assertFalse(record.alias_bounced_content)
        record_copy = record.copy()
        record_alias_copy = record_copy.alias_id
        self.assertNotEqual(record_alias, record_alias_copy)
        self.assertEqual(record_alias.alias_force_thread_id, record.id)
        self.assertEqual(record_alias_copy.alias_force_thread_id, record_copy.id)
        self.assertFalse(record_copy.alias_bounced_content)
        self.assertEqual(record_copy.alias_contact, record.alias_contact)
        self.assertFalse(record_copy.alias_name, "Copy should not duplicate name")

        new_content = "<p>Bounced Content</p>"
        record_copy.write({"alias_bounced_content": new_content})
        self.assertEqual(record_copy.alias_bounced_content, new_content)
        record_copy2 = record_copy.copy()
        self.assertEqual(record_copy2.alias_bounced_content, new_content)

    @users("employee")
    def test_copy_optional_alias_model(self):
        record = self.env["mail.test.alias.optional"].create(
            {
                "name": "Test Optional Alias Record",
                "alias_name": "test.optional.alias.record",
            }
        )
        self.assertTrue(record.alias_id)
        record_copy = record.copy()
        self.assertFalse(record_copy.alias_id)

    @users("erp_manager")
    def test_multi_company_setup(self):
        counter = 0
        for create_cid, exp_company, exp_alias_domain in [
            (None, self.company_2, self.mail_alias_domain_c2),
            (False, self.env["res.company"], self.mail_alias_domain_c2),
            (self.env.user.company_id.id, self.company_2, self.mail_alias_domain_c2),
            (self.company_admin.id, self.company_admin, self.mail_alias_domain),
            (
                self.company_no_alias.id,
                self.company_no_alias,
                self.env["mail.alias.domain"],
            ),
        ]:
            with self.subTest(
                create_cid=create_cid,
                exp_company=exp_company,
                exp_alias_domain=exp_alias_domain,
            ):
                counter += 1
                base_values = {
                    "name": f"Test Record {counter}",
                    "alias_name": f"alias.test.{counter}",
                    "alias_contact": "followers",
                }
                if create_cid is not None:
                    base_values["company_id"] = create_cid
                record = self.env["mail.test.container.mc"].create(base_values)
                self.assertEqual(record.alias_domain_id, exp_alias_domain)
                self.assertEqual(record.company_id, exp_company)

                record_copy = record.copy(
                    default={
                        "alias_name": f"alias.copy.{counter}",
                        "name": f"Copy of {record.name}",
                    }
                )
                self.assertEqual(record_copy.alias_domain_id, exp_alias_domain)
                self.assertEqual(record_copy.company_id, record.company_id)

                record_copy_2 = record.copy(
                    default={
                        "alias_name": f"alias.copy.{counter}.2",
                        "company_id": self.company_admin.id,
                        "name": f"Copy 2 of {record.name}",
                    }
                )
                self.assertEqual(record_copy_2.alias_domain_id, self.mail_alias_domain)
                self.assertEqual(record_copy_2.company_id, self.company_admin)

                record.write({"company_id": self.company_admin.id})
                self.assertEqual(record.alias_domain_id, self.mail_alias_domain)
                self.assertEqual(record.company_id, self.company_admin)

                record.write({"company_id": False})
                self.assertEqual(record.alias_domain_id, self.mail_alias_domain)
                self.assertFalse(record.company_id)


@tagged("mail_alias")
class TestMailAliasAddressInput(TestMailAliasCommon):
    """An address has two halves; the form has two fields. Typing both in one."""

    @users("admin")
    def test_a_full_address_resolves_its_domain(self):
        other = self.env["mail.alias.domain"].create({"name": "support.test.example"})
        alias = self.env["mail.alias"].create(
            {
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_model_id": self.env["ir.model"]._get("mail.test.container").id,
                "alias_name": "jobs@support.test.example",
            }
        )
        self.assertEqual(alias.alias_name, "jobs")
        self.assertEqual(alias.alias_domain_id, other)
        self.assertEqual(alias.alias_full_name, "jobs@support.test.example")

        alias.write({"alias_name": f"jobs2@{self.mail_alias_domain.name}"})
        self.assertEqual(alias.alias_domain_id, self.mail_alias_domain)

    @users("admin")
    def test_a_bare_word_after_the_at_is_not_a_domain(self):
        alias = self.env["mail.alias"].create(
            {
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_model_id": self.env["ir.model"]._get("mail.test.container").id,
                "alias_name": "Ctx Déf@ult",
            }
        )
        self.assertEqual(alias.alias_name, "ctx-def")
        self.assertEqual(alias.alias_domain_id, self.mail_alias_domain)

    @users("admin")
    def test_an_unknown_domain_is_refused_not_dropped(self):
        with self.assertRaises(exceptions.ValidationError) as capture:
            self.env["mail.alias"].create(
                {
                    "alias_domain_id": self.mail_alias_domain.id,
                    "alias_model_id": self.env["ir.model"]
                    ._get("mail.test.container")
                    .id,
                    "alias_name": "jobs@nowhere.test.example",
                }
            )
        self.assertIn("nowhere.test.example", str(capture.exception))

    @users("admin")
    def test_the_mixin_no_longer_eats_the_domain_first(self):
        other = self.env["mail.alias.domain"].create({"name": "mixin.test.example"})
        record = self.env["mail.test.container"].create(
            {"name": "Mixin Host", "alias_name": "intake@mixin.test.example"}
        )
        self.assertEqual(record.alias_id.alias_name, "intake")
        self.assertEqual(record.alias_id.alias_domain_id, other)


@tagged("mail_alias")
class TestMailAliasStatus(TestMailAliasCommon):
    @users("admin")
    def test_an_explicit_status_wins_over_the_reset(self):
        alias = self.env["mail.alias"].create(
            {
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_model_id": self.env["ir.model"]._get("mail.test.container").id,
                "alias_name": "status.explicit",
            }
        )
        alias.write({"alias_status": "valid", "alias_contact": "partners"})
        alias.flush_recordset()
        alias.invalidate_recordset()
        self.assertEqual(alias.alias_status, "valid")

        alias.write({"alias_contact": "followers"})
        self.assertEqual(alias.alias_status, "not_tested")


@tagged("mail_alias", "mail_alias_mixin")
class TestMailAliasMixinModelOverride(TestMailAliasCommon):
    @users("admin")
    def test_a_caller_may_alias_a_narrower_model(self):
        narrow = self.env["ir.model"]._get_id("mail.test.ticket.partner")
        record = self.env["mail.test.container.mc"].create(
            {
                "alias_defaults": {"state": "new"},
                "alias_model_id": narrow,
                "alias_name": "narrow.model",
                "name": "Narrow Host",
            }
        )
        self.assertEqual(record.alias_id.alias_model_id.id, narrow)
        self.assertEqual(
            record.alias_id._prepare_alias_defaults(),
            {"container_id": record.id, "state": "new"},
            "the mixin's own defaults still merge in, they just stop clobbering",
        )


@tagged("mail_alias")
class TestMailAliasDanglingDocument(TestMailAliasCommon):
    """`alias_*_thread_id` is an integer, not a foreign key.

    Nothing deletes the alias when the document it names goes away, nothing stops a
    module from being uninstalled under one, and the field is editable in the form
    view, so any integer can end up in it. Every read of the pair therefore has to
    survive an id that names nothing -- and the two places that did not were both
    code whose entire job was to *explain* a problem, so the dangling id replaced a
    diagnostic with a bare `MissingError`.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.container_mc_model = cls.env["ir.model"]._get("mail.test.container.mc")
        cls.container_model = cls.env["ir.model"]._get("mail.test.container")
        cls.gone_id = 2**30

    @users("admin")
    def test_mc_constraint_survives_a_deleted_target(self):
        alias = self.env["mail.alias"].create(
            {
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_model_id": self.container_mc_model.id,
                "alias_name": "dangling.target",
            }
        )
        self.assertTrue(
            self.mail_alias_domain.company_ids,
            "constraint only runs for a domain owned by companies",
        )
        alias.alias_force_thread_id = self.gone_id
        alias._check_alias_domain_id_mc()
        alias.write({"alias_domain_id": self.mail_alias_domain.id})

    @users("admin")
    def test_mc_constraint_survives_a_deleted_owner(self):
        alias = self.env["mail.alias"].create(
            {
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_model_id": self.container_mc_model.id,
                "alias_name": "dangling.owner",
                "alias_parent_model_id": self.container_mc_model.id,
                "alias_parent_thread_id": self.gone_id,
            }
        )
        alias._check_alias_domain_id_mc()

    @users("admin")
    def test_duplicate_error_survives_a_deleted_owner(self):
        self.env["mail.alias"].create(
            {
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_model_id": self.container_model.id,
                "alias_name": "clashing.alias",
                "alias_parent_model_id": self.container_model.id,
                "alias_parent_thread_id": self.gone_id,
            }
        )
        with self.assertRaises(exceptions.UserError) as capture:
            self.env["mail.alias"].create(
                {
                    "alias_domain_id": self.mail_alias_domain.id,
                    "alias_model_id": self.container_model.id,
                    "alias_name": "clashing.alias",
                }
            )
        self.assertIn("clashing.alias", str(capture.exception))

    @users("admin")
    def test_bounce_clash_error_survives_a_deleted_owner(self):
        self.env["mail.alias"].create(
            {
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_model_id": self.container_model.id,
                "alias_name": "clashing.bounce",
                "alias_parent_model_id": self.container_model.id,
                "alias_parent_thread_id": self.gone_id,
            }
        )
        with self.assertRaises(exceptions.ValidationError) as capture:
            self.mail_alias_domain.write({"bounce_alias": "clashing.bounce"})
        self.assertIn("clashing.bounce", str(capture.exception))

    @users("admin")
    def test_bounce_clash_names_the_document_it_finds(self):
        cases = [
            ("owner", {"alias_parent_model_id": self.container_model.id}, "Owning Doc"),
            ("target", {}, "Target Doc"),
            ("none", {}, None),
        ]
        for kind, extra, doc_name in cases:
            with self.subTest(kind=kind):
                domain = self.env["mail.alias.domain"].create(
                    {"name": f"clash-{kind}.test"}
                )
                values = {
                    "alias_domain_id": domain.id,
                    "alias_model_id": self.container_model.id,
                    "alias_name": f"clash.{kind}",
                    **extra,
                }
                if doc_name:
                    document = self.env["mail.test.container"].create(
                        {"name": doc_name}
                    )
                    if kind == "owner":
                        values["alias_parent_thread_id"] = document.id
                    else:
                        values["alias_force_thread_id"] = document.id
                self.env["mail.alias"].create(values)

                with self.assertRaises(exceptions.ValidationError) as capture:
                    domain.write({"bounce_alias": f"clash.{kind}"})
                message = str(capture.exception)
                self.assertIn(f"clash.{kind}@clash-{kind}.test", message)
                if doc_name:
                    self.assertIn(doc_name, message)
                else:
                    self.assertIn("change it on the linked model", message)

    @users("admin")
    def test_only_stored_reads_are_the_hazard(self):
        gone = self.env["mail.test.container"].browse(self.gone_id)
        self.assertTrue(gone, "a browse of a missing id is still truthy")
        self.assertFalse(gone.message_partner_ids)
        self.assertFalse(
            gone._partner_get_or_create_from_emails_single(["x@y.com"], no_create=True)
        )
        with self.assertRaises(exceptions.MissingError):
            gone.name

    @users("admin")
    def test_alias_get_document_answers_empty_not_missing(self):
        alias = self.env["mail.alias"].create(
            {
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_force_thread_id": self.gone_id,
                "alias_model_id": self.container_model.id,
                "alias_name": "resolver.probe",
            }
        )
        self.assertFalse(alias._alias_get_document("target"))
        self.assertFalse(alias._alias_get_document("owner"))
        record = self.env["mail.test.container"].create({"name": "Real Container"})
        alias.alias_force_thread_id = record.id
        self.assertEqual(alias._alias_get_document("target"), record)


@tagged("mail_alias")
class TestMailAliasDefaultsValidation(TestMailAliasCommon):
    DEFAULTS_CASES = [
        ("mail.test.recipients", "customer_email", "kept@test.example.com", True),
        ("mail.test.gateway", "email_normalized", "gone@test.example.com", False),
        ("mail.test.container", "display_name", "Gone Name", False),
        ("mail.test.container", "alias_email", "gone2@test.example.com", False),
    ]

    @users("admin")
    def test_alias_defaults_verdict_matches_what_create_does(self):
        for model, fname, value, survives in self.DEFAULTS_CASES:
            with self.subTest(model=model, field=fname):
                record = self.env[model].create(
                    {"name": "defaults probe", fname: value}
                )
                record.flush_recordset()
                record.invalidate_recordset()
                self.assertEqual(
                    record[fname] == value,
                    survives,
                    f"fixture drifted: create() on {model}.{fname} no longer "
                    f"{'keeps' if survives else 'drops'} the value",
                )

                alias = self.env["mail.alias"].create(
                    {
                        "alias_domain_id": self.mail_alias_domain.id,
                        "alias_model_id": self.env["ir.model"]._get(model).id,
                        "alias_name": f"defaults.{fname.replace('_', '.')}",
                    }
                )
                defaults = repr({fname: value})
                if survives:
                    alias.write({"alias_defaults": defaults})
                    self.assertEqual(alias._prepare_alias_defaults(), {fname: value})
                else:
                    with self.assertRaises(exceptions.ValidationError):
                        alias.write({"alias_defaults": defaults})

    @users("admin")
    def test_alias_defaults_accept_a_writable_related(self):
        alias = self.env["mail.alias"].create(
            {
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_model_id": self.env["ir.model"]._get("mail.test.container").id,
                "alias_name": "defaults.related",
            }
        )
        alias.write({"alias_defaults": "{'alias_name': 'sub.alias'}"})
        self.assertEqual(alias._prepare_alias_defaults(), {"alias_name": "sub.alias"})

    @users("admin")
    def test_precompute_readonly_is_inside_the_refused_set(self):
        field = self.env["mail.activity"]._fields["res_model"]
        self.assertTrue(field.precompute and field.readonly and field.compute)
        record = self.env["mail.test.container"].create({"name": "precompute probe"})
        activity = self.env["mail.activity"].create(
            {
                "activity_type_id": self.env.ref("mail.mail_activity_data_todo").id,
                "res_id": record.id,
                "res_model": "forced.value",
                "res_model_id": self.env["ir.model"]._get_id("mail.test.container"),
            }
        )
        activity.flush_recordset()
        activity.invalidate_recordset()
        self.assertEqual(activity.res_model, "mail.test.container")

    @users("admin")
    def test_alias_name_length_is_deliberately_unbounded(self):
        MailAlias = self.env["mail.alias"]
        base = "customer-invoices-acme-international-manufacturing-and-distri"
        long_one, long_two = base + "bution-holdings-bv", base + "bution-holdings-nv"
        self.assertGreater(len(long_one), 64)
        self.assertNotEqual(
            MailAlias._normalize_alias_name(long_one),
            MailAlias._normalize_alias_name(long_two),
            "sanitizing must not truncate: these two differ only past character 64",
        )
        alias = MailAlias.create(
            {
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_model_id": self.env["ir.model"]._get("mail.test.container").id,
                "alias_name": long_one,
            }
        )
        self.assertEqual(alias.alias_name, long_one)


@tagged("mail_gateway", "mail_alias", "multi_company")
class TestMailAliasDomainConfigCache(TestMailAliasCommon):
    """`_get_config` is what the gateway matches against; pin its contract.

    Restores the five cases `e803ea6dd1f` wrote for the cache and `e4df7f5569b`
    dropped when it deleted the round-numbered hardening suites. Their absence was
    measured, not assumed: with all three `clear_cache("mail")` calls removed,
    `/mail,/test_mail` produced a failure set identical to the control -- the whole
    invalidation mechanism could be deleted and nothing noticed.
    """

    def _live_config(self):
        domains = self.env["mail.alias.domain"].sudo().search([])
        return (
            tuple(domains.ids),
            tuple(filter(None, domains.mapped("name"))),
            tuple(filter(None, domains.mapped("bounce_email"))),
            tuple(filter(None, domains.mapped("catchall_email"))),
            tuple(filter(None, domains.mapped("default_from_email"))),
        )

    @users("admin")
    def test_cached_config_matches_a_live_read(self):
        self.assertEqual(
            tuple(self.env["mail.alias.domain"]._get_config()), self._live_config()
        )

    @users("admin")
    def test_config_members_are_addressable_by_name(self):
        config = self.env["mail.alias.domain"]._get_config()
        Domain = self.env["mail.alias.domain"]
        self.assertEqual(config.names, Domain._get_alias_domain_names())
        self.assertEqual(config.bounce_emails, Domain._get_bounce_emails())
        self.assertEqual(config.catchall_emails, Domain._get_catchall_emails())
        self.assertEqual(config.ids[:1], tuple(Domain._get_default_domain().ids))

    @users("admin")
    def test_cache_is_invalidated_on_create(self):
        Domain = self.env["mail.alias.domain"]
        Domain._get_config()
        Domain.create(
            {
                "bounce_alias": "bounce.new",
                "catchall_alias": "catchall.new",
                "name": "created.example.com",
            }
        )
        self.assertIn("catchall.new@created.example.com", Domain._get_catchall_emails())
        self.assertEqual(tuple(Domain._get_config()), self._live_config())

    @users("admin")
    def test_cache_is_invalidated_on_write(self):
        Domain = self.env["mail.alias.domain"]
        domain = self.mail_alias_domain.with_env(self.env)
        Domain._get_config()
        domain.write({"catchall_alias": "catchall.renamed"})
        self.assertIn(f"catchall.renamed@{domain.name}", Domain._get_catchall_emails())
        self.assertEqual(tuple(Domain._get_config()), self._live_config())

    @users("admin")
    def test_cache_is_invalidated_on_unlink(self):
        Domain = self.env["mail.alias.domain"]
        doomed = Domain.create(
            {
                "bounce_alias": "bounce.doomed",
                "catchall_alias": "catchall.doomed",
                "name": "doomed.example.com",
            }
        )
        self.assertIn("bounce.doomed@doomed.example.com", Domain._get_bounce_emails())
        doomed.unlink()
        self.assertNotIn(
            "bounce.doomed@doomed.example.com", Domain._get_bounce_emails()
        )
        self.assertEqual(tuple(Domain._get_config()), self._live_config())

    @users("admin")
    def test_gateway_sees_a_freshly_renamed_catchall(self):
        Thread = self.env["mixin.mail.thread"]
        domain = self.mail_alias_domain.with_env(self.env)
        domain.write({"catchall_alias": "catchall.rerouted"})
        self.assertTrue(
            Thread._is_write_to_catchall(
                {"to_normalized": [f"catchall.rerouted@{domain.name}"]}
            )
        )
        self.assertFalse(
            Thread._is_write_to_catchall(
                {"to_normalized": [f"catchall.test@{domain.name}"]}
            ),
            "the pre-rename address must stop being the catchall",
        )

    @users("admin")
    def test_a_config_change_clears_the_mail_cache_only(self):
        clears = []
        registry_class = type(self.env.registry)
        clear_cache = registry_class.clear_cache

        def spy(registry, *cache_names):
            clears.append(cache_names)
            return clear_cache(registry, *cache_names)

        Domain = self.env["mail.alias.domain"]
        with patch.object(registry_class, "clear_cache", spy):
            created = Domain.create(
                {
                    "bounce_alias": "bounce.bucket",
                    "catchall_alias": "catchall.bucket",
                    "name": "bucket.example.com",
                }
            )
            created.write({"catchall_alias": "catchall.bucket.renamed"})
            created.unlink()
        self.assertTrue(clears)
        self.assertNotIn(
            "stable",
            {name for names in clears for name in names},
            "a stable clear would drop every worker's default, xmlid and "
            "template caches with the alias-domain config",
        )

    @users("admin")
    def test_a_domain_rename_reaches_the_alias_addresses(self):
        Alias = self.env["mail.alias"]
        alias = self.test_alias_mc.with_env(self.env)
        domain = alias.alias_domain_id
        self.assertIn(alias.alias_full_name, Alias._get_alias_addresses().full_names)
        domain.write({"name": "renamed-bucket.example.com"})
        self.assertIn(
            f"{alias.alias_name}@renamed-bucket.example.com",
            Alias._get_alias_addresses().full_names,
            "alias_full_name is recomputed without mail.alias.write: the domain's "
            "own invalidation must reach the alias address cache",
        )


@tagged("mail_gateway", "mail_alias", "multi_company")
class TestMailAliasDomainName(TestMailAliasCommon):
    """`name` is the field every composed address ends with."""

    @users("admin")
    def test_the_domain_name_is_normalised_like_every_other_address_part(self):
        domain = self.env["mail.alias.domain"].create(
            {
                "bounce_alias": "bounce",
                "catchall_alias": "catchall",
                "name": "  MiXeD.Example.CoM  ",
            }
        )
        self.assertEqual(domain.name, "mixed.example.com")
        self.assertEqual(domain.catchall_email, "catchall@mixed.example.com")
        domain.write({"name": "SECOND.Example.COM"})
        self.assertEqual(domain.name, "second.example.com")

    @users("admin")
    def test_a_normalised_name_is_what_the_gateway_matches(self):
        Domain = self.env["mail.alias.domain"]
        domain = Domain.create(
            {
                "bounce_alias": "bounce",
                "catchall_alias": "catchall",
                "name": "MiXeD.Example.CoM",
            }
        )
        self.assertTrue(
            self.env["mixin.mail.thread"]._is_write_to_catchall(
                {"to_normalized": ["catchall@mixed.example.com"]}
            )
        )
        self.assertEqual(
            Domain._get_alias_emails(["catchall@mixed.example.com"]),
            ["catchall@mixed.example.com"],
        )
        self.assertIn(domain.bounce_email, Domain._get_bounce_emails())

    @users("admin")
    def test_a_name_that_is_not_a_domain_still_says_so(self):
        for failing_name in ["outlook.fr, gmail.com", "", " ", "exa mple.com"]:
            with self.subTest(failing_name=failing_name):
                with self.assertRaises(exceptions.ValidationError):
                    self.env["mail.alias.domain"].create({"name": failing_name})

    @users("admin")
    def test_a_non_ascii_name_is_idna_encoded_rather_than_refused(self):
        domain = self.env["mail.alias.domain"].create(
            {
                "bounce_alias": "bounce",
                "catchall_alias": "catchall",
                "name": "почта.рф",
            }
        )
        self.assertEqual(domain.name, "xn--80a1acny.xn--p1ai")
        self.assertTrue(domain.catchall_email.isascii())


@tagged("mail_gateway", "mail_alias", "multi_company")
class TestMailAliasDomainReservedAddresses(TestMailAliasCommon):
    """Bounce and catchall are one address space, not two."""

    @users("admin")
    def test_one_domain_cannot_use_one_local_part_for_both_roles(self):
        with self.assertRaises(exceptions.ValidationError):
            self.env["mail.alias.domain"].create(
                {
                    "bounce_alias": "shared",
                    "catchall_alias": "shared",
                    "name": "same.example.com",
                }
            )

    @users("admin")
    def test_a_catchall_cannot_be_a_sibling_domains_bounce(self):
        Domain = self.env["mail.alias.domain"]
        Domain.create(
            {"bounce_alias": "aa", "catchall_alias": "bb", "name": "cross.example.com"}
        )
        with self.assertRaises(exceptions.ValidationError):
            Domain.create(
                {
                    "bounce_alias": "bb",
                    "catchall_alias": "cc",
                    "name": "cross.example.com",
                }
            )

    @users("admin")
    def test_distinct_addresses_on_the_same_name_are_still_allowed(self):
        Domain = self.env["mail.alias.domain"]
        Domain.create(
            {"bounce_alias": "aa", "catchall_alias": "bb", "name": "ok.example.com"}
        )
        second = Domain.create(
            {"bounce_alias": "cc", "catchall_alias": "dd", "name": "ok.example.com"}
        )
        self.assertEqual(second.bounce_email, "cc@ok.example.com")


@tagged("mail_gateway", "mail_alias", "multi_company")
class TestMailAliasDomainPersonalServers(TestMailAliasCommon):
    """A personal mail server may veto a `default_from`, but only its own."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.personal_user = cls.env["res.users"].create(
            {
                "email": "personal.owner@test.example.com",
                "login": "personal_owner",
                "name": "Personal Owner",
            }
        )
        cls.personal_server = cls.env["ir.mail_server"].create(
            {
                "from_filter": "personal.owner@test.example.com",
                "name": "Personal",
                "owner_user_id": cls.personal_user.id,
                "smtp_host": "localhost",
            }
        )

    @users("admin")
    def test_a_matching_default_from_is_still_refused(self):
        with self.assertRaises(exceptions.ValidationError):
            self.env["mail.alias.domain"].create(
                {
                    "default_from": "personal.owner@test.example.com",
                    "name": "veto.example.com",
                }
            )

    @users("admin")
    def test_an_unrestricted_personal_server_vetoes_nothing(self):
        self.personal_server.sudo().from_filter = False
        Domain = self.env["mail.alias.domain"]
        without = Domain.create(
            {"default_from": False, "name": "nodefault.example.com"}
        )
        self.assertFalse(without.default_from_email)
        with_one = Domain.create(
            {"default_from": "notifications", "name": "withdefault.example.com"}
        )
        self.assertEqual(
            with_one.default_from_email, "notifications@withdefault.example.com"
        )

    @users("admin")
    def test_an_unrelated_write_does_not_consult_mail_servers(self):
        domain = self.mail_alias_domain.with_env(self.env)
        self.personal_server.sudo().from_filter = False
        domain.write({"sequence": 42})
        self.assertEqual(domain.sequence, 42)


@tagged("mail_gateway", "mail_alias", "multi_company")
class TestMailAliasDomainLifecycle(TestMailAliasCommon):
    """Creating the first domain, and deleting one that is in use."""

    @users("admin")
    def test_the_first_batch_hands_companies_the_sequence_first_domain(self):
        Domain = self.env["mail.alias.domain"]
        self.env["res.company"].with_context(active_test=False).search(
            []
        ).alias_domain_id = False
        self.env["mail.alias"].sudo().search([]).alias_domain_id = False
        Domain.search([]).unlink()

        Domain.create(
            [
                {
                    "bounce_alias": "b1",
                    "catchall_alias": "c1",
                    "name": "second.example.com",
                    "sequence": 99,
                },
                {
                    "bounce_alias": "b2",
                    "catchall_alias": "c2",
                    "name": "first.example.com",
                    "sequence": 1,
                },
            ]
        )
        self.assertEqual(Domain._get_default_domain().name, "first.example.com")
        self.assertEqual(
            self.env.company.alias_domain_id,
            Domain._get_default_domain(),
            "the bootstrapped company must agree with every company created later",
        )

    @users("admin")
    def test_deleting_a_domain_a_company_uses_is_allowed_but_reported(self):
        domain = self.env["mail.alias.domain"].create(
            {
                "bounce_alias": "bounce",
                "catchall_alias": "catchall",
                "name": "inuse.example.com",
            }
        )
        self.company_no_alias.sudo().alias_domain_id = domain.id
        with self.assertLogs(
            "odoo.addons.mail.models.mail_alias_domain", level="WARNING"
        ) as capture:
            domain.unlink()
        self.assertFalse(domain.exists())
        self.assertIn("No Alias Company", capture.output[0])

    @users("admin")
    def test_a_domain_nothing_points_at_is_still_deletable(self):
        domain = self.env["mail.alias.domain"].create(
            {
                "bounce_alias": "bounce",
                "catchall_alias": "catchall",
                "name": "unused.example.com",
            }
        )
        domain.unlink()
        self.assertFalse(domain.exists())


@tagged("mail_gateway", "mail_alias", "multi_company")
class TestMailAliasDomainFindAliases(TestMailAliasCommon):
    """`_get_alias_emails` answers "is this address ours", not "can we route it"."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.local_alias = cls.env["mail.alias"].create(
            {
                "alias_domain_id": cls.mail_alias_domain.id,
                "alias_incoming_local": True,
                "alias_model_id": cls.env["ir.model"]._get("mail.test.container").id,
                "alias_name": "helpdesk",
            }
        )

    @users("admin")
    def test_an_unset_parameter_claims_the_local_part_on_every_domain(self):
        Domain = self.env["mail.alias.domain"]
        ours = f"helpdesk@{self.mail_alias_domain.name}"
        self.assertEqual(
            Domain._get_alias_emails([ours, "helpdesk@gmail.com"]),
            [ours, "helpdesk@gmail.com"],
        )

    @users("admin")
    def test_the_allowed_domains_parameter_narrows_rather_than_widens(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "mail.catchall.domain.allowed", "partner.example.com"
        )
        ours = f"helpdesk@{self.mail_alias_domain.name}"
        self.assertEqual(
            self.env["mail.alias.domain"]._get_alias_emails(
                ["helpdesk@partner.example.com", ours, "helpdesk@gmail.com"]
            ),
            ["helpdesk@partner.example.com", ours],
        )

    @users("admin")
    def test_repeated_inputs_answer_once(self):
        catchall = self.mail_alias_domain.catchall_email
        self.assertEqual(
            self.env["mail.alias.domain"]._get_alias_emails([catchall] * 3), [catchall]
        )

    @users("admin")
    def test_a_warm_lookup_runs_no_query(self):
        Domain = self.env["mail.alias.domain"]
        ours = f"helpdesk@{self.mail_alias_domain.name}"
        Domain._get_alias_emails([ours])
        with self.assertQueryCount(0):
            self.assertEqual(
                Domain._get_alias_emails([ours, "nobody@gmail.com"]), [ours]
            )

    @users("admin")
    def test_the_snapshot_follows_alias_and_domain_changes(self):
        Domain = self.env["mail.alias.domain"]
        domain = self.mail_alias_domain.with_env(self.env)
        name = domain.name
        self.assertEqual(Domain._get_alias_emails([f"sales@{name}"]), [])
        alias = self.env["mail.alias"].create(
            {
                "alias_domain_id": domain.id,
                "alias_model_id": self.env["ir.model"]._get("mail.test.container").id,
                "alias_name": "sales",
            }
        )
        self.assertEqual(
            Domain._get_alias_emails([f"sales@{name}", "sales@gmail.com"]),
            [f"sales@{name}"],
        )
        alias.alias_name = "orders"
        self.assertEqual(
            Domain._get_alias_emails([f"sales@{name}", f"orders@{name}"]),
            [f"orders@{name}"],
        )
        domain.name = "renamed.example.com"
        self.assertEqual(
            Domain._get_alias_emails([f"orders@{name}", "orders@renamed.example.com"]),
            ["orders@renamed.example.com"],
        )
        alias.alias_incoming_local = True
        self.assertEqual(
            Domain._get_alias_emails(["orders@gmail.com"]), ["orders@gmail.com"]
        )
        alias.unlink()
        self.assertEqual(
            Domain._get_alias_emails(
                ["orders@renamed.example.com", "orders@gmail.com"]
            ),
            [],
        )

    @users("admin")
    def test_the_reply_to_of_a_record_follows_its_alias(self):
        records = self.env["mail.test.simple"].create(
            [{"name": "first"}, {"name": "second"}]
        )
        first, second = records
        alias = self.env["mail.alias"].create(
            {
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_model_id": self.env["ir.model"]._get("mail.test.container").id,
                "alias_name": "support",
                "alias_parent_model_id": self.env["ir.model"]
                ._get("mail.test.simple")
                .id,
                "alias_parent_thread_id": first.id,
            }
        )
        support = f"support@{self.mail_alias_domain.name}"
        catchall = self.mail_alias_domain.catchall_email
        self.assertEqual(
            records._notify_get_reply_to_addresses(),
            {first.id: support, second.id: catchall},
        )
        alias.alias_parent_thread_id = second.id
        self.assertEqual(
            records._notify_get_reply_to_addresses(),
            {first.id: catchall, second.id: support},
        )


@tagged("mail_gateway", "mail_alias")
class TestMailAliasDomainAllowedParameter(TestMailAliasCommon):
    """`mail.catchall.domain.allowed` is a list of domain names."""

    @users("admin")
    def test_entries_are_held_to_the_domain_rule(self):
        Domain = self.env["mail.alias.domain"]
        for failing in ["foo bar.com", "ex..ample.com", ".example.com"]:
            with self.subTest(failing=failing):
                with self.assertRaises(exceptions.ValidationError):
                    Domain._normalize_allowed_domains(failing)

    @users("admin")
    def test_entries_are_normalised_and_deduplicated(self):
        Domain = self.env["mail.alias.domain"]
        self.assertEqual(
            Domain._normalize_allowed_domains(" Example.COM , example.com ,почта.рф"),
            "example.com,xn--80a1acny.xn--p1ai",
        )


@tagged("mail_gateway", "mail_alias", "mail_init")
class TestMailAliasDomainIcpMigration(TestMailAliasCommon):
    """`_migrate_icp_to_domain` is `mail`'s post-install hook."""

    @users("admin")
    def test_an_unusable_icp_is_skipped_not_raised(self):
        Domain = self.env["mail.alias.domain"]
        Icp = self.env["ir.config_parameter"].sudo()
        for junk in ["my domain.com", "outlook.fr, gmail.com", "почта .рф"]:
            with self.subTest(junk=junk):
                Icp.set_param("mail.catchall.domain", junk)
                before = Domain.search([])
                with self.assertLogs(
                    "odoo.addons.mail.models.mail_alias_domain", level="WARNING"
                ):
                    self.assertFalse(Domain._migrate_icp_to_domain())
                self.assertEqual(Domain.search([]), before)

    @users("admin")
    def test_a_usable_icp_is_normalised_on_the_way_in(self):
        Domain = self.env["mail.alias.domain"]
        self.env["ir.config_parameter"].sudo().set_param(
            "mail.catchall.domain", "Migrated.Example.COM"
        )
        migrated = Domain._migrate_icp_to_domain()
        self.assertEqual(migrated.name, "migrated.example.com")
        self.assertEqual(
            Domain._migrate_icp_to_domain(), migrated, "must not migrate twice"
        )


@tagged("mail_alias")
class TestMailAliasNameAuthority(TestMailAliasCommon):
    """One predicate decides what an `alias_name` may be, so two cannot drift."""

    @users("admin")
    def test_the_constraint_is_the_sanitizer_s_own_fixpoint(self):
        MailAlias = self.env["mail.alias"]
        self.assertTrue(dot_atom_text.match("MixedCase"), "the old rule accepted it")
        self.assertFalse(MailAlias._alias_name_is_valid("MixedCase"))
        self.assertFalse(MailAlias._alias_name_is_valid("a..b"))
        self.assertFalse(MailAlias._alias_name_is_valid("has space"))
        self.assertFalse(MailAlias._alias_name_is_valid(""))
        for name in ("jobs", "a.b", "a-b_c", "x" * 70):
            self.assertTrue(MailAlias._alias_name_is_valid(name), name)

        alias = MailAlias.create(
            {
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_model_id": self.env["ir.model"]._get("mail.test.container").id,
                "alias_name": "Mixed Case",
            }
        )
        self.assertEqual(alias.alias_name, "mixed-case")
        self.env.cr.execute(
            SQL(
                "UPDATE mail_alias SET alias_name = %s WHERE id = %s",
                "MixedCase",
                alias.id,
            )
        )
        alias.invalidate_recordset()
        with self.assertRaises(exceptions.ValidationError):
            alias._check_alias_name_is_normalized()

    @users("admin")
    def test_domain_local_parts_answer_to_the_same_predicate(self):
        domain = self.env["mail.alias.domain"].create(
            {"name": "predicate.test.example"}
        )
        domain.write({"bounce_alias": "Bounce", "catchall_alias": "a..b"})
        self.assertEqual(domain.bounce_alias, "bounce", "sanitized, not refused")
        self.assertEqual(domain.catchall_alias, "a.b")

        domain.write({"default_from": "Notifications@Predicate.Test.Example"})
        self.assertEqual(domain.default_from, "notifications@predicate.test.example")

        self.env.cr.execute(
            SQL(
                "UPDATE mail_alias_domain SET bounce_alias = %s WHERE id = %s",
                "Bounce",
                domain.id,
            )
        )
        domain.invalidate_recordset()
        with self.assertRaises(exceptions.ValidationError):
            domain._check_local_parts()


@tagged("mail_alias")
class TestMailAliasModelTarget(TestMailAliasCommon):
    """An alias may only name a model that can do something with the mail."""

    def _make(self, model_name, suffix=""):
        return self.env["mail.alias"].create(
            {
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_model_id": self.env["ir.model"]._get(model_name).id,
                "alias_name": f"target.probe{suffix}",
            }
        )

    @users("admin")
    def test_a_model_that_cannot_receive_is_refused_at_configuration(self):
        for model_name in ("res.currency", "mixin.mail.thread", "base"):
            with (
                self.subTest(model=model_name),
                self.assertRaises(exceptions.ValidationError),
            ):
                self._make(model_name, model_name)

    @users("admin")
    def test_a_model_that_can_receive_is_accepted(self):
        alias = self._make("mail.test.container")
        self.assertEqual(alias.alias_model_id.model, "mail.test.container")

    @users("admin")
    def test_the_gate_is_message_new_and_not_chatter(self):
        Alias = self.env["mail.alias"]
        self.assertTrue(
            Alias._alias_model_accepts_mail(self.env["mail.test.container"])
        )
        for model_name in ("res.currency", "mixin.mail.thread", "base"):
            with self.subTest(model=model_name):
                self.assertFalse(
                    Alias._alias_model_accepts_mail(self.env[model_name]), model_name
                )
        self.assertFalse(hasattr(self.env["res.currency"], "message_new"))
        self.assertTrue(hasattr(self.env["mail.test.container"], "message_new"))


@tagged("mail_alias")
class TestMailAliasStatusInputs(TestMailAliasCommon):
    """`alias_status` is a verdict; anything that changes its inputs drops it."""

    @users("admin")
    def test_the_owner_pair_repairs_the_fault_and_clears_the_verdict(self):
        model_id = self.env["ir.model"]._get("mail.test.container").id
        record = self.env["mail.test.container"].create({"name": "owner doc"})
        alias = self.env["mail.alias"].create(
            {
                "alias_contact": "followers",
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_model_id": model_id,
                "alias_name": "owner.repairs",
            }
        )
        self.assertIsNone(alias._alias_get_document("owner"))
        self.assertEqual(
            self.env["mail.test.container"]
            ._alias_resolve_error(None, {"author_id": False}, alias)
            .code,
            "config_follower_no_record",
            "no record to read followers from -- the fault the badge reports",
        )
        alias.alias_status = "invalid"
        alias.flush_recordset()
        alias.write(
            {"alias_parent_model_id": model_id, "alias_parent_thread_id": record.id}
        )
        self.assertEqual(alias.alias_status, "not_tested")
        self.assertNotEqual(
            record._alias_resolve_error(None, {"author_id": False}, alias).code,
            "config_follower_no_record",
            "and the fault really is gone",
        )

    @users("admin")
    def test_a_new_field_resets_by_default(self):
        alias = self.env["mail.alias"].create(
            {
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_model_id": self.env["ir.model"]._get("mail.test.container").id,
                "alias_name": "neutral.set",
            }
        )
        neutral = self.env["mail.alias"].ALIAS_STATUS_NEUTRAL
        self.assertEqual(
            neutral,
            frozenset(
                {
                    "alias_status",
                    "alias_bounced_content",
                    "alias_name",
                    "alias_domain_id",
                }
            ),
        )
        for fname, value in [
            ("alias_incoming_local", True),
            ("alias_parent_thread_id", 1),
            ("alias_contact", "partners"),
        ]:
            with self.subTest(field=fname):
                alias.alias_status = "valid"
                alias.flush_recordset()
                alias.write({fname: value})
                self.assertEqual(alias.alias_status, "not_tested", fname)
        for fname, value in [
            ("alias_name", "neutral.renamed"),
            ("alias_bounced_content", "<p>hi</p>"),
        ]:
            with self.subTest(field=fname):
                alias.alias_status = "valid"
                alias.flush_recordset()
                alias.write({fname: value})
                self.assertEqual(alias.alias_status, "valid", fname)


@tagged("mail_alias")
class TestMailAliasStatusRights(TestMailAliasCommon):
    """The gateway records a verdict; it does not need write access to do it."""

    @users("admin")
    def test_marking_an_alias_does_not_need_group_system(self):
        alias = self.env["mail.alias"].create(
            {
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_model_id": self.env["ir.model"]._get("mail.test.container").id,
                "alias_name": "rights.probe",
            }
        )
        alias.flush_recordset()
        as_employee = alias.with_user(self.user_employee)
        self.assertFalse(
            self.user_employee.has_group("base.group_system"), "premise of the test"
        )
        with self.assertRaises(exceptions.AccessError):
            as_employee.write({"alias_status": "valid"})

        as_employee._alias_mark_valid()
        self.assertEqual(alias.alias_status, "valid")
        as_employee._alias_mark_invalid()
        self.assertEqual(alias.alias_status, "invalid")


@tagged("mail_alias")
class TestMailAliasAddressAvailability(TestMailAliasCommon):
    """One question -- is this set of addresses free -- over one complete set."""

    def _make(self, name):
        return self.env["mail.alias"].create(
            {
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_model_id": self.env["ir.model"]._get("mail.test.container").id,
                "alias_name": name,
            }
        )

    @users("admin")
    def test_a_sibling_in_the_same_write_still_holds_its_address(self):
        held, renaming = self._make("avail.held"), self._make("avail.renaming")
        self.env.flush_all()
        with self.assertRaises(exceptions.UserError) as capture:
            (held | renaming).write(
                {"alias_name": "avail.held", "alias_contact": "partners"}
            )
        self.assertIn("avail.held", str(capture.exception))

    @users("admin")
    def test_a_collision_outside_the_recordset_reads_the_same(self):
        self._make("avail.outside")
        moving = self._make("avail.moving")
        self.env.flush_all()
        with self.assertRaises(exceptions.UserError):
            moving.write({"alias_name": "avail.outside"})

    @users("admin")
    def test_an_untouched_recordset_is_not_re_checked(self):
        alias = self._make("avail.quiet")
        self.env.flush_all()
        alias.write({"alias_name": "avail.quiet", "alias_contact": "partners"})
        self.assertEqual(alias.alias_name, "avail.quiet")

    @users("admin")
    def test_the_refusal_names_the_alias_it_found_not_the_one_being_written(self):
        taken = self._make("avail.taken")
        writing = self._make("avail.writing")
        self.env.flush_all()
        with self.assertRaises(exceptions.UserError) as capture:
            writing.write({"alias_name": "avail.taken"})
        message = str(capture.exception)
        self.assertIn(str(taken.id), message, "the alias that holds the address")
        self.assertNotIn(
            f"({writing.id})",
            message,
            "the alias being written is not what the reader has to go look at",
        )

    @users("admin")
    def test_create_does_not_rewrite_the_caller_s_dict(self):
        vals = {
            "alias_model_id": self.env["ir.model"]._get("mail.test.container").id,
            "alias_name": "Caller Dict",
        }
        untouched = dict(vals)
        self.env["mail.alias"].create(vals)
        self.assertEqual(vals, untouched)

    @users("admin")
    def test_write_does_not_rewrite_the_caller_s_dict(self):
        alias = self._make("caller.write")
        vals = {"alias_contact": "partners"}
        untouched = dict(vals)
        alias.write(vals)
        self.assertEqual(vals, untouched, "alias_status was injected into it")
        self.assertEqual(alias.alias_status, "not_tested")

    @users("admin")
    def test_a_batch_resolves_its_domains_in_one_query(self):
        self.env["mail.alias.domain"].create({"name": "batched.test.example"})
        model_id = self.env["ir.model"]._get("mail.test.container").id
        self.env.flush_all()
        self.env.invalidate_all()

        def make(count, offset):
            return [
                {
                    "alias_model_id": model_id,
                    "alias_name": f"batched{offset + index}@batched.test.example",
                }
                for index in range(count)
            ]

        before = self.env.cr.sql_statement_count
        self.env["mail.alias"].create(make(2, 0))
        self.env.flush_all()
        small = self.env.cr.sql_statement_count - before

        self.env.invalidate_all()
        before = self.env.cr.sql_statement_count
        self.env["mail.alias"].create(make(20, 100))
        self.env.flush_all()
        large = self.env.cr.sql_statement_count - before

        self.assertLessEqual(
            large - small,
            2,
            f"resolving the domain must not scale with the batch ({small} -> {large})",
        )


@tagged("mail_alias")
class TestMailAliasIncomingLocalReservations(TestMailAliasCommon):
    """`alias_incoming_local` matches a local part on every domain, so it must
    respect every domain's reservations."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.domain_a = cls.env["mail.alias.domain"].create(
            {"name": "a.local.test", "bounce_alias": "bnc-a", "catchall_alias": "rep-a"}
        )
        cls.domain_b = cls.env["mail.alias.domain"].create(
            {"name": "b.local.test", "bounce_alias": "bnc-b", "catchall_alias": "rep-b"}
        )

    def _vals(self, **kw):
        return dict(
            {
                "alias_domain_id": self.domain_a.id,
                "alias_model_id": self.env["ir.model"]._get("mail.test.container").id,
                "alias_name": "rep-b",
            },
            **kw,
        )

    @users("admin")
    def test_a_local_alias_may_not_shadow_another_domain_s_catchall(self):
        with self.assertRaises(exceptions.ValidationError):
            self.env["mail.alias"].create(self._vals(alias_incoming_local=True))
        with self.assertRaises(exceptions.ValidationError):
            self.env["mail.alias"].create(
                self._vals(alias_name="bnc-b", alias_incoming_local=True)
            )

    @users("admin")
    def test_a_scoped_alias_is_unaffected(self):
        alias = self.env["mail.alias"].create(self._vals())
        self.assertEqual(alias.alias_full_name, "rep-b@a.local.test")
        with self.assertRaises(exceptions.ValidationError):
            self.env["mail.alias"].create(self._vals(alias_name="rep-a"))

    @users("admin")
    def test_setting_the_flag_later_is_checked_too(self):
        alias = self.env["mail.alias"].create(self._vals())
        with self.assertRaises(exceptions.ValidationError):
            alias.write({"alias_incoming_local": True})

    @users("admin")
    def test_a_domain_may_not_reserve_a_local_alias_s_name_either(self):
        self.env["mail.alias"].create(
            self._vals(alias_name="freeform", alias_incoming_local=True)
        )
        with self.assertRaises(exceptions.ValidationError):
            self.domain_b.write({"catchall_alias": "freeform"})
        with self.assertRaises(exceptions.ValidationError):
            self.env["mail.alias.domain"].create(
                {"name": "c.local.test", "bounce_alias": "freeform"}
            )


@tagged("mail_alias", "multi_company")
class TestMailAliasBounceCompany(TestMailAliasCommon):
    """A bounce goes to an outside sender; it must name the company they wrote to."""

    @users("admin")
    def test_the_bounce_names_the_alias_s_company_not_the_gateway_s(self):
        company = self.env["res.company"].create({"name": "Bounce Company"})
        company.partner_id.email = "hello@bounce-company.test.example"
        domain = self.env["mail.alias.domain"].create({"name": "bc.test.example"})
        company.alias_domain_id = domain.id
        record = self.env["mail.test.gateway.company"].create(
            {"name": "bc record", "company_id": company.id}
        )
        alias = self.env["mail.alias"].create(
            {
                "alias_contact": "partners",
                "alias_domain_id": domain.id,
                "alias_model_id": self.env["ir.model"]
                ._get("mail.test.gateway.company")
                .id,
                "alias_name": "bc.alias",
                "alias_parent_model_id": self.env["ir.model"]
                ._get("mail.test.gateway.company")
                .id,
                "alias_parent_thread_id": record.id,
            }
        )
        self.assertNotEqual(self.env.company, company, "premise of the test")
        self.assertEqual(alias._alias_get_company(), company)

        message_dict = {
            "author_id": False,
            "body": "<p>hello</p>",
            "email_from": "outside@test.example.com",
        }
        for body, label in [
            (alias._get_alias_bounced_body(message_dict), "security bounce"),
            (alias._get_alias_invalid_body(message_dict), "config bounce"),
        ]:
            with self.subTest(body=label):
                self.assertNotIn(self.env.company.name, body)

    @users("admin")
    def test_the_domain_answers_when_no_document_does(self):
        company = self.env["res.company"].create({"name": "Domain Only Company"})
        domain = self.env["mail.alias.domain"].create({"name": "doc.test.example"})
        company.alias_domain_id = domain.id
        alias = self.env["mail.alias"].create(
            {
                "alias_domain_id": domain.id,
                "alias_model_id": self.env["ir.model"]._get("mail.test.container").id,
                "alias_name": "domain.only",
            }
        )
        self.assertIsNone(alias._alias_get_document("owner"))
        self.assertIsNone(alias._alias_get_document("target"))
        self.assertEqual(alias._alias_get_company(), company)


@tagged("mail_alias")
class TestMailAliasMixinDomainPrecedence(TestMailAliasCommon):
    """A domain typed into the address means the same thing on every path in."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.typed_domain = cls.env["mail.alias.domain"].create(
            {"name": "typed.test.example"}
        )

    @users("admin")
    def test_the_typed_domain_wins_on_every_path(self):
        model_id = self.env["ir.model"]._get("mail.test.container").id
        expected = self.typed_domain

        record = self.env["mail.test.container"].create(
            {
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_name": "cell.a@typed.test.example",
                "name": "cell A",
            }
        )
        self.assertEqual(
            record.alias_id.alias_domain_id, expected, "mixin create, explicit domain"
        )

        record = self.env["mail.test.container"].create(
            {"alias_name": "cell.b@typed.test.example", "name": "cell B"}
        )
        self.assertEqual(
            record.alias_id.alias_domain_id, expected, "mixin create, no domain"
        )

        record = self.env["mail.test.container"].create(
            {"alias_name": "cellc", "name": "cell C"}
        )
        record.write({"alias_name": "cell.c@typed.test.example"})
        self.assertEqual(record.alias_id.alias_domain_id, expected, "mixin write")

        record = self.env["mail.test.container"].create(
            {"alias_name": "celld", "name": "cell D"}
        )
        record.write(
            {
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_name": "cell.d@typed.test.example",
            }
        )
        self.assertEqual(
            record.alias_id.alias_domain_id, expected, "mixin write, explicit domain"
        )

        alias = self.env["mail.alias"].create(
            {
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_model_id": model_id,
                "alias_name": "cell.e@typed.test.example",
            }
        )
        self.assertEqual(
            alias.alias_domain_id, expected, "mail.alias create, explicit domain"
        )

    @users("admin")
    def test_a_caller_s_values_still_win_over_the_recomputed_ones(self):
        narrow = self.env["ir.model"]._get_id("mail.test.ticket.partner")
        record = self.env["mail.test.container.mc"].create(
            {
                "alias_defaults": {"state": "new"},
                "alias_model_id": narrow,
                "alias_name": "still.wins",
                "name": "Still Wins",
            }
        )
        self.assertEqual(record.alias_id.alias_model_id.id, narrow)
        self.assertEqual(
            record.alias_id._prepare_alias_defaults(),
            {"container_id": record.id, "state": "new"},
        )


@tagged("mail_alias")
class TestMailAliasDefaultsShape(TestMailAliasCommon):
    """`_prepare_alias_defaults` owns the whole shape, not half of it."""

    def _make(self, defaults):
        return self.env["mail.alias"].create(
            {
                "alias_defaults": defaults,
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_model_id": self.env["ir.model"]._get("mail.test.container").id,
                "alias_name": "shape.probe",
            }
        )

    @users("admin")
    def test_a_key_that_is_not_a_field_name_is_refused_like_every_other_fault(self):
        for defaults in ("{1: 2}", "{None: 'x'}", "{(1, 2): 'x'}"):
            with (
                self.subTest(defaults=defaults),
                self.assertRaises(exceptions.ValidationError),
            ):
                self._make(defaults)

    @users("admin")
    def test_the_shapes_that_were_already_refused_still_are(self):
        for defaults in (
            "[1, 2]",
            "not python",
            "{'nope': 1}",
            "{'display_name': 'x'}",
        ):
            with (
                self.subTest(defaults=defaults),
                self.assertRaises(exceptions.ValidationError),
            ):
                self._make(defaults)

    @users("admin")
    def test_a_valid_mapping_is_still_accepted(self):
        alias = self._make("{'name': 'ok'}")
        self.assertEqual(alias._prepare_alias_defaults(), {"name": "ok"})


@tagged("mail_alias")
class TestAliasDomainNameRule(TestMailAliasCommon):
    """A domain name is LDH, not the local part's alphabet."""

    @users("admin")
    def test_a_bare_hyphen_is_not_a_domain_name(self):
        MailAlias = self.env["mail.alias"]
        self.assertTrue(dot_atom_text.match("-"), "the old rule accepted it")
        self.assertFalse(MailAlias._normalize_alias_domain_name("-"))
        with self.assertRaises(exceptions.ValidationError):
            self.env["mail.alias.domain"].create({"name": "-"})

    @users("admin")
    def test_the_shapes_a_resolver_refuses(self):
        MailAlias = self.env["mail.alias"]
        for name in (
            "-",
            "-a.com",
            "a-.com",
            "a..com",
            "~!#$.com",
            "_dmarc.example.com",
            "a" * 64 + ".com",
            ("a" * 63 + ".") * 4 + "com",
        ):
            with self.subTest(name=name):
                self.assertFalse(
                    MailAlias._normalize_alias_domain_name(name), repr(name)
                )

    @users("admin")
    def test_the_shapes_a_resolver_answers(self):
        MailAlias = self.env["mail.alias"]
        for name in (
            "example.com",
            "sub.a-b.example.co.uk",
            "localhost",
            "a" * 63 + ".com",
            "xn--provader-y2a.xn--cm-fka",
        ):
            with self.subTest(name=name):
                self.assertEqual(MailAlias._normalize_alias_domain_name(name), name)

    @users("admin")
    def test_the_rule_reaches_every_consumer_of_the_sanitizer(self):
        with self.assertRaises(exceptions.ValidationError):
            self.env["mail.alias.domain"]._normalize_allowed_domains("example.com,-")
        alias = self.env["mail.alias"].create(
            {
                "alias_domain_id": self.mail_alias_domain.id,
                "alias_model_id": self.env["ir.model"]._get("mail.test.container").id,
                "alias_name": "jobs@-",
            }
        )
        self.assertEqual(alias.alias_name, "jobs")
        self.assertEqual(
            alias.alias_domain_id,
            self.mail_alias_domain,
            "an unusable domain half is dropped, not resolved to nothing",
        )

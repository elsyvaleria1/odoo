from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestCompanyConfigDelegation(TransactionCase):
    def test_a_root_write_reaches_every_branch(self):
        Config = self.env["report.config"]
        first, second = self.env["report.paperformat"].search([], limit=2)
        with patch.object(
            type(Config),
            "_get_field_names_delegated_to_root",
            lambda self: ["paperformat_id"],
        ):
            Company = self.env["res.company"]
            root = Company.create({"name": "Delegating Root"})
            Config._for(root).paperformat_id = first
            branch = Company.create({"name": "Delegating Branch", "parent_id": root.id})
            leaf = Company.create({"name": "Delegating Leaf", "parent_id": branch.id})
            configs = Config._for_each(branch + leaf)
            self.assertEqual(configs.paperformat_id, first)

            Config._for(root).write({"paperformat_id": second.id})

            self.assertEqual(configs.paperformat_id, second)
            configs._check_delegated_fields_match_root()

    def test_a_root_write_reaches_an_archived_branch(self):
        Config = self.env["report.config"]
        first, second = self.env["report.paperformat"].search([], limit=2)
        with patch.object(
            type(Config),
            "_get_field_names_delegated_to_root",
            lambda self: ["paperformat_id"],
        ):
            Company = self.env["res.company"]
            root = Company.create({"name": "Dormant Delegating Root"})
            Config._for(root).paperformat_id = first
            branch = Company.create(
                {"name": "Dormant Delegating Branch", "parent_id": root.id}
            )
            branch.action_archive()

            Config._for(root).write({"paperformat_id": second.id})

            self.assertEqual(Config._for(branch).paperformat_id, second)

    def test_a_create_naming_no_company_writes_the_current_company_config(self):
        Config = self.env["report.config"]
        existing = Config._for(self.env.company)

        created = Config.create({"report_footer": "<p>written, not created</p>"})

        self.assertEqual(created, existing)
        self.assertIn("written, not created", str(existing.report_footer))

    def test_a_branch_config_created_without_a_company_inherits_from_its_root(self):
        Config = self.env["report.config"]
        _first, second = self.env["report.paperformat"].search([], limit=2)
        with patch.object(
            type(Config),
            "_get_field_names_delegated_to_root",
            lambda self: ["paperformat_id"],
        ):
            Company = self.env["res.company"]
            root = Company.create({"name": "Default Root"})
            Config._for(root).paperformat_id = second
            branch = Company.create({"name": "Default Branch", "parent_id": root.id})
            Config._for(branch).unlink()

            created = Config.with_company(branch).create({})

            self.assertEqual(created.company_id, branch)
            self.assertEqual(created.paperformat_id, second)

    def test_a_create_returns_each_config_at_the_position_of_its_values(self):
        Config = self.env["report.config"]
        company = self.env["res.company"].create({"name": "Config Newcomer"})
        Config._for(company).unlink()

        configs = Config.create(
            [{"company_id": company.id}, {"company_id": self.env.company.id}]
        )

        self.assertEqual(
            [config.company_id for config in configs], [company, self.env.company]
        )

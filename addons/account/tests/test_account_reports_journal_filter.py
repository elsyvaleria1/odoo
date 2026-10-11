from odoo import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestAccountReportsJournalFilter(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.vanilla_company1 = cls.env["res.company"].create({"name": "Vanilla1"})
        cls.vanilla_company2 = cls.env["res.company"].create({"name": "Vanilla2"})

        cls.env.user.write(
            {
                "company_ids": [
                    Command.set((cls.vanilla_company1 + cls.vanilla_company2).ids)
                ],
                "company_id": cls.vanilla_company1.id,
            }
        )

        cls.report = cls.env.ref("account.balance_sheet")

    def _assert_filter_journal(self, options, display_name, expected_values_list):
        journal_options = options["journals"]
        self.assertEqual(options["name_journal_group"], display_name)
        self.assertEqual(len(journal_options), len(expected_values_list))
        for journal_option, expected_values in zip(
            journal_options, expected_values_list, strict=False
        ):
            if isinstance(expected_values, dict):
                self.assertDictEqual(
                    expected_values, {k: journal_option.get(k) for k in expected_values}
                )
            elif len(expected_values) == 2:
                record, selected = expected_values
                self.assertDictEqual(
                    {
                        "id": journal_option.get("id"),
                        "model": journal_option.get("model"),
                        "selected": journal_option.get("selected"),
                    },
                    {
                        "id": record.id,
                        "model": record._name,
                        "selected": selected,
                    },
                )

    def _assert_filter_journal_visible_unfolded(self, options, expected_values):
        self.assertEqual(len(options["journals"]), len(expected_values))
        for journal, results in zip(options["journals"], expected_values, strict=False):
            self.assertTupleEqual(
                (journal.get("visible", None), journal.get("unfolded", None)), results
            )

    def _quick_create_journal(self, name, company, journal_type="sale"):
        return self.env["account.journal"].create(
            [
                {
                    "name": name,
                    "code": name,
                    "type": journal_type,
                    "company_id": company.id,
                }
            ]
        )

    def _quick_create_journal_group(self, name, company, excluded_journals):
        return self.env["account.journal.group"].create(
            [
                {
                    "name": name,
                    "excluded_journal_ids": [Command.set(excluded_journals.ids)],
                    "company_id": company.id if company else False,
                }
            ]
        )

    def _press_journal_filter(self, options, journals):
        for option_journal in options["journals"]:
            if (
                option_journal.get("model") == "account.journal"
                and option_journal.get("id") in journals.ids
            ):
                option_journal["selected"] = not option_journal["selected"]

    def test_journal_filter_single_company(self):
        j1 = self._quick_create_journal("j1", self.vanilla_company1)
        j2 = self._quick_create_journal("j2", self.vanilla_company1)
        j3 = self._quick_create_journal("j3", self.vanilla_company1)
        j4 = self._quick_create_journal("j4", self.vanilla_company1)
        j5 = self._quick_create_journal("j5", self.vanilla_company1)
        j6 = self._quick_create_journal("j6", self.vanilla_company1)
        j7 = self._quick_create_journal("j7", self.vanilla_company1)
        j8 = self._quick_create_journal("j8", self.vanilla_company1)

        options = self.report.get_options({})
        self._assert_filter_journal(
            options,
            "All Journals",
            [
                (j1, False),
                (j2, False),
                (j3, False),
                (j4, False),
                (j5, False),
                (j6, False),
                (j7, False),
                (j8, False),
            ],
        )

        self._press_journal_filter(options, (j1 + j2 + j3))
        options = self.report.get_options(previous_options=options)
        self._assert_filter_journal(
            options,
            "j1, j2, j3",
            [
                (j1, True),
                (j2, True),
                (j3, True),
                (j4, False),
                (j5, False),
                (j6, False),
                (j7, False),
                (j8, False),
            ],
        )

        self._press_journal_filter(options, (j4 + j5 + j6))
        options = self.report.get_options(previous_options=options)
        self._assert_filter_journal(
            options,
            "j1, j2, j3, j4, j5 and one other",
            [
                (j1, True),
                (j2, True),
                (j3, True),
                (j4, True),
                (j5, True),
                (j6, True),
                (j7, False),
                (j8, False),
            ],
        )

        self._press_journal_filter(options, j7)
        options = self.report.get_options(previous_options=options)
        self._assert_filter_journal(
            options,
            "j1, j2, j3, j4, j5 and 2 others",
            [
                (j1, True),
                (j2, True),
                (j3, True),
                (j4, True),
                (j5, True),
                (j6, True),
                (j7, True),
                (j8, False),
            ],
        )

        self._press_journal_filter(options, j8)
        options = self.report.get_options(previous_options=options)
        self._assert_filter_journal(
            options,
            "All Journals",
            [
                (j1, False),
                (j2, False),
                (j3, False),
                (j4, False),
                (j5, False),
                (j6, False),
                (j7, False),
                (j8, False),
            ],
        )

    def test_journal_filter_multi_company(self):
        j1 = self._quick_create_journal("j1", self.vanilla_company1)
        j2 = self._quick_create_journal("j2", self.vanilla_company1)
        j3 = self._quick_create_journal("j3", self.vanilla_company2)
        j4 = self._quick_create_journal("j4", self.vanilla_company2)
        j5 = self._quick_create_journal("j5", self.vanilla_company1)
        j6 = self._quick_create_journal("j6", self.vanilla_company1)
        j7 = self._quick_create_journal("j7", self.vanilla_company2)
        j8 = self._quick_create_journal("j8", self.vanilla_company2)

        options = self.report.get_options({"is_opening_report": True})
        self._assert_filter_journal(
            options,
            "All Journals",
            [
                {"id": "divider"},
                (j1, False),
                (j2, False),
                (j5, False),
                (j6, False),
                {"id": "divider"},
                (j3, False),
                (j4, False),
                (j7, False),
                (j8, False),
            ],
        )

        self._press_journal_filter(options, (j1 + j3 + j5 + j7))
        options = self.report.get_options(previous_options=options)
        self._assert_filter_journal(
            options,
            "j1, j5, j3, j7",
            [
                {"id": "divider"},
                (j1, True),
                (j2, False),
                (j5, True),
                (j6, False),
                {"id": "divider"},
                (j3, True),
                (j4, False),
                (j7, True),
                (j8, False),
            ],
        )

    def test_journal_filter_with_groups_single_company(self):
        j1 = self._quick_create_journal("j1", self.vanilla_company1)
        j2 = self._quick_create_journal("j2", self.vanilla_company1)
        j3 = self._quick_create_journal("j3", self.vanilla_company1)
        j4 = self._quick_create_journal("j4", self.vanilla_company1)
        j5 = self._quick_create_journal("j5", self.vanilla_company1)
        j6 = self._quick_create_journal("j6", self.vanilla_company1)

        g1 = self._quick_create_journal_group("g1", self.vanilla_company1, j2 + j4)
        g2 = self._quick_create_journal_group("g2", self.vanilla_company1, j2 + j5)

        options = self.report.get_options({"is_opening_report": True})
        self._assert_filter_journal(
            options,
            "All Journals",
            [
                {"id": "divider"},
                (g1, False),
                (g2, False),
                {"id": "divider"},
                (j1, False),
                (j2, False),
                (j3, False),
                (j4, False),
                (j5, False),
                (j6, False),
            ],
        )

        options["__journal_group_action"] = {"action": "add", "id": g2.id}
        options = self.report.get_options(previous_options=options)
        self._assert_filter_journal(
            options,
            "g2",
            [
                {"id": "divider"},
                (g1, False),
                (g2, True),
                {"id": "divider"},
                (j1, True),
                (j2, False),
                (j3, True),
                (j4, True),
                (j5, False),
                (j6, True),
            ],
        )

        options["is_opening_report"] = True
        options = self.report.get_options(previous_options=options)
        self.assertEqual(options["name_journal_group"], "g2")

        options["__journal_group_action"] = {"action": "remove", "id": g2.id}
        options = self.report.get_options(previous_options=options)
        self._assert_filter_journal(
            options,
            "All Journals",
            [
                {"id": "divider"},
                (g1, False),
                (g2, False),
                {"id": "divider"},
                (j1, False),
                (j2, False),
                (j3, False),
                (j4, False),
                (j5, False),
                (j6, False),
            ],
        )

    def test_journal_filter_with_groups_multi_company(self):
        j1 = self._quick_create_journal("j1", self.vanilla_company1)
        j2 = self._quick_create_journal("j2", self.vanilla_company1)
        j3 = self._quick_create_journal("j3", self.vanilla_company1)
        j4 = self._quick_create_journal("j4", self.vanilla_company1)
        j5 = self._quick_create_journal("j5", self.vanilla_company2)
        j6 = self._quick_create_journal("j6", self.vanilla_company2)

        g1 = self._quick_create_journal_group("g1", self.vanilla_company1, j2 + j3)
        g2 = self._quick_create_journal_group("g2", self.vanilla_company2, j6)

        options = self.report.get_options({"is_opening_report": True})
        self._assert_filter_journal(
            options,
            "All Journals",
            [
                {"id": "divider"},
                (g1, False),
                (g2, False),
                {"id": "divider"},
                (j1, False),
                (j2, False),
                (j3, False),
                (j4, False),
                {"id": "divider"},
                (j5, False),
                (j6, False),
            ],
        )

        options["__journal_group_action"] = {"action": "add", "id": g2.id}
        options = self.report.get_options(previous_options=options)
        self._assert_filter_journal(
            options,
            "g2",
            [
                {"id": "divider"},
                (g1, False),
                (g2, True),
                {"id": "divider"},
                (j1, False),
                (j2, False),
                (j3, False),
                (j4, False),
                {"id": "divider"},
                (j5, True),
                (j6, False),
            ],
        )

        options["__journal_group_action"] = {"action": "remove", "id": g2.id}
        options = self.report.get_options(previous_options=options)
        self._assert_filter_journal(
            options,
            "All Journals",
            [
                {"id": "divider"},
                (g1, False),
                (g2, False),
                {"id": "divider"},
                (j1, False),
                (j2, False),
                (j3, False),
                (j4, False),
                {"id": "divider"},
                (j5, False),
                (j6, False),
            ],
        )

    def test_journal_filter_with_single_group_multi_company(self):
        j1 = self._quick_create_journal("j1", self.vanilla_company1)
        j2 = self._quick_create_journal("j2", self.vanilla_company1)
        j3 = self._quick_create_journal("j3", self.vanilla_company2)
        j4 = self._quick_create_journal("j4", self.vanilla_company2)

        g1 = self._quick_create_journal_group("g1", self.vanilla_company1, j2)

        options = self.report.get_options({"is_opening_report": True})
        self._assert_filter_journal(
            options,
            "All Journals",
            [
                {"id": "divider"},
                (g1, False),
                {"id": "divider"},
                (j1, False),
                (j2, False),
                {"id": "divider"},
                (j3, False),
                (j4, False),
            ],
        )

        self._press_journal_filter(options, j3)
        options = self.report.get_options(previous_options=options)
        self._assert_filter_journal(
            options,
            "j3",
            [
                {"id": "divider"},
                (g1, False),
                {"id": "divider"},
                (j1, False),
                (j2, False),
                {"id": "divider"},
                (j3, True),
                (j4, False),
            ],
        )

        options["__journal_group_action"] = {"action": "add", "id": g1.id}
        options = self.report.get_options(previous_options=options)
        self._assert_filter_journal(
            options,
            "g1",
            [
                {"id": "divider"},
                (g1, True),
                {"id": "divider"},
                (j1, True),
                (j2, False),
                {"id": "divider"},
                (j3, False),
                (j4, False),
            ],
        )

        self._press_journal_filter(options, j3)
        options = self.report.get_options(previous_options=options)
        self._assert_filter_journal(
            options,
            "j1, j3",
            [
                {"id": "divider"},
                (g1, False),
                {"id": "divider"},
                (j1, True),
                (j2, False),
                {"id": "divider"},
                (j3, True),
                (j4, False),
            ],
        )

        self._press_journal_filter(options, j3)
        options = self.report.get_options(previous_options=options)
        self._assert_filter_journal(
            options,
            "g1",
            [
                {"id": "divider"},
                (g1, True),
                {"id": "divider"},
                (j1, True),
                (j2, False),
                {"id": "divider"},
                (j3, False),
                (j4, False),
            ],
        )

    def test_journal_filter_with_groups_cash_flow_statement(self):
        bnk = self._quick_create_journal("BNK", self.vanilla_company1, "bank")
        csh = self._quick_create_journal("CSH", self.vanilla_company1, "cash")
        misc = self._quick_create_journal("MISC", self.vanilla_company1, "general")
        exch = self._quick_create_journal("EXCH", self.vanilla_company1, "general")
        ifrs = self._quick_create_journal("IFRS", self.vanilla_company1, "general")
        caba = self._quick_create_journal("CABA", self.vanilla_company1, "general")
        inv = self._quick_create_journal(
            "INV", self.vanilla_company1, "sale"
        )
        bill = self._quick_create_journal(
            "BILL", self.vanilla_company1, "purchase"
        )

        g1 = self._quick_create_journal_group("g1", self.vanilla_company1, inv + bill)
        g2 = self._quick_create_journal_group("g2", self.vanilla_company1, misc + bill)

        report = self.env.ref("account.cash_flow_report")
        options = report.get_options({"is_opening_report": True})
        self._assert_filter_journal(
            options,
            "All Journals",
            [
                {"id": "divider"},
                (g1, False),
                (
                    g2,
                    False,
                ),
                {"id": "divider"},
                (bnk, False),
                (caba, False),
                (csh, False),
                (exch, False),
                (ifrs, False),
                (misc, False),
            ],
        )

        options["__journal_group_action"] = {"action": "add", "id": g2.id}
        options = report.get_options(previous_options=options)
        self._assert_filter_journal(
            options,
            "g2",
            [
                {"id": "divider"},
                (g1, False),
                (g2, True),
                {"id": "divider"},
                (bnk, True),
                (caba, True),
                (csh, True),
                (exch, True),
                (ifrs, True),
                (misc, False),
            ],
        )

        options["__journal_group_action"] = {"action": "remove", "id": g2.id}
        options = report.get_options(previous_options=options)
        self._assert_filter_journal(
            options,
            "All Journals",
            [
                {"id": "divider"},
                (g1, False),
                (g2, False),
                {"id": "divider"},
                (bnk, False),
                (caba, False),
                (csh, False),
                (exch, False),
                (ifrs, False),
                (misc, False),
            ],
        )

    def test_journal_filter_branch_company(self):
        self.vanilla_company1.write(
            {"child_ids": [Command.create({"name": "Vanilla3"})]}
        )
        vanilla_company3 = self.vanilla_company1.child_ids[0]
        self.env.user.write(
            {
                "company_ids": [
                    Command.set(
                        (
                            self.vanilla_company1
                            + self.vanilla_company2
                            + vanilla_company3
                        ).ids
                    )
                ],
                "company_id": self.vanilla_company1.id,
            }
        )

        j1 = self._quick_create_journal("j1", self.vanilla_company1)
        j2 = self._quick_create_journal("j2", self.vanilla_company1)
        j3 = self._quick_create_journal("j3", self.vanilla_company2)
        j4 = self._quick_create_journal("j4", self.vanilla_company2)
        j5 = self._quick_create_journal("j5", self.vanilla_company1)
        j6 = self._quick_create_journal("j6", self.vanilla_company1)
        j7 = self._quick_create_journal("j7", self.vanilla_company2)
        j8 = self._quick_create_journal("j8", self.vanilla_company2)
        j9 = self._quick_create_journal("j9", vanilla_company3)
        j10 = self._quick_create_journal("j10", vanilla_company3)

        options = self.report.get_options({"is_opening_report": True})
        self._assert_filter_journal(
            options,
            "All Journals",
            [
                {"id": "divider"},
                (j1, False),
                (j2, False),
                (j5, False),
                (j6, False),
                {"id": "divider"},
                (j3, False),
                (j4, False),
                (j7, False),
                (j8, False),
                {"id": "divider"},
                (j10, False),
                (j9, False),
            ],
        )

        self._press_journal_filter(options, (j1 + j3 + j5 + j7 + j9))
        options = self.report.get_options(previous_options=options)
        self._assert_filter_journal(
            options,
            "j1, j5, j3, j7, j9",
            [
                {"id": "divider"},
                (j1, True),
                (j2, False),
                (j5, True),
                (j6, False),
                {"id": "divider"},
                (j3, True),
                (j4, False),
                (j7, True),
                (j8, False),
                {"id": "divider"},
                (j10, False),
                (j9, True),
            ],
        )

        self.env.user.write(
            {
                "company_ids": [Command.set((vanilla_company3).ids)],
                "company_id": vanilla_company3.id,
            }
        )

        options = self.report.get_options({"is_opening_report": True})
        self._assert_filter_journal(
            options,
            "All Journals",
            [
                {"id": "divider"},
                (j1, False),
                (j2, False),
                (j5, False),
                (j6, False),
                {"id": "divider"},
                (j10, False),
                (j9, False),
            ],
        )

        self._press_journal_filter(options, (j1 + j5 + j10))
        options = self.report.get_options(previous_options=options)
        self._assert_filter_journal(
            options,
            "j1, j5, j10",
            [
                {"id": "divider"},
                (j1, True),
                (j2, False),
                (j5, True),
                (j6, False),
                {"id": "divider"},
                (j10, True),
                (j9, False),
            ],
        )

        self.env.user.write(
            {
                "company_ids": [Command.set((self.vanilla_company1).ids)],
                "company_id": self.vanilla_company1.id,
            }
        )

        options = self.report.get_options({"is_opening_report": True})
        self._assert_filter_journal(
            options,
            "All Journals",
            [
                (j1, False),
                (j2, False),
                (j5, False),
                (j6, False),
            ],
        )

        self._press_journal_filter(options, (j1 + j5))
        options = self.report.get_options(previous_options=options)
        self._assert_filter_journal(
            options,
            "j1, j5",
            [
                (j1, True),
                (j2, False),
                (j5, True),
                (j6, False),
            ],
        )

    def test_journal_filter_with_groups_no_company_multi_company(self):
        j1 = self._quick_create_journal("j1", self.vanilla_company1)
        j2 = self._quick_create_journal("j2", self.vanilla_company1)
        j3 = self._quick_create_journal("j3", self.vanilla_company1)
        j4 = self._quick_create_journal("j4", self.vanilla_company2)
        j5 = self._quick_create_journal("j5", self.vanilla_company2)

        g1 = self._quick_create_journal_group("g1", self.vanilla_company1, j1)

        g2 = self._quick_create_journal_group("g2", False, j2 + j5)

        self.env.user.write(
            {
                "company_ids": [Command.set(self.vanilla_company2.ids)],
                "company_id": self.vanilla_company2.id,
            }
        )

        options = self.report.get_options({"is_opening_report": True})
        self._assert_filter_journal(
            options,
            "All Journals",
            [
                {"id": "divider"},
                (g2, False),
                {"id": "divider"},
                (j4, False),
                (j5, False),
            ],
        )

        self.env.user.write(
            {
                "company_ids": [
                    Command.set((self.vanilla_company1 + self.vanilla_company2).ids)
                ],
                "company_id": self.vanilla_company2.id,
            }
        )

        options["__journal_group_action"] = {"action": "add", "id": g1.id}
        options = self.report.get_options(previous_options=options)
        self._assert_filter_journal(
            options,
            "g1",
            [
                {"id": "divider"},
                (g1, True),
                (g2, False),
                {"id": "divider"},
                (j1, False),
                (j2, True),
                (j3, True),
                {"id": "divider"},
                (j4, False),
                (j5, False),
            ],
        )

        options["__journal_group_action"] = {"action": "add", "id": g2.id}
        options = self.report.get_options(previous_options=options)
        self._assert_filter_journal(
            options,
            "g2",
            [
                {"id": "divider"},
                (g1, False),
                (g2, True),
                {"id": "divider"},
                (j1, True),
                (j2, False),
                (j3, True),
                {"id": "divider"},
                (j4, True),
                (j5, False),
            ],
        )

        self.env.user.write(
            {
                "company_ids": [Command.set(self.vanilla_company1.ids)],
                "company_id": self.vanilla_company1.id,
            }
        )

        options = self.report.get_options({"is_opening_report": True})
        self._assert_filter_journal(
            options,
            "All Journals",
            [
                {"id": "divider"},
                (g1, False),
                (g2, False),
                {"id": "divider"},
                (j1, False),
                (j2, False),
                (j3, False),
            ],
        )

        options["__journal_group_action"] = {"action": "add", "id": g2.id}
        options = self.report.get_options(previous_options=options)
        self._assert_filter_journal(
            options,
            "g2",
            [
                {"id": "divider"},
                (g1, False),
                (g2, True),
                {"id": "divider"},
                (j1, True),
                (j2, False),
                (j3, True),
            ],
        )

        g2.sequence = g1.sequence - 1
        options = self.report.get_options({"is_opening_report": True})
        self._assert_filter_journal(
            options,
            "All Journals",
            [
                {"id": "divider"},
                (g2, False),
                (g1, False),
                {"id": "divider"},
                (j1, False),
                (j2, False),
                (j3, False),
            ],
        )

    def test_filter_journal_visible_items(self):
        j1 = self._quick_create_journal("j1", self.vanilla_company1)
        j2 = self._quick_create_journal("j5", self.vanilla_company2)
        g1 = self._quick_create_journal_group("g1", False, j1)
        options = self.report.get_options({"is_opening_report": True})

        self._assert_filter_journal(
            options,
            "All Journals",
            [
                {"id": "divider"},
                (g1, False),
                {"id": "divider"},
                (j1, False),
                {"id": "divider"},
                (j2, False),
            ],
        )

        expected_values_at_opening = [
            (None, None),
            (None, None),
            (None, False),
            (False, None),
            (None, False),
            (False, None),
        ]
        self._assert_filter_journal_visible_unfolded(
            options, expected_values_at_opening
        )

        options["journals"][2]["unfolded"] = True
        options["journals"][3]["visible"] = True

        options = self.report.get_options(previous_options=options)

        expected_values_after_unfolding = [
            (None, None),
            (None, None),
            (None, True),
            (True, None),
            (None, False),
            (False, None),
        ]
        self._assert_filter_journal_visible_unfolded(
            options, expected_values_after_unfolding
        )

        options["is_opening_report"] = True
        options = self.report.get_options(previous_options=options)
        self._assert_filter_journal_visible_unfolded(
            options, expected_values_at_opening
        )

    def test_journal_filter_group_without_report_journals(self):
        bnk = self._quick_create_journal("BNK", self.vanilla_company1, "bank")
        inv = self._quick_create_journal("INV", self.vanilla_company1, "sale")
        g1 = self._quick_create_journal_group("g1", self.vanilla_company1, bnk)

        report = self.env.ref("account.cash_flow_report")
        options = report.get_options({"is_opening_report": True})
        self.assertFalse(options["selected_journal_groups"])
        self._assert_filter_journal(
            options,
            "All Journals",
            [
                {"id": "divider"},
                (g1, False),
                {"id": "divider"},
                (bnk, False),
            ],
        )
        self.assertNotIn(inv.id, [j["id"] for j in options["journals"]])

    def test_journal_filter_groups_with_same_journals(self):
        j1 = self._quick_create_journal("j1", self.vanilla_company1)
        j2 = self._quick_create_journal("j2", self.vanilla_company1)
        g1 = self._quick_create_journal_group("g1", self.vanilla_company1, j2)
        g2 = self._quick_create_journal_group("g2", self.vanilla_company1, j2)

        options = self.report.get_options({"is_opening_report": True})
        options["__journal_group_action"] = {"action": "add", "id": g2.id}
        options = self.report.get_options(previous_options=options)
        expected = [
            {"id": "divider"},
            (g1, False),
            (g2, True),
            {"id": "divider"},
            (j1, True),
            (j2, False),
        ]
        self._assert_filter_journal(options, "g2", expected)

        self._press_journal_filter(options, j1)
        options = self.report.get_options(previous_options=options)
        self._press_journal_filter(options, j1)
        options = self.report.get_options(previous_options=options)
        self._assert_filter_journal(
            options,
            "g1",
            [
                {"id": "divider"},
                (g1, True),
                (g2, False),
                {"id": "divider"},
                (j1, True),
                (j2, False),
            ],
        )

    def test_open_journal_items_view_with_journal_group(self):
        self._quick_create_journal("BNK", self.vanilla_company1, "bank")
        csh = self._quick_create_journal("CSH", self.vanilla_company1, "cash")
        inv = self._quick_create_journal("INV", self.vanilla_company1, "sale")
        g_bank = self._quick_create_journal_group(
            "g_bank", self.vanilla_company1, csh + inv
        )
        g_mixed = self._quick_create_journal_group(
            "g_mixed", self.vanilla_company1, self.env["account.journal"]
        )
        account = self.env["account.account"].create(
            {
                "code": "101999",
                "name": "Journal items account",
                "account_type": "asset_current",
                "company_ids": [Command.set(self.vanilla_company1.ids)],
            }
        )
        line_id = self.report._get_generic_line_id("account.account", account.id)

        def open_items(group, **params):
            options = self.report.get_options({"is_opening_report": True})
            options["__journal_group_action"] = {"action": "add", "id": group.id}
            options = self.report.get_options(previous_options=options)
            return self.report.open_journal_items(
                options, {"line_id": line_id, **params}
            )

        action = open_items(g_bank)
        self.assertEqual(
            action["views"],
            [
                (
                    self.env.ref(
                        "account.view_account_move_line_list_grouped_bank_cash"
                    ).id,
                    "list",
                )
            ],
        )
        self.assertEqual(action["context"]["search_default_bank"], 1)
        self.assertEqual(
            action["context"]["search_default_journal_group_id"], [g_bank.id]
        )

        action = open_items(g_mixed)
        self.assertEqual(action["views"], [(None, "list")])
        for search_default in (
            "search_default_bank",
            "search_default_cash",
            "search_default_sales",
        ):
            self.assertEqual(action["context"][search_default], 1)

        action = open_items(g_mixed, journal_type="sale")
        self.assertEqual(
            action["views"],
            [
                (
                    self.env.ref(
                        "account.view_account_move_line_list_grouped_sales_purchases"
                    ).id,
                    "list",
                )
            ],
        )

from odoo.tests.common import TransactionCase


class TestUnityWebReadGroupGantt(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pill_1, cls.pill_2 = cls.env["test.web.gantt.pill"].create(
            [
                {"name": "PillParent1"},
                {"name": "PillParent2"},
            ]
        )
        cls.dependency_pills = cls.env["test.web.gantt.pill"].create(
            [
                {"name": "Tag 1"},
                {"name": "Tag 2"},
                {"name": "Tag 3"},
                {"name": "Tag 4"},
            ]
        )
        cls.pills = cls.env["test.web.gantt.pill"].create(
            [
                {
                    "name": "one",
                    "parent_id": cls.pill_1.id,
                    "dependency_field": cls.dependency_pills[0],
                },
                {
                    "name": "two",
                    "parent_id": cls.pill_2.id,
                    "dependency_field": cls.dependency_pills[:2],
                },
                {"name": "there", "parent_id": cls.pill_2.id},
                {"name": "four", "parent_id": cls.pill_2.id},
                {
                    "name": "four",
                    "parent_id": cls.pill_2.id,
                    "dependency_field": cls.dependency_pills[1:3],
                },
                {
                    "name": "six",
                    "parent_id": cls.pill_1.id,
                    "dependency_field": cls.dependency_pills[:3],
                },
            ]
        )

    def test_get_gantt_data_without_limit(self):
        self.env.invalidate_all()
        with self.assertQueryCount(1):
            result = self.env["test.web.gantt.pill"].get_gantt_data(
                [("id", "in", self.pills.ids)],
                [],
                {"display_name": {}},
            )
            self.assertEqual(
                result,
                {
                    "groups": [{"__record_ids": self.pills.ids}],
                    "records": [
                        {"id": self.pills[0].id, "display_name": "one"},
                        {"id": self.pills[1].id, "display_name": "two"},
                        {"id": self.pills[2].id, "display_name": "there"},
                        {"id": self.pills[3].id, "display_name": "four"},
                        {"id": self.pills[4].id, "display_name": "four"},
                        {"id": self.pills[5].id, "display_name": "six"},
                    ],
                    "length": 1,
                    "unavailabilities": {},
                    "progress_bars": {},
                },
            )

        self.env.invalidate_all()
        with self.assertQueryCount(3):
            result = self.env["test.web.gantt.pill"].get_gantt_data(
                [("id", "in", self.pills.ids)],
                ["dependency_field"],
                {"display_name": {}},
            )
            self.assertEqual(
                result,
                {
                    "groups": [
                        {
                            "dependency_field": (self.dependency_pills[0].id, "Tag 1"),
                            "__record_ids": [
                                self.pills[0].id,
                                self.pills[1].id,
                                self.pills[5].id,
                            ],
                        },
                        {
                            "dependency_field": (self.dependency_pills[1].id, "Tag 2"),
                            "__record_ids": [
                                self.pills[1].id,
                                self.pills[4].id,
                                self.pills[5].id,
                            ],
                        },
                        {
                            "dependency_field": (self.dependency_pills[2].id, "Tag 3"),
                            "__record_ids": [
                                self.pills[4].id,
                                self.pills[5].id,
                            ],
                        },
                        {
                            "dependency_field": False,
                            "__record_ids": [
                                self.pills[2].id,
                                self.pills[3].id,
                            ],
                        },
                    ],
                    "records": [
                        {"id": self.pills[0].id, "display_name": "one"},
                        {"id": self.pills[1].id, "display_name": "two"},
                        {"id": self.pills[2].id, "display_name": "there"},
                        {"id": self.pills[3].id, "display_name": "four"},
                        {"id": self.pills[4].id, "display_name": "four"},
                        {"id": self.pills[5].id, "display_name": "six"},
                    ],
                    "length": 4,
                    "unavailabilities": {},
                    "progress_bars": {},
                },
            )

    def test_get_gantt_data_with_limit(self):
        self.env.invalidate_all()
        with self.assertQueryCount(4):
            result = self.env["test.web.gantt.pill"].get_gantt_data(
                [("id", "in", self.pills.ids)],
                ["parent_id", "name"],
                {"display_name": {}},
                limit=2,
            )
            self.assertEqual(
                result,
                {
                    "groups": [
                        {
                            "parent_id": (self.pill_1.id, "PillParent1"),
                            "name": "one",
                            "__record_ids": [self.pills[0].id],
                        },
                        {
                            "parent_id": (self.pill_1.id, "PillParent1"),
                            "name": "six",
                            "__record_ids": [self.pills[5].id],
                        },
                    ],
                    "records": [
                        {"id": self.pills[0].id, "display_name": "one"},
                        {"id": self.pills[5].id, "display_name": "six"},
                    ],
                    "length": 5,
                    "unavailabilities": {},
                    "progress_bars": {},
                },
            )

        self.env.invalidate_all()
        with self.assertQueryCount(4):
            result = self.env["test.web.gantt.pill"].get_gantt_data(
                [("id", "in", self.pills.ids)],
                ["parent_id", "name"],
                {"display_name": {}},
                limit=2,
                offset=1,
            )
            self.assertEqual(
                result,
                {
                    "groups": [
                        {
                            "parent_id": (self.pill_1.id, "PillParent1"),
                            "name": "six",
                            "__record_ids": [self.pills[5].id],
                        },
                        {
                            "parent_id": (self.pill_2.id, "PillParent2"),
                            "name": "four",
                            "__record_ids": [self.pills[3].id, self.pills[4].id],
                        },
                    ],
                    "records": [
                        {"id": self.pills[3].id, "display_name": "four"},
                        {"id": self.pills[4].id, "display_name": "four"},
                        {"id": self.pills[5].id, "display_name": "six"},
                    ],
                    "length": 5,
                    "unavailabilities": {},
                    "progress_bars": {},
                },
            )

    def test_get_gantt_data_with_inactive(self):
        self.env.invalidate_all()
        self.pills[0:2].active = False
        with self.assertQueryCount(3):
            result = self.env["test.web.gantt.pill"].get_gantt_data(
                [("id", "in", self.pills.ids), ("active", "=", False)],
                ["dependency_field"],
                {"display_name": {}},
            )
            self.assertEqual(
                result,
                {
                    "groups": [
                        {
                            "dependency_field": (self.dependency_pills[0].id, "Tag 1"),
                            "__record_ids": [
                                self.pills[0].id,
                                self.pills[1].id,
                            ],
                        },
                        {
                            "dependency_field": (self.dependency_pills[1].id, "Tag 2"),
                            "__record_ids": [
                                self.pills[1].id,
                            ],
                        },
                    ],
                    "records": [
                        {"id": self.pills[0].id, "display_name": "one"},
                        {"id": self.pills[1].id, "display_name": "two"},
                    ],
                    "length": 2,
                    "unavailabilities": {},
                    "progress_bars": {},
                },
            )

    def test_ungrouped_call_tolerates_unavailability_fields(self):
        result = self.env["test.web.gantt.pill"].get_gantt_data(
            [("id", "in", self.pills[0].ids)],
            [],
            {"display_name": {}},
            unavailability_fields=["parent_id"],
            progress_bar_fields=["parent_id"],
            start_date="2024-01-01 00:00:00",
            stop_date="2024-02-01 00:00:00",
            scale="week",
        )

        self.assertEqual(result["length"], 1)
        self.assertEqual(result["groups"][0]["__record_ids"], self.pills[0].ids)
        self.assertEqual(result["unavailabilities"], {"parent_id": {}})
        self.assertEqual(result["progress_bars"], {"parent_id": {}})

    def test_get_gantt_data_groups_by_date_granularity(self):
        pills = self.env["test.web.gantt.pill"].create(
            [
                {"name": "jan", "date_start": "2021-01-05 08:00:00"},
                {"name": "feb", "date_start": "2021-02-05 08:00:00"},
                {"name": "jan2", "date_start": "2021-01-20 08:00:00"},
            ]
        )
        result = self.env["test.web.gantt.pill"].get_gantt_data(
            [("id", "in", pills.ids)], ["date_start:month"], {"display_name": {}}
        )
        self.assertEqual(
            [
                (g["date_start:month"], sorted(g["__record_ids"]))
                for g in result["groups"]
            ],
            [
                (
                    ("2021-01-01 00:00:00", "January 2021"),
                    sorted([pills[0].id, pills[2].id]),
                ),
                (("2021-02-01 00:00:00", "February 2021"), [pills[1].id]),
            ],
        )
        self.assertEqual(result["length"], 2)

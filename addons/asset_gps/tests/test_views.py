from lxml import etree

from odoo.tests.common import TransactionCase


class TestGpsKanbanAnchors(TransactionCase):
    """Where the GPS blocks land in the parent cards.

    Every xpath this module uses to reach into asset_ledger's kanbans matches
    by class shape, not by a named node, so a class added or reordered upstream
    would relocate a block with no error. Each expression resolves to exactly
    one node today; these tests turn a future collision into a red suite.
    """

    def _card(self, xml_id):
        return etree.fromstring(self.env.ref(xml_id).get_combined_arch())

    @staticmethod
    def _container_of(node):
        """The nearest ancestor that is a real element, not a `t-if` wrapper.

        Everything this module inserts is wrapped in
        `<t t-if="record.gps_device_id.raw_value">`, so the immediate parent of
        an inserted node is that `t` and carries no class of its own.
        """
        parent = node.getparent()
        while parent is not None and parent.tag == "t":
            parent = parent.getparent()
        return parent

    def _classes_of_container(self, node):
        container = self._container_of(node)
        return (container.get("class") or "") if container is not None else ""

    def _tag_of_container(self, node):
        container = self._container_of(node)
        return container.tag if container is not None else ""

    def _live_status_block(self, arch):
        block = next(
            (
                node
                for node in arch.iter("div")
                if "border-top" in (node.get("class") or "")
                and (node.get("class") or "").startswith("row g-2")
            ),
            None,
        )
        self.assertIsNotNone(block, "no GPS live-status block in the card")
        return block

    def _badge_containers(self, arch, labels):
        return {
            self._classes_of_container(span)
            for span in arch.iter("span")
            if any(label in "".join(span.itertext()) for label in labels)
            and "badge" in (span.get("class") or "")
        }

    def test_the_live_status_block_follows_the_fleet_totals_row(self):
        arch = self._card("asset_ledger.resource_asset_view_kanban_fleet")

        rows = [
            node
            for node in arch.iter("div")
            if (node.get("class") or "").startswith("row g-2")
        ]

        self.assertEqual(
            [node.get("class") for node in rows],
            ["row g-2 mt-1", "row g-2 mt-2 pt-2 border-top"],
            "The GPS live-status block sits immediately after the parent's row.",
        )
        self.assertEqual(
            self._classes_of_container(rows[1]),
            self._classes_of_container(rows[0]),
            "Both rows hang off the same container in the parent card.",
        )

    def test_the_live_status_block_shows_when_the_data_arrived(self):
        arch = self._card("asset_ledger.resource_asset_view_kanban_fleet")

        shown = [
            node
            for node in arch.iter("field")
            if node.get("name") == "gps_date_last_data"
        ]

        self.assertTrue(
            shown,
            "Ignition, movement, speed and fuel mean nothing without the time "
            "they were read at.",
        )

    def test_the_fleet_badges_land_in_the_card_body(self):
        """Core fleet's card is a bare `<main>`: it ships no badge strip, no
        footer and no title block, so the badges hang off `<main>` itself."""
        arch = self._card("asset_ledger.resource_asset_view_kanban_fleet")

        badges = [
            span
            for span in arch.iter("span")
            if any(
                label in "".join(span.itertext()) for label in ("GPS Error", "Tracking")
            )
            and "badge" in (span.get("class") or "")
        ]

        self.assertTrue(badges)
        self.assertEqual({self._tag_of_container(span) for span in badges}, {"main"})

    def test_the_general_badges_land_in_the_badge_strip(self):
        arch = self._card("asset_ledger.resource_asset_view_kanban_general")

        self.assertEqual(
            self._badge_containers(arch, ("Moving", "GPS Active")),
            {"d-flex gap-1 flex-wrap mt-2"},
        )

    def test_the_gps_history_link_lands_in_the_fleet_card_body(self):
        arch = self._card("asset_ledger.resource_asset_view_kanban_fleet")

        links = [
            node
            for node in arch.iter("a")
            if node.get("name") == "action_view_tracking_history"
        ]

        self.assertEqual(len(links), 1)
        self.assertEqual(
            self._tag_of_container(links[0]),
            "main",
            "The GPS history link belongs in the card body core fleet ships.",
        )

    def test_the_connection_badge_follows_the_name_on_every_card(self):
        """agromarin's own card keeps a title block; core fleet's does not, so
        there the badge follows the name inside `<main>`."""
        for xml_id, expected in (
            ("asset_ledger.resource_asset_view_kanban_fleet", {"main"}),
            ("asset_ledger.resource_asset_view_kanban_general", {"div"}),
        ):
            with self.subTest(view=xml_id):
                arch = self._card(xml_id)
                icons = [
                    icon
                    for icon in arch.iter("i")
                    if "fa-signal" in (icon.get("class") or "")
                    or "fa-exclamation-triangle" in (icon.get("class") or "")
                ]
                self.assertTrue(icons)
                self.assertEqual(
                    {self._tag_of_container(icon.getparent()) for icon in icons},
                    expected,
                )

    def _column_of(self, arch, icon_class):
        """The live-status column whose icon carries `icon_class`."""
        column = next(
            (
                icon.getparent()
                for icon in arch.iter("i")
                if icon_class in (icon.get("class") or "")
            ),
            None,
        )
        self.assertIsNotNone(
            column, f"no live-status column with a {icon_class!r} icon"
        )
        return column

    def test_an_empty_tank_is_not_reported_as_no_data(self):
        """`0` is falsy in JS, so guarding a value branch on the value's own
        truthiness sends an empty tank to the "N/A" branch -- and empty is
        precisely the reading worth seeing. The speed column beside it already
        knows this and writes `|| 0`.
        """
        arch = self._card("asset_ledger.resource_asset_view_kanban_fleet")
        column = self._column_of(self._live_status_block(arch), "fa-gas-pump")

        guards = [
            node.get("t-if") or node.get("t-elif") or "t-else"
            for node in column.iter("t")
            if node.get("t-if") or node.get("t-elif") or "t-else" in node.attrib
        ]

        self.assertEqual(
            guards,
            [
                "record.gps_fuel_level_l.raw_value",
                "record.gps_fuel_level.raw_value",
                "record.gps_date_last_data.raw_value",
                "t-else",
            ],
            "A zero reading needs a branch of its own, reached when the device "
            "has reported at all; 'N/A' is only for a device that never has.",
        )

    def test_every_gps_field_the_fleet_card_fetches_is_rendered(self):
        """A field in the kanban's <field> list is fetched for every card, and
        all of these are non-stored related fields reaching into device.device.
        An unrendered one is therefore computed and thrown away once per card.
        gps_battery_level was exactly that.
        """
        arch = self._card("asset_ledger.resource_asset_view_kanban_fleet")
        rendered = etree.tostring(arch, encoding="unicode")

        declared = {
            node.get("name")
            for node in arch.iter("field")
            if (node.get("name") or "").startswith("gps_")
        }
        self.assertTrue(declared, "the fleet card fetches GPS fields")

        self.assertEqual(
            sorted(name for name in declared if f"record.{name}." not in rendered),
            [],
            "Every GPS field the card pays to fetch must be shown by it.",
        )


class TestGpsDeviceKanbanAsset(TransactionCase):
    """The asset line on the GPS device dashboard card."""

    def _card(self):
        return etree.fromstring(
            self.env.ref(
                "device_gps.view_device_device_kanban_gps_dashboard"
            ).get_combined_arch()
        )

    def test_the_asset_is_rendered_as_a_many2one(self):
        """asset_id is a Many2one. An x2many widget such as many2many_tags
        breaks the web client's arch parser on the whole kanban, so the GPS
        Devices action would not open at all.
        """
        arch = self._card()
        widgets = [
            node.get("widget")
            for node in arch.iter("field")
            if node.get("name") == "asset_id"
        ]

        self.assertTrue(widgets, "the card shows the assigned asset")
        self.assertEqual(set(widgets), {None})

    def test_the_asset_line_shows_when_an_asset_is_assigned(self):
        """A Many2one's raw value has no length; a `.length` guard hid the line
        on every card."""
        lines = self._card().xpath("//div[@name='asset_line']")

        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].get("t-if"), "record.asset_id.raw_value")


class TestKindFormButtons(TransactionCase):
    def test_every_button_on_a_resource_kind_form_runs_on_the_kind(self):
        kinds = [
            name
            for name in self.env.registry["mixin.resource.kind"]._inherit_children
            if not self.env.registry[name]._abstract
        ]
        self.assertIn("resource.asset.vehicle", kinds)
        for name in kinds:
            with self.subTest(kind=name):
                view = self.env["ir.ui.view"].browse(
                    self.env[name].get_view(view_type="form")["id"]
                )
                arch = etree.fromstring(view.get_combined_arch())
                buttons = {
                    button.get("name")
                    for button in arch.iter("button")
                    if button.get("type") == "object"
                }
                self.assertIn("action_view_gps_device", buttons)
                self.assertEqual(
                    sorted(b for b in buttons if not hasattr(self.env[name], b)), []
                )

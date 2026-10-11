from unittest.mock import MagicMock, patch

import pytest

from odoo.libs.json import loads as json_loads
from odoo.modules import loading
from odoo.orm.runtime._loading_phase import LoadingPhase


class TestDataFileDigestAndDynamicFlag:
    def test_a_plain_xml_file_is_static(self):
        digest, dynamic = loading._get_data_file_digest_and_dynamic_flag(
            "data/x.xml", b"<odoo></odoo>"
        )
        assert digest
        assert dynamic is False

    def test_the_digest_follows_the_content(self):
        first, _ = loading._get_data_file_digest_and_dynamic_flag(
            "data/x.xml", b"<odoo/>"
        )
        same, _ = loading._get_data_file_digest_and_dynamic_flag(
            "data/other.xml", b"<odoo/>"
        )
        changed, _ = loading._get_data_file_digest_and_dynamic_flag(
            "data/x.xml", b"<odoo> </odoo>"
        )
        assert first == same, "the digest is of the content, not the name"
        assert first != changed

    @pytest.mark.parametrize("marker", [b"<function", b"<delete"])
    def test_xml_carrying_a_marker_is_dynamic(self, marker):
        _, dynamic = loading._get_data_file_digest_and_dynamic_flag(
            "data/x.xml", b"<odoo>" + marker + b' model="x"/></odoo>'
        )
        assert dynamic is True, (
            "<function> runs code and <delete> removes records; neither leaves "
            "a result the file's own checksum describes"
        )

    def test_the_markers_are_matched_case_sensitively_as_xml_requires(self):
        _, dynamic = loading._get_data_file_digest_and_dynamic_flag(
            "d.xml", b"<odoo><FUNCTION/></odoo>"
        )
        assert dynamic is False, "XML element names are case sensitive"

    def test_a_marker_in_a_non_xml_file_does_not_make_it_dynamic(self):
        _, dynamic = loading._get_data_file_digest_and_dynamic_flag(
            "data/x.csv", b"id,name\n<function,x\n"
        )
        assert dynamic is False

    def test_a_file_with_no_extension_is_static(self):
        _, dynamic = loading._get_data_file_digest_and_dynamic_flag(
            "LICENSE", b"<function/>"
        )
        assert dynamic is False


@pytest.fixture
def loader(tmp_path):
    def _load_data(
        *,
        content=b"<odoo/>",
        stored=None,
        filename="data/x.xml",
        track=True,
        mode="update",
        kind="data",
        written=(),
        missing=(),
        moved=(),
        resolved=None,
        ids=None,
    ):
        converted, recorded_xmlids = [], {"mymod.a", "mymod.b"}

        def fake_convert(env, name, fname, idref, cmode, noupdate=False, content=None):
            converted.append(fname)
            _load_data.contents.append(content)
            idref.update(ids or {})
            if env.registry.loading.xmlid_recorder is not None:
                env.registry.loading.xmlid_recorder.update(recorded_xmlids)
            if env.registry.loading.ref_recorder is not None:
                env.registry.loading.ref_recorder.update(resolved or {})

        env = MagicMock()
        env.cr.fetchone.return_value = (stored,)
        last_query = []
        env.cr.execute.side_effect = lambda query, *args: last_query.append(query)

        def fetchall():
            if "d.res_id = x.res_id" in last_query[-1]:
                return [list(pair) for pair in moved]
            return [[xmlid] for xmlid in missing]

        env.cr.fetchall.side_effect = fetchall
        registry = env.registry
        registry.loaded_xmlids = set()
        registry.loading = LoadingPhase(xmlids_written=set(written))

        package = MagicMock()
        package.name, package.id = "mymod", 42
        package.manifest = {
            "init_xml": [],
            "data": [filename] if kind == "data" else [],
            "demo": [filename] if kind == "demo" else [],
            "demo_xml": [],
        }

        handle = MagicMock()
        handle.__enter__ = MagicMock(return_value=MagicMock(read=lambda: content))
        handle.__exit__ = MagicMock(return_value=False)
        tools_mod = MagicMock(
            config={"skip_unchanged_data_files": track},
            file_open=MagicMock(return_value=handle),
        )
        with (
            patch.object(loading, "tools", tools_mod),
            patch.object(loading, "convert_file", side_effect=fake_convert),
            patch.object(loading, "schema", MagicMock(column_exists=lambda *a: track)),
        ):
            _load_data.contents = []
            _load_data.recreated = loading.load_data(env, {}, mode, kind, package)

        stored_json = None
        for call in env.cr.execute.call_args_list:
            if "UPDATE ir_module_module" in call.args[0]:
                stored_json = json_loads(call.args[1][0])
        _load_data.registry = registry
        return converted, registry.loaded_xmlids, stored_json

    return _load_data


UNCHANGED = {"sha": None, "xmlids": ["mymod.a"], "dyn": False}


def _prepare_entry(digest, **over):
    return {"sha": digest, "xmlids": ["mymod.a"], "dyn": False, **over}


def _get_digest(content=b"<odoo/>", name="data/x.xml"):
    return loading._get_data_file_digest_and_dynamic_flag(name, content)[0]


class TestSkipDecision:
    def _prepare_store(self, files):
        return {"v": loading._DATA_FILE_CHECKSUM_VERSION, "files": files}

    def test_an_unchanged_static_file_is_skipped(self, loader):
        converted, xmlids, _ = loader(
            stored=self._prepare_store({"data/x.xml": _prepare_entry(_get_digest())})
        )
        assert converted == [], "the file did not change; re-applying it is waste"
        assert xmlids == {"mymod.a"}, (
            "the recorded xmlids must be replayed into loaded_xmlids — without "
            "them the ORM sees records nothing claims and deletes them as "
            "orphans on the next update"
        )

    def test_a_changed_file_is_re_applied(self, loader):
        converted, _, _ = loader(
            content=b"<odoo> changed </odoo>",
            stored=self._prepare_store({"data/x.xml": _prepare_entry(_get_digest())}),
        )
        assert converted == ["data/x.xml"]

    def test_a_file_that_is_now_dynamic_is_never_skipped(self, loader):
        content = b'<odoo><function model="x"/></odoo>'
        converted, _, _ = loader(
            content=content,
            stored=self._prepare_store(
                {"data/x.xml": _prepare_entry(_get_digest(content), dyn=False)}
            ),
        )
        assert converted == ["data/x.xml"], (
            "the checksum matches, but <function> runs code — the previous "
            "run's effect is not reproduced by the file being identical"
        )

    def test_a_file_that_WAS_dynamic_is_never_skipped(self, loader):
        converted, _, _ = loader(
            stored=self._prepare_store(
                {"data/x.xml": _prepare_entry(_get_digest(), dyn=True)}
            )
        )
        assert converted == ["data/x.xml"], (
            "it was dynamic when last applied, so what it did then is unknown; "
            "the `dyn` flag has to be checked on the STORED entry too"
        )

    def test_an_entry_with_no_recorded_xmlids_is_never_skipped(self, loader):
        entry = _prepare_entry(_get_digest())
        del entry["xmlids"]
        converted, _, _ = loader(stored=self._prepare_store({"data/x.xml": entry}))
        assert converted == ["data/x.xml"], (
            "skipping without the xmlids to replay leaves loaded_xmlids short, "
            "and the records it should have named get deleted as orphans"
        )

    def test_a_malformed_entry_is_never_skipped(self, loader):
        converted, _, _ = loader(
            stored=self._prepare_store({"data/x.xml": "not-a-dict"})
        )
        assert converted == ["data/x.xml"]

    def test_a_store_from_an_older_format_version_is_ignored(self, loader):
        converted, _, _ = loader(
            stored={
                "v": loading._DATA_FILE_CHECKSUM_VERSION - 1,
                "files": {"data/x.xml": _prepare_entry(_get_digest())},
            }
        )
        assert converted == ["data/x.xml"], (
            "an entry written by an older scanner may mean something else; "
            "reading it as current is how a format change becomes data loss"
        )

    def test_a_file_never_seen_before_is_applied(self, loader):
        converted, _, _ = loader(stored=self._prepare_store({}))
        assert converted == ["data/x.xml"]

    def test_with_tracking_off_nothing_is_skipped_and_nothing_is_written(self, loader):
        converted, _, written = loader(
            track=False,
            stored=self._prepare_store({"data/x.xml": _prepare_entry(_get_digest())}),
        )
        assert converted == ["data/x.xml"]
        assert written is None


class TestWhatGetsRecorded:
    def _prepare_store(self, files):
        return {"v": loading._DATA_FILE_CHECKSUM_VERSION, "files": files}

    def test_a_freshly_applied_file_records_its_digest_and_xmlids(self, loader):
        _, _, written = loader(stored=self._prepare_store({}))
        entry = written["files"]["data/x.xml"]
        assert entry["sha"] == _get_digest()
        assert entry["xmlids"] == ["mymod.a", "mymod.b"], "sorted, so it is stable"
        assert entry["dyn"] is False

    def test_a_freshly_applied_file_records_what_its_references_resolved_to(
        self, loader
    ):
        _, _, written = loader(
            stored=self._prepare_store({}),
            resolved={"other.parent": 1469, "mymod.a": 7},
        )
        assert written["files"]["data/x.xml"]["refs"] == {
            "mymod.a": 7,
            "other.parent": 1469,
        }

    def test_a_dynamic_file_records_that_it_was_dynamic(self, loader):
        content = b'<odoo><delete model="x"/></odoo>'
        _, _, written = loader(content=content, stored=self._prepare_store({}))
        assert written["files"]["data/x.xml"]["dyn"] is True, (
            "recording it as static would let the NEXT run skip it"
        )

    def test_a_tracked_file_is_read_once_and_its_bytes_converted(self, loader):
        loader(content=b"<odoo> </odoo>", stored=self._prepare_store({}))
        assert loader.contents == [b"<odoo> </odoo>"], (
            "convert_file opening the file again reads it twice per update"
        )

    def test_the_store_carries_its_format_version(self, loader):
        _, _, written = loader(stored=self._prepare_store({}))
        assert written["v"] == loading._DATA_FILE_CHECKSUM_VERSION

    def test_a_skipped_file_stays_in_the_store(self, loader):
        entry = _prepare_entry(_get_digest())
        _, _, written = loader(stored=self._prepare_store({"data/x.xml": entry}))
        assert written["files"]["data/x.xml"] == entry, (
            "dropping a skipped file's entry means the next run cannot skip it "
            "either, and the optimisation decays to nothing over time"
        )


class TestAFileWhoseRecordsWereAlreadyRewritten:
    def _prepare_store(self, files):
        return {"v": loading._DATA_FILE_CHECKSUM_VERSION, "files": files}

    def test_it_is_re_applied_rather_than_skipped(self, loader):
        converted, _, _ = loader(
            stored=self._prepare_store({"data/x.xml": _prepare_entry(_get_digest())}),
            written={"mymod.a"},
        )
        assert converted == ["data/x.xml"], (
            "the file owns mymod.a, which this run already rewrote, so its own "
            "bytes being unchanged does not make it redundant"
        )

    def test_a_file_nothing_contends_for_is_still_skipped(self, loader):
        converted, _, _ = loader(
            stored=self._prepare_store({"data/x.xml": _prepare_entry(_get_digest())}),
            written={"mymod.unrelated"},
        )
        assert converted == [], (
            "an unrelated write must not cost the optimisation its skip"
        )

    def test_applying_a_file_publishes_what_it_wrote(self, loader):
        loader(stored=self._prepare_store({}))
        assert {"mymod.a", "mymod.b"} <= loader.registry.loading.xmlids_written, (
            "a later file can only detect contention if earlier writes are "
            "recorded as they happen"
        )

    def test_a_skipped_file_publishes_nothing(self, loader):
        loader(
            stored=self._prepare_store({"data/x.xml": _prepare_entry(_get_digest())}),
            written={"mymod.unrelated"},
        )
        assert loader.registry.loading.xmlids_written == {"mymod.unrelated"}, (
            "a file that never ran wrote nothing, so it must not make a later "
            "file look contended"
        )

    def test_the_untracked_path_records_too(self, loader):
        loader(stored=self._prepare_store({}), track=False)
        assert {"mymod.a", "mymod.b"} <= loader.registry.loading.xmlids_written, (
            "tracking off for one module does not make its writes invisible to "
            "a module that is tracked"
        )

    def test_re_application_refreshes_the_stored_entry(self, loader):
        _, _, stored_json = loader(
            stored=self._prepare_store({"data/x.xml": _prepare_entry(_get_digest())}),
            written={"mymod.a"},
        )
        entry = stored_json["files"]["data/x.xml"]
        assert entry["sha"] == _get_digest()
        assert entry["xmlids"] == ["mymod.a", "mymod.b"], (
            "a re-applied file records what it actually wrote, so the next run "
            "starts from the truth"
        )


class TestAFileThatOverridesAnotherModule:
    def _prepare_store(self, files):
        return {"v": loading._DATA_FILE_CHECKSUM_VERSION, "files": files}

    def test_it_is_re_applied_even_when_nothing_contends_for_it(self, loader):
        converted, _, _ = loader(
            stored=self._prepare_store(
                {
                    "data/x.xml": _prepare_entry(
                        _get_digest(), xmlids=["other.menu_root"]
                    )
                }
            ),
        )
        assert converted == ["data/x.xml"], (
            "the definer may have reset the record in an earlier run, which "
            "this run has no way to see"
        )

    def test_a_file_writing_only_its_own_records_is_still_skipped(self, loader):
        converted, _, _ = loader(
            stored=self._prepare_store(
                {
                    "data/x.xml": _prepare_entry(
                        _get_digest(), xmlids=["mymod.a", "mymod.b"]
                    )
                }
            ),
        )
        assert converted == [], (
            "a file nothing outside the module can rewrite keeps its skip"
        )

    def test_one_foreign_record_among_many_is_enough(self, loader):
        converted, _, _ = loader(
            stored=self._prepare_store(
                {
                    "data/x.xml": _prepare_entry(
                        _get_digest(), xmlids=["mymod.a", "mymod.b", "other.c"]
                    )
                }
            ),
        )
        assert converted == ["data/x.xml"]

    def test_re_application_refreshes_the_stored_entry(self, loader):
        _, _, stored_json = loader(
            stored=self._prepare_store(
                {
                    "data/x.xml": _prepare_entry(
                        _get_digest(), xmlids=["other.menu_root"]
                    )
                }
            ),
        )
        entry = stored_json["files"]["data/x.xml"]
        assert entry["sha"] == _get_digest()
        assert entry["xmlids"] == ["mymod.a", "mymod.b"]


class _RecordCursor:
    def __init__(self, absent):
        self.absent = set(absent)
        self.asked = None
        self.queries = []

    def execute(self, query, params=None):
        self.queries.append(query)
        [asked] = params
        self.asked = list(asked)
        self._rows = [[xmlid] for xmlid in self.asked if xmlid in self.absent]

    def fetchall(self):
        return self._rows


class TestFilesMissingRecords:
    def test_a_file_whose_records_are_all_present_is_not_named(self):
        cr = _RecordCursor(absent=[])
        stale = loading._get_files_missing_records(
            cr,
            {
                "data/x.xml": _prepare_entry(
                    _get_digest(), xmlids=["mymod.a", "mymod.b"]
                )
            },
        )
        assert stale == set()
        assert sorted(cr.asked) == ["mymod.a", "mymod.b"]

    def test_one_absent_record_names_the_file_that_declares_it(self):
        cr = _RecordCursor(absent=["mymod.b"])
        stale = loading._get_files_missing_records(
            cr,
            {
                "data/x.xml": _prepare_entry(_get_digest(), xmlids=["mymod.a"]),
                "data/y.xml": _prepare_entry(_get_digest(), xmlids=["mymod.b"]),
            },
        )
        assert stale == {"data/y.xml"}, "only the file that would rebuild it"

    def test_a_record_declared_by_two_files_names_both(self):
        cr = _RecordCursor(absent=["mymod.a"])
        stale = loading._get_files_missing_records(
            cr,
            {
                "data/x.xml": _prepare_entry(_get_digest(), xmlids=["mymod.a"]),
                "data/y.xml": _prepare_entry(_get_digest(), xmlids=["mymod.a"]),
            },
        )
        assert stale == {"data/x.xml", "data/y.xml"}, (
            "which of the two put the record there is not knowable from the "
            "entries, and re-applying the wrong one alone would not rebuild it"
        )

    def test_entries_carrying_no_xmlid_list_are_ignored(self):
        cr = _RecordCursor(absent=[])
        stale = loading._get_files_missing_records(
            cr, {"data/x.xml": "not-a-dict", "data/y.xml": {"sha": "s", "dyn": False}}
        )
        assert stale == set()
        assert cr.queries == [], "nothing recorded, nothing to ask about"

    def test_nothing_stored_asks_the_database_nothing(self):
        cr = _RecordCursor(absent=[])
        assert loading._get_files_missing_records(cr, {}) == set()
        assert cr.queries == []


class TestARecordGoneFromTheDatabase:
    def _prepare_store(self, files):
        return {"v": loading._DATA_FILE_CHECKSUM_VERSION, "files": files}

    def test_an_unchanged_file_is_re_applied_when_its_record_is_gone(self, loader):
        converted, _, _ = loader(
            stored=self._prepare_store({"data/x.xml": _prepare_entry(_get_digest())}),
            missing=["mymod.a"],
        )
        assert converted == ["data/x.xml"], (
            "the digest witnesses that the FILE has not changed, never that "
            "its records are still there; a migration that drops a view leaves "
            "the entry claiming a load that no longer holds, and skipping on it "
            "means nothing ever rebuilds the view"
        )

    def test_an_unchanged_file_whose_records_are_present_is_still_skipped(self, loader):
        converted, xmlids, _ = loader(
            stored=self._prepare_store({"data/x.xml": _prepare_entry(_get_digest())}),
        )
        assert converted == [], "the check must not cost the skip its purpose"
        assert xmlids == {"mymod.a"}

    def test_re_application_refreshes_the_stored_entry(self, loader):
        _, _, stored_json = loader(
            stored=self._prepare_store({"data/x.xml": _prepare_entry(_get_digest())}),
            missing=["mymod.a"],
        )
        entry = stored_json["files"]["data/x.xml"]
        assert entry["sha"] == _get_digest()
        assert entry["xmlids"] == ["mymod.a", "mymod.b"]


class _PairCursor:
    def __init__(self, moved):
        self.moved = set(moved)
        self.queries = []
        self._rows = []

    def execute(self, query, params=None):
        self.queries.append(query)
        xmlids, res_ids = params
        self._rows = [
            [xmlid, res_id]
            for xmlid, res_id in zip(xmlids, res_ids, strict=True)
            if (xmlid, res_id) in self.moved
        ]

    def fetchall(self):
        return self._rows


class TestFilesWithMovedRefs:
    def test_a_file_whose_references_still_resolve_is_not_named(self):
        cr = _PairCursor(moved=[])
        entry = _prepare_entry(_get_digest(), refs={"other.parent": 1469})
        assert loading._get_files_with_moved_refs(cr, {"data/x.xml": entry}) == set()
        assert len(cr.queries) == 1

    def test_a_reference_now_resolving_elsewhere_names_the_file(self):
        cr = _PairCursor(moved=[("other.parent", 1469)])
        stale = loading._get_files_with_moved_refs(
            cr,
            {
                "data/x.xml": _prepare_entry(
                    _get_digest(), refs={"other.parent": 1469}
                ),
                "data/y.xml": _prepare_entry(_get_digest(), refs={"other.kept": 12}),
            },
        )
        assert stale == {"data/x.xml"}

    def test_entries_without_references_ask_the_database_nothing(self):
        cr = _PairCursor(moved=[])
        assert (
            loading._get_files_with_moved_refs(
                cr,
                {
                    "data/x.xml": _prepare_entry(_get_digest()),
                    "data/y.xml": "not-a-dict",
                },
            )
            == set()
        )
        assert cr.queries == []


class TestAReferencedRecordRecreated:
    def _prepare_store(self, files):
        return {"v": loading._DATA_FILE_CHECKSUM_VERSION, "files": files}

    def test_an_unchanged_file_is_re_applied_when_a_reference_moved(self, loader):
        converted, _, _ = loader(
            stored=self._prepare_store(
                {
                    "data/x.xml": _prepare_entry(
                        _get_digest(), refs={"other.parent": 1469}
                    )
                }
            ),
            moved=[("other.parent", 1469)],
        )
        assert converted == ["data/x.xml"], (
            "the file's records hold the ids its refs resolved to; once the "
            "referenced record is deleted and recreated under the same xmlid, "
            "skipping leaves them pointing at the old id -- a theme view's "
            "inherit_id at a configurator view the website upgrade rebuilt"
        )

    def test_an_unchanged_file_whose_references_hold_is_still_skipped(self, loader):
        converted, _, _ = loader(
            stored=self._prepare_store(
                {
                    "data/x.xml": _prepare_entry(
                        _get_digest(), refs={"other.parent": 1469}
                    )
                }
            ),
        )
        assert converted == []

    def test_re_application_records_the_new_resolution(self, loader):
        _, _, stored_json = loader(
            stored=self._prepare_store(
                {
                    "data/x.xml": _prepare_entry(
                        _get_digest(), refs={"other.parent": 1469}
                    )
                }
            ),
            moved=[("other.parent", 1469)],
            resolved={"other.parent": 4042},
        )
        assert stored_json["files"]["data/x.xml"]["refs"] == {"other.parent": 4042}


class TestARecordItsFileRecreated:
    def _prepare_store(self, files):
        return {"v": loading._DATA_FILE_CHECKSUM_VERSION, "files": files}

    def test_an_applied_file_records_the_ids_of_the_records_it_wrote(self, loader):
        _, _, written = loader(
            stored=self._prepare_store({}), ids={"mymod.a": 7, "other.parent": 1469}
        )
        assert written["files"]["data/x.xml"]["ids"] == {"mymod.a": 7}, (
            "an idref entry the file only resolved is a reference, not a record "
            "it wrote"
        )

    def test_a_record_written_under_a_new_id_is_reported_recreated(self, loader):
        loader(
            content=b"<odoo> changed </odoo>",
            stored=self._prepare_store(
                {
                    "data/x.xml": _prepare_entry(
                        _get_digest(), ids={"mymod.a": 7, "mymod.b": 8}
                    )
                }
            ),
            ids={"mymod.a": 9, "mymod.b": 8},
        )
        assert loader.recreated == {"mymod.a": 9}, (
            "a module skipped before this one loaded still holds id 7 wherever "
            "its data points at mymod.a"
        )

    def test_records_written_in_place_report_nothing(self, loader):
        loader(
            content=b"<odoo> changed </odoo>",
            stored=self._prepare_store(
                {"data/x.xml": _prepare_entry(_get_digest(), ids={"mymod.a": 7})}
            ),
            ids={"mymod.a": 7, "mymod.b": 8},
        )
        assert loader.recreated == {}, "a record new to the file moved nothing"

    def test_an_entry_without_ids_reports_nothing(self, loader):
        loader(
            content=b"<odoo> changed </odoo>",
            stored=self._prepare_store({"data/x.xml": _prepare_entry(_get_digest())}),
            ids={"mymod.a": 9},
        )
        assert loader.recreated == {}

    def test_a_skipped_file_reports_nothing(self, loader):
        converted, _, _ = loader(
            stored=self._prepare_store(
                {"data/x.xml": _prepare_entry(_get_digest(), ids={"mymod.a": 7})}
            ),
        )
        assert converted == []
        assert loader.recreated == {}

    def test_an_untracked_load_reports_nothing(self, loader):
        loader(track=False, ids={"mymod.a": 9})
        assert loader.recreated == {}


class TestMarkingModulesHoldingRecreatedRefs:
    def _prepare_package_loader(self, recreated, graph_nodes):
        package_loader = object.__new__(loading._PackageLoader)
        package_loader.recreated_ids = recreated
        package_loader.cr = MagicMock()
        package_loader.registry = MagicMock(
            loaded_modules={"base", "mymod"},
            loading=LoadingPhase(),
        )
        package_loader.package = MagicMock(module_graph=graph_nodes)
        package_loader.package.name = "mymod"
        return package_loader

    def _prepare_node(self, name, state):
        node = MagicMock(state=state)
        node.name = name
        return node

    def test_nothing_recreated_asks_the_database_nothing(self):
        package_loader = self._prepare_package_loader(
            {}, [self._prepare_node("dependent", "installed")]
        )
        package_loader.mark_modules_holding_recreated_refs()
        package_loader.cr.execute.assert_not_called()

    def test_no_module_left_unloaded_asks_the_database_nothing(self):
        package_loader = self._prepare_package_loader(
            {"mymod.a": 9},
            [
                self._prepare_node("base", "installed"),
                self._prepare_node("mymod", "installed"),
                self._prepare_node("upgraded", "to upgrade"),
            ],
        )
        package_loader.mark_modules_holding_recreated_refs()
        package_loader.cr.execute.assert_not_called()

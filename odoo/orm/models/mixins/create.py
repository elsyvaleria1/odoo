import typing
from collections import defaultdict
from collections.abc import Collection
from itertools import chain
from operator import attrgetter
from typing import Self

from odoo.libs.collections import OrderedSet
from odoo.libs.debug_log import DebugLog
from odoo.libs.iteration import PENDING, SENTINEL
from odoo.tools import clean_context
from odoo.tools.cache import TransactionMemo

from ... import decorators as api
from ..._typing import ValuesType
from ...helpers import get_or_create_class_memo, invalid_field_message
from ...primitives import (
    Command,
    NewId,
)
from ...profiling import _OrmProfile
from ._crud_common import (
    _BAD_NAMES_LOG,
    _orm_crud,
    get_forbidden_field_names,
)
from ._model_stubs import _ModelStubs

if typing.TYPE_CHECKING:
    from ..._typing import BaseModel, IdType
    from ...fields.base import Field
    from ...fields.relational._base import _RelationalMulti

_debug = DebugLog(__name__)


class CreateMixin(_ModelStubs):
    __slots__ = ()

    @api.model
    def default_get(self, fields: list[str]) -> ValuesType:
        env = self.env
        _fields = self._fields
        defaults = {}
        parent_fields = defaultdict(list)
        ir_defaults = env.registry.metaschema.model_defaults(env, self._name)
        context_defaults = env._context_defaults

        for name in fields:
            if name in context_defaults:
                defaults[name] = context_defaults[name]
                continue

            field = _fields.get(name)
            if not field:
                continue

            if not (field.default or field.inherited or name in ir_defaults):
                continue

            if not field.company_dependent and name in ir_defaults:
                defaults[name] = ir_defaults[name]
                continue

            if field.default:
                defaults[name] = field.default(self)
                continue

            if field.company_dependent and name in ir_defaults:
                defaults[name] = ir_defaults[name]
                continue

            if (
                field.inherited
                and self._has_field_access(field, "write")
                and field.related_field is not None
            ):
                field = field.related_field
                parent_fields[field.model_name].append(field.name)

        for fname, value in defaults.items():
            field = _fields.get(fname)
            if field is not None:
                value = field.convert_to_cache(value, self, validate=False)
                defaults[fname] = field.convert_to_write(value, self)

        for model, names in parent_fields.items():
            defaults.update(env[model].default_get(names))

        if _debug.logic.enabled:
            _debug.logic(
                "create.default_get",
                model=self._name,
                requested=len(fields),
                resolved=len(defaults),
                from_context=sum(1 for name in fields if name in context_defaults),
                from_ir_default=sum(1 for name in fields if name in ir_defaults),
                parent_models=len(parent_fields),
            )
        return defaults

    @api.model
    def _add_missing_default_values(
        self,
        values: ValuesType,
        _missing_defaults_cache: dict[frozenset[str], list[str]] | None = None,
        only: Collection[str] | None = None,
    ) -> ValuesType:
        vals_keys = frozenset(values)
        cache_key = (
            vals_keys if only is None else vals_keys | {"\0only"} | frozenset(only)
        )
        if _missing_defaults_cache is not None and cache_key in _missing_defaults_cache:
            missing_defaults = _missing_defaults_cache[cache_key]
        else:
            avoid_models = set()

            def collect_models_to_avoid(model: typing.Any) -> None:
                for parent_mname, parent_fname in model._inherits.items():
                    if parent_fname in values:
                        avoid_models.add(parent_mname)
                    else:
                        collect_models_to_avoid(self.env[parent_mname])

            collect_models_to_avoid(self)

            def avoid(field: Field[typing.Any]) -> bool:
                if avoid_models:
                    while field.inherited:
                        field = field.related_field
                        if field.model_name in avoid_models:
                            return True
                return False

            candidates = (
                self._fields.items()
                if only is None
                else [
                    (name, field)
                    for name in only
                    if (field := self._fields.get(name)) is not None
                ]
            )
            missing_defaults = [
                name
                for name, field in candidates
                if name not in values
                if not avoid(field)
            ]
            _debug.logic(
                "create.missing_defaults_computed",
                model=self._name,
                given=len(values),
                missing=len(missing_defaults),
                avoided_parents=len(avoid_models),
                cached=_missing_defaults_cache is not None,
            )
            if _missing_defaults_cache is not None:
                _missing_defaults_cache[cache_key] = missing_defaults

        if missing_defaults:
            defaults = self.default_get(missing_defaults)
            _fields = self._fields
            for name, value in defaults.items():
                field_type = _fields[name].type
                if not value:
                    continue
                if field_type == "many2many":
                    if isinstance(value[0], int):
                        defaults[name] = [Command.set(value)]
                elif field_type == "one2many" and isinstance(value[0], dict):
                    defaults[name] = [Command.create(x) for x in value]
            defaults.update(values)

        else:
            defaults = dict(values)

        if only is not None:
            return defaults

        cls = type(self)
        properties_names = get_or_create_class_memo(
            cls,
            "_properties_field_names__",
            lambda: tuple(
                fname for fname, field in self._fields.items() if field.is_properties
            ),
        )
        for name in properties_names:
            defaults[name] = self._fields[name]._add_default_values(self.env, defaults)

        return defaults

    def _create_check_field_access(
        self, vals_list: list[ValuesType]
    ) -> OrderedSet[str]:
        field_names = OrderedSet(fname for vals in vals_list for fname in vals)
        field_names.update(
            field_name
            for context_key in self.env.context
            if context_key.startswith("default_")
            and (field_name := context_key.removeprefix("default_"))
            and field_name in self._fields
        )
        self._check_fields_write_access(field_names)
        _debug.pipeline(
            "create.field_access_checked",
            model=self._name,
            records=len(vals_list),
            fields=len(field_names),
        )
        return field_names

    def _create_partition_values(
        self, new_vals_list: list[ValuesType]
    ) -> tuple[
        list[dict[str, typing.Any]],
        dict[typing.Any, OrderedSet[Field[typing.Any]]],
    ]:
        data_list = []
        inverses_by_hook: defaultdict[typing.Any, OrderedSet[Field[typing.Any]]] = (
            defaultdict(OrderedSet)
        )
        bypass_access_ids: defaultdict[Field[typing.Any], OrderedSet[IdType]] = (
            defaultdict(OrderedSet)
        )

        for vals in new_vals_list:
            precomputed = vals.pop("__precomputed__", ())
            recompute = vals.pop("__recompute_after_create__", ())

            data: dict[str, typing.Any] = {}
            data["stored"] = stored = {}
            data["inversed"] = inversed = {}
            data["cached_only"] = cached_only = {}
            inherited: defaultdict[str, ValuesType] = defaultdict(dict)
            data["inherited"] = inherited
            data["protected"] = protected = set()
            for key, val in vals.items():
                field = self._fields.get(key)
                if not field:
                    raise ValueError(invalid_field_message(self, key))
                if field.store:
                    stored[key] = val
                delegated = field.inherited and field.related_field is not None
                if delegated:
                    inherited[field.related_field.model_name][key] = val
                elif field.inverse and field not in precomputed:
                    inversed[key] = val
                    inverses_by_hook[field.inverse].add(field)
                elif not field.store and not field.compute:
                    cached_only[key] = val
                # a delegated value was applied by the parent's create, which has
                # returned: protected here, it reads (and caches) as empty from
                # anything an inverse below flushes or computes
                if (
                    field.compute
                    and (not field.readonly or field.precompute)
                    and not delegated
                ) or key in cached_only:
                    protected.update(self.pool.field_computed.get(field, [field]))
                if field.is_many2one and field.bypass_search_access and not self.env.su:
                    if co_id := field.convert_to_cache(val, self):
                        bypass_access_ids[field].add(co_id)

            data["recompute_after_create"] = recompute
            data_list.append(data)

        _debug.pipeline(
            "create.partitioned",
            model=self._name,
            records=len(data_list),
            inverse_hooks=len(inverses_by_hook),
            bypass_access_fields=len(bypass_access_ids),
        )
        for field, co_ids in bypass_access_ids.items():
            self.env[field.comodel_name].browse(co_ids).check_access("read")
        return data_list, inverses_by_hook

    def _create_parent_records(self, data_list: list[dict[str, typing.Any]]) -> None:
        for model_name, parent_name in self._inherits.items():
            parent_data_list = []
            for data in data_list:
                if not data["stored"].get(parent_name):
                    parent_data_list.append(data)
                elif data["inherited"][model_name]:
                    parent = self.env[model_name].browse(data["stored"][parent_name])
                    parent.write(data["inherited"][model_name])

            if parent_data_list:
                _debug.pipeline(
                    "create.parent_records",
                    model=self._name,
                    parent=model_name,
                    records=len(parent_data_list),
                )
                parents = self.env[model_name].create(
                    [data["inherited"][model_name] for data in parent_data_list]
                )
                for parent, data in zip(parents, parent_data_list, strict=True):
                    data["stored"][parent_name] = parent.id

        if shared := self._inherits_shared_id:
            for data in data_list:
                data["stored"]["id"] = data["stored"][shared]

    def _create_apply_inverses(
        self, data_list: list[dict[str, typing.Any]], inverses_by_hook: typing.Any
    ) -> None:
        protected_fields = [(data["protected"], data["record"]) for data in data_list]
        with self.env.protecting(protected_fields):
            for data in data_list:
                if vals := data["cached_only"]:
                    data["record"]._update_cache(vals)
            for fields in inverses_by_hook.values():
                inv_names = {field.name for field in fields}
                inv_rec_ids = []
                for data in data_list:
                    if inv_names.isdisjoint(data["inversed"]):
                        continue
                    record = data["record"]
                    record._update_cache(
                        {
                            fname: value
                            for fname, value in data["inversed"].items()
                            if fname in inv_names and fname not in data["stored"]
                        }
                    )
                    inv_rec_ids.append(record.id)

                inv_records = self.browse(inv_rec_ids)
                _debug.pipeline(
                    "create.inverse_hook",
                    model=self._name,
                    field=next(iter(fields)).name,
                    fields=len(fields),
                    records=len(inv_rec_ids),
                )
                next(iter(fields)).apply_inverse(inv_records)
                inv_relational_fnames = [
                    field.name
                    for field in fields
                    if field.is_x2many and not field.store
                ]
                inv_records.invalidate_recordset(fnames=inv_relational_fnames)

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        if not isinstance(vals_list, (list, tuple)):
            raise TypeError(
                f"create() expects a list of dicts, got {type(vals_list).__name__}"
            )
        if not vals_list:
            return self.browse()

        TransactionMemo.discard_for_model(self.env, self._name)
        prof = _OrmProfile(_orm_crud)

        if self.env.transaction.observers:
            fnames = frozenset(fname for vals in vals_list for fname in vals)
            self.env.transaction.observe_operation(
                "create", self._name, len(vals_list), fnames
            )

        self = self.browse()
        self.check_access("create")

        field_names = self._create_check_field_access(vals_list)
        prof.mark("acl")

        new_vals_list = self._prepare_create_values(vals_list)
        data_list, inverses_by_hook = self._create_partition_values(new_vals_list)
        prof.mark("prep")

        self._create_parent_records(data_list)
        prof.mark("parent")

        with self.env.transaction.create_frame():
            records = self._create(data_list)
            prof.mark("sql")

            self._create_apply_inverses(data_list, inverses_by_hook)
            prof.mark("trigger")

            self._check_created(data_list)

        for data in data_list:
            for field in data["recompute_after_create"]:
                self.env.add_to_compute(field, data["record"])

        if self._check_company_auto:
            records._check_company()
        records._check_fields_write_records(field_names)

        records._access_inputs_written(field_names, created=True)
        if transitions := self.env.registry.verb_transitions.get(self._name):
            records._check_verb_creations(transitions)

        prof.stop("validate")
        prof.report(
            _orm_crud,
            "create %s: %d records, %d fields",
            self._name,
            len(records),
            len(field_names),
        )
        if prof.timed and self.env.transaction.observers:
            self.env.transaction.observe_timing(
                "create", self._name, len(records), prof.elapsed
            )

        _debug.lifecycle(
            "create.records",
            model=self._name,
            records=len(records),
            fields=len(field_names),
            uid=self.env.uid,
            company_checked=self._check_company_auto,
        )
        self._create_update_xmlids(records, vals_list)
        return records

    def _check_created(self, data_list: list[dict[str, typing.Any]]) -> None:
        # The second half of write's two passes: every constraint that reads a
        # field inverted in this batch runs once the inverses have written, on
        # every record of the batch, including one that constrains a stored field
        # as well and was therefore left out of the stored pass in _create.
        inversed_names = {name for data in data_list for name in data["inversed"]}
        if inversed_names:
            self.browse([data["record"].id for data in data_list])._check_fields(
                inversed_names
            )

    def _prepare_create_values(self, vals_list: list[ValuesType]) -> list[ValuesType]:
        bad_names = get_forbidden_field_names(self)

        cls = type(self)
        precompute_readonly = get_or_create_class_memo(
            cls,
            "_precompute_readonly_names__",
            lambda: frozenset(
                fname
                for fname, field in self._fields.items()
                if field.precompute and field.readonly
            ),
        )
        if precompute_readonly:
            bad_names |= precompute_readonly

        missing_defaults_cache: dict[frozenset[str], list[str]] = {}

        result_vals_list = []
        for vals in vals_list:
            vals = self._add_missing_default_values(vals, missing_defaults_cache)

            for fname in bad_names:
                vals.pop(fname, None)
            if self._log_access:
                vals.setdefault("create_uid", self.env.uid)
                vals.setdefault("create_date", self.env.cr.now())
                vals.setdefault("write_uid", self.env.uid)
                vals.setdefault("write_date", self.env.cr.now())

            result_vals_list.append(vals)

        _debug.pipeline(
            "create.values_prepared",
            model=self._name,
            records=len(result_vals_list),
            forbidden=len(bad_names),
            precompute_readonly=len(precompute_readonly),
            default_sets=len(missing_defaults_cache),
        )
        self._add_precomputed_values(result_vals_list)

        return result_vals_list

    def _get_precompute_fields(self) -> tuple[Field[typing.Any], ...]:
        cls = type(self)
        return get_or_create_class_memo(
            cls,
            "_precompute_fields__",
            lambda: tuple(field for field in cls._fields.values() if field.precompute),
        )

    def _get_precompute_scratch_fields(self) -> frozenset[Field[typing.Any]]:
        def collect() -> frozenset[Field[typing.Any]]:
            fields = self._fields
            field_computed = self.pool.field_computed
            field_depends = self.pool.field_depends
            seen: set[Field[typing.Any]] = set()
            todo = list(self._get_precompute_fields())
            while todo:
                field = todo.pop()
                if field in seen:
                    continue
                seen.add(field)
                todo.extend(field_computed.get(field, ()))
                for path in field_depends.get(field, ()):
                    dependency = fields.get(path.split(".", 1)[0])
                    if dependency is not None:
                        todo.append(dependency)
            return frozenset(seen)

        cls = type(self)
        return get_or_create_class_memo(cls, "_precompute_scratch_fields__", collect)

    def _add_precomputed_values(self, vals_list: list[ValuesType]) -> None:
        precomputable = self._get_precompute_fields()
        if not precomputable:
            return

        vals_list_todo = [
            vals
            for vals in vals_list
            if any(field.name not in vals for field in precomputable)
        ]
        # a record whose draft reads its x2many commands otherwise than the
        # create applies them is computed once its lines exist; a required
        # field cannot wait for that (its column refuses NULL), so it is
        # precomputed all the same and computed again after the create
        skipped_ids = {
            id(vals) for vals in self._get_vals_a_draft_reads_otherwise(vals_list)
        }
        if skipped_ids:
            vals_list_todo = [
                vals
                for vals in vals_list_todo
                if id(vals) not in skipped_ids
                or any(
                    field.required and field.name not in vals for field in precomputable
                )
            ]
        recompute_after: dict[int, set[Field[typing.Any]]] = {
            id(vals): {
                field
                for field in precomputable
                if field.required and field.name not in vals
            }
            for vals in vals_list_todo
            if id(vals) in skipped_ids
        }
        if not vals_list_todo:
            return

        records = self.browse().concat(*(self.new(vals) for vals in vals_list_todo))
        for vals in vals_list_todo:
            if (fields_again := recompute_after.get(id(vals))) is not None:
                vals["__recompute_after_create__"] = fields_again
        _debug.pipeline(
            "create.precompute",
            model=self._name,
            records=len(vals_list_todo),
            fields=len(precomputable),
        )

        _fields = self._fields
        given_names: set[str] = set()
        givens = []
        for record, vals in zip(records, vals_list_todo, strict=True):
            given = {
                field: field._get_cache(record.env).get(record._ids[0], SENTINEL)
                for fname in vals
                if (field := _fields.get(fname)) is not None and field.compute
            }
            givens.append(given)
            given_names.update(vals)

        with _debug.perf(
            "create.precompute_values",
            cr=self.env.cr,
            model=self._name,
            records=len(vals_list_todo),
            fields=len(precomputable),
        ):
            try:
                for vals in vals_list_todo:
                    vals["__precomputed__"] = set()

                for field in precomputable:
                    fname = field.name
                    todo = [
                        (record, vals, given)
                        for record, vals, given in zip(
                            records, vals_list_todo, givens, strict=True
                        )
                        if fname not in vals
                        and (
                            id(vals) not in recompute_after
                            or field in recompute_after[id(vals)]
                        )
                    ]
                    if not todo:
                        continue
                    for record, vals, given in todo:
                        if given:
                            self._restore_given_values(
                                typing.cast("BaseModel", record), vals, given
                            )
                    reads_as_su = (
                        field.access_classes is not None and field.compute_sudo
                    )
                    for record, vals, _given in todo:
                        source = record.sudo() if reads_as_su else record
                        vals[fname] = field.convert_to_write(source[fname], self)
                        vals["__precomputed__"].add(field)
            finally:
                self._discard_precompute_scratch(records, given_names)

    def _get_vals_a_draft_reads_otherwise(
        self, vals_list: list[ValuesType]
    ) -> list[ValuesType]:
        # the precompute reads a draft per record, each alone; the create
        # applies the x2many commands of the batch in turn. They disagree
        # where a command reaches a record that exists: an UPDATE links its
        # record into a draft and not into a created one, a record of the
        # batch may delete, detach, update or take a line another one reads,
        # and a CLEAR or SET of a one2many drops from a draft the lines
        # created or linked before it in the same list, which a create keeps.
        # Those records are computed once the batch's lines exist instead
        batch = len(vals_list) > 1
        for vals in vals_list:
            for field, command in self._iter_x2many_commands(vals):
                code = command[0] if isinstance(command, (tuple, list)) else None
                if code == Command.UPDATE or (
                    batch
                    and (
                        code in (Command.DELETE, Command.UNLINK)
                        or (
                            field.is_one2many
                            and code in (Command.LINK, Command.SET, None)
                        )
                    )
                ):
                    _debug.logic(
                        "create.precompute_skipped_commands_reach_records",
                        model=self._name,
                        records=len(vals_list),
                        field=field.name,
                        command=code,
                    )
                    return vals_list
        return [vals for vals in vals_list if self._has_lines_a_create_keeps(vals)]

    def _iter_x2many_commands(
        self, vals: ValuesType
    ) -> typing.Iterator[tuple[Field[typing.Any], typing.Any]]:
        fields = self._fields
        for fname, value in vals.items():
            field = fields.get(fname)
            if field is not None and field.is_x2many and isinstance(value, list):
                for command in value:
                    if not isinstance(command, dict):
                        yield field, command

    def _has_lines_a_create_keeps(self, vals: ValuesType) -> bool:
        commanded: set[Field[typing.Any]] = set()
        for field, command in self._iter_x2many_commands(vals):
            code = command[0] if isinstance(command, (tuple, list)) else None
            replaces = code in (Command.CLEAR, Command.SET)
            if replaces and field in commanded and field.is_one2many:
                return True
            if not replaces:
                commanded.add(field)
        return False

    @staticmethod
    def _restore_given_values(
        record: BaseModel, vals: ValuesType, given: dict[Field[typing.Any], typing.Any]
    ) -> None:
        # a compute that assigns its whole group, or the invalidation of what
        # depends on a field it assigns, may have replaced a given value since
        # the draft was made: only then is it converted and applied again
        id_ = record._ids[0]
        env = record.env
        clobbered = {
            field.name: vals[field.name]
            for field, cache_value in given.items()
            if field._get_cache(env).get(id_, SENTINEL) != cache_value
        }
        if clobbered:
            record._update_cache(clobbered, validate=False)
            for name in clobbered:
                field = record._fields[name]
                given[field] = field._get_cache(env).get(id_, SENTINEL)

    def _discard_precompute_scratch(
        self, records: Self, given_names: Collection[str] = ()
    ) -> None:
        if not records._ids:
            return
        env = self.env
        _fields = self._fields
        fields = self._get_precompute_scratch_fields().union(
            _fields[name] for name in given_names if name in _fields
        )
        # drafts the scratch rows hold through relational values (lines from
        # Command.create, a many2one from a dict) were made for them alone
        scratch: dict[str, OrderedSet[NewId]] = defaultdict(OrderedSet)
        # drafts of existing rows a scratch row was linked into, per inverse
        linked: dict[Field[typing.Any], OrderedSet[NewId]] = defaultdict(OrderedSet)
        field_inverses = self.pool.field_inverses
        todo: list[tuple[BaseModel, Collection[Field[typing.Any]]]] = [
            (typing.cast("BaseModel", records), fields)
        ]
        while todo:
            drafts, drafts_fields = todo.pop()
            ids = drafts._ids
            reached: dict[str, list[NewId]] = defaultdict(list)
            for field in drafts_fields:
                if field.relational and field.comodel_name:
                    cached = field._get_all_cache_ids(env)
                    inverses = field_inverses[field]
                    for id_ in ids:
                        value = cached.get(id_)
                        for co_id in value if type(value) is tuple else (value,):
                            if not isinstance(co_id, NewId):
                                continue
                            if co_id.origin is None:
                                reached[field.comodel_name].append(co_id)
                            else:
                                for invf in inverses:
                                    linked[invf].add(co_id)
                field._invalidate_cache(env, ids)
            for model_name, co_ids in reached.items():
                seen = scratch[model_name]
                fresh = [co_id for co_id in co_ids if co_id not in seen]
                if fresh:
                    seen.update(fresh)
                    comodel = env[model_name]
                    todo.append((comodel.browse(fresh), comodel._fields.values()))
        if _debug.logic.enabled:
            _debug.logic(
                "create.precompute_scratch_discarded",
                model=self._name,
                records=len(records),
                fields=len(fields),
                reached={name: len(ids) for name, ids in scratch.items()},
            )
        scratch[self._name].update(typing.cast("Collection[NewId]", records._ids))
        for invf, drafts_linked in linked.items():
            if scratch_ids := scratch.get(invf.comodel_name):
                invf._forget_draft_links(env, drafts_linked, scratch_ids)
        # Scratch rows never become database rows. Leaving their queued
        # computes behind makes a later flush recompute an empty NewId.
        if env.core.has_pending():
            for field in env.core.get_pending_fields():
                scratch_ids = scratch.get(field.model_name)
                if scratch_ids:
                    env.remove_to_compute(
                        field, env[field.model_name].browse(scratch_ids)
                    )

    @api.model
    def _create(self, data_list: list[ValuesType]) -> Self:
        if not data_list:
            raise ValueError("_create() called with empty data_list")
        prof = _OrmProfile(_orm_crud)

        other_fields: OrderedSet[Field[typing.Any]] = OrderedSet()
        # the backend chooses how to send the rows (INSERT batches, or one COPY
        # that preallocates every id at once), so it is handed all of them
        stored_list = [data["stored"] for data in data_list]
        fnames = sorted({name for stored in stored_list for name in stored})

        columns: list[str] = []
        col_fields: list[Field[typing.Any]] = []
        for fname in fnames:
            field = self._fields[fname]
            if field.column_type:
                columns.append(fname)
                col_fields.append(field)
            else:
                other_fields.add(field)

            if field.is_properties:
                other_fields.add(field)

        self._convert_column_values(stored_list, col_fields)
        ids = self.env.backend.create_rows(self, stored_list, columns, col_fields)
        if self._inherits_shared_id:
            # the id was the backend's to insert, and is the record's from here on
            for stored in stored_list:
                stored.pop("id", None)

        _debug.pipeline(
            "create.rows_inserted",
            model=self._name,
            records=len(ids),
            other_fields=len(other_fields),
        )
        prof.mark("sql")

        records, inverses_update = self._update_create_cache(ids, data_list)
        self.env.transaction.note_created(self._name, records._ids)
        prof.mark("cache")

        for field, updates in inverses_update.items():
            field._update_inverses(
                [
                    (typing.cast("BaseModel", self.browse(record_ids)), value)
                    for value, record_ids in updates.items()
                ]
            )
        prof.mark("inverses")

        records._update_parent_path_on_create()

        protected = [(data["protected"], data["record"]) for data in data_list]
        with self.env.protecting(protected):
            records.modified(self._fields, create=True)

            if other_fields:
                others = records.with_context(clean_context(self.env.context))
                for field in sorted(other_fields, key=attrgetter("_sequence")):
                    field.create(
                        [
                            (
                                typing.cast("BaseModel", other),
                                data["stored"][field.name],
                            )
                            for other, data in zip(others, data_list, strict=True)
                            if field.name in data["stored"]
                        ]
                    )

                records.modified([field.name for field in other_fields], create=True)

        if _debug.logic.enabled and self._constrained_projection_names:
            _debug.logic(
                "create.projection_constraints",
                model=self._name,
                records=len(records),
                fields=sorted(self._constrained_projection_names),
            )
        with self.env.transaction.checking_inserted(self._name, records._ids):
            records._check_fields(
                chain(
                    (name for data in data_list for name in data["stored"]),
                    # a related field without a column is in no `stored` list, and a
                    # new record has a value for it as soon as its path is written
                    self._constrained_projection_names,
                    # an omitted required file is as missing as a False one
                    self._required_attachment_names,
                ),
                {name for data in data_list for name in data["inversed"]},
            )
        records.check_access("create")

        prof.stop("trigger")
        prof.report(_orm_crud, "_create %s: %d records", self._name, len(records))
        return records

    def _convert_column_values(
        self, stored_list: list[ValuesType], col_fields: list[Field[typing.Any]]
    ) -> None:
        converted = [field for field in col_fields if field.column_value_is_cache]
        for stored in stored_list:
            for field in converted:
                if field.name in stored:
                    stored[field.name] = field.convert_to_column(
                        stored[field.name], self, stored
                    )

    def _update_create_cache(
        self, ids: list[int], data_list: list[dict[str, typing.Any]]
    ) -> tuple[Self, dict[Field[typing.Any], defaultdict[typing.Any, list[int]]]]:
        records = self.browse(ids)
        inverses_update: defaultdict[
            Field[typing.Any], defaultdict[typing.Any, list[int]]
        ] = defaultdict(lambda: defaultdict(list))
        common_set_vals = _BAD_NAMES_LOG

        env = self.env
        _stored_x2m_fields = self._get_stored_x2many_fields()
        _stored_scalar_caches = [
            (field, field.name, field._get_cache(env), default)
            for field, default in self._get_stored_scalar_fields()
        ]

        _fields = self._fields
        _field_inverses = self.pool.field_inverses

        vals_list = []
        set_vals_list = []
        record_ids = []
        for data, record in zip(
            data_list, records.with_context(bin_size=False), strict=True
        ):
            data["record"] = record
            vals = dict(
                {k: v for d in data["inherited"].values() for k, v in d.items()},
                **data["stored"],
            )
            vals_list.append((vals, record, data["stored"]))
            set_vals_list.append(common_set_vals.union(vals))
            record_ids.append(record._ids[0])

        supplied = set().union(*set_vals_list) if set_vals_list else set()
        # a new row has no relation rows: the empty value is primed in the
        # creating scope and mirrored to the superuser one, where a compute_sudo
        # compute reads it -- unmirrored, that read fetched the relation
        for x2m_field in _stored_x2m_fields:
            x2m_field._update_cache(records, (), created=True)
        for _field, fname, cache, default in _stored_scalar_caches:
            if fname not in supplied:
                cache.update(dict.fromkeys(record_ids, default))
            else:
                cache.update(
                    (rid, default)
                    for rid, set_vals in zip(record_ids, set_vals_list, strict=True)
                    if fname not in set_vals
                )

        for vals, record, stored in vals_list:
            for fname, value in vals.items():
                field = _fields[fname]
                if field.is_x2many:
                    continue
                if field.column_value_is_cache:
                    if fname not in stored:
                        continue
                    cache_value = field.convert_to_cache(value, record, validate=False)
                else:
                    cache_value = field.convert_to_cache(value, record)
                field._update_cache(record, cache_value)
                if (
                    field.is_many2one or field.is_many2one_reference
                ) and _field_inverses[field]:
                    inverses_update[field][cache_value].append(record.id)

        _debug.perf.count(
            "create.cache_primed",
            model=self._name,
            records=len(record_ids),
            x2many_fields=len(_stored_x2m_fields),
            scalar_fields=len(_stored_scalar_caches),
            supplied=len(supplied),
            inverse_updates=sum(len(updates) for updates in inverses_update.values()),
        )
        return records, inverses_update

    def _get_stored_x2many_fields(self) -> tuple[_RelationalMulti, ...]:
        cls = type(self)
        return get_or_create_class_memo(
            cls,
            "_stored_tomany_fields__",
            lambda: tuple(
                typing.cast("_RelationalMulti", field)
                for field in cls._fields.values()
                if field.store and field.is_x2many
            ),
        )

    def _get_stored_scalar_fields(
        self,
    ) -> tuple[tuple[Field[typing.Any], typing.Any], ...]:
        cls = type(self)
        return get_or_create_class_memo(
            cls,
            "_stored_scalar_fields__",
            lambda: tuple(
                (field, PENDING if field.is_stored_computed else None)
                for field in cls._fields.values()
                if field.store and not field.is_x2many
            ),
        )

    @api.model
    def _create_update_xmlids(self, records: Self, vals_list: list[ValuesType]) -> None:
        import_module = self.env.context.get("_import_current_module")
        if not import_module:
            return

        noupdate = self.env.context.get("noupdate", False)
        xids = (v.get("id") for v in vals_list)
        entries = [
            {
                "xml_id": (xid if "." in xid else f"{import_module}.{xid}"),
                "record": rec,
                "noupdate": noupdate,
            }
            for rec, xid in zip(records, xids, strict=True)
            if xid and isinstance(xid, str)
        ]
        _debug.lifecycle(
            "create.xmlids_updated",
            model=self._name,
            module=import_module,
            records=len(records),
            xmlids=len(entries),
            noupdate=noupdate,
        )
        self.env.registry.xmlids.update(self.env, entries)

    def _update_parent_path_on_create(self) -> None:
        if not self._parent_store:
            return

        updated = self.env.backend.set_parent_paths(self, self.ids)

        _debug.perf.count(
            "create.parent_path_updated",
            model=self._name,
            records=len(self),
            rows=len(updated),
        )
        self._fields["parent_path"]._update_cache_items(self.env, updated)

import itertools
import logging
import typing
from collections import defaultdict
from collections.abc import Callable, Collection
from typing import Self

from odoo.libs.debug_log import DebugLog

from ..._typing import ValuesType
from ...primitives import MAGIC_COLUMNS, PREFETCH_MAX, Command
from ._model_stubs import _ModelStubs

if typing.TYPE_CHECKING:
    from ..._typing import BaseModel, IdType
    from ...fields import Field
else:
    type Field[T] = typing.Any

_logger = logging.getLogger("odoo.models")
_debug = DebugLog(__name__)

COPY_TRANSLATIONS_STORED = "__copy_translations_stored"


class CopyMixin(_ModelStubs):
    __slots__ = ()

    def copy_data(self, default: ValuesType | None = None) -> list[ValuesType | None]:
        if len(set(self._ids)) != len(self._ids):
            raise ValueError(
                f"Cannot copy {self._name} records: the same record appears "
                f"more than once in {self}. Deduplicate the recordset first "
                f"(e.g. `records.browse(unique(records._ids))`); copying it "
                f"twice over would yield a single copy."
            )

        vals_list: list[ValuesType | None] = []
        default = dict(default or {})
        if "__copy_data_seen" not in self.env.context:
            self = self.with_context(__copy_data_seen=defaultdict(set))

        blacklist = set(MAGIC_COLUMNS + ["parent_path"])
        whitelist = {
            name for name, field in self._fields.items() if not field.inherited
        }

        def blacklist_given_fields(model: typing.Any) -> None:
            for parent_model, parent_field in model._inherits.items():
                blacklist.add(parent_field)
                if parent_field in default:
                    blacklist.update(set(self.env[parent_model]._fields) - whitelist)
                else:
                    blacklist_given_fields(self.env[parent_model])

        blacklist_given_fields(self)

        fields_to_copy = {
            name: field
            for name, field in self._fields.items()
            if field.copy
            and name not in default
            and name not in blacklist
            and self._has_field_access(field, "read")
        }
        unreadable = [
            name
            for name, field in fields_to_copy.items()
            if (field.is_one2many or field.is_many2many)
            and not self.env[field._get_comodel_name()].browse().has_access("read")
        ]
        for name in unreadable:
            del fields_to_copy[name]
        if unreadable:
            _debug.logic(
                "copy.unreadable_comodel_withheld", model=self._name, fields=unreadable
            )
        withheld = [
            name
            for name, field in fields_to_copy.items()
            if not self._has_field_access(field, "write")
        ]
        for name in withheld:
            del fields_to_copy[name]
        if withheld:
            _debug.logic("copy.write_gated_withheld", model=self._name, fields=withheld)

        readable_by_field = {
            name: set(
                self._filtered_field_access(field)[name]._filtered_access("read")._ids
            )
            for name, field in fields_to_copy.items()
            if field.is_many2many
        }
        masked_by_field = {
            name: masked
            for name, field in fields_to_copy.items()
            if field.access_classes is not None
            and (masked := self._field_masked_ids(field))
        }

        seen_map = self.env.context["__copy_data_seen"]
        _debug.pipeline(
            "copy.data",
            model=self._name,
            records=len(self),
            fields=len(fields_to_copy),
            blacklisted=len(blacklist),
            defaults=len(default),
        )

        for record in self:
            if record.id in seen_map[record._name]:
                _debug.logic(
                    "copy.data_seen_skipped", model=self._name, record=record.id
                )
                vals_list.append(None)
                continue
            seen_map[record._name].add(record.id)

            vals = default.copy()

            for name, field in fields_to_copy.items():
                if record.id in masked_by_field.get(name, ()):
                    continue
                if field.is_one2many:
                    lines = record[name].sorted(key="id")
                    lines = lines.filtered(
                        lambda line: line.id not in seen_map[line._name]
                    ).with_prefetch(lines._prefetch_ids)
                    vals[name] = [
                        Command.create(line) for line in lines.copy_data() if line
                    ]
                elif field.is_many2many:
                    readable = readable_by_field[name]
                    vals[name] = [
                        Command.set(
                            [id_ for id_ in record[name]._ids if id_ in readable]
                        )
                    ]
                else:
                    vals[name] = field.convert_to_write(record[name], record)
            vals_list.append(vals)
        return vals_list

    def copy_translations(self, new: Self, excluded: Collection[str] = ()) -> None:
        excluded = frozenset(excluded)
        old = self
        if "__copy_translations_seen" not in old.env.context:
            old = old.with_context(__copy_translations_seen=defaultdict(set))
        if COPY_TRANSLATIONS_STORED not in old.env.context:
            old = old.with_context(**{COPY_TRANSLATIONS_STORED: {}})
        seen_map = old.env.context["__copy_translations_seen"]
        if old.id in seen_map[old._name]:
            _debug.logic(
                "copy.translations_seen_skipped", model=old._name, record=old.id
            )
            return
        seen_map[old._name].add(old.id)
        valid_langs = {*self.env.registry.locale.installed_langs(self.env), "en_US"}
        multilingual = valid_langs != {self.env.lang or "en_US"}

        for name, field in old._fields.items():
            if not field.copy:
                continue

            if (
                field.inherited
                and field.related is not None
                and field.related.split(".")[0] in excluded
            ):
                continue

            if field.is_one2many and field.name not in excluded:
                old_lines = (
                    old.with_context(active_test=False)[name]
                    .sorted(key="id")
                    .with_env(old.env)
                )
                new_lines = (
                    new.with_context(active_test=False)[name]
                    .sorted(key="id")
                    .with_env(new.env)
                )
                if len(old_lines) != len(new_lines):
                    _logger.debug(
                        "copy_translations: skipping one2many field %r on %s: "
                        "%d source line(s) but %d copied line(s) "
                        "(copy_data recursion guard dropped lines)",
                        name,
                        old._name,
                        len(old_lines),
                        len(new_lines),
                    )
                    _debug.logic(
                        "copy.translations_o2m_mismatch",
                        model=old._name,
                        field=name,
                        source_lines=len(old_lines),
                        copied_lines=len(new_lines),
                    )
                    continue
                for old_line, new_line in zip(old_lines, new_lines, strict=True):
                    old_line.copy_translations(new_line)

            elif (
                multilingual
                and field.translate
                and field.store
                and name not in excluded
                and old[name]
            ):
                old._copy_field_translations(new, name, field, valid_langs)
        _debug.pipeline(
            "copy.translations",
            model=old._name,
            record=old.id,
            target=new.id,
            excluded=len(excluded),
            langs=len(valid_langs),
            multilingual=multilingual,
        )

    def _get_copied_stored_translations(
        self, field: Field[typing.Any]
    ) -> dict[str, str] | None:
        stored_by_field = self.env.context.get(COPY_TRANSLATIONS_STORED)
        record_id = self._ids[0]
        if stored_by_field is None or not isinstance(record_id, int):
            return field._get_stored_translations(typing.cast("BaseModel", self))
        stored: dict[IdType, dict[str, str] | None] = stored_by_field.setdefault(
            (self._name, field.name), {}
        )
        if record_id not in stored:
            batch = self.browse(
                [
                    record_id,
                    *itertools.islice(
                        (
                            id_
                            for id_ in self._prefetch_ids
                            if isinstance(id_, int)
                            and id_ != record_id
                            and id_ not in stored
                        ),
                        PREFETCH_MAX - 1,
                    ),
                ]
            )
            batch.flush_recordset([field.name])
            read = field._get_stored_translations_multi(batch)
            for id_ in batch._ids:
                stored[id_] = read.get(id_)
            if _debug.perf.enabled:
                _debug.perf.count(
                    "copy.stored_translations_batch",
                    model=self._name,
                    field=field.name,
                    records=len(batch),
                )
        return stored[record_id]

    def _copy_field_translations(
        self, new: Self, name: str, field: Field[typing.Any], valid_langs: set[str]
    ) -> None:
        old_stored_translations = self._get_copied_stored_translations(field)
        if not old_stored_translations:
            return
        lang = self.env.lang or "en_US"
        if field.translate is True:
            translations: dict[str, typing.Any] = {
                k: v
                for k, v in old_stored_translations.items()
                if k in valid_langs and k != lang
            }
        else:
            old_translations = {
                k: old_stored_translations.get(f"_{k}", v)
                for k, v in old_stored_translations.items()
                if k in valid_langs
            }
            source_term = old_translations.pop(lang, None)
            if source_term is None:
                source_term = old_translations.get("en_US")
            if source_term is None:
                _debug.logic(
                    "copy.field_translations_no_source",
                    model=self._name,
                    field=name,
                    record=self.id,
                    lang=lang,
                )
                return
            translation_dictionary = field.get_translation_dictionary(
                source_term,
                old_translations,
            )
            translations = defaultdict(dict)
            for from_lang_term, to_lang_terms in translation_dictionary.items():
                for term_lang, to_lang_term in to_lang_terms.items():
                    translations[term_lang][from_lang_term] = to_lang_term
        if not translations:
            _debug.logic(
                "copy.field_translations_none",
                model=self._name,
                field=name,
                record=self.id,
            )
            return
        _debug.logic(
            "copy.field_translations",
            model=self._name,
            field=name,
            record=self.id,
            target=new.id,
            terms=field.translate is not True,
            langs=len(translations),
        )
        new.update_field_translations(name, translations)

    def _copy_translations_of_renamed_field(
        self,
        new: Self,
        field_name: str,
        rename: Callable[[Self, str], str],
    ) -> None:
        field = self._fields[field_name]
        assert field.translate is True and field.store, (
            f"{field} is not a stored translate=True field"
        )
        if new[field_name] != rename(self, self[field_name]):
            return
        stored_translations = self._get_copied_stored_translations(field)
        if not stored_translations:
            return
        valid_langs = {*self.env.registry.locale.installed_langs(self.env), "en_US"}
        renamed = {
            lang: rename(self.with_context(lang=lang), term)
            for lang, term in stored_translations.items()
            if lang in valid_langs
        }
        _debug.logic(
            "copy.renamed_field_translations",
            model=self._name,
            field=field_name,
            record=self.id,
            target=new.id,
            langs=len(renamed),
        )
        field._update_cache(new, renamed, dirty=True)

    def copy(self, default: ValuesType | None = None) -> Self:
        vals_list = self.with_context(active_test=False).copy_data(default)
        pairs = [
            (rec, vals)
            for rec, vals in zip(self, vals_list, strict=True)
            if vals is not None
        ]
        _debug.pipeline(
            "copy.records",
            model=self._name,
            records=len(self),
            copyable=len(pairs),
            default_keys=len(default or ()),
        )
        if not pairs:
            return self.browse()
        new_records = self.create([vals for _, vals in pairs])
        _debug.lifecycle(
            "copy.records_created",
            model=self._name,
            sources=len(pairs),
            created=len(new_records),
        )
        sources = self.browse([old_record.id for old_record, _ in pairs]).with_context(
            **{COPY_TRANSLATIONS_STORED: {}}
        )
        for old_record, new_record in zip(sources, new_records, strict=True):
            old_record.copy_translations(new_record, excluded=default or ())
        return new_records

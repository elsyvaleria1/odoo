from hashlib import sha256
from json import dumps

from odoo import api, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, TransactionMemo, float_repr

from .account_move import MAX_HASH_VERSION

_debug = DebugLog(__name__)

LAST_UNPREFIXED_HASH_VERSION = 3


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_fields_integrity_hash(self) -> list:
        hash_version = self.env.context.get("hash_version", MAX_HASH_VERSION)
        if hash_version == 1:
            return ["date", "journal_id", "company_id"]
        elif hash_version in (2, 3, 4, 5):
            return ["name", "date", "journal_id", "company_id"]
        raise NotImplementedError(f"hash_version={hash_version} doesn't exist")

    @api.model
    def _get_domain_move_hash(self, common_domain=False, force_hash=False):
        domain = Domain(common_domain or Domain.TRUE) & Domain("state", "=", "posted")
        if force_hash:
            return domain
        return domain & Domain("restrict_mode_hash_table", "=", True)

    @api.model
    def _is_move_restricted(self, move, force_hash=False) -> bool:
        return bool(
            move.filtered_domain(self._get_domain_move_hash(force_hash=force_hash))
        )

    def _serialize_hash_chains(self, chains) -> None:
        # Under REPEATABLE READ a concurrent poster's committed entries are
        # invisible, so its chain looks gapped or unhashed. Every poster
        # rewrites the row its new hashes build on (the chain's last hashed
        # entry, or the journal while the chain has none), so the later of two
        # posters to one chain fails to serialize and is retried on a snapshot
        # that sees the other's entries, while other chains stay unblocked.
        predecessors = self.env["account.move"].concat(
            *(chain["last_move_hashed"] for chain in chains)
        )
        journals = self.env["account.journal"].concat(
            *(chain["journal"] for chain in chains if not chain["last_move_hashed"])
        )
        _debug.logic(
            "hash_chains_serialized", predecessors=predecessors, journals=journals
        )
        for records in (predecessors, journals):
            if records:
                self.env.cr.execute(
                    SQL(
                        "UPDATE %s SET write_date = write_date WHERE id = ANY(%s)",
                        SQL.identifier(records._table),
                        records.ids,
                    )
                )

    def _write_inalterable_hashes(self, move_hashes) -> None:
        self.flush_recordset(["inalterable_hash"])
        self._write_multi([{"inalterable_hash": move_hashes[move]} for move in self])
        self.modified(["inalterable_hash"])
        self.invalidate_recordset(["inalterable_hash"])
        TransactionMemo.discard_for_model(self.env, self._name, ["inalterable_hash"])

    @api.model
    def _hash_chains(self, chains) -> None:
        if not chains:
            return
        moves = self.env["account.move"].concat(*(chain["moves"] for chain in chains))
        moves_sudo = moves.sudo()
        move_hashes = {}
        for chain in chains:
            _debug.pipeline(
                "hashing_chain",
                moves=chain["moves"],
                warnings=chain.get("warnings"),
            )
            move_hashes.update(
                chain["moves"]
                .with_env(moves_sudo.env)
                ._get_hashes(chain["previous_hash"])
            )
        moves_sudo._write_inalterable_hashes(move_hashes)
        moves._message_log_batch(
            bodies=dict.fromkeys(
                moves.ids, self.env._("This journal entry has been secured.")
            )
        )
        if not all(moves.journal_id.mapped("restrict_mode_hash_table")):
            self.env["res.groups"]._activate_group_account_secured()

    def _hash_moves(self, **kwargs) -> None:
        chains_to_hash = self._get_chains_to_hash(serialize=True, **kwargs)
        _debug.pipeline(
            "_hash_moves", records=self, chains_to_hash_count=len(chains_to_hash)
        )
        self._hash_chains(chains_to_hash)

    def _get_domain_chain_hash(
        self, last_move_in_chain, last_move_hashed, common_domain, include_pre_last_hash
    ):
        domain = self.env["account.move"]._get_domain_move_hash(
            [
                *common_domain,
                ("sequence_number", "<=", last_move_in_chain.sequence_number),
                ("inalterable_hash", "=", False),
            ],
            force_hash=True,
        )
        if last_move_hashed and not include_pre_last_hash:
            domain &= Domain("sequence_number", ">", last_move_hashed.sequence_number)
        return domain

    def _get_chain_warnings(
        self, moves_to_hash, last_move_hashed, include_pre_last_hash, journal
    ):
        warnings = set()
        if not moves_to_hash:
            warnings.add("no_document")
            _debug.logic("chain_empty", last_move=last_move_hashed)
            return warnings

        seq_numbers = moves_to_hash.mapped("sequence_number")
        if last_move_hashed and not include_pre_last_hash:
            start = last_move_hashed.sequence_number + 1
        else:
            start = seq_numbers[0]
        if seq_numbers != list(range(start, seq_numbers[-1] + 1)):
            warnings.add("gap")

        has_unreconciled = journal.type in (
            "bank",
            "cash",
            "credit",
        ) and bool(
            self.env["account.bank.statement.line"].search_count(
                [
                    ("move_id", "in", moves_to_hash.ids),
                    ("is_reconciled", "=", False),
                ],
                limit=1,
            )
        )
        if has_unreconciled:
            warnings.add("unreconciled")
        _debug.logic(
            "chain_warnings_collected",
            moves=moves_to_hash,
            last_move=last_move_hashed,
            start=start,
            warnings=warnings,
        )
        return warnings

    def _set_chain_warnings(self, chain, include_pre_last_hash=False) -> set:
        if "warnings" not in chain:
            chain["warnings"] = self._get_chain_warnings(
                chain["moves"].with_env(self.env),
                chain["last_move_hashed"],
                include_pre_last_hash,
                chain["journal"],
            )
        return chain["warnings"]

    @_debug.perf.timed
    def _get_chain_info(
        self,
        force_hash=False,
        include_pre_last_hash=False,
        early_stop=False,
        with_warnings=True,
    ):
        if not self:
            return False

        last_move_in_chain = (
            self.env["account.move"]
            .sudo()
            .search_fetch(
                domain=[("id", "in", self.ids)],
                field_names=[
                    "sequence_prefix",
                    "sequence_number",
                    "journal_id",
                    "state",
                    "restrict_mode_hash_table",
                ],
                order="sequence_number desc",
                limit=1,
            )
        )
        journal = last_move_in_chain.journal_id
        if not self._is_move_restricted(last_move_in_chain, force_hash=force_hash):
            _debug.logic(
                "chain_not_restricted_no_hashing",
                journal=journal,
                sequence_prefix=last_move_in_chain.sequence_prefix,
                force=force_hash,
            )
            return False

        common_domain = [
            ("journal_id", "=", journal.id),
            ("sequence_prefix", "=", last_move_in_chain.sequence_prefix),
        ]
        last_move_hashed = (
            self.env["account.move"]
            .sudo()
            .search_fetch(
                [
                    *common_domain,
                    ("inalterable_hash", "!=", False),
                ],
                ["sequence_number", "inalterable_hash"],
                order="sequence_number desc",
                limit=1,
            )
        )

        domain = self._get_domain_chain_hash(
            last_move_in_chain,
            last_move_hashed,
            common_domain,
            include_pre_last_hash,
        )
        if early_stop:
            return self.env["account.move"].sudo().search_count(domain, limit=1)
        moves_to_hash = (
            self.env["account.move"]
            .sudo()
            .search_fetch(domain, ["sequence_number"], order="sequence_number")
        )
        moves = moves_to_hash.sudo(False)
        info = {
            "journal": journal,
            "previous_hash": last_move_hashed.inalterable_hash,
            "last_move_hashed": last_move_hashed,
            "moves": moves,
            "remaining_moves": self - moves,
        }
        if with_warnings:
            self._set_chain_warnings(info, include_pre_last_hash)
        _debug.logic(
            "chain_last_hashed_hash",
            journal=journal,
            sequence_prefix=last_move_in_chain.sequence_prefix,
            sequence_number=last_move_hashed.sequence_number,
            moves_to_hash_count=len(moves_to_hash),
            warnings=info.get("warnings"),
        )
        return info

    @_debug.perf.timed
    def _get_chains_to_hash(
        self,
        force_hash=False,
        raise_if_gap=True,
        raise_if_no_document=True,
        raise_if_unreconciled=True,
        include_pre_last_hash=False,
        early_stop=False,
        serialize=False,
    ):
        chains = []
        for journal, journal_moves in self.grouped("journal_id").items():
            for chain_moves in journal_moves.grouped("sequence_prefix").values():
                chain_info = chain_moves._get_chain_info(
                    force_hash=force_hash,
                    include_pre_last_hash=include_pre_last_hash,
                    early_stop=early_stop,
                )

                if not chain_info:
                    _debug.logic(
                        "nothing_hash", journal=journal, chain_moves=chain_moves
                    )
                    continue
                if early_stop:
                    return True

                if "unreconciled" in chain_info["warnings"] and not force_hash:
                    # hashing a statement line before it is reconciled would
                    # forbid reconciling it; the chain is secured once it is
                    _debug.logic(
                        "chain_deferred_unreconciled",
                        journal=journal,
                        moves=chain_info["moves"],
                    )
                    continue
                chains.append(chain_info)
        if early_stop:
            return False
        if serialize:
            self._serialize_hash_chains(chains)

        for chain_info in chains:
            warnings = chain_info["warnings"]
            if raise_if_unreconciled and "unreconciled" in warnings:
                raise UserError(
                    self.env._(
                        "An error occurred when computing the inalterability. All entries have to be reconciled."
                    )
                )

            if raise_if_no_document and "no_document" in warnings:
                raise UserError(
                    self.env._(
                        "This move could not be locked either because "
                        "some move with the same sequence prefix has a higher number. You may need to resequence it."
                    )
                )
            if raise_if_gap and "gap" in warnings:
                raise UserError(
                    self.env._(
                        "An error occurred when computing the inalterability. A gap has been detected in the sequence."
                    )
                )
        return chains

    def _recompute_integrity_hash(self, previous_hash, start_version) -> tuple:
        self.check_singleton()
        # Versions never decrease along a chain: a hash older than its
        # predecessor's version is itself the corruption.
        if not previous_hash:
            min_version = 1
        elif previous_hash.startswith("$"):
            min_version = int(previous_hash.split("$")[1])
        else:
            min_version = min(start_version, LAST_UNPREFIXED_HASH_VERSION)
        stored_hash = self.inalterable_hash or ""
        if stored_hash.startswith("$"):
            version = stored_hash.split("$")[1]
            if not (
                version.isdigit()
                and max(min_version, LAST_UNPREFIXED_HASH_VERSION + 1)
                <= int(version)
                <= MAX_HASH_VERSION
            ):
                _debug.logic(
                    "hash_version_rejected",
                    move=self,
                    version=version,
                    min_version=min_version,
                )
                return None, min_version
            versions = [int(version)]
        else:
            versions = range(min_version, LAST_UNPREFIXED_HASH_VERSION + 1)
        computed_hash = None
        for version in versions:
            computed_hash = self.with_context(hash_version=version)._get_hashes(
                previous_hash
            )[self]
            if computed_hash == stored_hash:
                return computed_hash, version
        return computed_hash, max(min_version, start_version)

    @_debug.perf.timed
    def _get_hashes(self, previous_hash):
        hash_version = self.env.context.get("hash_version", MAX_HASH_VERSION)

        def get_field_as_string(obj, field_name):
            field = obj._fields[field_name]
            field_value = obj[field_name]
            if field.type == "many2one":
                field_value = field_value.id
            if field.type == "monetary" and hash_version >= 3:
                currency = (
                    obj[field.get_currency_field(obj)]
                    if hash_version >= 5
                    else obj.currency_id
                )
                return float_repr(field_value, currency.decimal_places)
            return str(field_value)

        move2hash = {}
        previous_hash = previous_hash or ""
        _debug.pipeline(
            "hash_chain_start",
            moves=self,
            hash_version=hash_version,
            chained=bool(previous_hash),
        )

        for move in self:
            if previous_hash and previous_hash.startswith("$"):
                previous_hash = previous_hash.split("$")[2]
            values = {}
            for fname in move._get_fields_integrity_hash():
                values[fname] = get_field_as_string(move, fname)

            for line in move.line_ids:
                for fname in line._get_fields_integrity_hash():
                    k = "line_%d_%s" % (line.id, fname)
                    values[k] = get_field_as_string(line, fname)
            current_record = dumps(
                values,
                sort_keys=True,
                ensure_ascii=True,
                indent=None,
                separators=(",", ":"),
            )
            hash_string = sha256(
                (previous_hash + current_record).encode("utf-8")
            ).hexdigest()
            move2hash[move] = (
                f"${hash_version}${hash_string}"
                if hash_version > LAST_UNPREFIXED_HASH_VERSION
                else hash_string
            )
            previous_hash = move2hash[move]
        _debug.pipeline(
            "hashes_computed",
            moves=self,
            count=len(move2hash),
            hash_version=hash_version,
        )
        return move2hash

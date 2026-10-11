from typing import Any

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.http import request


class WizardBaseExplainAccess(models.TransientModel):
    _name = "wizard.base.explain.access"
    _description = "Why Can I See This?"
    _access_verbs = {
        "explain_others": models.Verb(requires="read", methods=("action_who_can",)),
    }

    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Person",
        default=lambda self: self.env.user,
        required=True,
        help="Whose access is explained. Someone else's is for the access "
        "administrators, and logged.",
    )
    record_ref = fields.Reference(
        selection="_selection_record_models",
        string="Record",
        required=True,
    )
    operation = fields.Char(
        default="read",
        required=True,
        help="read, write, create, unlink, or a verb the model declares (post, "
        "confirm, ...).",
    )
    explanation = fields.Text(readonly=True)
    who_can = fields.Text(readonly=True)

    @api.model
    def _selection_record_models(self) -> list[tuple[str, str]]:
        registry = self.env.registry
        return sorted(
            (name, registry[name]._description or name)
            for name in registry.models
            if not registry[name]._abstract and not registry[name]._transient
        )

    @api.model
    def default_get(self, fields: list[str]) -> dict[str, Any]:
        values = super().default_get(fields)
        model_name = self.env.context.get("explain_model")
        record_id = self.env.context.get("explain_id")
        if model_name in self.env and record_id and "record_ref" in fields:
            values["record_ref"] = f"{model_name},{int(record_id)}"
        return values

    def _check_record(self) -> models.BaseModel:
        self.check_singleton()
        record = self.record_ref
        if not record or not record.exists():
            raise UserError(self.env._("Choose a record that exists."))
        operations = {"read", "write", "create", "unlink"} | set(
            self.env.registry.model_verbs.get(record._name, {})
        )
        if self.operation not in operations:
            raise UserError(
                self.env._(
                    "%(model)s knows no operation %(operation)s: choose one of "
                    "%(operations)s.",
                    model=record._name,
                    operation=self.operation,
                    operations=", ".join(sorted(operations)),
                )
            )
        return record

    def action_explain(self) -> dict[str, Any]:
        record = self._check_record()
        Access = self.env["ir.access"]
        explanation = Access._explain_as(self.user_id, record, self.operation)
        me = self.env.user
        if self.user_id != me:
            self.check_access("explain_others")
        detailed = self.has_access("explain_others") or (
            self.user_id == me and bool(request and request.session.debug)
        )
        self.explanation = self._render(explanation, detailed)
        return self._reopen()

    def action_who_can(self) -> dict[str, Any]:
        record = self._check_record()
        users = self.env["res.users"]
        lines = [
            f"- {users.browse(entry['user']).name}: {', '.join(entry['through'])}"
            for entry in self.env["ir.access"]._who_can(record, self.operation)
        ]
        self.who_can = "\n".join(lines) or self.env._("Nobody.")
        return self._reopen()

    def _reopen(self) -> dict[str, Any]:
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def _render(self, explanation: dict, detailed: bool, depth: int = 0) -> str:
        env = self.env
        groups = env["res.groups"]
        users = env["res.users"]
        pad = "    " * depth
        record = env[explanation["model"]].browse(explanation["record"])
        name = (
            record.display_name
            if record.has_access("read")
            else env._("a record you cannot read")
        )
        verdict = (
            env._("may %(operation)s", operation=explanation["operation"])
            if explanation["allowed"]
            else env._("may not %(operation)s", operation=explanation["operation"])
        )
        person = users.browse(explanation["user"]).name
        lines = [f"{pad}{person} {verdict} {name} ({record._name}, {record.id})."]
        if not detailed:
            if not explanation["allowed"]:
                lines.extend(pad + line for line in self._refusal_lines(explanation))
            return "\n".join(lines)
        if not explanation["model_allowed"]:
            lines.append(pad + env._("No group held grants this operation at all."))
        for entry in explanation["permissions"]:
            reach = f" ({entry['reach']})" if entry["reach"] else ""
            state = env._("reaches it") if entry["admits"] else env._("does not")
            lines.append(f"{pad}+ {entry['name']}{reach}: {state}")
            for grant in entry["held_through"]:
                scope = ", ".join(
                    env["res.company"].browse(grant["companies"]).mapped("name")
                ) or env._("every company")
                until = env._(" until %s", grant["date_to"]) if grant["date_to"] else ""
                lines.append(
                    f"{pad}    {env._('held through')} "
                    f"{groups.browse(grant['group']).full_name} "
                    f"({grant['cause']}, {scope}{until})"
                )
        for entry in [
            *explanation["guards"],
            *filter(None, [explanation["own_guard"]]),
        ]:
            state = env._("passes") if entry["admits"] else env._("refuses")
            lines.append(f"{pad}! {entry['name']}: {state}")
        for parent in explanation["parents"]:
            lines.append(pad + env._("Through %(field)s:", field=parent["field"]))
            lines.append(self._render(parent, detailed, depth + 1))
        if explanation["requires"]:
            lines.append(pad + env._("The verb requires:"))
            lines.append(self._render(explanation["requires"], detailed, depth + 1))
        for obligation in explanation["obligations"]:
            covered = obligation.get("covered")
            state = (
                env._("does not apply")
                if not obligation["applies"]
                else env._("approved")
                if covered
                else env._("not approved")
                if covered is False
                else env._("applies")
            )
            lines.append(f"{pad}~ {obligation['name']} ({obligation['mode']}): {state}")
        for source in explanation["graph"]:
            partner = env["res.partner"].browse(source["partner"])
            holder = (
                groups.browse(source["group"]).full_name
                if not partner
                else partner.display_name
                if partner.has_access("read")
                else env._("someone")
            )
            node = env[explanation["model"]].browse(source["node"])
            where = (
                node.display_name
                if node.has_access("read")
                else env._("a folder you cannot read")
            )
            inherited = env._(" (inherited)") if source["inherited"] else ""
            lines.append(
                f"{pad}> {holder}: {source['role']} {env._('from')} {where}{inherited}"
            )
        hidden = [
            entry["string"] or entry["field"]
            for entry in explanation["fields"]
            if not entry["read"]
        ]
        if hidden:
            lines.append(pad + env._("Hidden fields: %s", ", ".join(hidden)))
        if not explanation["allowed"]:
            lines.append(pad + self._refusal_lines(explanation)[-1])
        return "\n".join(lines)

    def _refusal_lines(self, explanation: dict) -> list[str]:
        env = self.env
        refusing = [
            guard["name"]
            for guard in [*explanation["guards"], explanation["own_guard"]]
            if guard and not guard["admits"]
        ]
        ask = env["ir.access"]._whom_to_ask(
            explanation["model"], explanation["operation"]
        )
        return [
            env._("Refused by: %s", ", ".join(refusing))
            if refusing
            else env._("None of your accesses reaches it."),
            env._("Ask: %s", ", ".join(ask)),
        ]

from odoo import Command, fields
from odoo.tests.common import TransactionCase, tagged

MEMBERSHIPS = {
    "absent": None,
    "view": ("view", None),
    "edit": ("edit", None),
    "manage": ("manage", None),
    "view_expired": ("view", -1),
    "team_edit": ("edit", None),
    "team_edit_other": ("edit", None),
}
ACCESS_LEVELS = ("none", "view", "edit")
RANK = {"view": 1, "edit": 2, "manage": 3}


class LiveFormula:
    """The live inheritance formula over stored records, in Python.

    role(P, d) = max over the live grants of P (its partner, its groups within
    the node's companies) on the nodes of d's scope, a grant on a file reaching
    that file only, and the top role where P owns d or a folder of its scope;
    the scope is d and its folders up to the nearest boundary, inclusive. The
    document then composes it: members in any company but disabled ones, the
    internal audience in the companies in use, managers' edit wherever the
    audience reaches, shortcuts through their target, an edit link, and a
    link-shared document found through its folder.
    """

    def __init__(self, env, subject):
        self.subject = subject.sudo()
        self.now = fields.Datetime.now()
        self.env_companies = env["document.document"].with_user(subject).env.companies
        self.every_company = self.subject.with_context(active_test=False).company_ids
        self.audience = env.ref("base.group_user")
        self.groups = self.subject.all_group_ids - self.audience
        self.is_system = subject.has_group("document.group_documents_system")
        self.opens_drives = subject.has_group("base.group_break_glass")
        self.is_manager = subject.has_group("document.group_documents_manager")

    def _in_others_drive(self, document):
        root = document
        while root.folder_id:
            root = root.folder_id
        return bool(root.owner_id) and root.owner_id != self.subject

    def _scope(self, document):
        node, chain = document, []
        while node:
            chain.append(node)
            if node.is_access_restricted:
                break
            node = node.folder_id
        return chain

    def _rank(self, document, *, partner, groups, owner):
        best = 0
        in_companies = (
            not document.company_id or document.company_id in self.every_company
        )
        for node in self._scope(document):
            reaches = node == document or node.type == "folder"
            if not reaches:
                continue
            if owner and node.owner_id == self.subject:
                best = 3
            for grant in node.sudo().access_ids:
                if grant.date_to and grant.date_to <= self.now:
                    continue
                held_there = not grant.company_id or (
                    grant.company_id in self.every_company
                )
                if (partner and grant.partner_id == self.subject.partner_id) or (
                    grant.group_id in groups
                    and grant.group_id
                    and in_companies
                    and held_there
                ):
                    best = max(best, RANK[grant.role])
        return best

    def _any_but_disabled(self, document):
        company = document.company_id
        return (
            not company
            or company in self.env_companies
            or (company not in self.every_company)
        )

    def _allowed_or_none(self, document):
        return not document.company_id or document.company_id in self.env_companies

    def _audience(self, document):
        return self._rank(document, partner=False, groups=self.audience, owner=False)

    def _graph(self, document, role, *, owner=True):
        rank = RANK[role]
        members = self._any_but_disabled(document) and (
            self._rank(document, partner=True, groups=self.groups, owner=owner) >= rank
        )
        if self.subject.share:
            return members
        return members or (
            self._allowed_or_none(document) and self._audience(document) >= rank
        )

    def _direct(self, document, role):
        target = document.shortcut_document_id
        if not target:
            reached = self._graph(document, role)
        else:
            reached = self._graph(target, role) or (
                document.owner_id == self.subject
                and (target.owner_id == self.subject or self._graph(target, "view"))
            )
        if role == "edit" and self.is_manager:
            node = target or document
            reached = reached or (
                self._allowed_or_none(node) and self._audience(node) >= 1
            )
        return reached

    def _reach(self, document, role):
        reached = self._direct(document, role)
        if role == "edit":
            reached = reached or (
                self._direct(document, "view") and document.access_via_link == "edit"
            )
        link_roles = ("view", "edit") if role == "view" else ("edit",)
        return reached or (
            self._any_but_disabled(document)
            and document.access_via_link in link_roles
            and not document.is_access_via_link_hidden
            and bool(document.folder_id)
            and self._direct(document.folder_id, "view")
        )

    def permission(self, document):
        document = document.sudo()
        if self.subject._is_public():
            return "none"
        if self.is_system:
            company = document.company_id
            reached = (
                company in self.env_companies
                or company not in self.every_company
                or not company.active
            )
            if reached and (self.opens_drives or not self._in_others_drive(document)):
                return "edit"
        if self._reach(document, "edit"):
            return "edit"
        if self._reach(document, "view"):
            return "view"
        return "none"


@tagged("post_install", "-at_install")
class TestPermissionAlgebraDifferential(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env["res.users"]
        cls.company_main = cls.env.company
        cls.company_other = cls.env["res.company"].create({"name": "Algebra Other Co"})
        cls.group_team = cls.env["res.groups"].create({"name": "Algebra Team"})

        def user(login, *groups):
            return Users.create(
                {
                    "name": login,
                    "login": login,
                    "group_ids": [
                        Command.link(cls.env.ref(group).id) for group in groups
                    ],
                    "company_id": cls.company_main.id,
                    "company_ids": [Command.set(cls.company_main.ids)],
                }
            )

        cls.user_system = user("algebra_system", "document.group_documents_system")
        cls.user_manager = user("algebra_manager", "document.group_documents_manager")
        cls.user_internal = user("algebra_internal", "document.group_documents_user")
        cls.user_portal = user("algebra_portal", "base.group_portal")
        cls.user_public = cls.env.ref("base.public_user")
        cls.user_other = user("algebra_other", "document.group_documents_user")
        (cls.user_manager | cls.user_internal).group_ids = [
            Command.link(cls.group_team.id)
        ]

        cls.member_subjects = (
            cls.user_system | cls.user_manager | cls.user_internal | cls.user_portal
        )
        cls.subjects = cls.member_subjects | cls.user_public

        cls.matrix = cls.env["document.document"]
        cls._build_root_matrix()
        cls._build_owned_matrix()
        cls._build_folder_matrix()
        cls._build_shortcut_matrix()
        cls.matrix.flush_recordset()

    @classmethod
    def _membership_commands(cls, membership):
        spec = MEMBERSHIPS[membership]
        if spec is None:
            return []
        role, offset = spec
        date_to = (
            fields.Datetime.add(fields.Datetime.now(), days=offset) if offset else False
        )
        if membership.startswith("team_"):
            company = cls.company_other if membership.endswith("_other") else False
            return [
                Command.create(
                    {
                        "group_id": cls.group_team.id,
                        "company_id": company.id if company else False,
                        "role": role,
                    }
                )
            ]
        return [
            Command.create(
                {"partner_id": subject.partner_id.id, "role": role, "date_to": date_to}
            )
            for subject in cls.member_subjects
        ]

    @classmethod
    def _create(cls, **vals):
        document = cls.env["document.document"].create({"type": "binary", **vals})
        cls.matrix |= document
        return document

    @classmethod
    def _build_root_matrix(cls):
        for owner in (cls.user_other, cls.env["res.users"]):
            for access_internal in ACCESS_LEVELS:
                for access_via_link in ACCESS_LEVELS:
                    for membership in MEMBERSHIPS:
                        for company in (
                            cls.env["res.company"],
                            cls.company_main,
                            cls.company_other,
                        ):
                            cls._create(
                                name=f"root/{owner.id}/{access_internal}/"
                                f"{access_via_link}/{membership}/{company.id}",
                                owner_id=owner.id,
                                company_id=company.id,
                                access_internal=access_internal,
                                access_via_link=access_via_link,
                                access_ids=cls._membership_commands(membership),
                            )

    @classmethod
    def _build_owned_matrix(cls):
        for subject in cls.member_subjects.filtered(lambda user: not user.share):
            for access_internal in ACCESS_LEVELS:
                for access_via_link in ACCESS_LEVELS:
                    cls._create(
                        name=f"owned/{subject.login}/{access_internal}/{access_via_link}",
                        owner_id=subject.id,
                        access_internal=access_internal,
                        access_via_link=access_via_link,
                    )

    @classmethod
    def _build_folder_matrix(cls):
        parents = [
            (f"internal-{level}", {"access_internal": level}) for level in ACCESS_LEVELS
        ]
        parents += [
            (
                f"member-{membership}",
                {
                    "access_internal": "none",
                    "access_ids": cls._membership_commands(membership),
                },
            )
            for membership in ("view", "edit", "manage", "view_expired", "team_edit")
        ]
        parents += [
            (
                f"owned-by-{subject.login}",
                {"access_internal": "none", "owner_id": subject.id},
            )
            for subject in cls.member_subjects.filtered(lambda user: not user.share)
        ]
        for company in (cls.company_main, cls.company_other):
            for label, parent_vals in parents:
                folder = cls._create(
                    name=f"folder/{label}/{company.id}",
                    type="folder",
                    access_via_link="none",
                    company_id=company.id,
                    **parent_vals,
                )
                for access_via_link in ACCESS_LEVELS:
                    for hidden in (False, True):
                        cls._create(
                            name=f"child/{label}/{company.id}/{access_via_link}/{hidden}",
                            folder_id=folder.id,
                            access_via_link=access_via_link,
                            is_access_via_link_hidden=hidden,
                        )
                for boundary in (False, True):
                    sub = cls._create(
                        name=f"sub/{label}/{company.id}/{boundary}",
                        type="folder",
                        folder_id=folder.id,
                        access_via_link="none",
                    )
                    for membership in ("absent", "view", "team_edit"):
                        cls._create(
                            name=f"leaf/{label}/{company.id}/{boundary}/{membership}",
                            folder_id=sub.id,
                            access_via_link="none",
                            access_ids=cls._membership_commands(membership),
                        )
                    # set after the content exists: the scope of what is
                    # already below a folder follows its boundary
                    sub.is_access_restricted = boundary
        # a folder moved under another takes the new one's grants and loses
        # the old one's, with everything below it
        moved = cls.matrix.filtered(
            lambda d: d.name == f"sub/member-edit/{cls.company_main.id}/False"
        )
        target = cls.matrix.filtered(
            lambda d: d.name == f"folder/internal-view/{cls.company_main.id}"
        )
        moved.folder_id = target

    @classmethod
    def _build_shortcut_matrix(cls):
        for target_internal in ACCESS_LEVELS:
            for target_link in ACCESS_LEVELS:
                target = cls._create(
                    name=f"target/{target_internal}/{target_link}",
                    owner_id=cls.user_other.id,
                    access_internal=target_internal,
                    access_via_link=target_link,
                )
                for shortcut_owner in (cls.user_other, cls.env["res.users"]):
                    cls._create(
                        name=f"shortcut/{target_internal}/{target_link}/{shortcut_owner.id}",
                        shortcut_document_id=target.id,
                        owner_id=shortcut_owner.id,
                    )
        for subject in cls.member_subjects.filtered(lambda user: not user.share):
            target = cls._create(
                name=f"target-owned/{subject.login}",
                owner_id=cls.user_other.id,
                access_internal="view",
                access_via_link="none",
            )
            cls._create(
                name=f"shortcut-owned/{subject.login}",
                shortcut_document_id=target.id,
                owner_id=subject.id,
            )

    def _computed(self, subject):
        documents = self.matrix.with_user(subject).sudo()
        documents.invalidate_recordset(["user_permission"])
        return {document.id: document.user_permission for document in documents}

    def _searched(self, subject, level):
        return set(
            self.env["document.document"]
            .with_user(subject)
            .sudo()
            .search([("id", "in", self.matrix.ids), ("user_permission", "in", [level])])
            .ids
        )

    def _assert_formula_holds(self, subject):
        formula = LiveFormula(self.env, subject)
        expected = {
            document.id: formula.permission(document) for document in self.matrix
        }
        computed = self._computed(subject)
        edit_ids = self._searched(subject, "edit")
        view_ids = self._searched(subject, "view")
        disagreements = []
        for document in self.matrix:
            searched = (
                "edit"
                if document.id in edit_ids
                else "view"
                if document.id in view_ids
                else "none"
            )
            cells = (expected[document.id], computed[document.id], searched)
            if len(set(cells)) > 1:
                disagreements.append((document.name, *cells))
        if disagreements:
            self.fail(
                f"{len(disagreements)}/{len(self.matrix)} cells disagree for "
                f"{subject.login} (formula, compute, search):\n"
                + "\n".join(f"  {row}" for row in sorted(disagreements))
            )
        if both := edit_ids & view_ids:
            self.fail(f"{len(both)} cells match both 'view' and 'edit'")
        return set(expected.values())

    def test_matrix_is_populated(self):
        self.assertGreater(len(self.matrix), 700)
        self.assertTrue(self.matrix.filtered("is_access_restricted"))

    def test_formula_holds_for_system_administrator(self):
        self._assert_formula_holds(self.user_system)

    def test_formula_holds_for_documents_manager(self):
        self.assertEqual(
            self._assert_formula_holds(self.user_manager), {"none", "view", "edit"}
        )

    def test_formula_holds_for_internal_user(self):
        self.assertEqual(
            self._assert_formula_holds(self.user_internal), {"none", "view", "edit"}
        )

    def test_formula_holds_for_portal_user(self):
        self.assertEqual(
            self._assert_formula_holds(self.user_portal), {"none", "view", "edit"}
        )

    def test_formula_holds_for_public_user(self):
        self._assert_formula_holds(self.user_public)

    def test_the_formula_sees_what_a_scope_drops(self):
        # negative control of the oracle itself: a boundary ignored, or a
        # grant on a file reaching below it, changes the answer on this matrix
        formula = LiveFormula(self.env, self.user_internal)
        honest = {d.id: formula.permission(d) for d in self.matrix}
        formula._scope = lambda document: list(
            document.search([("id", "parent_of", document.id)])
        )
        leaky = {d.id: formula.permission(d) for d in self.matrix}
        self.assertNotEqual(honest, leaky)

    def test_permission_never_undercuts_the_token_less_level(self):
        ranking = {"none": 0, "view": 1, "edit": 2}
        for subject in self.subjects:
            documents = self.matrix.with_user(subject).sudo()
            documents.invalidate_recordset(["user_permission"])
            token_less = documents._get_permission_without_token_multi()
            undercut = [
                (document.name, without_token, document.user_permission)
                for document, without_token in token_less.items()
                if ranking[without_token] > ranking[document.user_permission]
            ]
            self.assertFalse(
                undercut,
                f"{subject.login}: user_permission is weaker than the "
                f"token-less level for:\n"
                + "\n".join(
                    f"  {name}: without_token={without_token!r} "
                    f"user_permission={permission!r}"
                    for name, without_token, permission in sorted(undercut)
                ),
            )

    def test_every_divergence_traces_to_a_known_blind_spot(self):
        ranking = {"none": 0, "view": 1, "edit": 2}
        unexplained = []
        divergent_cells = 0
        for subject in self.subjects:
            is_system = subject.has_group("document.group_documents_system")
            documents = self.matrix.with_user(subject).sudo()
            documents.invalidate_recordset(["user_permission"])
            token_less = documents._get_permission_without_token_multi()
            for document, without_token in token_less.items():
                permission = document.user_permission
                if without_token == permission:
                    continue
                divergent_cells += 1
                self.assertLess(
                    ranking[without_token],
                    ranking[permission],
                    f"{subject.login}/{document.name}: a divergence may only "
                    "ever be an upgrade",
                )
                explained = (
                    is_system
                    or document.access_via_link != "none"
                    or bool(document.shortcut_document_id)
                )
                if not explained:
                    unexplained.append(
                        (subject.login, document.name, without_token, permission)
                    )

        self.assertFalse(
            unexplained,
            "these cells diverge without a link, system rights or a shortcut to "
            "explain it, so the two implementations have genuinely drifted:\n"
            + "\n".join(map(str, unexplained)),
        )
        self.assertTrue(
            divergent_cells,
            "no divergence found at all -- the matrix no longer exercises any "
            "of the three blind spots, so this test proves nothing",
        )

    def test_link_shared_child_is_searchable_at_the_level_the_link_grants(self):
        Document = self.env["document.document"]
        folder = Document.create(
            {"name": "Viewer folder", "type": "folder", "access_internal": "view"}
        )
        child = Document.create(
            {
                "name": "Editor link child",
                "type": "binary",
                "folder_id": folder.id,
                "access_internal": "none",
                "access_via_link": "edit",
                "is_access_via_link_hidden": False,
            }
        )
        as_user = Document.with_user(self.user_internal)

        self.assertEqual(child.with_user(self.user_internal).user_permission, "edit")
        self.assertIn(
            child.id,
            as_user.sudo().search([("user_permission", "=", "edit")]).ids,
            "a document the user can edit must be findable as editable",
        )
        self.assertNotIn(
            child.id, as_user.sudo().search([("user_permission", "=", "view")]).ids
        )

    def test_owned_document_is_not_reported_as_view_only(self):
        Document = self.env["document.document"]
        owned = Document.create(
            {
                "name": "Mine but internally view",
                "type": "binary",
                "owner_id": self.user_internal.id,
                "access_internal": "view",
                "access_via_link": "view",
            }
        )
        as_user = Document.with_user(self.user_internal)

        self.assertEqual(owned.with_user(self.user_internal).user_permission, "edit")
        self.assertIn(
            owned.id, as_user.sudo().search([("user_permission", "=", "edit")]).ids
        )
        self.assertNotIn(
            owned.id,
            as_user.sudo().search([("user_permission", "=", "view")]).ids,
            "an owner must not show up under the Viewer filter",
        )

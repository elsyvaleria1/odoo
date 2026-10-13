import inspect

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMixinDocumentsContract(TransactionCase):
    def _hooks(self):
        mixin = type(self.env["mixin.documents"])
        return {
            name: inspect.signature(getattr(mixin, name))
            for name in dir(mixin)
            if name.startswith("_get_document")
            or name in ("_prepare_document_vals", "_check_create_documents")
            if callable(getattr(mixin, name, None))
        }

    def test_the_hook_roster_is_not_empty(self):
        hooks = self._hooks()
        self.assertIn("_prepare_document_vals", hooks)
        self.assertGreaterEqual(len(hooks), 5, sorted(hooks))

    def test_no_consumer_redefines_a_hook_with_another_signature(self):
        mixin_model = self.env["mixin.documents"]
        hooks = self._hooks()
        divergent = []
        for model_name in self.registry:
            if model_name == mixin_model._name:
                continue
            model_class = self.registry[model_name]
            if not issubclass(model_class, self.registry[mixin_model._name]):
                continue
            for hook, expected in hooks.items():
                found = getattr(model_class, hook, None)
                if found is None:
                    continue
                actual = inspect.signature(found)
                if list(actual.parameters) != list(expected.parameters):
                    divergent.append(
                        f"{model_name}.{hook}{actual} shadows "
                        f"mixin.documents.{hook}{expected} "
                        f"(defined in {inspect.getsourcefile(found)})"
                    )

        self.assertFalse(
            divergent,
            "a hook redefined with different parameters is called by "
            "`document` with the mixin's arguments and silently produces the "
            "wrong vals:\n  " + "\n  ".join(divergent),
        )

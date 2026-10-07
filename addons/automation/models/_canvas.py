"""Canvas geometry shared by the steps that persist it and the graph payload.

Not a model. These bounds cannot live on `ir.actions.server`, because
`ir_actions_server` already imports from `automation_rule`, which reads them
too, and the owner would close an import cycle.
"""

NODE_SIZE_DEFAULT = {"width": 200, "height": 140}
NODE_SIZE_MIN = {"width": 160, "height": 72}
NODE_SIZE_MAX = {"width": 480, "height": 320}

NODE_HEADER_HEIGHT = 34

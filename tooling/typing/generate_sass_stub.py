
import ast
import subprocess
import sys
import tempfile
from pathlib import Path

from google.protobuf.descriptor_pb2 import FileDescriptorSet


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    vendor = root / "odoo/libs/_vendor"
    tree = ast.parse((vendor / "embedded_sass_pb2.py").read_text())
    descriptor_call = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "AddSerializedFile"
    )
    serialized = ast.literal_eval(descriptor_call.args[0])
    descriptor_set = FileDescriptorSet()
    descriptor = descriptor_set.file.add()
    descriptor.ParseFromString(serialized)
    with tempfile.TemporaryDirectory(prefix="odoo-sass-stub-") as directory:
        source = Path(directory) / "descriptor.pb"
        source.write_bytes(descriptor_set.SerializeToString())
        subprocess.run(
            [
                sys.executable,
                "-m",
                "grpc_tools.protoc",
                f"--descriptor_set_in={source}",
                f"--pyi_out={vendor}",
                descriptor.name,
            ],
            check=True,
        )
    stub = vendor / "embedded_sass_pb2.pyi"
    header = "# Generated from embedded_sass_pb2.py; regenerate with tooling/typing/generate_sass_stub.py.\n"
    stub.write_text(header + stub.read_text())


if __name__ == "__main__":
    main()

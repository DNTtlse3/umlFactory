"""
    Agent générateur Python — montre l'ajout d'un langage sans toucher à la partie commune.
"""

from pathlib import Path

from common.a2a.generator_base import CodeGeneratorAgentBase, LanguageProfile


def _to_snake_case(name: str) -> str:
    out = [name[0].lower()]
    for ch in name[1:]:
        if ch.isupper():
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


class PythonProfile(LanguageProfile):
    file_extension = "py"
    type_map = {"Integer": "int", "String": "str", "Boolean": "bool",
                "Float": "float", "void": "None"}

    def to_file_name(self, class_name: str) -> str:
        return f"{_to_snake_case(class_name)}.py"

    def collection_type(self, element_type: str) -> str:
        return f"list[{element_type}]"


class PythonGeneratorAgent(CodeGeneratorAgentBase):
    target_language = "python"
    template_dir = Path(__file__).parent / "templates"
    profile = PythonProfile()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Agent générateur Python (A2A)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8002)
    args = ap.parse_args()
    PythonGeneratorAgent(port=args.port, host=args.host).serve()
"""
    Agent générateur Java — portage de la partie 'Génération Java' de umlfactory2Java.py (Remy Courdier, V0.1) en agent A2A.
"""
from pathlib import Path

from common.a2a.generator_base import CodeGeneratorAgentBase, LanguageProfile


class JavaProfile(LanguageProfile):
    file_extension = "java"
    type_map = {"Integer": "int", "String": "String", "Boolean": "boolean",
                "Float": "double", "void": "void"}

    def to_file_name(self, class_name: str) -> str:
        return f"{class_name}.java"

    def collection_type(self, element_type: str) -> str:
        return f"List<{element_type}>"


class JavaGeneratorAgent(CodeGeneratorAgentBase):
    target_language = "java"
    template_dir = Path(__file__).parent / "templates"
    profile = JavaProfile()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Agent générateur Java (A2A)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8001)
    args = ap.parse_args()
    JavaGeneratorAgent(port=args.port, host=args.host).serve()
"""
    Agent générateur C++ — extension de umlfactory2code.
"""
from pathlib import Path

from common.a2a.generator_base import CodeGeneratorAgentBase, LanguageProfile
from common.model.uml_model import UmlModel


class CppProfile(LanguageProfile):
    file_extension = "cpp"
    type_map = {
        "Integer": "int", "String": "std::string",
        "Boolean": "bool", "Float": "double", "void": "void",
    }

    def to_file_name(self, class_name: str) -> str:
        return class_name

    def collection_type(self, element_type: str) -> str:
        return f"std::vector<{element_type}*>"


class CppGeneratorAgent(CodeGeneratorAgentBase):
    target_language = "cpp"
    template_dir = Path(__file__).parent / "templates"
    profile = CppProfile()

    def generate(self, payload: dict) -> list[dict]:
        """Génère un fichier d'en-tête et un fichier source par classe."""
        model = UmlModel.from_dict(payload["model"])
        artifacts = []
        for cls in model.classes:
            context = self.build_context(cls, model)
            name = self.profile.to_file_name(cls.name)
            artifacts.append({
                "fileName": f"{name}.hpp",
                "content": self.env.get_template("class.hpp.j2").render(**context),
            })
            artifacts.append({
                "fileName": f"{name}.cpp",
                "content": self.env.get_template("class.cpp.j2").render(**context),
            })
        return artifacts


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Agent générateur C++ (A2A)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8003)
    args = parser.parse_args()
    CppGeneratorAgent(host=args.host, port=args.port).serve()

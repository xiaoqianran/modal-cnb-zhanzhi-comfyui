"""One explicit thin join, not another RefMod runtime or reference library."""
import json
from comfy_api.latest import io
from .core import sorted_autogrow_values
from .nodes_reference_package import PACKAGE, schema
from .reference_package import canonical
from .refmod_bridge import join_packages


class MiniMaxH3ReferenceJoinEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return schema(cls,"Join qualified packages / 显式合并参考成员",[
            io.Autogrow.Input("packages",template=io.Autogrow.TemplatePrefix(input=PACKAGE.Input("package"),prefix="package_",min=1,max=15)),
            io.String.Input("merge_roles_json",default="[]",multiline=True)],
            [PACKAGE.Output("reference_package"),io.String.Output("report_json")],
            "Join already qualified native/v4-v5 imports in input order. Explicit merge_roles=['C'] groups C-video and C-voice; no guessed roles, blur strength, MODEL hooks, extra VAE encode or library. Existing Route/Apply/EAV/Relay stay separate.")

    @classmethod
    def execute(cls,packages,merge_roles_json="[]"):
        package,report=join_packages(sorted_autogrow_values(packages),merge_roles=json.loads(merge_roles_json))
        return io.NodeOutput(package,canonical(report))


NODES=[MiniMaxH3ReferenceJoinEXPT8]

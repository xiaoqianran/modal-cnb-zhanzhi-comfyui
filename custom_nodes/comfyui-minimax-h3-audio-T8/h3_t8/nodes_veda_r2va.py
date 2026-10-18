"""Append-only R2VA Veda nodes. Legacy T2VA IDs and directory unchanged."""
import json
from pathlib import Path

import folder_paths
from comfy_api.latest import io

from .veda_r2va_bundle import inspect_bundle
from .veda_r2va_runtime import R2VARuntime, apply_r2va

folder_paths.add_model_folder_path("veda_r2va", str(Path(folder_paths.models_dir) / "veda_r2va"))


class MiniMaxH3VedaR2VABundleEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__, display_name="H3 Veda R2VA · Bundle (EXP)",
            category="T8/MiniMax H3/Acceleration/Experimental", is_experimental=True,
            description="R2VA visual-reference predictor, not an H3 DiT or LoRA. Select models/veda_r2va. "
                        "Separate from the legacy T2VA loader; official preview uses 32 reference / 32 generated tiles.",
            inputs=[io.Combo.Input("bundle_name", options=[n for n in folder_paths.get_filename_list("veda_r2va")
                    if Path(n).suffix.lower() == ".safetensors"] or ["放入 models/veda_r2va"])],
            outputs=[io.Custom("T8_VEDA_R2VA_BUNDLE").Output("bundle"), io.String.Output("report_json")])

    @classmethod
    def execute(cls, bundle_name):
        if bundle_name == "放入 models/veda_r2va":
            raise ValueError("Place the official R2VA Veda predictor in models/veda_r2va")
        bundle = inspect_bundle(folder_paths.get_full_path_or_raise("veda_r2va", bundle_name))
        return io.NodeOutput(bundle, json.dumps(bundle.report(), ensure_ascii=False, indent=2))


class MiniMaxH3VedaR2VAApplyEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__, display_name="H3 Veda R2VA · Apply Flex Sparse (EXP)",
            category="T8/MiniMax H3/Acceleration/Experimental", is_experimental=True,
            description="Independent MODEL clone for LOW or HIGH. Official R2VA predictor/selection with T8 Flex, "
                        "not upstream INT8. trained budgets read the file (official 32/32). Text/audio stay dense. "
                        "strict_exact is default; non-trained sizes require explicit nearest_exp. "
                        "Preserves foreign EAV/Relay owners and masks with audited dense delegation. "
                        "Windows apply requires UTF8 and --disable-dynamic-vram. No speed/flicker-fix promise.",
            inputs=[io.Model.Input("model"), io.Custom("T8_VEDA_R2VA_BUNDLE").Input("bundle"),
                    io.Combo.Input("mode", options=["report_only", "apply_exp"], default="report_only"),
                    io.Combo.Input("plan_mode", options=["strict_exact", "nearest_exp"], default="strict_exact"),
                    io.String.Input("generated_budget", default="trained"),
                    io.String.Input("reference_budget", default="trained"),
                    io.Int.Input("max_copy_mib", default=64, min=1, max=256, advanced=True)],
            outputs=[io.Model.Output("model"), io.Custom("T8_VEDA_R2VA_RUNTIME").Output("runtime")])

    @classmethod
    def execute(cls, model, bundle, mode="report_only", plan_mode="strict_exact",
                generated_budget="trained", reference_budget="trained", max_copy_mib=64):
        model, runtime = apply_r2va(model, bundle, mode=mode, plan_mode=plan_mode,
            generated_budget=generated_budget, reference_budget=reference_budget, max_copy_mib=max_copy_mib)
        return io.NodeOutput(model, runtime)


class MiniMaxH3VedaR2VAAuditEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__, display_name="H3 Veda R2VA · Audit After Sample (EXP)",
            category="T8/MiniMax H3/Acceleration/Experimental", is_experimental=True, is_output_node=True,
            description="Pass through the actual sampler LATENT, exposing sparse/delegate calls and plan/grid evidence. "
                        "Does not certify human quality or end-to-end speed.",
            inputs=[io.Latent.Input("av_latent"), io.Custom("T8_VEDA_R2VA_RUNTIME").Input("runtime")],
            outputs=[io.Latent.Output("av_latent"), io.String.Output("report_json")])

    @classmethod
    def execute(cls, av_latent, runtime):
        if type(runtime) is not R2VARuntime:
            raise TypeError("Use the paired R2VA Apply runtime, not legacy T2VA")
        report = json.dumps(runtime.snapshot(), ensure_ascii=False, indent=2)
        return io.NodeOutput(av_latent, report, ui={"text": (report,)})


NODES = [MiniMaxH3VedaR2VABundleEXPT8, MiniMaxH3VedaR2VAApplyEXPT8, MiniMaxH3VedaR2VAAuditEXPT8]

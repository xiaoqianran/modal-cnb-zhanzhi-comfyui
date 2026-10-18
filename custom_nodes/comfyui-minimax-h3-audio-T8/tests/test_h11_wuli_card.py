"""One narrow new card contract; descriptors never grant model execution."""
from h3_audio_t8_pkg.model_recipe_cards import recipe_from_header


def test_four_explicit_wuli_roles_and_wrong_shape_without_filename_gate():
    meta8 = {"fixed_num_steps": "8", "source": "Wuli-art/MiniMax-H3-Turbo turbo-8step/transformer"}
    header8 = {"adaln_t_table": {"shape": [1025, 25]}, "final_layer.video_out.weight": {"shape": [96, 5376]},
               "final_layer.audio_out.weight": {"shape": [32, 5376]}}
    card = recipe_from_header(header8, meta8)["wuli_native_recipe"]
    assert card["role"] == "native8_complete_checkpoint" and not card["descriptor_mismatches"]
    assert not card["runtime_or_quality_proven_by_header"]
    header8["adaln_t_table"]["shape"] = [1025, 8]
    assert recipe_from_header(header8, meta8)["wuli_native_recipe"]["descriptor_mismatches"]
    meta4 = {"format": "wuli_minimax_h3_turbo_v1_comfyui"}
    assert recipe_from_header({}, meta4)["wuli_native_recipe"]["role"] == "native4_trunk_only_NOT_complete"
    assert recipe_from_header({"x.reshape_weight": {}}, meta4)["wuli_native_recipe"]["role"] == "native4_zero_head_widen"
    bank = {"diffusion_model.final_layer.video_out.set_weight": {"shape": [384, 5376]},
            "diffusion_model.final_layer.audio_out.set_weight": {"shape": [128, 5376]}}
    assert recipe_from_header(bank, meta4)["wuli_native_recipe"]["role"] == "native4_absolute_head_set"
    assert "wuli_native_recipe" not in recipe_from_header(header8, {"model_name": "wuli turbo"})

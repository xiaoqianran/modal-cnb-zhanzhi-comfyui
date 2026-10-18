import asyncio
import json

import pytest
from safetensors.torch import save_file
import torch
import h3_audio_t8_pkg
from h3_audio_t8_pkg import refmod_bridge as b
from h3_audio_t8_pkg.reference_package import capture_package, NORMALIZATION, tensor_record, file_sha
from h3_audio_t8_pkg.reference_runtime import capture_set
from h3_audio_t8_pkg.nodes_refmod_bridge import NODES


def package(role,kind,number,producer="1"*64):
    shape = (1,32,2,3) if kind == "audio" else (1,24,1 if kind == "image" else 2,2,2)
    tensors = {"latent":torch.full(shape,number/10)}
    if kind != "audio":
        tensors["rgb"]=torch.full((1 if kind == "image" else 5,32,32,3),number/10)
    source = tensor_record(tensors["latent" if kind == "audio" else "rgb"])["sha256"]
    return capture_package([dict(id="member",role_id=role,kind=kind,latent="latent",grounding=None if kind == "audio" else "rgb",
        source=dict(sha256=source,scope="actual_decoded_pcm_tensor" if kind == "audio" else "actual_decoded_rgb_tensor"),
        producer=dict(role="audio_vae" if kind == "audio" else "video_vae",sha256=producer,
                      scope="actual_native_weights_tokenizer_configuration_and_implementation"),normalization=NORMALIZATION)],tensors)


def test_A_B_images_C_video_voice_join_preserves_order_and_routes_offscreen_voice():
    packages=[package("A","image",1),package("B","image",2),package("C","video",3),package("C","audio",4)]
    before=[p.verify() for p in packages]
    with pytest.raises(ValueError,match="Duplicate role"):
        b.join_packages(packages)
    joined,report=b.join_packages(packages,merge_roles=["C"])
    roles=[dict(role_id=role,visual=role!="C",voice=role=="C") for role in ("A","B","C")]
    refs,mapping=capture_set([joined],json.dumps(roles))
    routed=refs.routed()
    assert [r["kind"] for r in routed["refs"]]==["image","image","audio"]
    assert [r["role_id"] for r in mapping["mapping"]]==["A","B","C"]
    assert [r["ordinal"] for r in mapping["mapping"]]==[1,2,1]
    assert [r["type"] for r in routed["qwen_ref_items"]]==["image","image","audio"]
    assert torch.equal(routed["refs"][-1]["audio_latent"],packages[-1].tensors["latent"])
    assert not report["strength_applied"] and not report["MODEL_hooks_changed"]
    assert [p.verify() for p in packages]==before
    assert [r["kind"] for r in report["mapping"]]==["image","image","video","audio"]
    assert b.join_packages(packages[::-1],merge_roles=["C"])[1]["joined_manifest_sha256"]!=report["joined_manifest_sha256"]


def test_duplicate_source_wrong_producer_and_unknown_provider_are_real_errors():
    original=package("A","image",1)
    with pytest.raises(ValueError,match="Duplicate actual"):
        b.join_packages([original,original],merge_roles=["A"])
    with pytest.raises(ValueError,match="producers differ"):
        b.join_packages([original,package("B","image",2,"2"*64)])
    with pytest.raises(ValueError,match="qualified native"):
        b.join_packages([object()])
    joined,_=b.join_packages([original])
    joined.tensors["p1_m1_z"].add_(1)
    assert original.verify() and not torch.equal(original.tensors["latent"],joined.tensors["p1_m1_z"])


@pytest.mark.parametrize("mode,strength,status",[("encode",1.,"candidate_for_existing_exact_RGB_PCM_importers"),
    ("encode",.5,"delegate_original_MODEL_hook_semantics"),("trained",1.,"delegate_original_MODEL_hook_semantics"),
    ("encode",0.,"slot_skipped_explicitly")])
def test_actual_external_file_modes_and_blur_strength_are_not_remapped(tmp_path,mode,strength,status):
    path=tmp_path/"external.safetensors"
    meta=dict(_format_version=4,kind="image",mode=mode,latent_t=1,latent_h=2,latent_w=2,refmod_config='{"execute":"never"}')
    save_file({"latent":torch.zeros(1,24,1,2,2)},str(path),metadata={"refmod_meta":json.dumps(meta)})
    before=file_sha(path)
    report=b.assess_external(path,before,strength)
    assert report["status"]==status and report["tensor_loads"]==0
    assert not report["foreign_config_executed"] and not report["imported"] and file_sha(path)==before
    with pytest.raises(ValueError,match="pinned SHA"):
        b.assess_external(path,"0"*64,strength)


def test_invalid_strengths_and_registration():
    for strength in (True,float("nan"),float("inf"),-1,2):
        with pytest.raises(ValueError,match="finite"):
            b.assess_external("not-opened","0"*64,strength)
    registered=asyncio.run(h3_audio_t8_pkg.comfy_entrypoint().get_node_list())
    position=registered.index(NODES[0])
    assert registered[position:position+len(NODES)]==NODES
    assert NODES[0].define_schema().get_v1_info(NODES[0]).name==NODES[0].__name__

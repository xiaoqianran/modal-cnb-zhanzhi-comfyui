import asyncio
import json

import pytest
import torch
import h3_audio_t8_pkg
from h3_audio_t8_pkg import prompt_provider as p
from h3_audio_t8_pkg.nodes_prompt_provider import NODES


TEXT = "固定镜头，一位红衣女士拿起唯一白杯，微笑说道：你好，今天天气不错。没有额外人物、配乐或字幕。"
LITERAL = "你好，今天天气不错。"


def proposal(request,text=None):
    text = text or ("integrated_multimodal_description: [Shot 1] A woman in red picks up the single white cup in a locked shot. "
                    "She smiles and says (S1) <d>[Chinese] "+LITERAL+"</d>.\noverall_soundscape: Quiet room.\nnon_diegetic_music: N/A.")
    value = dict(schema="t8.h09.prompt-proposal.v1",request_sha256=request.sha256,text=text)
    return p.PromptProposal(p.canonical(value),p.content_sha(value))


def test_literal_and_explicit_adoption_preserve_original_and_stale_rejection():
    request = p.make_request(TEXT,5,[],[LITERAL])
    result = proposal(request)
    assert p.choose(request,result)[0]==TEXT
    assert p.choose(request,result,True)[0]==result.verify(request)["text"]
    changed = p.make_request(TEXT+"动作不同",5,[],[LITERAL])
    with pytest.raises(ValueError,match="stale"):
        p.choose(changed,result,True)
    damaged = proposal(request,result.verify(request)["text"]+LITERAL)
    with pytest.raises(ValueError,match="repeated"):
        p.choose(request,damaged,True)
    damaged = proposal(request,result.verify(request)["text"].replace(LITERAL,"再见。"))
    with pytest.raises(ValueError,match="protected literal"):
        p.choose(request,damaged,True)
    no_speech = p.make_request("A woman stands still in a room.",5,[],[])
    with pytest.raises(ValueError,match="undeclared dialogue"):
        p.choose(no_speech,proposal(no_speech),True)


def test_actual_image_order_snapshot_and_media_change_invalidates():
    images = torch.zeros(2,32,32,3)
    request = p.make_request(TEXT,5,["last","first"],[LITERAL],images)
    assert request.verify()["media_order"]==[1,0]
    images.add_(.5)
    assert request.verify()
    request.images[0].add_(.1)
    with pytest.raises(ValueError,match="pixels changed"):
        request.verify()
    with pytest.raises(ValueError,match="cannot mix"):
        p.make_request(TEXT,5,["first","reference"],[LITERAL],images)
    with pytest.raises(ValueError,match="literal substrings"):
        p.make_request(TEXT,5,[],["未出现的台词"])
    with pytest.raises(ValueError,match="actual IMAGE"):
        p.make_request(TEXT,5,["reference"],[LITERAL])


def test_actual_config_content_file_and_proposal_hash_tamper(tmp_path):
    file = tmp_path/"source.py"
    file.write_text("# test source, never executed",encoding="utf8")
    files = [dict(path=str(file),bytes=file.stat().st_size,sha256=p.digest(file))]
    value = dict(schema=p.SCHEMA,source_revision=p.REVISION,model_revision=p.MODEL_REVISION,
                 model_ready=True,files=files,inventory_sha256=p.content_sha(files))
    path = tmp_path/"config.json"
    path.write_text(json.dumps(value),encoding="utf8")
    with pytest.raises(ValueError,match="absolute"):
        p.load_config(path)
    file.write_text("# changed",encoding="utf8")
    with pytest.raises(ValueError,match="size changed"):
        p.load_config(path)
    request = p.make_request(TEXT,5,[],[LITERAL])
    result = proposal(request)
    with pytest.raises(ValueError,match="modified"):
        p.choose(request,p.PromptProposal(result.json,"0"*64),True)


def test_author_pinned_rules_mechanical_validation_and_actual_schemas():
    import importlib.util
    from pathlib import Path
    path = Path("G:/T8-H09/freevideo-int8/source-v1/freevideo_engine/prompt_vlm/rules.py")
    spec = importlib.util.spec_from_file_location("h09_author_rules_test",path)
    rules = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rules)
    request = p.make_request(TEXT,5,[],[LITERAL])
    output = proposal(request).verify(request)["text"]
    author = rules.request(dict(text=TEXT,seconds=5,media=[]))
    assert rules.validate_output(output,author)==output
    registered = asyncio.run(h3_audio_t8_pkg.comfy_entrypoint().get_node_list())
    assert registered[-3:]==NODES
    for node in NODES:
        assert node.define_schema().get_v1_info(node).name==node.__name__


def test_complete_layout_keeps_selected_config_path_not_last_bound_python(monkeypatch):
    # Layout-only regression: actual source/catalog/config metadata, no model
    # import/inference. The separate prepared/inference run verifies all bytes.
    from pathlib import Path
    path = Path("G:/T8-H09/prompt-provider/config-v2.json")
    monkeypatch.setattr(p,"verify_files",lambda rows: None)
    value,sha = p.load_config(path)
    assert sha==p.digest(path) and value["python"]!=str(path)


def test_actual_isolated_worker_imports_our_namespace_before_config_validation(tmp_path):
    from pathlib import Path
    import os
    import time
    from h3_audio_t8_pkg.freevideo_exp.supervision import owned_process
    worker = Path(p.__file__).with_name("prompt_provider_worker.py")
    (tmp_path/"request.json").write_text(json.dumps(dict(config_path=str(tmp_path/"missing.json"),config_sha256="0"*64)),encoding="utf8")
    log_path = tmp_path/"worker.log"
    with log_path.open("w",encoding="utf8") as log, owned_process(
            ["G:/FreeVideo/FreeVideo-Windows/python/python.exe","-I","-B","-X","utf8",str(worker),str(tmp_path)],
            dict(os.environ,CUDA_VISIBLE_DEVICES="-1"),tmp_path,log) as process:
        started = time.monotonic()
        while process.poll() is None:
            assert time.monotonic()-started<30
            time.sleep(.1)
        assert process.returncode!=0
    text = log_path.read_text(encoding="utf8")
    assert "FileNotFoundError" in text and "ModuleNotFoundError" not in text

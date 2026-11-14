"""Warm worker for cosmos_sim_transfer. Runs in feasibility/cosmos-src/.venv (Python 3.13, torch 2.10 for CUDA 13).

Loads Cosmos3-Nano-Sim-Transfer once with NVIDIA's reference settings (4 steps, guidance 1, full history, eager),
then answers one job per line.

Job inputs:   {"controls": {"rgb": path, "depth": path, "seg": path}, "prompt": str, "out_dir": path, "name": str}
              controls come from isaac/render_control_clip.py; prompt is the structured caption
Job settings: {"control": "edge" | "depth" | "seg", "seed": int, "frames": 121, "fps": 30}
              edge is computed by Cosmos from the rgb clip; depth and seg are used as given
Outputs:      {"clip": out_dir/name/vision.mp4, "control_clip": ..., "sample_outputs": ...}

Memory: about 48 GB. Guardrails are off because nvidia/Cosmos-Guardrail1 is gated for this account.
"""
import json, os, sys
from pathlib import Path

FE = Path(__file__).resolve().parents[2] / 'feasibility'; SRC = FE / 'cosmos-src'
os.chdir(SRC)
for k, v in {'COSMOS_INTERNAL': '0', 'COSMOS_TRAINING': '1', 'COSMOS_SMOKE': '0', 'COSMOS_DEVICE': 'cuda', 'WANDB_MODE': 'disabled',
             'OMP_NUM_THREADS': '1', 'TOKENIZERS_PARALLELISM': 'false'}.items():
    os.environ.setdefault(k, v)
os.environ.pop('PYTHONPATH', None); os.environ.pop('COSMOS_DISTILLATION_IMPL', None)

HF = Path.home() / '.cache/huggingface/hub'
CK = SRC / 'checkpoints/Cosmos3-Nano-Sim-Transfer'
TOK = HF / 'models--nvidia--Cosmos3-Nano/snapshots/e59a53c25979a090fa8706c9acc0c254a6e89b92/text_tokenizer'
VAE = HF / 'models--Wan-AI--Wan2.2-TI2V-5B/snapshots/921dbaf3f1674a56f47e83fb80a34bac8a8f203e/Wan2.2_VAE.pth'
DEFAULTS = SRC / '.agents/skills/cosmos3-nano-sim-transfer/inference/assets/sample_args.json'
WORK = FE / 'out/cosmos_worker'; WORK.mkdir(parents=True, exist_ok=True)


def request(inputs: dict, settings: dict) -> dict:
    """The request JSON the Cosmos CLI reads, built from a job. Pure, so it is testable without a GPU."""
    c = settings.get('control', 'edge'); n = int(settings.get('frames', 121))
    req = {**json.loads(DEFAULTS.read_text()), 'fps': float(settings.get('fps', 30)), 'num_frames': n, 'max_frames': n,
           'num_video_frames_per_chunk': n, 'name': inputs['name'], 'model_mode': 'video2video', 'aspect_ratio': '16,9',
           'seed': int(settings.get('seed', 2025)), 'prompt': inputs['prompt']}
    ctl = inputs['controls']
    if c == 'edge': req['vision_path'] = str(ctl['rgb']); req['edge'] = {'preset_edge_threshold': settings.get('edge_threshold', 'medium')}
    elif c in ('depth', 'seg'): req[c] = {'control_path': str(ctl[c])}
    else: raise ValueError(f'unknown control {c}; use edge, depth or seg')
    return req


ARGV = ['-i', 'PLACEHOLDER', '-o', str(WORK), '--checkpoint-path', str(CK), '--config-file', str(CK / 'config.json'), '--credential-path', '',
        '--experiment-overrides', 'model.config.tokenizer.bucket_name=', 'model.config.tokenizer.object_store_credential_path_pretrained=',
        f'model.config.tokenizer.vae_path={VAE}', 'model.config.vlm_config.tokenizer.config_variant=hf',
        f'model.config.vlm_config.tokenizer.pretrained_model_name={TOK}', 'model.config.vlm_config.pretrained_weights.enabled=False',
        'model.config.teacher_forcing_frames_per_chunk=1', 'model.config.kv_cache_dtype=null',
        '--defaults-file', str(DEFAULTS), '--autoregressive=True', '--cp-size', '1', '--cfgp-size', '1', '--dp-shard-size', '1',
        '--dp-replicate-size', '1', '--num-outputs', '1', '--max-num-seqs', '1', '--num-steps', '4', '--guidance', '1',
        '--control-guidance', '1', '--kv-cache-inference-size', '0', '--attention-sink-size', '0', '--no-use-torch-compile',
        '--no-use-cuda-graphs', '--no-condition-stream-encode', '--no-diffusion-cache', '--prompt-upsampling=False', '--no-guardrails']


def main():
    from cosmos_framework.inference.common.init import init_script
    init_script()
    import tyro
    from cosmos_framework.scripts.inference import InferenceArgs
    from cosmos_framework.inference.common.args import tyro_cli
    dummy = WORK / 'warmup.json'; dummy.write_text('{}')
    argv = list(ARGV); argv[1] = str(dummy)
    args = tyro_cli(InferenceArgs, args=argv, config=(tyro.conf.OmitArgPrefixes, tyro.conf.CascadeSubcommandArgs, tyro.conf.OmitSubcommandPrefixes))
    setup = args.setup.build_setup()
    pipe = setup.get_inference_cls().create(setup)
    print(json.dumps({'ready': True}), flush=True)
    for line in sys.stdin:
        j = json.loads(line)
        try:
            out_dir = Path(j['inputs']['out_dir']); out_dir.mkdir(parents=True, exist_ok=True)
            rq = out_dir / f"{j['inputs']['name']}.request.json"; rq.write_text(json.dumps(request(j['inputs'], j['settings']), indent=2))
            ov = setup.get_sample_overrides_cls().from_files([rq], overrides=setup.sample_overrides)[0]
            ov.output_dir = out_dir / ov.name
            pipe.generate([ov.build_sample(model_config=pipe.model_config)])
            d = out_dir / ov.name; c = j['settings'].get('control', 'edge')
            print(json.dumps({'job_id': j['job_id'], 'outputs': {'clip': str(d / 'vision.mp4'), 'control_clip': str(d / f'control_{c}.mp4'),
                                                                   'sample_outputs': str(d / 'sample_outputs.json'), 'request': str(rq)}}), flush=True)
        except Exception as e:
            print(json.dumps({'job_id': j['job_id'], 'error': f'{type(e).__name__}: {e}'}), flush=True)


if __name__ == '__main__':
    main()

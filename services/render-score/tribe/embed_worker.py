"""Warm worker for vjepa_embed: each dataset item as a V-JEPA 2 vector, the encoder TRIBE v2 reads video with, so a
dataset can be sorted by similarity to one item (#22). Runs in the tribe environment (/data/envs/tribe on the node),
with the weights from the Hugging Face cache (HF_HUB_CACHE).

Job inputs:   {"paths": ["/path/a.jpg", "/path/b.mp4", ...], "out": "/path/part.npy"}
              an image is held for 64 frames; a video gives 64 frames spread evenly over its length
Outputs:      {"embeddings": out, "n": number of paths, "dim": 1408}; out holds one row per path, in order, each the mean
              of the last layer's tokens, scaled to unit length (float16)
"""
import json, subprocess, sys
from pathlib import Path
import numpy as np, torch
from PIL import Image
from transformers import AutoModel, AutoVideoProcessor

NAME = 'facebook/vjepa2-vitg-fpc64-256'; FRAMES, SIZE = 64, 256
IMAGE = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.gif', '.webp'}
proc = AutoVideoProcessor.from_pretrained(NAME)
model = AutoModel.from_pretrained(NAME, torch_dtype=torch.bfloat16).to('cuda').eval()
print(json.dumps({'ready': True}), flush=True)


def frames(p: Path) -> np.ndarray:
    if p.suffix.lower() in IMAGE:
        im = np.asarray(Image.open(p).convert('RGB').resize((SIZE, SIZE)))
        return np.repeat(im[None], FRAMES, 0)
    raw = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', str(p), '-vf', f'scale={SIZE}:{SIZE}', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                         capture_output=True, check=True).stdout
    v = np.frombuffer(raw, np.uint8).reshape(-1, SIZE, SIZE, 3)
    if not len(v): raise ValueError(f'no frames in {p.name}')
    return v[np.linspace(0, len(v) - 1, FRAMES).round().astype(int)]


for line in sys.stdin:
    j = json.loads(line)
    try:
        rows = []
        for p in j['inputs']['paths']:
            x = proc(videos=[list(frames(Path(p)))], return_tensors='pt')
            with torch.inference_mode():
                h = model(pixel_values_videos=x['pixel_values_videos'].to('cuda', torch.bfloat16)).last_hidden_state.float().mean(1)[0]
            rows.append((h / h.norm()).cpu().numpy())
        out = Path(j['inputs']['out']); out.parent.mkdir(parents=True, exist_ok=True); np.save(out, np.stack(rows).astype(np.float16))
        print(json.dumps({'job_id': j['job_id'], 'outputs': {'embeddings': str(out), 'n': len(rows), 'dim': int(rows[0].shape[0])}}), flush=True)
    except Exception as e:
        print(json.dumps({'job_id': j['job_id'], 'error': f'{type(e).__name__}: {e}'}), flush=True)

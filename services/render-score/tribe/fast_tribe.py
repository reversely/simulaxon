"""TRIBE v2 with the two measured speed fixes, as one importable wrapper.

1. V-JEPA2 runs in bfloat16 (test 1c: per-vertex correlation 0.9998 against float32).
2. Each clip is decoded once into memory, in place of MoviePy seeking 64 frames per window.

Usage:
    from fast_tribe import load, predict_clip
    model = load(cache_folder='cache_fast')
    preds = predict_clip(model, 'clip.mp4')   # (seconds, 20484)

One clip per call, never concatenated (test 2: TRIBE reads the whole window at once).
"""
from pathlib import Path
import numpy as np, pandas as pd, torch

def _patch_bf16():
    import transformers
    if getattr(transformers.AutoModel, '_vcl_bf16', False): return
    orig = transformers.AutoModel.from_pretrained.__func__
    def fp(cls, name, *a, **k):
        m = orig(cls, name, *a, **k)
        if 'vjepa2' in str(name):
            m = m.to(torch.bfloat16); fwd = m.forward
            def forward(*fa, **fk):
                cast = lambda v: v.to(torch.bfloat16) if torch.is_tensor(v) and v.is_floating_point() else v
                out = fwd(*[cast(v) for v in fa], **{kk: cast(v) for kk, v in fk.items()})
                if getattr(out, 'hidden_states', None) is not None: out.hidden_states = tuple(h.float() for h in out.hidden_states)
                if getattr(out, 'last_hidden_state', None) is not None: out.last_hidden_state = out.last_hidden_state.float()
                return out
            m.forward = forward
        return m
    transformers.AutoModel.from_pretrained = classmethod(fp); transformers.AutoModel._vcl_bf16 = True

def _patch_decode_once():
    from moviepy import VideoFileClip
    if getattr(VideoFileClip, '_vcl_fast', False): return
    orig = VideoFileClip.get_frame
    def get_frame(self, t):
        frames = getattr(self, '_vcl_frames', None)
        if frames is None:
            import subprocess
            w, h = self.size
            raw = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', str(self.filename), '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                                 check=True, capture_output=True).stdout
            frames = np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)
            self._vcl_frames = frames
        i = min(int(round(t * self.fps)), len(frames) - 1)
        return frames[max(i, 0)]
    VideoFileClip.get_frame = get_frame; VideoFileClip._vcl_fast = True; VideoFileClip._vcl_orig_get_frame = orig

def load(cache_folder='cache_fast', bf16=True, decode_once=True):
    if bf16: _patch_bf16()
    if decode_once: _patch_decode_once()
    from tribev2.demo_utils import TribeModel
    return TribeModel.from_pretrained('facebook/tribev2', cache_folder=str(cache_folder))

def predict_clip(model, path):
    from neuralset.events.utils import standardize_events
    ev = standardize_events(pd.DataFrame([{'type': 'Video', 'filepath': str(path), 'start': 0.0, 'timeline': 'default', 'subject': 'default'}]))
    preds, _ = model.predict(ev, verbose=False)
    return preds

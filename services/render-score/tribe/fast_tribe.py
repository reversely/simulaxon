"""TRIBE v2 with the two measured speed fixes, as one importable wrapper.

1. V-JEPA2 runs in bfloat16 (test 1c: per-vertex correlation 0.9998 against float32).
2. Each clip is decoded once into memory, in place of MoviePy seeking 64 frames per window.
3. Identical windows are encoded once (Simulaxon #13): V-JEPA 2 reads a 64-frame window twice per clip second, and in a
   held still image or a grey stretch consecutive windows are pixel-identical, so their output is too. The window's
   frames are hashed and a repeat reuses the earlier output; any difference in any pixel encodes afresh.

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

def _patch_same_windows(keep=8):
    """Reuse V-JEPA 2's output for a window whose 64 frames are byte-identical to one of the last few encoded.

    The model returns every layer's tokens (41 x 8192 x 1408 for V-JEPA 2 giant, about 1.9 GB), and TRIBE's extractor then
    averages over the tokens (token_aggregation: mean in TRIBE v2's config). So the memo keeps only that token mean, with a
    token axis of length one: on a repeat the extractor's mean over that one value returns it unchanged. Valid only for
    mean aggregation, which load() checks."""
    from neuralset.extractors import video as V
    cls = V._HFVideoModel
    if getattr(cls, '_vcl_same', False): return
    orig = cls.predict_hidden_states
    import hashlib
    from collections import OrderedDict
    memo: OrderedDict = OrderedDict(); stats = {'encoded': 0, 'reused': 0}
    def predict_hidden_states(self, images, audio=None):
        if audio is not None: return orig(self, images, audio)
        a = np.ascontiguousarray(images)
        key = (self.model_name, a.shape, str(a.dtype), hashlib.blake2b(a.tobytes(), digest_size=16).hexdigest())
        if key in memo:
            memo.move_to_end(key); stats['reused'] += 1; return memo[key]
        out = orig(self, images, audio); stats['encoded'] += 1
        memo[key] = out.mean(dim=2, keepdim=True)   # B x layers x 1 x dim: the token mean the extractor takes next
        if len(memo) > keep: memo.popitem(last=False)
        return out
    cls.predict_hidden_states = predict_hidden_states; cls._vcl_same = True; cls._vcl_stats = stats; cls._vcl_memo = memo


def load(cache_folder='cache_fast', bf16=True, decode_once=True, same_windows=True):
    if bf16: _patch_bf16()
    if decode_once: _patch_decode_once()
    from tribev2.demo_utils import TribeModel
    model = TribeModel.from_pretrained('facebook/tribev2', cache_folder=str(cache_folder))
    if same_windows:
        import glob, os, re
        hub = os.environ.get('HF_HUB_CACHE') or os.path.join(os.environ.get('HF_HOME', os.path.expanduser('~/.cache/huggingface')), 'hub')   # where TRIBE's weights and config are, here and on the node
        cfg = sorted(glob.glob(os.path.join(hub, 'models--facebook--tribev2', 'snapshots', '*', 'config.yaml')))
        text = open(cfg[-1]).read() if cfg else ''
        m = re.search(r'video_feature:.*?token_aggregation:\s*(\w+)', text, re.S); agg = m.group(1) if m else None
        if agg == 'mean': _patch_same_windows()   # the memo keeps token means; any other aggregation encodes every window
    return model

def predict_clip(model, path):
    from neuralset.events.utils import standardize_events
    ev = standardize_events(pd.DataFrame([{'type': 'Video', 'filepath': str(path), 'start': 0.0, 'timeline': 'default', 'subject': 'default'}]))
    preds, _ = model.predict(ev, verbose=False)
    return preds

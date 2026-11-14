"""Datasets: list a repository's files with sizes and licence, fetch the chosen ones in the background, list what is here.

A reference is a URL or a short form: openneuro:ds000117, osf:abcd3, zenodo:123456, figshare:123456,
github:owner/repo[@branch], hf:owner/name, or any direct file URL. Files land in backend/data/fetched/<id>/ with their
repository paths; archives (.zip, .tar.gz) are unpacked beside themselves. A fetch never leaves less than FLOOR_GB free.
Requests carry no personal details.
"""
from __future__ import annotations
import fnmatch, json, re, shutil, tarfile, threading, time, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import requests
from .ingest import DATA

HERE = DATA / 'fetched'
UA = {'User-Agent': 'simulaxon/0.1 (research tool)'}
FLOOR_GB = 60
KIND = {**{e: 'image' for e in ('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.gif', '.webp')},
        **{e: 'video' for e in ('.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v', '.mpg', '.mpeg')},
        **{e: 'audio' for e in ('.wav', '.mp3', '.flac', '.ogg', '.m4a')},
        **{e: 'text' for e in ('.txt', '.csv', '.tsv', '.json', '.md')},
        **{e: 'archive' for e in ('.zip', '.tar', '.gz', '.tgz')},
        **{e: 'brain data' for e in ('.nii', '.gii', '.mgz', '.h5', '.hdf5', '.mat', '.npy')}}


def kind_of(path: str) -> str:
    p = path.lower()
    if p.endswith('.nii.gz'): return 'brain data'
    return KIND.get(Path(p).suffix, 'other')


def _get(url, **kw):
    r = requests.get(url, headers=UA, timeout=60, **kw); r.raise_for_status(); return r


def dataset_id(ref: str) -> str:
    return re.sub(r'[^A-Za-z0-9]+', '_', ref.strip().lower()).strip('_')[:80]


def parse(ref: str) -> tuple[str, str]:
    r = ref.strip()
    for pat, repo in [(r'openneuro(?:\.org/datasets/|:)(ds\d+)', 'openneuro'), (r'osf(?:\.io/|:)([a-z0-9]{5})\b', 'osf'),
                      (r'zenodo(?:\.org/records?/|:)(\d+)', 'zenodo'), (r'figshare(?:\.com/articles/(?:[^/]+/)*?|:)(\d{5,})', 'figshare'),
                      (r'github(?:\.com/|:)([\w.-]+/[\w.-]+(?:@[\w./-]+)?)', 'github'), (r'(?:huggingface\.co/datasets/|hf:)([\w.-]+/[\w.-]+)', 'hf')]:
        if m := re.search(pat, r, re.I): return repo, m.group(1).removesuffix('.git')
    if r.startswith('http'): return 'url', r
    raise ValueError(f'not a dataset reference: {ref}')


def listing(ref: str) -> dict:
    """Every file with its size and a download URL, the licence and the title, as the repository reports them."""
    repo, key = parse(ref); files, licence, title = [], None, key
    if repo == 'openneuro':
        token = None
        while True:
            q = {'list-type': '2', 'prefix': f'{key}/'} | ({'continuation-token': token} if token else {})
            x = ET.fromstring(_get('https://s3.amazonaws.com/openneuro.org', params=q).content); ns = {'s': x.tag.split('}')[0].strip('{')}
            for c in x.findall('s:Contents', ns):
                k = c.find('s:Key', ns).text; files.append({'path': k[len(key) + 1:], 'size': int(c.find('s:Size', ns).text), 'url': f'https://s3.amazonaws.com/openneuro.org/{k}'})
            token = (x.find('s:NextContinuationToken', ns).text if x.find('s:NextContinuationToken', ns) is not None else None)
            if not token: break
        try:
            d = json.loads(_get(f'https://s3.amazonaws.com/openneuro.org/{key}/dataset_description.json').text); title = d.get('Name', key); licence = d.get('License')
        except Exception: pass
    elif repo == 'osf':
        node = _get(f'https://api.osf.io/v2/nodes/{key}/', params={'embed': 'license'}).json()['data']; title = node['attributes'].get('title', key)
        licence = (((node.get('embeds') or {}).get('license') or {}).get('data') or {}).get('attributes', {}).get('name')
        def walk(url, prefix):
            while url:
                j = _get(url).json()
                for it in j['data']:
                    a = it['attributes']
                    if a['kind'] == 'folder': walk(it['relationships']['files']['links']['related']['href'], prefix + a['name'] + '/')
                    else: files.append({'path': prefix + a['name'], 'size': a.get('size') or 0, 'url': it['links']['download']})
                url = j['links'].get('next')
        walk(f'https://api.osf.io/v2/nodes/{key}/files/osfstorage/', '')
    elif repo == 'zenodo':
        j = _get(f'https://zenodo.org/api/records/{key}').json(); title = j['metadata'].get('title'); licence = (j['metadata'].get('license') or {}).get('id')
        files = [{'path': f['key'], 'size': f['size'], 'url': f['links']['self']} for f in j.get('files', [])]
    elif repo == 'figshare':
        j = _get(f'https://api.figshare.com/v2/articles/{key}').json(); title = j.get('title'); licence = (j.get('license') or {}).get('name')
        files = [{'path': f['name'], 'size': f['size'], 'url': f['download_url']} for f in j.get('files', [])]
    elif repo == 'github':
        name, _, branch = key.partition('@'); info = _get(f'https://api.github.com/repos/{name}').json()
        branch = branch or info.get('default_branch', 'main'); title = info.get('description') or name; licence = (info.get('license') or {}).get('spdx_id')
        tree = _get(f'https://api.github.com/repos/{name}/git/trees/{branch}', params={'recursive': '1'}).json()
        files = [{'path': t['path'], 'size': t.get('size', 0), 'url': f'https://raw.githubusercontent.com/{name}/{branch}/{t["path"]}'} for t in tree.get('tree', []) if t['type'] == 'blob']
    elif repo == 'hf':
        from huggingface_hub import HfApi
        api = HfApi(); info = api.dataset_info(key); licence = (info.card_data or {}).get('license') if info.card_data else None; title = key
        files = [{'path': f.path, 'size': f.size or 0, 'url': f'https://huggingface.co/datasets/{key}/resolve/main/{f.path}'}
                 for f in api.list_repo_tree(key, repo_type='dataset', recursive=True) if hasattr(f, 'size') and f.size is not None]
    else:
        h = requests.head(key, headers=UA, timeout=60, allow_redirects=True)
        files = [{'path': Path(key.split('?')[0]).name or 'file', 'size': int(h.headers.get('content-length', 0)), 'url': key}]
    return {'id': dataset_id(f'{repo}:{key}'), 'ref': ref, 'repository': repo, 'key': key, 'title': title, 'licence': licence, 'files': files}


def summary(lst: dict, pattern: str | None = None, limit: int = 150) -> dict:
    """What the agent sees: totals by kind and the files matching the pattern, at most limit of them."""
    fs = [f for f in lst['files'] if not pattern or fnmatch.fnmatch(f['path'], pattern) or fnmatch.fnmatch(Path(f['path']).name, pattern)]
    by: dict[str, list] = {}
    for f in lst['files']: by.setdefault(kind_of(f['path']), []).append(f['size'])
    return {k: lst[k] for k in ('id', 'ref', 'repository', 'title', 'licence')} | {
        'files': len(lst['files']), 'gigabytes': round(sum(f['size'] for f in lst['files']) / 1e9, 3),
        'by_kind': {k: {'files': len(v), 'gigabytes': round(sum(v) / 1e9, 3)} for k, v in sorted(by.items())},
        'matching': len(fs), 'matching_gigabytes': round(sum(f['size'] for f in fs) / 1e9, 3),
        'shown': [{'path': f['path'], 'megabytes': round(f['size'] / 1e6, 3)} for f in fs[:limit]]}


_fetches: dict[str, dict] = {}


def fetch(ref: str, include: list[str], max_gb: float, on_event=lambda m: None) -> dict:
    """Start fetching the files matching any include pattern. Returns at once; on_event reports progress and the end."""
    lst = listing(ref); did = lst['id']
    want = [f for f in lst['files'] if any(fnmatch.fnmatch(f['path'], p) or fnmatch.fnmatch(Path(f['path']).name, p) for p in include)]
    total = sum(f['size'] for f in want)
    if not want: raise ValueError(f'no file matches {include}; {len(lst["files"])} files in {lst["title"]}')
    if total > max_gb * 1e9: raise ValueError(f'{len(want)} files, {total / 1e9:.2f} GB, over the {max_gb} GB limit; narrow the patterns or raise max_gb')
    free = shutil.disk_usage(HERE.parent).free
    if free - total < FLOOR_GB * 1e9: raise ValueError(f'only {free / 1e9:.0f} GB free; this fetch would leave less than {FLOOR_GB} GB')
    if _fetches.get(did, {}).get('status') == 'fetching': return _fetches[did]
    st = _fetches[did] = {'dataset_id': did, 'status': 'fetching', 'files': len(want), 'done': 0, 'bytes': 0, 'total_bytes': total, 'started': time.time(), 'error': None}
    root = HERE / did

    def go():
        try:
            for f in want:
                dst = root / f['path']; dst.parent.mkdir(parents=True, exist_ok=True)
                if not (dst.exists() and (f['size'] == 0 or dst.stat().st_size == f['size'])):
                    for attempt in range(5):   # servers drop connections mid-fetch; each file is retried with a growing pause
                        try:
                            got = 0
                            with requests.get(f['url'], headers=UA, stream=True, timeout=120) as r:
                                r.raise_for_status(); tmp = dst.with_suffix(dst.suffix + '.part')
                                with open(tmp, 'wb') as out:
                                    for chunk in r.iter_content(1 << 20): out.write(chunk); got += len(chunk)
                                tmp.rename(dst); st['bytes'] += got; break
                        except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError):
                            if attempt == 4: raise
                            time.sleep(2 ** attempt)
                    if kind_of(f['path']) == 'archive': _unpack(dst)
                else: st['bytes'] += f['size']
                st['done'] += 1; on_event({'fetch': did, 'stage': 'fetching', **_pub(st)})
            meta = {k: lst[k] for k in ('id', 'ref', 'repository', 'key', 'title', 'licence')} | {'include': include, 'fetched_at': time.strftime('%Y-%m-%d %H:%M'), 'files': [f['path'] for f in want]}
            (root / '_dataset.json').write_text(json.dumps(meta, indent=1))
            st['status'] = 'done'; on_event({'fetch': did, 'stage': 'done', **_pub(st)})
        except Exception as e:
            st['status'] = 'failed'; st['error'] = f'{type(e).__name__}: {e}'[:400]; on_event({'fetch': did, 'stage': 'failed', **_pub(st)})
    threading.Thread(target=go, daemon=True).start()
    return _pub(st)


def _pub(st: dict) -> dict:
    return {k: v for k, v in st.items() if k != 'started'} | {'seconds': round(time.time() - st['started'])}


def _unpack(p: Path):
    out = p.with_name(p.name.split('.')[0])
    if zipfile.is_zipfile(p):
        with zipfile.ZipFile(p) as z: z.extractall(out)
    elif tarfile.is_tarfile(p):
        with tarfile.open(p) as t: t.extractall(out, filter='data')


def status(did: str) -> dict | None:
    return _pub(_fetches[did]) if did in _fetches else None


def here() -> list[dict]:
    """Datasets on this machine: source, licence, files and size."""
    out = []
    for m in sorted(HERE.glob('*/_dataset.json')):
        d = json.loads(m.read_text()); n = sum(1 for p in m.parent.rglob('*') if p.is_file()) - 1
        out.append({k: d.get(k) for k in ('id', 'ref', 'title', 'licence', 'fetched_at')} | {'files_here': n, 'gigabytes': round(sum(p.stat().st_size for p in m.parent.rglob('*') if p.is_file()) / 1e9, 3)})
    for did, st in _fetches.items():
        if st['status'] != 'done': out.append({'id': did, **_pub(st)})
    return out


def files(did: str, pattern: str = '*', limit: int = 300) -> dict:
    """Files of a fetched dataset matching the pattern, with their kind and size; images also with their size in pixels."""
    root = HERE / did
    if not root.exists(): raise ValueError(f'no fetched dataset {did}')
    fs = sorted(p for p in root.rglob('*') if p.is_file() and not p.name.endswith('.part') and p.name != '_dataset.json'
                and (fnmatch.fnmatch(str(p.relative_to(root)), pattern) or fnmatch.fnmatch(p.name, pattern)))
    rows = []
    for p in fs[:limit]:
        r = {'path': str(p.relative_to(root)), 'kind': kind_of(p.name), 'kilobytes': round(p.stat().st_size / 1e3, 1)}
        if r['kind'] == 'image':
            try:
                from PIL import Image
                with Image.open(p) as im: r['pixels'] = list(im.size)
            except Exception: pass
        rows.append(r)
    by: dict[str, int] = {}
    for p in fs: by[kind_of(p.name)] = by.get(kind_of(p.name), 0) + 1
    return {'dataset_id': did, 'pattern': pattern, 'matching': len(fs), 'by_kind': by, 'shown': rows}

"""Papers: find one, fetch its open-access full text, and read it in parts.

Full text comes from, in order: Europe PMC's open-access XML (sections as the journal marked them), arXiv's PDF, then
the open-access PDF OpenAlex lists. PDFs become text with pdftotext and are split at lines that look like headings.
Each paper is saved once under backend/data/files/papers/<id>.json. Requests carry no personal details.
"""
from __future__ import annotations
import json, re, subprocess, tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
import requests
from .ingest import FILES

DIR = FILES / 'papers'
UA = {'User-Agent': 'simulaxon/0.1 (research tool)'}
EPMC = 'https://www.ebi.ac.uk/europepmc/webservices/rest'
PART = 6000   # characters returned per read


def _get(url: str, **kw) -> requests.Response:
    r = requests.get(url, headers=UA, timeout=60, **kw); r.raise_for_status(); return r


def paper_id(ref: str) -> str:
    return re.sub(r'[^A-Za-z0-9]+', '_', ref.strip().lower()).strip('_')[:80]


def parse_ref(ref: str) -> dict:
    """A DOI, PMCID, PMID, arXiv id, or a URL holding one of them."""
    r = ref.strip()
    if m := re.search(r'(10\.\d{4,9}/[^\s"<>]+)', r): return {'doi': m.group(1).rstrip('.')}
    if m := re.search(r'\b(PMC\d+)\b', r, re.I): return {'pmcid': m.group(1).upper()}
    if m := re.search(r'arxiv\.org/(?:abs|pdf)/([\w.\-/]+?)(?:v\d+)?(?:\.pdf)?$', r) or re.fullmatch(r'(\d{4}\.\d{4,5})(?:v\d+)?', r): return {'arxiv': m.group(1)}
    if re.fullmatch(r'\d{6,9}', r): return {'pmid': r}
    raise ValueError(f'not a DOI, PMCID, PMID or arXiv id: {ref}')


def search(query: str, n: int = 8) -> list[dict]:
    """Works matching the words, most cited first among the best matches, with whether full text is open."""
    j = _get('https://api.openalex.org/works', params={'search': query, 'per-page': n}).json()
    return [{'title': w.get('title'), 'year': w.get('publication_year'), 'doi': (w.get('doi') or '').replace('https://doi.org/', '') or None,
             'authors': ', '.join(a['author']['display_name'] for a in w.get('authorships', [])[:4]) + (' et al.' if len(w.get('authorships', [])) > 4 else ''),
             'venue': ((w.get('primary_location') or {}).get('source') or {}).get('display_name'),
             'open_access': (w.get('open_access') or {}).get('is_oa'), 'cited_by': w.get('cited_by_count')} for w in j.get('results', [])]


def _text(el) -> str:
    return re.sub(r'\s+', ' ', ''.join(el.itertext())).strip() if el is not None else ''


def _from_jats(xml: str) -> list[dict]:
    root = ET.fromstring(xml); out = []
    if (ab := root.find('.//abstract')) is not None: out.append({'heading': 'Abstract', 'text': _text(ab)})
    def walk(sec, prefix):
        title = _text(sec.find('title')) or 'Section'
        paras = [_text(p) for p in sec.findall('p')]
        caps = [f"[{_text(f.find('label'))}] {_text(f.find('caption'))}" for f in sec.findall('fig') + sec.findall('table-wrap')]
        if paras or caps: out.append({'heading': prefix + title, 'text': '\n\n'.join(paras + caps)})
        for sub in sec.findall('sec'): walk(sub, prefix + title + ' / ')
    body = root.find('.//body')
    for sec in (body.findall('sec') if body is not None else []): walk(sec, '')
    for f in root.findall('.//floats-group/fig') + root.findall('.//floats-group/table-wrap'):
        out.append({'heading': 'Figures and tables', 'text': f"[{_text(f.find('label'))}] {_text(f.find('caption'))}"})
    for s in root.findall('.//supplementary-material'):
        link = s.get('{http://www.w3.org/1999/xlink}href')
        if link: out.append({'heading': 'Supplementary material', 'text': f'{_text(s)} (file: {link})'})
    return out


HEAD = re.compile(r'^(?:\d+(?:\.\d+)*\.?\s+)?(abstract|introduction|background|methods?|materials and methods|experimental procedures|participants|subjects|stimuli|procedure|design|data analysis|analysis|results|discussion|general discussion|conclusions?|references|acknowledg(e)?ments|supplementary.*|data availability.*|code availability.*|experiment \d+.*)$', re.I)


def _from_pdf(data: bytes) -> list[dict]:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / 'p.pdf'; p.write_bytes(data)
        txt = subprocess.run(['pdftotext', '-layout', str(p), '-'], capture_output=True, text=True, timeout=120).stdout
    out, cur, buf = [], 'Start', []
    for line in txt.splitlines():
        s = line.strip()
        if s and len(s) < 70 and HEAD.match(s):
            if buf: out.append({'heading': cur, 'text': '\n'.join(buf).strip()})
            cur, buf = s, []
        else: buf.append(line.rstrip())
    if buf: out.append({'heading': cur, 'text': '\n'.join(buf).strip()})
    return [x for x in out if x['text']]


def fetch(ref: str) -> dict:
    """The paper's metadata and sections, from the first source with open full text; saved, so a second fetch is instant.
    A path to a PDF on this machine (one a person added) is read directly: papers that are free to read on a publisher's
    site but not openly licensed are not fetched here, because publishers refuse automated clients."""
    if ref.lower().endswith('.pdf') and Path(ref).expanduser().is_file():
        pdf = Path(ref).expanduser(); pid = paper_id(pdf.stem); f = DIR / f'{pid}.json'
        if f.exists(): return json.loads(f.read_text())
        sections = _from_pdf(pdf.read_bytes())
        paper = {'id': pid, 'ref': ref, 'title': pdf.stem, 'source': f'PDF added by a person, {pdf.name}', 'full_text': bool(sections), 'sections': sections}
        DIR.mkdir(parents=True, exist_ok=True); f.write_text(json.dumps(paper)); return paper
    ids = parse_ref(ref); pid = paper_id(next(iter(ids.values())))
    f = DIR / f'{pid}.json'
    if f.exists(): return json.loads(f.read_text())
    meta, sections, source = {}, [], None
    q = {'doi': f'DOI:"{ids.get("doi")}"', 'pmcid': f'PMCID:{ids.get("pmcid")}', 'pmid': f'EXT_ID:{ids.get("pmid")} AND SRC:MED'}.get(next(iter(ids)))
    if q:
        hits = _get(f'{EPMC}/search', params={'query': q, 'format': 'json', 'resultType': 'core'}).json().get('resultList', {}).get('result', [])
        if hits:
            h = hits[0]
            meta = {'title': h.get('title'), 'authors': h.get('authorString'), 'year': h.get('pubYear'), 'venue': (h.get('journalInfo') or {}).get('journal', {}).get('title'),
                    'doi': h.get('doi'), 'pmcid': h.get('pmcid'), 'abstract': re.sub(r'<[^>]+>', '', h.get('abstractText') or ''), 'licence': h.get('license')}
            if h.get('pmcid') and h.get('isOpenAccess') == 'Y':
                try: sections = _from_jats(_get(f"{EPMC}/{h['pmcid']}/fullTextXML").text); source = f"Europe PMC, {h['pmcid']}, full text XML"
                except Exception: sections = []
    if not sections and ids.get('arxiv'):
        a = ids['arxiv']; entry = _get('https://export.arxiv.org/api/query', params={'id_list': a}).text
        t = re.search(r'<entry>.*?<title>(.*?)</title>', entry, re.S)
        meta = meta or {'title': re.sub(r'\s+', ' ', t.group(1)).strip() if t else a, 'authors': ', '.join(re.findall(r'<name>(.*?)</name>', entry)), 'year': (re.search(r'<published>(\d{4})', entry) or [None, None])[1], 'arxiv': a}
        sections = _from_pdf(_get(f'https://arxiv.org/pdf/{a}').content); source = f'arXiv {a}, PDF'
    if not sections and (doi := ids.get('doi') or meta.get('doi')):
        w = _get(f'https://api.openalex.org/works/doi:{doi}').json()
        meta = meta or {'title': w.get('title'), 'year': w.get('publication_year'), 'doi': doi,
                        'authors': ', '.join(a['author']['display_name'] for a in w.get('authorships', []))}
        for loc in [w.get('best_oa_location') or {}] + (w.get('locations') or []):
            url = loc.get('pdf_url')
            if not url: continue
            try:
                r = _get(url, allow_redirects=True)
                if r.content[:4] == b'%PDF': sections = _from_pdf(r.content); source = f'open-access PDF, {url}'; meta.setdefault('licence', loc.get('license')); break
            except Exception: continue
    if not meta: raise ValueError(f'no record found for {ref}')
    paper = {'id': pid, 'ref': ref, **meta, 'source': source, 'full_text': bool(sections),
             'sections': sections or ([{'heading': 'Abstract', 'text': meta.get('abstract', '')}] if meta.get('abstract') else [])}
    DIR.mkdir(parents=True, exist_ok=True); f.write_text(json.dumps(paper))
    return paper


def outline(p: dict) -> dict:
    """What a fetch returns to the agent: metadata and the list of parts, without the text."""
    return {k: p.get(k) for k in ('id', 'title', 'authors', 'year', 'venue', 'doi', 'pmcid', 'licence', 'source', 'full_text')} | {
        'parts': [{'part': i, 'heading': s['heading'], 'characters': len(s['text'])} for i, s in enumerate(p['sections'])],
        'note': None if p['full_text'] else 'No open full text was found; only the abstract is available.'}


def read(paper_id: str, part: int | None = None, find: str | None = None, offset: int = 0) -> dict:
    """One part of a paper from offset, at most PART characters, or every passage containing the words in find."""
    p = json.loads((DIR / f'{paper_id}.json').read_text())
    if find:
        words = [w.lower() for w in find.split()]; hits = []
        for i, s in enumerate(p['sections']):
            t = s['text']; low = t.lower()
            for m in re.finditer(re.escape(words[0]), low):
                a, b = max(0, m.start() - 400), min(len(t), m.end() + 400)
                if all(w in low[a:b] for w in words): hits.append({'part': i, 'heading': s['heading'], 'offset': a, 'text': t[a:b]})
                if len(hits) >= 12: break
        return {'paper_id': paper_id, 'find': find, 'passages': hits}
    s = p['sections'][part or 0]; t = s['text'][offset:offset + PART]
    return {'paper_id': paper_id, 'part': part or 0, 'heading': s['heading'], 'offset': offset, 'text': t,
            'next_offset': offset + PART if offset + PART < len(s['text']) else None}

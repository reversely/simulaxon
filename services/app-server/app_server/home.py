"""Where the lab's data and research tools live: backend/data (the store, files, fetched datasets, chat sessions) and
feasibility/ (TRIBE's source and environment, the search indexes, finished runs, the observer scripts, the workers'
environments).

SIMULAXON_HOME names the folder that holds both. On the Spark it is the visual-cortex-lab checkout; on the cluster the
wiring moves them under /data (docs/wiring-prompt.md, section 2).
"""
import os
from pathlib import Path

HOME = Path(os.environ.get('SIMULAXON_HOME', '/data'))

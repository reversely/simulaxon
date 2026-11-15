"""One setting names the app server's data root (#9): SIMULAXON_HOME and SIMULAXON_DATA each fall back to the other,
then to /data. Each case imports the modules fresh, since they read the environment at import."""
import json, os, subprocess, sys
from pathlib import Path
import pytest

APP = Path(__file__).resolve().parents[1]


def roots(**env):
    e = {k: v for k, v in os.environ.items() if k not in ('SIMULAXON_HOME', 'SIMULAXON_DATA')} | env | {'PYTHONPATH': str(APP)}
    out = subprocess.run([sys.executable, '-c', 'import json; from app_server import home, config; print(json.dumps([str(home.HOME), str(config.DATA)]))'],
                         env=e, capture_output=True, text=True, check=True).stdout
    return json.loads(out)


@pytest.mark.parametrize('env, home, data', [
    ({}, '/data', '/data'),
    ({'SIMULAXON_HOME': '/srv/lab'}, '/srv/lab', '/srv/lab'),
    ({'SIMULAXON_DATA': '/mnt/vast'}, '/mnt/vast', '/mnt/vast'),
    ({'SIMULAXON_HOME': '/srv/lab', 'SIMULAXON_DATA': '/mnt/vast'}, '/srv/lab', '/mnt/vast'),
])
def test_either_setting_names_the_root(env, home, data):
    assert roots(**env) == [home, data]

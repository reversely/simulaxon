"""One run per project: a second project_run while one is live is refused, never started beside it (#12)."""
import pytest
from app_server.lab import runner


def test_a_second_run_of_a_live_project_is_refused():
    runner.LIVE['project_x'] = 'token_1'
    try:
        with pytest.raises(ValueError, match='already running'):
            runner.start(None, None, 'project_x', 'agent')
    finally:
        runner.LIVE.pop('project_x', None)

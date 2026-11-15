"""Every tool a step can record has a plain name in the app's one name table (frontend/src/api.ts TOOL_NAMES, #21), so
History and the chat never show a tool's code name."""
import re, unittest
from pathlib import Path
from app_server.store import Store
from app_server.tools import Tools
from app_server.lab.tools import register

API = Path(__file__).resolve().parents[3] / 'frontend' / 'src' / 'api.ts'


class ToolNames(unittest.TestCase):
    def test_every_tool_named(self):
        t = Tools(Store()); register(t, lambda m: None)
        body = API.read_text().split('export const TOOL_NAMES', 1)[1].split('\n}', 1)[0]
        named = set(re.findall(r'(\w+):\s*["\']', body))
        missing = sorted(set(t.registry) - named)
        self.assertEqual(missing, [], f'tools without a plain name in api.ts TOOL_NAMES: {missing}')


if __name__ == '__main__':
    unittest.main()

"""Package identity, translations, and publication boundary checks."""

import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.build_release import COMPONENT, FILES, validate_component


def leaf_paths(value, prefix=()):
    if not isinstance(value, dict):
        return {prefix}
    return set().union(*(leaf_paths(item, (*prefix, key)) for key, item in value.items()))


class PackageTests(unittest.TestCase):
    def test_manifest_and_hacs(self):
        manifest = validate_component()
        self.assertEqual(manifest["iot_class"], "local_polling")
        self.assertEqual(manifest["requirements"], ["python-miio>=0.5.12"])
        self.assertNotIn("single_config_entry", manifest)
        hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
        self.assertEqual(hacs["homeassistant"], "2026.10.4")

    def test_translations_cover_identical_keys(self):
        strings = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))
        for language in ("en", "zh-Hans"):
            translation = json.loads(
                (COMPONENT / "translations" / f"{language}.json").read_text(encoding="utf-8")
            )
            self.assertEqual(leaf_paths(strings), leaf_paths(translation))
        self.assertEqual(
            strings, json.loads((COMPONENT / "translations/en.json").read_text(encoding="utf-8"))
        )

    def test_allowlist_covers_only_component_sources(self):
        actual = {
            str(path.relative_to(COMPONENT)).replace("\\", "/")
            for path in COMPONENT.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        }
        self.assertEqual(actual, set(FILES))
        self.assertTrue(all(not part.endswith((".dpapi", ".zip", ".log")) for part in FILES))

    def test_all_python_compiles(self):
        for name in FILES:
            if name.endswith(".py"):
                compile((COMPONENT / name).read_text(encoding="utf-8"), name, "exec")

    def test_energy_has_no_unverified_accumulation_state_class(self):
        if importlib.util.find_spec("homeassistant") is None:
            self.skipTest("Requires Home Assistant runtime")
        from custom_components.yutai_wifi.sensor import DESCRIPTIONS

        energy = next(item for item in DESCRIPTIONS if item.key == "energy")
        self.assertIsNone(energy.state_class)


if __name__ == "__main__":
    unittest.main()

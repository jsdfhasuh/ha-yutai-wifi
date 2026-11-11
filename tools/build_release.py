"""Build only the reviewed component allowlist. Never bundle a workspace tree."""

import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "yutai_wifi"
FILES = (
    "__init__.py",
    "client.py",
    "config_flow.py",
    "const.py",
    "coordinator.py",
    "diagnostics.py",
    "entity.py",
    "models.py",
    "sensor.py",
    "switch.py",
    "manifest.json",
    "strings.json",
    "translations/en.json",
    "translations/zh-Hans.json",
    "brand/icon.png",
    "brand/icon@2x.png",
)


def validate_component():
    manifest = json.loads((COMPONENT / "manifest.json").read_text(encoding="utf-8"))
    if manifest["domain"] != "yutai_wifi" or not manifest["config_flow"]:
        raise ValueError("Unexpected integration manifest")
    if not re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"]):
        raise ValueError("Unexpected version")
    for name in FILES:
        path = COMPONENT / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(COMPONENT.resolve()):
            raise ValueError("Invalid package source")
        if path.suffix == ".png":
            data = path.read_bytes()
            if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > 131072:
                raise ValueError("Unexpected brand image")
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"(?i)\b[0-9a-f]{32}\b|\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b|\b192\.168\.\d+\.\d+\b", text):
            raise ValueError("Potential private identity or credential in component")
    return manifest


def build():
    manifest = validate_component()
    output = ROOT / "dist" / f"yutai_wifi-{manifest['version']}.zip"
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(COMPONENT / name, "custom_components/yutai_wifi/" + name)
    with zipfile.ZipFile(output) as archive:
        expected = {"custom_components/yutai_wifi/" + name for name in FILES}
        if set(archive.namelist()) != expected or archive.testzip() is not None:
            raise ValueError("Invalid release package")
    print(f"Package: {output}")
    print(f"Files: {len(FILES)}")
    print(f"SHA256: {hashlib.sha256(output.read_bytes()).hexdigest()}")
    return output


if __name__ == "__main__":
    build()

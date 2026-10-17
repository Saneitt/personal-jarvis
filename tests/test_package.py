import importlib.util
import json
from pathlib import Path
import zipfile

def test_release_excludes_personal_data_and_matches_hashes(tmp_path):
    import hashlib
    path=Path(__file__).resolve().parents[1]/"scripts/package_release.py"
    spec=importlib.util.spec_from_file_location("packager",path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    package=module.package(tmp_path/"release.zip")
    with zipfile.ZipFile(package) as archive:
        names=archive.namelist()
        forbidden=("PersonalJarvis/data/","PersonalJarvis/models/","PersonalJarvis/.venv/",
                   "PersonalJarvis/.runtime/","PersonalJarvis/reference/","PersonalJarvis/output/")
        assert not any(name.startswith(forbidden) or name.endswith("config.local.json") for name in names)
        manifest=json.loads(archive.read("PersonalJarvis/PACKAGE.json"))
        for name,digest in manifest["files"].items():
            assert hashlib.sha256(archive.read("PersonalJarvis/"+name)).hexdigest()==digest
        assert "PersonalJarvis/Setup Jarvis.cmd" in names
        assert "PersonalJarvis/config/models.json" in names

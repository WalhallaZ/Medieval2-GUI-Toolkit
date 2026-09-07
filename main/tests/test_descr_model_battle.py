"""Smoke tests for descriptor-first battle model support.

Run with: ``python -m tests.test_descr_model_battle`` from ``main/``.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import PropertyMock, patch

from unittransfer import dmb, modeldb
from unittransfer.mod import Mod


SOURCE = """; descriptor preamble\n\n\
type\tknight\n\
scale\t1.2\n\
skeleton\tfs_human, fs_human_secondary\n\
skeleton_attachment_primary\tshield\n\
mesh\tunit_models/knight/one.mesh, 11\n\
texture\tengland, unit_models/knight/a.texture, unit_models/knight/a_normal.texture, unit_sprites/a.spr\n\
texture_attachments\tengland, unit_models/sets/shield.texture, unit_models/sets/shield_normal.texture\n\
torch\t16, 0, 0, 0, 0, 0, 0\n\n\
type\tarcher\n\
mesh\tunit_models/archer/one.mesh, 20\n\
texture\tslave, unit_models/archer/a.texture, unit_models/archer/a_normal.texture, unit_sprites/a.spr\n"""


def check(label, ok):
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}")
    if not ok:
        raise SystemExit(1)


db = dmb.parse_text(SOURCE)
check("descriptor parses types and faction textures", db.get("knight").main_textures[0].faction == "england")
check("descriptor is byte-exact when untouched", db.to_text() == SOURCE)
changed = modeldb.rewrite_entry_paths(db.get("knight").raw,
                                      {"unit_models/knight/one.mesh": "unit_models/new/one.mesh"})
changed = modeldb.add_texture_factions(changed, ["france"], prefer="england")
entry = modeldb.parse_entry_text(changed)
check("path rewrite stays in descriptor syntax", entry.lods[0][0] == "unit_models/new/one.mesh")
check("faction clone works for descriptor textures", any(t.faction == "france" for t in entry.main_textures))

with TemporaryDirectory() as temp:
    root = Path(temp) / "mod"
    data = root / "data"
    data.mkdir(parents=True)
    (data / "descr_model_battle.txt").write_text(SOURCE, encoding="latin-1")
    legacy = data / "unit_models" / "battle_models.modeldb"
    legacy.parent.mkdir()
    legacy.write_text("not selected", encoding="latin-1")
    (data / "descr_caps_ex.txt").write_text(
        "; model battle source:\nmodel_battle_source\t  text\n", encoding="latin-1")
    mod = Mod(root)
    check("descriptor does not win without M2EX", mod.modeldb_path == legacy)
    with patch.object(Mod, "m2ex", new_callable=PropertyMock, return_value=True):
        check("descriptor wins with M2EX and caps opt-in", mod.modeldb_path.name == "descr_model_battle.txt")
        check("selected source is parsed as descriptor", mod.modeldb.format == "dmb")
    (data / "descr_caps_ex.txt").write_text("model_battle_source modeldb\n", encoding="latin-1")
    with patch.object(Mod, "m2ex", new_callable=PropertyMock, return_value=True):
        check("legacy remains selected without the text setting", mod.modeldb_path == legacy)

print("descriptor battle-model checks - ALL PASSED")

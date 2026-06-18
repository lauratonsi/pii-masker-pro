"""CLI smoke tests."""

import json

from pii_masker.cli import main


def test_inline_text_to_file(tmp_path, capsys):
    out = tmp_path / "out.txt"
    rc = main(["Scrivi a mario.rossi@gmail.com", "-o", str(out)])
    assert rc == 0
    assert out.read_text() == "Scrivi a [EMAIL]"


def test_reversible_writes_map(tmp_path, capsys):
    map_path = tmp_path / "map.json"
    rc = main(["Mail a a@b.it", "--reversible", "--map-out", str(map_path)])
    assert rc == 0
    mapping = json.loads(map_path.read_text())
    assert "a@b.it" in mapping.values()


def test_report_to_stderr(capsys):
    main(["Scrivi a mario.rossi@gmail.com", "--report"])
    err = capsys.readouterr().err
    assert "EMAIL_ADDRESS" in err

"""F5 `ilias download` für die ILIAS-Instanz `hhn` (ANFORDERUNGEN.md §3, F5).

Nur gegen die Fake-HHN (localhost). Geprüft: Ordnerstruktur, Auswahl per Pfad/ref_id,
erneuter Lauf lädt nichts doppelt, Änderung wird nachgeladen, verweigerte Dateien
brechen den Rest nicht ab, Session-Ende -> Exit 3, keine Secrets/Tokens in Ausgaben.
Eigener Lauf: `HHN_STRICT=1 uv run pytest tests/hhn/test_download.py -q`
"""

from __future__ import annotations

import json
from pathlib import Path

from .conftest import HhnHarness
from .fixtures.ls.data import LONG_TITLE, NFC_TITLE
from .helpers import err_json, ok_json

COURSE = "900101"


def _course_dir(h: HhnHarness, data: dict) -> Path:
    path = Path(data["target_dir"])
    assert path.is_dir(), data
    assert path.parent == (h.cwd / "dl").resolve(), path
    return path


def _files(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and not p.name.startswith(".")}


def _items(data: dict, status: str) -> list[dict]:
    return [i for i in data["items"] if i["status"] == status]


def test_download_help(hh: HhnHarness):
    r = hh.run("download", "--help")
    assert r.exit_code == 0, str(r)
    for opt in ("--out", "--dry-run", "--force", "--json", "--instance"):
        assert opt in r.stdout


def test_download_whole_course_keeps_folder_structure(logged_in: HhnHarness):
    h = logged_in
    since = len(h.world.requests)
    data = ok_json(h.run("download", COURSE, "-o", "dl", "--json"))
    root = _course_dir(h, data)
    assert root.name.startswith("Mathematik A")
    got = _files(root)
    expected = {
        "Skript Kapitel 1.pdf",
        f"{LONG_TITLE}.pdf",
        "Übungsblätter/Blatt 10.pdf",
        "Übungsblätter/Blatt 2.pdf",
        "Übungsblätter/Lösungen/Lösung Blatt 2.pdf",
        "[Klausur] Altklausuren/Klausur Beispieljahr.pdf",
        f"[Klausur] Altklausuren/{NFC_TITLE}.html",
    }
    assert got == expected, got
    # Inhalt kommt wirklich vom Server (inkl. Umweg über /data/… für Blatt 2)
    assert b"ref=900312" in (root / "Übungsblätter/Blatt 2.pdf").read_bytes()
    assert sorted(h.world.downloads(since)) == sorted([900301, 900302, 900311, 900312, 900321, 900331, 900332])
    # offline-Datei wird nicht angefragt, sondern als übersprungen gemeldet
    offline = [i for i in data["items"] if i["ref_id"] == 900303]
    assert offline and offline[0]["status"] == "skipped" and offline[0]["error_code"] == "offline"
    assert data["ok"] is True and data["summary"]["downloaded"] == 7
    assert not list(root.rglob("*.part"))


def test_second_run_skips_and_change_is_reloaded(logged_in: HhnHarness):
    h = logged_in
    ok_json(h.run("download", COURSE, "-o", "dl", "--json"))
    since = len(h.world.requests)
    data = ok_json(h.run("download", COURSE, "-o", "dl", "--json"))
    assert data["summary"]["downloaded"] == 0 and data["summary"]["skipped"] == 8
    assert h.world.downloads(since) == []
    # --force lädt alles neu
    data = ok_json(h.run("download", COURSE, "Übungsblätter/Blatt 10", "-o", "dl", "--force", "--json"))
    assert [i["ref_id"] for i in _items(data, "downloaded")] == [900311]


def test_select_folder_and_ref_id(logged_in: HhnHarness):
    h = logged_in
    data = ok_json(h.run("download", COURSE, "übungsblätter", "-o", "dl", "--json"))
    assert sorted(i["ref_id"] for i in data["items"]) == [900311, 900312, 900321]
    root = _course_dir(h, data)
    assert _files(root) == {"Übungsblätter/Blatt 10.pdf", "Übungsblätter/Blatt 2.pdf", "Übungsblätter/Lösungen/Lösung Blatt 2.pdf"}
    data = ok_json(h.run("download", COURSE, "900301", "-o", "dl", "--json"))
    assert [i["ref_id"] for i in data["items"]] == [900301]


def test_dry_run_downloads_nothing(logged_in: HhnHarness):
    h = logged_in
    since = len(h.world.requests)
    data = ok_json(h.run("download", COURSE, "-o", "dl", "--dry-run", "--json"))
    assert data["dry_run"] is True and data["summary"]["planned"] == 7
    assert h.world.downloads(since) == []
    assert not (h.cwd / "dl").exists() or not _files(h.cwd / "dl")


def test_unknown_path_is_error(logged_in: HhnHarness):
    err_json(logged_in.run("download", COURSE, "Gibt es nicht", "-o", "dl", "--json"), 1, "path_not_found")


def test_forbidden_file_is_reported_rest_continues(logged_in: HhnHarness):
    h = logged_in
    h.world.file_modes[900311] = "forbidden"
    h.world.file_modes[900312] = "html"
    r = h.run("download", COURSE, "Übungsblätter", "-o", "dl", "--json")
    assert r.exit_code == 1, str(r)
    data = json.loads(r.stdout)
    assert data["ok"] is False
    failed = {i["ref_id"]: i["error_code"] for i in _items(data, "failed")}
    assert failed == {900311: "permission_denied", 900312: "parse_error"}
    assert [i["ref_id"] for i in _items(data, "downloaded")] == [900321]
    # nach Freigabe lädt der nächste Lauf genau die fehlenden
    h.world.file_modes.clear()
    data = ok_json(h.run("download", COURSE, "Übungsblätter", "-o", "dl", "--json"))
    assert sorted(i["ref_id"] for i in _items(data, "downloaded")) == [900311, 900312]


def test_session_expired_during_download_exit3(logged_in: HhnHarness):
    h = logged_in
    h.world.file_modes[900301] = "login_redirect"
    err_json(h.run("download", COURSE, "-o", "dl", "--json"), 3, "session_expired")


def test_server_error_exit4(logged_in: HhnHarness):
    h = logged_in
    h.world.file_modes[900301] = "error500"
    err_json(h.run("download", COURSE, "900301", "-o", "dl", "--json"), 4, "network_error")


def test_not_logged_in_exit2(hh: HhnHarness):
    err_json(hh.run("download", COURSE, "-o", "dl", "--json"), 2, "not_logged_in")


def test_no_secrets_in_output(logged_in: HhnHarness):
    h = logged_in
    r = h.run("download", COURSE, "-o", "dl")
    assert r.exit_code == 0, str(r)
    blob = r.stdout + r.stderr
    for secret in ("il_wac_token", "PHPSESSID", h.world.ilias_client_id or "§§"):
        assert secret not in blob, secret
    for sid in h.world.valid_sessions:
        assert sid not in blob
    assert "geladen" in r.stdout
    manifest = (Path(json.loads(h.run("download", COURSE, "-o", "dl", "--json").stdout)["target_dir"]) / ".ilias-download.json").read_text()
    assert "il_wac_token" not in manifest and "PHPSESSID" not in manifest

"""Konfiguration und Backend-Auswahl (INTERFACE.md §4, N6/N7) - ohne Netzwerk.

Hier wird nur aufgelöst, nicht verbunden: die Basis-URL des eingebauten Profils
wird nie angefragt.
"""

from __future__ import annotations

import stat

import pytest

from ilias_core import ConfigError, Instance, SessionStore, load_instance, open_service
from ilias_core.backends import available_backends
from ilias_core.backends.ilias import IliasBackend
from ilias_core.backends.moodle import MoodleBackend
from ilias_core.config import BUILTIN_INSTANCES, config_dir, config_path
from ilias_core.errors import NotLoggedInError, NotSupportedError
from ilias_core.secrets import Secret


@pytest.fixture(autouse=True)
def config_env(tmp_path, monkeypatch):
    """Eigene Config-Umgebung: nichts wird aus dem echten Benutzerverzeichnis gelesen."""
    monkeypatch.setenv("ILIAS_CLI_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir(exist_ok=True)
    return tmp_path


def write_config(tmp_path, text: str):
    path = config_dir() / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ------------------------------------------------------------------ eingebaute Profile
def test_builtin_profile_hs_mannheim_is_moodle(config_env):
    """Eingebautes Profil `hs-mannheim`: Moodle an der Hochschule Mannheim (NOTES.md, 08.10.2026)."""
    instance = load_instance("hs-mannheim")
    assert instance.lms == "moodle"
    assert instance.base_url == "https://moodle.hs-mannheim.de"
    assert instance.normalized_base_url == "https://moodle.hs-mannheim.de"


def test_ilias_stays_default(config_env):
    """ILIAS bleibt Default, wenn keine Instanz angegeben ist."""
    instance = load_instance()
    assert instance.key == "hhn"
    assert instance.lms == "ilias"
    assert instance.base_url == "https://ilias.hs-heilbronn.de"
    assert instance.client_id == "iliashhn"


def test_config_dir_env_is_respected(config_env):
    assert config_dir() == config_env / "config"
    assert config_path().parent == config_dir()


def test_config_dir_falls_back_to_home(config_env, monkeypatch):
    """N6: ohne ILIAS_CLI_CONFIG_DIR liegt die Config in ~/.config/ilias-cli."""
    monkeypatch.delenv("ILIAS_CLI_CONFIG_DIR", raising=False)
    assert config_dir() == config_env / "home" / ".config" / "ilias-cli"


# ------------------------------------------------------------------ config.toml
def test_instance_key_from_config_selects_moodle(config_env):
    write_config(
        config_env,
        'instance = "hs-mannheim"\n\n[instances.hs-mannheim]\nlms = "moodle"\nbase_url = "https://moodle.example.org"\n',
    )
    instance = load_instance()
    assert instance.key == "hs-mannheim"
    assert instance.base_url == "https://moodle.example.org"
    assert open_service().backend.__class__ is MoodleBackend


def test_base_url_stays_overridable(config_env):
    """N7: Basis-URL nie hart kodiert - config.toml schlägt das eingebaute Profil."""
    write_config(config_env, '[instances.hs-mannheim]\nbase_url = "http://127.0.0.1:8080/moodle"\n')
    instance = load_instance("hs-mannheim")
    assert instance.lms == "moodle"  # Backend bleibt aus dem eingebauten Profil
    assert instance.base_url == "http://127.0.0.1:8080/moodle"
    assert instance.normalized_base_url == "http://127.0.0.1:8080/moodle"


def test_lms_key_selects_backend(config_env):
    """`lms = "moodle"` schaltet das Backend; ohne Angabe bleibt ILIAS."""
    write_config(config_env, '[instances.my-lms]\nlms = "moodle"\nbase_url = "https://lms.example.org"\n')
    instance = load_instance("my-lms")
    assert instance.lms == "moodle"
    assert open_service("my-lms").backend.__class__ is MoodleBackend

    write_config(config_env, '[instances.my-lms]\nbase_url = "https://ilias.example.org"\n')
    assert load_instance("my-lms").lms == "ilias"
    assert open_service("my-lms").backend.__class__ is IliasBackend


def test_flat_config_still_describes_ilias(config_env):
    """Die alte flache Form (base_url/client_id oben) gilt für die ILIAS-Default-Instanz."""
    write_config(config_env, 'base_url = "https://ilias.example.org"\nclient_id = "iliashhn"\n')
    instance = load_instance()
    assert instance.key == "hhn"
    assert instance.base_url == "https://ilias.example.org"
    assert instance.client_id == "iliashhn"


def test_unknown_instance_is_a_config_error(config_env):
    with pytest.raises(ConfigError) as excinfo:
        load_instance("gibtsnicht")
    assert "gibtsnicht" in excinfo.value.message


def test_unknown_backend_is_a_config_error(config_env):
    write_config(config_env, '[instances.my-lms]\nlms = "canvas"\nbase_url = "https://x.example.org"\n')
    with pytest.raises(ConfigError) as excinfo:
        load_instance("my-lms")
    assert "canvas" in excinfo.value.message


def test_broken_toml_is_a_config_error(config_env):
    write_config(config_env, "base_url = =\n")
    with pytest.raises(ConfigError):
        load_instance()


def test_missing_config_file_uses_defaults(config_env):
    assert not config_path().exists()
    assert load_instance().lms == "ilias"


def test_builtin_profiles_are_documented():
    assert set(BUILTIN_INSTANCES) >= {"hhn", "hs-mannheim"}
    assert set(available_backends()) == {"ilias", "moodle"}


# ------------------------------------------------------------------ Backends
def test_moodle_backend_without_session_is_not_logged_in(config_env):
    backend = open_service("hs-mannheim").backend
    assert isinstance(backend, MoodleBackend)
    with pytest.raises(NotLoggedInError) as excinfo:
        backend.status()
    assert excinfo.value.exit_code == 2


def test_moodle_logout_without_session_succeeds(config_env):
    result = open_service("hs-mannheim").backend.logout()
    assert result.token_removed is False
    assert result.instance == "hs-mannheim" and result.lms == "moodle"


def test_ilias_backend_login_is_not_implemented(config_env):
    backend = open_service("hhn").backend
    assert isinstance(backend, IliasBackend)
    assert backend.supports_login is False
    with pytest.raises(NotSupportedError):
        backend.login(object())  # type: ignore[arg-type]
    assert backend.logout().token_removed is False


# ------------------------------------------------------------------ Session-Speicher (A4)
def test_secret_is_never_reprd(config_env):
    secret = Secret("super-geheim")
    assert repr(secret) == "Secret(***)"
    assert str(secret) == "***"
    assert "super-geheim" not in f"{secret!r} {secret}"


def test_session_file_created_with_0600(config_env, monkeypatch):
    """A4: Datei-Fallback wird von Anfang an mit 0600 angelegt (kein Fenster mit zu weiten Rechten)."""
    monkeypatch.setattr("ilias_core.session.keyring_usable", lambda: False)
    instance = load_instance("hs-mannheim")
    store = SessionStore(instance.key, instance.lms, instance.base_url)
    assert store.save("tok-123", username="student") == "file"

    path = store.path
    assert path.parent.name == "sessions"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert [p for p in path.parent.iterdir()] == [path], "keine Restdateien"

    loaded = store.load()
    assert loaded is not None and loaded.token == "tok-123"
    assert "tok-123" not in repr(loaded)

    assert store.delete() is True
    assert not path.exists()
    assert store.load() is None
    assert store.delete() is False


def test_sessions_are_stored_per_instance(config_env, monkeypatch):
    monkeypatch.setattr("ilias_core.session.keyring_usable", lambda: False)
    a = SessionStore(*_parts("hs-mannheim"))
    b = SessionStore(*_parts("hs-mannheim-test"))
    a.save("tok-a")
    b.save("tok-b")
    assert a.path != b.path
    assert a.load().token == "tok-a"
    assert b.load().token == "tok-b"


def _parts(key: str):
    instance = load_instance(key) if key in BUILTIN_INSTANCES else Instance(key, "moodle", "https://x.example.org")
    return instance.key, instance.lms, instance.base_url

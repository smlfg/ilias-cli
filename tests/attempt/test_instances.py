"""Instanz-Profile, Auth-Auswahl und Sessions pro Instanz (ohne Netzwerk)."""

from __future__ import annotations

import pytest

from ilias_core.auth import KeycloakLoginFlow, ShibbolethLoginFlow, get_adapter
from ilias_core.config import load_config
from ilias_core.errors import ConfigError
from ilias_core.session import SessionStore


def _write(config_dir, text: str) -> None:
    (config_dir / "config.toml").write_text(text, encoding="utf-8")


def test_default_is_hhn_oidc(config_dir):
    cfg = load_config()
    assert (cfg.instance, cfg.base_url, cfg.client_id, cfg.auth) == (
        "hhn", "https://ilias.hs-heilbronn.de", "iliashhn", "oidc-keycloak"
    )
    assert get_adapter(cfg.auth) is KeycloakLoginFlow


def test_builtin_uni_mannheim_profile(config_dir):
    cfg = load_config(instance="uni-mannheim")
    assert (cfg.base_url, cfg.client_id, cfg.auth) == (
        "https://ilias.uni-mannheim.de", "ILIAS", "saml-shibboleth"
    )
    assert get_adapter(cfg.auth) is ShibbolethLoginFlow
    assert ShibbolethLoginFlow.start_path == "saml.php"


def test_instance_key_in_config_file(config_dir):
    _write(config_dir, 'instance = "uni-mannheim"\n')
    assert load_config().instance == "uni-mannheim"


def test_top_level_overrides_apply_only_to_configured_instance(config_dir):
    _write(config_dir, 'base_url = "https://test.example.invalid/"\nclient_id = "x"\n')
    assert load_config().base_url == "https://test.example.invalid"
    other = load_config(instance="uni-mannheim")
    assert other.base_url == "https://ilias.uni-mannheim.de"
    assert other.client_id == "ILIAS"


def test_instance_table_overrides(config_dir):
    _write(
        config_dir,
        '[instances.uni-mannheim]\nbase_url = "https://staging.example.invalid"\nclient_id = "STAGE"\n',
    )
    cfg = load_config(instance="uni-mannheim")
    assert (cfg.base_url, cfg.client_id, cfg.auth) == (
        "https://staging.example.invalid", "STAGE", "saml-shibboleth"
    )


def test_custom_instance(config_dir):
    _write(
        config_dir,
        '[instances.meine-uni]\nbase_url = "https://ilias.example.invalid"\n'
        'client_id = "ILIAS"\nauth = "saml-shibboleth"\n',
    )
    cfg = load_config(instance="meine-uni")
    assert cfg.auth == "saml-shibboleth"
    assert cfg.base_url == "https://ilias.example.invalid"


def test_unknown_instance_raises(config_dir):
    with pytest.raises(ConfigError, match="uni-mannheim"):
        load_config(instance="nirgendwo")


def test_unknown_auth_raises(config_dir):
    _write(config_dir, 'auth = "kerberos"\n')
    with pytest.raises(ConfigError, match="saml-shibboleth"):
        load_config()


def test_invalid_instance_name_raises(config_dir):
    with pytest.raises(ConfigError):
        load_config(instance="../etc")


def test_sessions_are_stored_per_instance(config_dir, memory_keyring):
    hhn = SessionStore(load_config(instance="hhn"))
    uma = SessionStore(load_config(instance="uni-mannheim"))
    hhn.save({"PHPSESSID": "a"})
    uma.save({"PHPSESSID": "b"})
    assert hhn.load() == {"PHPSESSID": "a"}
    assert uma.load() == {"PHPSESSID": "b"}
    uma.clear()
    assert uma.load() is None
    assert hhn.load() == {"PHPSESSID": "a"}


def test_session_files_are_per_instance(config_dir):
    a = load_config(instance="hhn").session_file
    b = load_config(instance="uni-mannheim").session_file
    assert a != b and a.parent == b.parent == config_dir

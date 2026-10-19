"""URL-Auflösung gegen base_url mit optionalem Pfad-Präfix."""

from ilias_core.ilias_html.fetch import join_base_url


def test_join_base_url_preserves_path_prefix():
    base = "http://127.0.0.1:1234/ilias"
    assert join_base_url(base, "/ilias.php?baseClass=x") == f"{base}/ilias.php?baseClass=x"
    assert join_base_url(base, "ilias.php?baseClass=x") == f"{base}/ilias.php?baseClass=x"


def test_join_base_url_without_prefix():
    base = "https://ilias.example.org"
    assert join_base_url(base, "/ilias.php") == "https://ilias.example.org/ilias.php"

# UX-Spec: ilias-cli

Stand: 04.11.2026. Erkundet wurden nur öffentliche, lesende GET-Antworten
(`ilias.hs-heilbronn.de`, `ilias.uni-mannheim.de`, `moodle.hs-mannheim.de`).
Es wurde kein echtes Konto angemeldet und keine schreibende Aktion ausgelöst.

## Meta

```ux-meta
{"tool": "ilias",
 "install": "pipx install git+https://github.com/smlfg/ilias-cli",
 "base_url_env": "ILIAS_CLI_BASE_URL",
 "env": {},
 "credential_env": []}
```

`ILIAS_CLI_BASE_URL` überschreibt die `base_url` der aktiven Instanz, damit die
Harness gegen einen Fake-Server laufen kann. `ILIAS_CLI_CONFIG_DIR` bleibt
unverändert. Zugangsdaten kommen ausschließlich aus der interaktiven Eingabe,
deshalb ist `credential_env` leer.

## Live-Befunde

- **HHN (ILIAS, OIDC/Keycloak):** `GET /openidconnect.php` antwortet mit `302`
  auf `https://login.hs-heilbronn.de/realms/hhn/protocol/openid-connect/auth`
  (`client_id=hhn_common_ilias`, `state`, `nonce`). Das Keycloak-Formular
  `#kc-form-login` hat `username`, `password`, das versteckte Feld
  `credentialId` und den Submit `login`; die `action` ist eine absolute
  `login-actions/authenticate`-URL mit `session_code`, `execution`,
  `client_id` und `tab_id`. Der TOTP-Schritt ist ohne Konto nicht sichtbar; er
  wird als `#kc-otp-login-form` mit Feld `otp` angenommen (Keycloak-Standard).
- **Uni Mannheim (ILIAS, SAML/Shibboleth):** `GET /login.php` leitet über
  `saml.php` zum IdP `idp.uni-mannheim.de` weiter. Das Formular `#login-form`
  hat `j_username`, `j_password`, den Submit `_eventId_proceed` und die
  versteckten Felder `csrf_token` sowie optionale Consent-/Storage-Felder.
- **Moodle HS Mannheim:** `GET /login/index.php` zeigt `form#login` mit
  `username`, `password`, dem versteckten `logintoken` und `anchor`; die
  `action` ist `/login/index.php`. Der eigentliche Moodle-Zugriff läuft nach dem
  Login über den Mobile-Webservice (`moodle_mobile_app`), nicht über HTML.
- **Lesen nach Login:** `GET /ilias.php?baseClass=ilmembershipoverviewgui`
  liefert „Meine Kurse und Gruppen“, `GET /ilias.php?baseClass=ilrepositorygui&ref_id=<ref>`
  den Kursinhalt, `GET /ilias.php?...cmdClass=ilObjFileGUI&cmd=sendfile&ref_id=<ref>`
  eine Datei. Ohne Login ist die Mitgliedschaftsseite leer und das Dashboard
  zeigt einen Anmelde-Link.
- **Schreibende Aktion:** `download` schreibt nur lokal. Es gibt keinen
  server-schreibenden Formularschritt; der verbindliche Schritt ist der
  Datei-GET nach der `[j/N]`-Bestätigung. Vorher werden Kursliste und
  Kursinhalt nur gelesen.

## Sitzungen

### Installation und Login

Der Login fragt Benutzername, Passwort und – nur bei der HHN – den TOTP-Code
verdeckt ab. Die Instanz ist standardmäßig `hhn` und lässt sich mit
`--instance` oder in `config.toml` wählen. Passwort und Code werden nie
gespeichert oder angezeigt; die Sitzung landet im Schlüsselbund oder in einer
Datei mit Rechten 0600.

```ux-session
$ pipx install git+https://github.com/smlfg/ilias-cli
< ilias
$ ilias login
< Benutzername:
> beispiel@example.invalid
< Passwort:
> geheim
< TOTP-Code:
> 123456
< Login erfolgreich
! exit 0
```

### Kurse und Kursinhalt lesen

`courses` zeigt ID, Name und Semester. `ls` nimmt einen Kursnamen als
positionalen Suchbegriff (alternativ Kursnummer oder ref_id) und zeigt den
Inhalt als Baum. Beide Befehle ändern nichts auf dem Server.

```ux-session
$ ilias courses
< Kurse (hhn, ilias)
< 900101
< Beispielkurs Programmierung (WiSe 2026/27)
< WiSe 2026/27
$ ilias ls "Beispielkurs Programmierung"
< Beispielkurs Programmierung (WiSe 2026/27)
< Inhalt
< Blatt 10
! exit 0
```

### Kurs herunterladen

`download` zeigt zuerst Kurs, Zielordner und Anzahl der Dateien. Danach fragt es
mit Default Nein. Erst nach `j` wird die Datei geschrieben; bei `N` oder ohne
TTY ohne `--confirm` endet der Befehl vor dem ersten Schreibzugriff.

```ux-session
$ ilias download "Beispielkurs Programmierung"
< Kurs: Beispielkurs Programmierung (WiSe 2026/27)
< Zielordner: ./Beispielkurs Programmierung
< Dateien: 1 (neu 1, aktuell 0)
< Download verbindlich? [j/N]
> j
< Heruntergeladen: 1 Datei
! exit 0
```

## Lesende Routen

Alle Requests, die vor der Bestätigung bzw. für die reinen Lesebefehle nötig
sind. Der Login-POST ist lesend, weil er keine fachliche Aktion auslöst.
Konto-/Login-Seiten sind synthetisch, ebenso die Konto-Seiten mit Kursdaten
(siehe `tests/fixtures/ux/NOTES.md`).

```ux-routes
[{"method":"GET","path":"/openidconnect.php","response":"tests/fixtures/ux/login_keycloak.html","status":200,"content_type":"text/html; charset=utf-8"},
 {"method":"POST","path":"/login-actions/authenticate","response":"tests/fixtures/ux/login_totp.html","status":200,"content_type":"text/html; charset=utf-8"},
 {"method":"POST","path":"/login-actions/authenticate-otp","response":"tests/fixtures/ux/login_erfolg.html","status":200,"content_type":"text/html; charset=utf-8"},
 {"method":"GET","path":"/ilias.php","query_contains":"baseClass=ilDashboardGUI","response":"tests/fixtures/ux/dashboard.html","status":200,"content_type":"text/html; charset=utf-8"},
 {"method":"GET","path":"/ilias.php","query_contains":"baseClass=ilmembershipoverviewgui","response":"tests/fixtures/ux/membership.html","status":200,"content_type":"text/html; charset=utf-8"},
 {"method":"GET","path":"/ilias.php","query_contains":"ref_id=900101","response":"tests/fixtures/ux/container_900101.html","status":200,"content_type":"text/html; charset=utf-8"}]
```

## Formularschritte der schreibenden Aktion

`download` hat keinen server-schreibenden Formularschritt. Der einzige
verbindliche Schritt ist der Datei-GET, der erst nach `j` gesendet wird; davor
laufen ausschließlich die lesenden Routen oben. Der Schritt ist synthetisch,
weil die Datei nur mit einem Konto erreichbar wäre.

```ux-formsteps
[{"id":"datei_laden","method":"GET","path":"/ilias.php","sends":["baseClass","cmdClass","cmd","ref_id"],"response":"tests/fixtures/ux/download_blatt10.pdf","final":true,"live":"synthetisch"}]
```

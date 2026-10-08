# Echter Login-Test: ILIAS Uni Mannheim (SAML/Shibboleth)

Für Samuel, auf dem eigenen Mac im eigenen Terminal. Dauer ca. 5 Minuten.
Der Code wurde bisher **nur gegen lokale Fake-Server** getestet (nachgebaut aus den echten,
anonym abgerufenen Login-Seiten). Das ist der erste Kontakt mit dem echten Server.

Dein Passwort wird nur verdeckt abgefragt, direkt an `idp.uni-mannheim.de` gesendet und
nirgends gespeichert oder ausgegeben. Gespeichert wird nur das ILIAS-Session-Cookie
(macOS-Schlüsselbund).

## 0. Voraussetzungen (einmalig)

```bash
brew install gh uv        # falls noch nicht da
gh auth status            # muss als smlfg eingeloggt sein
```

## 1. Holen und installieren

```bash
gh repo clone smlfg/ilias-cli
cd ilias-cli
git checkout feature/saml-uni-mannheim
uv sync
```

## 2. Login

```bash
uv run ilias login --instance uni-mannheim
```

Erwartet: Abfrage `Uni-ID (Kennung):`, dann `Passwort:` (verdeckt, kein TOTP). Danach:

```text
Login erfolgreich und geprüft (saml-shibboleth) – https://ilias.uni-mannheim.de (Instanz uni-mannheim, ILIAS)
```

„Erfolgreich“ erscheint nur, wenn ILIAS wirklich eine neue Session ausgestellt hat und
das Dashboard ohne Umleitung auf `login.php` mit Abmelde-Link lädt. Fragt macOS nach
Zugriff auf den Schlüsselbund: „Erlauben“.

## 3. Status

```bash
uv run ilias status --instance uni-mannheim --json
```

Erwartet (Exit-Code 0):

```json
{"authenticated": true, "base_url": "https://ilias.uni-mannheim.de", "client_id": "ILIAS", "message": "Session ist gültig.", "instance": "uni-mannheim"}
```

## 4. Logout

```bash
uv run ilias logout --instance uni-mannheim
```

Erwartet: `Session gelöscht.` (Löscht nur die lokal gespeicherte Session.)

## Wenn etwas schiefgeht

Exit-Codes: `1` Login abgelehnt (z. B. falsches Passwort) · `2` nicht eingeloggt ·
`3` Session abgelaufen · `4` Netzwerk/Server · `5` unbekannte Seite (Parser).

Bei `4` oder `5` (oder wenn „erfolgreich“ fehlt, obwohl das Passwort stimmt) bitte mit
Debug-Log wiederholen:

```bash
uv run ilias login --instance uni-mannheim --debug 2>&1 | tee ilias-debug.txt
uv run ilias status --instance uni-mannheim --debug 2>&1 | tee -a ilias-debug.txt
```

`--debug` protokolliert nur URLs (Query-Werte geschwärzt, außer Routing-Parametern wie
`execution`, `baseClass`), HTTP-Statuscodes und die **Namen** von Formularfeldern. Nie Werte,
Passwort, Uni-ID, Cookies oder Seiteninhalte. Kurz drüberschauen und `ilias-debug.txt`
schicken.

## Fallback: Login im Browser

Falls der Headless-Login nicht klappt: Ein sichtbares Chromium-Fenster öffnet die
Uni-Anmeldung, du loggst dich selbst ein, danach werden nur die ILIAS-Cookies übernommen
und gegen das Dashboard geprüft.

```bash
uv sync --extra browser && uv run playwright install chromium
uv run ilias login --instance uni-mannheim --browser
uv run ilias status --instance uni-mannheim --json
```

Hinweis: Ein späteres einfaches `uv sync` entfernt Playwright wieder. Dann den ersten
Befehl erneut ausführen.

## HHN bleibt unverändert

`uv run ilias login` (ohne `--instance`) ist weiter der HHN-Login (Keycloak + TOTP).
Die Sessions beider Instanzen liegen getrennt.

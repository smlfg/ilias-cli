# HHN-ILIAS mit 2FA: Spezifikation für die nächste Bau-Runde

Stand: 08.10.2026, 11:20 (Europe/Berlin), mit Live-Befunden (§13). Ziel-Instanz: `hhn` = Hochschule Heilbronn, `https://ilias.hs-heilbronn.de`, ILIAS 9.24, Client `iliashhn`.
Gilt zusätzlich zu [ANFORDERUNGEN.md](../ANFORDERUNGEN.md) (F1–F12, A1–A6, N1–N7) und [INTERFACE.md](../INTERFACE.md). Bei Widerspruch gilt dieses Dokument.

Kennzeichnung: **[V]** selbst geprüft (öffentlich, ohne Login) · **[M]** steht so auf `main` · **[L]** *live zu bestätigen/zu messen* (braucht den Login des Repo-Inhabers, macht IliasCLI/MCP mit `loop/test_hhn.sh`) · **[A]** Annahme.

---

## 0. Kurzfassung für die Bau-Modelle

1. **`ilias setup`** (neu, alle Instanzen): geführte Erst-Einrichtung → Instanz wählen, Benutzername, Passwort verdeckt, TOTP nur bei `hhn`. Speichert nur Session + nicht-geheime Config.
2. **HHN-Login** ist auf `main` schon gebaut und grün (PR #6, OIDC/Keycloak + TOTP, [M]). Er wird **nicht neu geschrieben**, nur von `setup` wiederverwendet und um die Fehlversuch-Regeln (§3.5) ergänzt.
3. **`ilias courses`** für ILIAS per HTML: Titel, ref_id, Typ (crs/grp), Semester, URL, visible.
4. **`ilias ls <kurs>`** für ILIAS per HTML: Blöcke → Objekte → rekursiv Ordner, mit Dateigröße, Links, Übungen, Tests, Foren.
5. Gleiche Befehle, Optionen, JSON-Formen und Exit-Codes wie beim Moodle-Backend (`hs-mannheim`), damit CLI und später MCP nur **eine** Form kennen.
6. Akzeptanztests: `tests/hhn/` (94 Tests, pro Funktion getrennt, siehe §11, Fake-Keycloak + Fake-ILIAS, nur synthetische Daten, Markup strukturtreu zu den echten HHN-Seiten, §13).
7. **Vor S6–S8 §13 lesen**: Kursnummern sind keine ref_ids, Kursliste nur aus „Meine Kurse und Gruppen“, Permalinks `/go/<typ>/<ref>`, Dateigrößen mit Punkt. `HHN_STRICT=1 uv run pytest tests/hhn -q` muss am Ende grün sein.

## 1. Rahmen und Lehren (verbindlich)

Aus `smlfg/agent-learnings` `rules/AGENTS.md` und den Runden F1–F3:

| # | Regel | Wo geprüft |
|---|---|---|
| L1 | Login gilt erst als erfolgreich, wenn eine **nur-eingeloggt-Seite** geladen wurde (Dashboard mit `logout.php`-Link). | `tests/acceptance/test_login_verification.py`, `test_setup.py` |
| L2 | Gespeichert werden **nur ILIAS-Cookies** (Allowlist: `PHPSESSID`, `ilClientId`). Nie Keycloak-Cookies (`KEYCLOAK_IDENTITY`, `KEYCLOAK_SESSION`, `AUTH_SESSION_ID`, `KC_RESTART`, `KC_AUTH_SESSION_HASH`). | `tests/acceptance` |
| L3 | **HTTP-Status vor dem Parsen prüfen** (≥ 500 → 4, Login-Redirect → 3, dann erst HTML lesen). | `test_courses_server_503_exit4`, `test_ls_folder_500_exit4` |
| L4 | **Ein Exit-Code pro Fehlerklasse** (§8). Keine Sammel-Exit-1 für Netz/Parser. | alle `err_json`-Tests |
| L5 | Tests erreichen **nie echte Server** (Netzwerk-Sandbox `tests/acceptance/support/sitecustomize.py`). | Fixture `hh` |
| L6 | **Keine erfundenen Personendaten**, keine echten Kursinhalte in Fixtures, keine Matrikelnummern. PII-Guard (`scripts/pii_guard.py`, PR #19) muss grün sein. | CI |
| L7 | Jeder Lauf **committet und pusht am Ende automatisch** (ein Schritt = ein Commit mit Testergebnis in der Nachricht). | Opencode-Runner |
| L8 | Fix-Runden ≤ 40 Minuten oder kleiner schneiden. | Planung §10 |
| L9 | Spec vor dem Start **gegen echte Daten prüfen**: Semester-Regel SoSe = März–August, WiSe = September–Februar. Alles, was nur live prüfbar ist, ist hier mit [L] markiert. | §5.3, §9 |
| L10 | Ausgaben: HTML-Entities dekodieren, jedes Objekt genau einmal, Titel/URLs nie abschneiden (Lehre aus dem Moodle-Live-Test 6363). | `test_ls_no_duplicate_entries_and_entities` |

Architektur [M]: Logik in `ilias_core` (Backend + Service, Rückgabe als Dataclass), CLI nur Hülle. Seit PR #20 (`integrate/moodle`) gibt es auf `main` `Backend.courses()` und `Backend.course_contents(ref_id)`; das ILIAS-Backend liefert dort bisher `NotSupportedError`. Diese Runde ersetzt genau diese zwei Methoden für `lms = "ilias"` und ergänzt `setup`.

## 2. Was öffentlich bekannt ist [V]

| Punkt | Befund (08.10.2026, ohne Login) |
|---|---|
| Login-Einstieg | `GET /openidconnect.php` → 302 `https://login.hs-heilbronn.de/realms/hhn/protocol/openid-connect/auth?response_type=code&redirect_uri=https://ilias.hs-heilbronn.de/openidconnect.php&client_id=hhn_common_ilias&nonce=…&state=…&scope=openid+openid`. ILIAS setzt dabei schon ein anonymes `PHPSESSID`. |
| Keycloak-Formular | `<form id="kc-form-login">`, Felder `username`, `password`, hidden `credentialId`, Button `login`. Altes Keycloak-Theme (`kc-content`, `kc-form-wrapper`), **kein „Angemeldet bleiben“** (`rememberMe` fehlt). Cookies: `AUTH_SESSION_ID`, `KC_RESTART`, `KC_AUTH_SESSION_HASH`. |
| TOTP-Schritt | Nicht öffentlich sichtbar. Fake nimmt `#kc-otp-login-form` mit Feld `otp` an (Keycloak-Standard) [L]. |
| Schnittstellen | SOAP 403, kein REST-Plugin (404), WebDAV 403, `calendar.php` 200 (Token-Feed, gut für F4 später), `privfeed.php` 401, `robots.txt` `Disallow: /`. → **Web-Session + HTML-Scraping**, sparsam (N2). |
| Kurse (UC4) | Sieben Kursnummern aus der Einschreibung (Liste nur lokal in `loop/truth/hhn_courses.json`). **Live 08.10.: Das sind keine ref_ids** (§13.1). |

## 3. `ilias setup`: geführte Erst-Einrichtung (alle Instanzen)

### 3.1 Aufruf
```
ilias setup [--instance NAME] [--username NAME] [--json]
ilias setup --list [--filter TEXT] [--json]
```
- **Kein** `--password`, `--totp`, `--otp`, `--code` (A1). Passwort und Code kommen nie aus Flags oder Umgebungsvariablen.
- `--json`: genau ein JSON-Objekt auf stdout, Prompts auf **stderr**.

### 3.2 Schritt 1: Hochschule wählen
- Interaktiv (TTY): Auswahlliste aller eingebauten Instanzen mit **Autovervollständigung**: Tippen filtert die Liste, Enter übernimmt den einzigen/markierten Treffer. Umsetzung frei (z. B. `prompt_toolkit`-Completer oder `questionary.autocomplete`); ohne diese Bibliothek reicht eine nummerierte Liste mit Filter-Eingabe.
- Filterregel (eine Kernfunktion, z. B. `ilias_core.setup.filter_instances(text)`): case-insensitiver Teilstring in Schlüssel, Anzeigename, Stadt oder LMS. Beispiele: `heil` → `hhn`, `mannheim` → `uni-mannheim`, `hs-mannheim`, `moodle` → `hs-mannheim`.
- `ilias setup --list [--filter X] --json` → `{"instances": [{"key", "name", "lms", "auth", "requires_totp", "base_url"}]}`. `requires_totp` ist `true` nur für `hhn`.
- Eingebaute Instanzen: `hhn` (Hochschule Heilbronn, ILIAS, `oidc-keycloak`, TOTP), `uni-mannheim` (Universität Mannheim, ILIAS, `saml-shibboleth`), `hs-mannheim` (Hochschule Mannheim, Moodle, Token).
- Nicht interaktiv: `--instance NAME`. Unbekannte Instanz → Exit 1 (`config_error`), kein Netz.

### 3.3 Schritte 2–4
2. **Benutzername**: Prompt mit Default aus der vorhandenen Config (`[instances.<key>] username`). `--username` überspringt den Prompt.
3. **Passwort** verdeckt (`getpass`/`typer.prompt(hide_input=True)`). Nie gespeichert, nie geloggt, nie im JSON, nie in Tracebacks.
4. **Nur wenn `requires_totp`**: einmal den TOTP-Code verdeckt abfragen (Hinweis „6-stelliger Code aus der Authenticator-App“). Der Code wird erst abgefragt, **nachdem** Keycloak das Passwort akzeptiert hat. Kein TOTP-Secret, keine Code-Generierung im Tool (A2).

### 3.4 Danach
- Login über den vorhandenen Auth-Adapter der Instanz (kein zweiter Login-Code).
- **Beweis** wie L1. Erst danach speichern:
  - Session: Keyring, sonst Datei `0600` (A4), nur Allowlist-Cookies bzw. Moodle-Token.
  - Config (nicht geheim): `instance = "<key>"` oben und `[instances.<key>] username = "…"`. **Bestehende Werte bleiben erhalten** (z. B. `base_url`-Overrides, andere Instanzen). Atomar schreiben (temp + rename).
- Ausgabe: „Eingerichtet: hhn als <username>. Neue Eingabe erst nötig, wenn die Session abläuft.“ JSON: `{"ok": true, "command": "setup", "instance", "lms", "username", "verified": true, "session_stored": true, "config_path", "timestamp"}`.

### 3.5 Abbruch und Fehlversuche
| Fall | Verhalten |
|---|---|
| Ctrl-C (SIGINT) oder EOF (Ctrl-D, leeres stdin) an irgendeiner Stelle | Exit **1**, Meldung „Abgebrochen, nichts gespeichert.“, kein Traceback. **Weder Session noch Config** werden geschrieben. EOF vor dem Passwort → kein Keycloak-POST. |
| Falsches Passwort | Klare Meldung („Benutzername oder Passwort falsch“, Text von Keycloak `#input-error`/`.kc-feedback-text` übernehmen), Exit **1**. **Kein** automatischer zweiter Versuch (Konto-Sperre vermeiden). Genau ein Passwort-POST. |
| Falscher TOTP-Code | Im **selben** Keycloak-Ablauf neu fragen (neues Formular aus der Fehlerseite lesen, Passwort nicht neu senden). **Maximal 3 Code-Versuche** insgesamt, dann Exit **1**, nichts gespeichert. |
| Netz/Server/Parser beim Login | 4 / 4 / 5 wie §8, nichts gespeichert. |

`ilias login` übernimmt dieselben Regeln (Fehlversuche, Abbruch); `login` bleibt der kurze Weg ohne Instanz-Auswahl.

### 3.6 Ohne TTY
- stdin ist kein Terminal → keine Auswahlliste. Dann müssen `--instance` und ein Benutzername (`--username` oder aus Config) feststehen, sonst Exit **1** mit Hinweis: `Ohne Terminal: ilias setup --instance <name> --username <name> und Passwort (+ Code) zeilenweise über stdin`.
- Eingaben dann zeilenweise von stdin: Passwort, danach bis zu 3 Code-Zeilen. So testen es die Fake-Tests und so speist `loop/test_hhn.sh` das Passwort ein.

## 4. Session: so selten wie möglich 2FA

### 4.1 Was bekannt ist
- Die Session hängt am ILIAS-Cookie `PHPSESSID` [M]. Keycloak bietet kein „Angemeldet bleiben“ [V]; Keycloak-Cookies werden ohnehin nicht gespeichert (L2), ein stiller Re-Login über die Keycloak-SSO-Session ist also **nicht** vorgesehen.
- ILIAS-Session-Laufzeit an der HHN: noch nicht gemessen. Live 08.10.: nach dem Login mindestens ~10 min gültig, keine `PHPSESSID`-Rotation (§13.10). ILIAS-Standard ist eine Leerlauf-Grenze (Setting „Session-Dauer“, oft 1–4 h, verlängert sich bei Aktivität). Zu messen: §9 Frage 2.

### 4.2 Regeln
- Jeder Befehl nutzt die gespeicherte Session wieder. Kein Keycloak-Kontakt bei `status`, `courses`, `ls` (geprüft in `test_courses_only_get_requests_no_relogin`, `test_setup_then_courses_without_new_2fa`).
- Rotiert ILIAS das `PHPSESSID` in einer Antwort (`Set-Cookie`), wird der neue Wert gespeichert (nur Allowlist) [A]. Live 08.10. nicht beobachtet: ILIAS setzt pro Seite nur `ilClientId` neu (§13.10).
- **Kein Keep-Alive-Daemon** in dieser Runde. Optional später: `ilias status` als Cron-Ping, falls die Messung eine reine Leerlauf-Grenze zeigt (§9).

### 4.3 Nur lesen
`courses`/`ls` senden nur `GET`, eigener User-Agent `ilias-cli/<version>`, höchstens ~1 Request/s (N2). Die Pause ist per `ILIAS_CLI_REQUEST_INTERVAL` (Sekunden, Default `1.0`) einstellbar; die Tests setzen `0`.

### 4.4 Abgelaufen und nicht eingeloggt
| Lage | Erkennung | Exit / `error.code` |
|---|---|---|
| Keine Session gespeichert | lokal | 2 / `not_logged_in` |
| Session abgelaufen | Redirect auf `login.php` (`cmd=force_login`) **auf jeder Seite**, auch mitten im `ls`-Crawl; oder 200 mit Login-Formular statt Inhalt | 3 / `session_expired`, Hinweis „`ilias login` oder `ilias setup` ausführen“. **Kein** Auto-Re-Login, keine Teilausgabe als Erfolg. |

## 5. `ilias courses` für ILIAS

### 5.1 Aufruf und Ausgabe
`ilias courses [--instance hhn] [--json]`. Mensch: Tabelle `ID (ref_id) | Typ | Titel | Semester` (rich, Markup escapen). Sortierung wie Moodle: Semester neueste zuerst, `null` zuletzt, dann Titel.

### 5.2 Quelle und Felder
- Quelle: **nur** „Meine Kurse und Gruppen“: `GET {base}/ilias.php?baseClass=ilmembershipoverviewgui` (live bestätigt, §13.2). **Kein** Dashboard-Fallback: das Dashboard zeigt nur Favoriten (Teilmenge).
- Pro Eintrag (ILIAS-9-UI-Item, nur innerhalb von `#ilContentContainer .panel-body`, §13.2):
  - `id`: ref_id (int) aus dem Titel-Link (`/go/crs/<ref>`, Parser §13.5).
  - `type`: `crs` oder `grp`.
  - `fullname`: Titel, HTML-Entities dekodiert, ungekürzt. `shortname`: `""` (ILIAS hat keinen Kurznamen).
  - `semester`: §5.3.
  - `visible`: `false`, wenn als „Offline“ markiert.
  - `url`: kanonisch `{base}/go/<type>/<ref>` (so gibt die HHN ihre Permalinks selbst aus; ohne `client_id`, ohne Session).
  - `startdate`/`enddate`/`category`: `null`, wenn nicht ablesbar.
- JSON: `{"instance": "hhn", "lms": "ilias", "count", "courses": [...], "timestamp"}` (gleiche Hülle wie Moodle).
- Leere Liste mit Leer-Hinweis und Login-Merkmal → Exit 0, `count: 0`. Seite ohne Liste, ohne Leer-Hinweis, ohne Login-Merkmal → Exit 5.

### 5.3 Semester (Regel L9)
Reihenfolge: (1) Eigenschaft „Zeitraum“/„Kurszeitraum“/„Period“ → Startdatum → SoSe März–August, WiSe September–Februar (Jan/Feb gehören zum WiSe des Vorjahres). (2) Titel-Muster: `WiSe 2026/27`, `WS 2026/27`, `WS26/27`, `Wintersemester 2026/27` → `WiSe 2026/27`; `SoSe 2026`, `SS 2026`, `SS26`, `Sommersemester 2026` → `SoSe 2026`. (3) sonst `null`. Live 08.10.: Die HHN zeigt **keine** Zeitraum-Eigenschaft; das Semester steht nur im Titel, in weiteren Formen: `WiSe26/27`, `_WS26_27`, `2026 WS` → `WiSe 2026/27` (analog `SoSe26`, `_SS26`, `2026 SS` → `SoSe 2026`). Eigenschaften wie „Anmeldungsende“ oder „Freie Plätze“ bestimmen das Semester **nicht** (Test: Kurs 900106). Etwa die Hälfte der echten Titel enthält gar kein Semester → `semester: null` ist dort der Normalfall, kein Fehler.

## 6. `ilias ls <kurs>` für ILIAS

### 6.1 Aufruf
`ilias ls <kurs> [--instance hhn] [--depth N] [--json]`
- `<kurs>`: ref_id einer Mitgliedschaft oder Teilstring des Titels (case-insensitiv, NFC), exakter Titel gewinnt. Eine Zahl, die keine ref_id einer Mitgliedschaft ist, wird als **Kursnummer** gesucht: erst im Titel, dann in der Beschreibung (§13.1); Auflösung mit der vorhandenen `resolve_course` aus `service.py` [M nach `integrate/moodle`]. Kein Treffer → 1 `course_not_found`; mehrere → 1 `course_ambiguous` mit `candidates`.
- Kurse **und Gruppen**. Seite: `GET {base}/ilias.php?baseClass=ilrepositorygui&ref_id=<ref>` (oder `goto.php?target=crs_<ref>`, folgt dem Redirect).
- `--depth`: 1 = Abschnitte, 2 = + Objekte im Kurs, 3 = + Inhalt der ersten Ordnerebene, jede weitere Stufe eine Unterordner-Ebene. Default unbegrenzt. Ordnerseiten werden **nur geladen, wenn die Tiefe sie braucht** (`test_ls_depth_limits_requests`). N < 1 → Usage-Fehler.

### 6.2 Struktur und JSON
Gleiche Hülle wie Moodle, damit CLI/MCP eine Form haben:
```json
{"instance": "hhn", "lms": "ilias", "course": {"id": 900101, "fullname": "…", "shortname": ""}, "depth": null,
 "sections": [{"id": 1, "number": 0, "name": "Inhalt", "visible": true, "uservisible": true,
   "modules": [
     {"id": 900201, "ref_id": 900201, "name": "Übungsblätter", "modname": "fold", "url": "…", "visible": true, "uservisible": true, "availability": null,
      "children": [
        {"type": "file", "ref_id": 900311, "name": "Blatt 10", "path": "/Übungsblätter/", "size": 204800, "size_text": "200 KB", "suffix": "pdf", "mimetype": null, "timemodified": null, "fileurl": "…/goto.php?target=file_900311_download", "visible": true},
        {"type": "folder", "ref_id": 900202, "name": "Lösungen", "path": "/Übungsblätter/Lösungen/", "url": "…", "visible": true, "children": [ … ]},
        {"type": "item", "modname": "exc", "ref_id": 900521, "name": "Abgabe Lösungen", "url": "…", "visible": true}
      ]}]}],
 "timestamp": "…"}
```
- **Abschnitte** = ILIAS-Blöcke der Container-Seite (`.ilContainerBlock`, Titel aus dem Block-Kopf; Objektgruppen `itgr` werden eigene Abschnitte). Kurs ohne Blöcke/mit Leer-Hinweis → `sections: []` oder ein leerer Abschnitt, Exit 0.
- **Objekte** (`modules`) = Einträge `.ilContainerListItemOuter`. Name nur aus dem **Titel-Link** (`h3.il_ContainerItemTitle a`), nie aus Dropdown-/Aktions-Links (sonst doppelte Einträge wie „Link Link“).
- **Typ** (`modname` oben, `type`/`modname` in `children`): primär aus dem Link (`target=<typ>_<ref>`, `file_<ref>_download`, `ilLinkResourceHandlerGUI` → `webr`, `ilrepositorygui&ref_id` → Ordner/Kurs), sekundär aus dem Icon (`icon_<typ>.svg`). Bekannte Typen: `fold`, `file`, `webr`, `exc`, `tst`, `frm`, `sess`, `itgr`, `lm`, `htlm`, `copa`, `mcst`, `wiki`, `blog`, `grp`. Unbekannte (Plugins wie `xvid`) bleiben mit ihrem Kürzel (oder `other`) im Baum, kein Absturz.
- **Ordner** (`fold`, auch Unter-`grp`) werden rekursiv geladen und als `children` eingehängt (`type: "folder"`). Alle Nicht-Ordner in Ordnern sind `type: "file"`, `"url"` oder `"item"` (+ `modname`).
- **Weblinks**: `url` = ILIAS-Link (`…calldirectlink`). Die Ziel-URL steht live **nicht** in der Liste; erst ein GET auf `calldirectlink` antwortet mit 302 auf das externe Ziel. In dieser Runde nicht auflösen (`target_url: null`, sonst 1 Request pro Link).
- **Sitzungen** (`sess`) werden nicht aufgeklappt (`expand=`-Links nie folgen): Knoten mit `children: null`. **Kurslinks** (`crsr`) zeigen auf den Zielkurs, behalten aber ihre eigene ref_id (aus `data-list-item-id`) und werden nicht geladen.
- `visible: false`, wenn „Offline“ (`.il_ItemAlertProperty`, nur am Item; **kein** Seitenfehler, §13.7). Reihenfolge = Reihenfolge der Seite (Lehrende sortieren manuell), **nicht umsortieren**.

### 6.3 Text
HTML-Entities dekodieren (`--&gt;` → `-->`), Leerraum normalisieren, **nie kürzen** (weder Titel noch URLs, auch nicht in der Tabelle/im Baum mit `...`).

### 6.4 Dateien
- `size` in Bytes (int), `props.parse_size`: **Punkt und Komma** als Dezimaltrenner (HHN live: Punkt, z. B. `203.45 KB`; außerdem `1,5 MB`, `820 KB`, `1 GB`, `512 Bytes`); Basis 1024; `size_text` = Originaltext. Größe und Datum per Muster aus **allen** Eigenschaften, nicht per Position (z. B. `Version: 2` dazwischen). Fehlt die Größe → `null`.
- `suffix` = Dateiendung = 1. Eigenschaft (`pdf`, `html`, `docx`), klein geschrieben.
- `fileurl` = Titel-Link der Datei, absolut (HHN: `{base}/ilias.php?baseClass=ilrepositorygui&cmdClass=ilObjFileGUI&cmd=sendfile&ref_id=<ref>`, ggf. mit weiteren ILIAS-Steuerparametern, die nicht ausgewertet werden). Nie eine Session-ID, nie Cookies in URLs/Ausgaben. Download selbst ist F5 (nicht jetzt).
- `timemodified`: ISO 8601 Europe/Berlin aus `D. Mon YYYY, HH:MM` (Tag ohne führende Null, Monat deutsch abgekürzt: Jan Feb Mär Apr Mai Jun Jul Aug Sep Okt Nov Dez). Relative Angaben `Heute, HH:MM` / `Gestern, …` / `Morgen, …` → aus dem lokalen Datum berechnen oder `null`.

### 6.5 Baum für Menschen
rich `Tree` mit Typ-Symbolen (📁 Ordner, 📄 Datei mit Größe in KB/MB, 🔗 Link, 📝 Übung, ❓ Test, 💬 Forum, 📦 sonst) und `[offline]`-Markierung. Alle Server-Texte mit `rich.markup.escape` (`[Klausur] Altklausuren` bleibt wörtlich).

## 7. Robustheit beim Scraping (N4)
- Ein Parser-Modul pro Seitentyp: `ilias_core/ilias_html/membership.py`, `container.py`, `props.py` (Größe/Datum/Semester als reine Funktionen mit eigenen Unit-Tests).
- Reihenfolge pro Antwort (§13.7): Verbindung (→ 4) → Status ≥ 500 (→ 4) → Redirect-Kette endet auf `login.php`/`cmd=force_login`/`reloadpublic=1`, Login-Formular oder Metabar mit `login.php`-Link statt Abmelden (→ 3) → `.alert-danger` im Hauptinhalt (→ 1, `permission_denied`, Seite **nicht** parsen, nichts crawlen) → erwartete Struktur da? sonst → 5 (`parse_error`, Meldung nennt Seitentyp und URL ohne Query-Werte).
- Crawl-Schutz (§13.8): Rekursion nur in `fold`/`grp`-Einträge der gerade geladenen Containerliste, visited-Set über ref_id, harte Obergrenze `ILIAS_CLI_MAX_REQUESTS` (Default 300) pro Befehl → Exit 5 `crawl_limit`, keine Teilausgabe.
- Kein Traceback auf stderr, auch bei 5. `--debug` loggt wie bisher nur URLs (Query geschwärzt), Status, gefundene Selektoren und Anzahl Treffer.
- Selektoren zentral als Konstanten, je mit Fallback (z. B. `h3.il_ContainerItemTitle a` → `.il_ContainerItemTitle a` → `a.il_ContainerItemTitle`). Ein ILIAS-Update darf nur eine Stelle betreffen.
- Gespeicherte echte Seiten sind nur lokal unter `real-fixtures/` erlaubt (git-ignoriert, nie committen).

## 8. Exit-Codes (unverändert, INTERFACE.md §3)
0 OK · 1 Fehler, falsches Passwort/Code, Abbruch, nicht gefunden/mehrdeutig, keine Berechtigung · 2 nicht eingeloggt · 3 Session abgelaufen · 4 Netzwerk/Server (Verbindung, HTTP ≥ 500) · 5 Parser (unerwartetes HTML). Mit `--json` immer ein Objekt `{"ok": false, "command", "instance", "lms", "error": {"code", "message", "hint"?, "candidates"?}, "exit_code", "timestamp"}`.

## 9. Offene Fragen, die nur der Live-Login klärt [L]
Antworten vom 08.10. stehen in §13.11.

1. Sind die Kursnummern aus der Einschreibung die **ref_ids** oder nur Kursnummern zum Beitreten? Wie heißen die Kurse genau? (`loop/truth/hhn_courses.json` füllen)
2. **Session-Laufzeit**: Wie lange bleibt `PHPSESSID` gültig, mit und ohne Aktivität? Rotiert ILIAS den Cookie? (Messung: `status` nach 15 min, 1 h, 4 h, 24 h)
3. Wie sieht das **TOTP-Formular** genau aus (Form-ID, Feldname `otp`/`totp`, Fehlertext, Auswahl bei mehreren Authenticator-Geräten)? Max. Fehlversuche bis zur Sperre bei Keycloak?
4. Liefert `ilmembershipoverviewgui` die Liste, oder nur das Dashboard? Welche Klassen/Eigenschaften (Zeitraum, Offline) stehen dort?
5. Container-Markup an der HHN: `ilContainerListItemOuter`/`il_ContainerItemTitle` (Legacy-Liste) oder ILIAS-9-UI-Items? Gibt es Objektblöcke/Sitzungen/„Kacheln“-Ansicht in den eigenen Kursen?
6. Eigenschaften von Dateien: Format von Größe und Datum, steht die Endung drin?
7. Weblinks: steht die Ziel-URL in der Liste, oder nur `calldirectlink`?
8. Kalender-Abo (`calendar.php`-Token) unter *Kalender → Abonnieren* sichtbar, mit Übungsfristen? (für F4, nicht diese Runde)

## 10. Bau-Schritte (je ein Commit mit Testergebnis, je ≤ 40 min)
Commit-Nachricht: `HHN S<n>: <Thema> (<modell>) – tests/hhn: X passed / Y failed`. Am Ende jedes Laufs `git push` (L7).

| Schritt | Inhalt | Grün werden müssen (`HHN_STRICT=1`) |
|---|---|---|
| S0 | Basis: Branch ab `main` (enthält seit PR #20 `integrate/moodle`: ILIAS + Moodle in einer Codebasis); `uv run pytest tests/acceptance tests/moodle` grün, `tests/hhn` läuft (alles rot/xfail). | – |
| S1 | `setup --list/--filter` + Instanz-Metadaten (`name`, `requires_totp`, Stadt) als reine Kernfunktion | `test_setup_help_no_secret_flags`, `test_setup_list_instances_json`, `test_setup_filter_like_autocomplete[*]`, `test_setup_unknown_instance_exit1` |
| S2 | `setup` nicht interaktiv: stdin-Eingaben, Login über vorhandenen Adapter, Config atomar mergen, Username-Default | `test_setup_hhn_success_stores_session_and_config`, `test_setup_username_default_from_config`, `test_setup_no_tty_without_*`, `test_env_password_never_used`, `test_setup_uni_mannheim_no_totp` |
| S3 | Abbruch + Fehlversuche (EOF, SIGINT, Passwort 1×, Code 3×) in `setup` **und** `login` | `test_setup_wrong_password_exit1_no_retry`, `test_setup_totp_*`, `test_setup_eof_*`, `test_setup_sigint_is_abort`; `tests/acceptance` bleibt grün |
| S4 | Interaktive Auswahlliste mit Autovervollständigung (TTY), manuell prüfen; kein neuer Test nötig | Hilfetext + kurzer Screencast/Beschreibung im PR |
| S5 | ILIAS-HTTP-Basis: Session laden, `GET` mit Status/Redirect-Prüfung (L3), Request-Pause, Cookie-Rotation | `test_courses_not_logged_in_exit2`, `test_courses_session_expired_exit3_hint_no_relogin`, `test_courses_server_503_exit4`, `test_courses_unreachable_exit4` |
| S6 | `courses`: Membership-Parser, Semester-Funktion (+ Unit-Tests), Tabelle/JSON | übrige `test_courses_*` – Lauf: `HHN_STRICT=1 uv run pytest tests/hhn/test_courses*.py -q` |
| S7 | `ls` Ebene 1–2: Container-Parser, Link-Parser + Typtabelle (§13.5), Text-Regeln (NFC), Kursauflösung inkl. Kursnummer (§13.1), Fehlerseiten (§13.7) | `test_parse_ref_from_all_link_styles`, `test_ls_type_table_*`, `test_ls_inline_file_*`, `test_ls_session_not_expanded_*`, `test_ls_permission_denied_*`, `test_ls_public_page_*`, `test_ls_titles_nfc_*`, `test_ls_by_course_number_*`, `test_ls_unknown_number_*`, `test_ls_help`, `test_ls_by_*`, `test_ls_keeps_server_order`, `test_ls_no_duplicate_entries_and_entities`, `test_ls_offline_and_unknown_types`, `test_ls_ambiguous_exit1_candidates`, `test_ls_not_found_exit1`, `test_ls_not_logged_in_exit2`, `test_ls_group_supported`, `test_ls_garbage_course_page_exit5` |
| S8 | `ls` rekursiv + `--depth` + Dateigrößen/-daten + Crawl-Schutz (§13.8) + Baum | `test_parse_size_dot_and_comma`, `test_ls_file_dates`, `test_ls_cyclic_folders_terminate`, `test_ls_request_limit_exit5`, `test_ls_nested_folders`, `test_ls_file_*`, `test_ls_depth*`, `test_ls_human_tree_escapes_markup`, `test_ls_session_expires_mid_crawl_exit3`, `test_ls_folder_500_exit4` |
| S9 | Doku (INTERFACE.md §ILIAS-HTML, README), ruff sauber, PII-Guard grün, PR | alles: `tests/acceptance`, `tests/moodle`, `HHN_STRICT=1 tests/hhn` |

Danach Live-Test durch IliasCLI/MCP mit `loop/test_hhn.sh` (der Inhaber tippt einmal den Code), dann Bugfix-Runde gegen die Live-Befunde (≤ 40 min, neue Regressionstests mit **synthetischen** Fixtures, die den Live-Fehler nachbilden).

## 11. Tests in diesem Branch
- `tests/hhn/fake_hhn.py`: erweitert den Keycloak-+TOTP-Fake von `main` um „Meine Kurse und Gruppen“, Favoriten-Dashboard, Kurs-/Ordner-/Gruppenseiten, `/go/<typ>/<ref>`- und `goto.php`-Redirects und Fehlermodi (`membership_mode`; `container_modes`: `error500`, `garbage`, `login_redirect`, `forbidden`, `public_view`; `extra_items` für Zyklen; `endless_chain` für das Request-Limit). Seit 08.10. mit derselben Struktur (Tags, Klassen, ids, data-Attribute) wie die echten HHN-Seiten (§13), aber mit ausgedachten Inhalten (ref_ids 900101 ff.).
- Daten getrennt nach Funktion: `tests/hhn/fixtures/courses/data.py` (Mitgliedschaften, S6) und `tests/hhn/fixtures/ls/data.py` (Container-Inhalte, S7/S8); `fake_hhn.py` rendert beide.
- Tests pro Funktion (jeder Bau-Lauf prüft nur seine Dateien):

| Funktion | Dateien | Tests | Lauf |
|---|---|---|---|
| `setup` (S1–S5) | `test_setup.py` | 21 | `HHN_STRICT=1 uv run pytest tests/hhn/test_setup.py -q` |
| `courses` (S6) | `test_courses.py`, `test_courses_live_structure.py` | 12 + 3 | `HHN_STRICT=1 uv run pytest tests/hhn/test_courses*.py -q` |
| `ls` (S7/S8) | `test_ls.py`, `test_ls_live_structure.py` | 22 + 36 | `HHN_STRICT=1 uv run pytest tests/hhn/test_ls*.py -q` |

  S5-Tests (`test_courses_not_logged_in_exit2` usw.) liegen in `test_courses.py`, weil sie über `courses` laufen.
- Ohne `HHN_STRICT=1` sind alle als `xfail` markiert (CI auf `main` bleibt grün). Stand (Branch `spec/hhn-live-fixtures`): **92 xfailed, 2 xpassed** (nur die Hilfetexte von `courses`/`ls` gibt es schon), mit `HHN_STRICT=1` **92 failed, 2 passed**. Die Fehlschläge sind die erwarteten: `courses`/`ls` für `hhn` antworten mit `not_supported` (Exit 1), `setup` fehlt. ruff sauber, `tests/acceptance` unverändert grün.

## 12. Live-Test (nicht im Repo)
Das Live-Skript liegt bewusst **außerhalb** des öffentlichen Repos (bei IliasCLI/MCP unter `loop/test_hhn.sh`, Ground-Truth `loop/truth/hhn_courses.json`, Auswertung `loop/check_hhn.py`). Ablauf:
1. Test-Clone auf den Ziel-Commit, `uv sync`, `HHN_STRICT=1 pytest tests/hhn`, `pytest tests/acceptance`, ruff.
2. `ilias status --instance hhn`: Ist die gespeicherte Live-Session noch gültig, wird **ohne** 2FA weitergemacht (und das Session-Alter protokolliert, beantwortet §9 Frage 2).
3. Sonst **genau ein** Login-Versuch (`setup`, falls vorhanden, sonst `login`): Passwort aus der Umgebung über stdin, der Inhaber tippt einmal den aktuellen TOTP-Code (verdeckt). Kein zweiter Versuch bei Fehler.
4. `courses`, `ls` für alle Kurse, `--depth 1/2/0`, Teilstring, nicht gefunden; danach Leak-Check (Passwort, Session-IDs, Keycloak-Cookies) und Vergleich mit der Ground-Truth.

## 13. Live-Befunde 08.10.

Erhoben am 08.10.2026 zwischen 10:44 und 10:52 (Europe/Berlin) mit der gespeicherten `ilias-cli`-Session des Repo-Inhabers auf dessen Rechner, nur `GET`, 1 s Pause, insgesamt 20 Requests: „Meine Kurse und Gruppen“, Dashboard, ein `goto.php`-Test, drei Kursseiten, drei Ordnerseiten, eine Gruppenseite, Repository-Wurzel (nach Umleitung), ein Weblink ohne Redirect-Folgen. Keine Downloads, keine Formulare, kein Logout, kein Keycloak-Kontakt. `ilias status` danach: Session gültig. Die Rohseiten liegen nur lokal bei IliasCLI/MCP (nie im Repo); alle Fixtures in `tests/hhn/` sind **neu geschrieben** (nur Struktur übernommen, Inhalte ausgedacht).

### 13.1 Kursnummern sind keine ref_ids
- Alle sieben Kursnummern aus der Einschreibung stehen in der Kursliste, aber **im Titel** (`<nr> <Fach>`, `<Kürzel> <Fach> (<nr>)`) oder nur **in der Beschreibung** (`… SPO5 <nr>`). Die ref_ids sind andere, 6–7-stellige Zahlen.
- `ilrepositorygui&ref_id=<kursnummer>` → 302 auf die Repository-Wurzel (`ref_id=1`) mit Fehler-Alert; `goto.php?target=crs_<kursnummer>` → 302 aufs Dashboard.
- Folge für `ls <kurs>`: Zahl = ref_id einer Mitgliedschaft? Sonst Kursnummer → Teilstring im Titel, dann in der Beschreibung. Nie eine unbekannte Zahl direkt abrufen (Tests `test_ls_by_course_number_in_title`, `test_ls_by_course_number_in_description`, `test_ls_unknown_number_not_found_no_root_crawl`).
- Die Liste enthält 10 Einträge (9 `crs`, 1 `grp`), darunter auch Kurse mit „Anmeldungsende“ und „Keine freien Plätze verfügbar“. Alle zählen als Mitgliedschaft.

### 13.2 Kursliste: Markup
- Seite `ilias.php?baseClass=ilmembershipoverviewgui`, alle Einträge direkt im HTML (keine Paginierung, kein Nachladen). Das Dashboard (`block_pditems_0`, „Favoriten“) zeigt nur eine Teilmenge → **nicht** verwenden (`test_courses_only_from_membership_overview`).
- Pfad: `#ilContentContainer` → `div.panel.panel-secondary.panel-flex` (Kopf `.panel-title h2` „Meine Kurse und Gruppen“, Sortierung `.il-viewcontrol-sortation`, Default „Nach Ort“) → `div.panel-body` → `div.il-item-group` (`h3` = **übergeordnete Kategorie**, nicht Semester/Typ; bei anderer Sortierung andere Gruppen → Parser gruppierungsunabhängig) → `div.il-item-group-items > ul > li.il-std-item-container > div.il-item.il-std-item > div.media`.
- In `div.media`: `div.media-left > img.icon.custom.medium` (`src …/icon_crs.svg|icon_grp.svg`, `alt` „Kurs“/„Gruppe“) und `div.media-body` mit `h4.il-item-title > a[href="{base}/go/crs/<ref>"]`, Aktionen `div.il-item-actions` (Dropdown aus `button.btn-link[data-action]`, nie auswerten), optional `div.il-item-description`, optional `hr.il-item-divider` + `div.row > div.col-md-6.il-multi-line-cap-3 > span.il-item-property-name + span.il-item-property-value` (Name kann leer sein).
- **Achtung:** Auch der Metabar enthält `div.il-item` (Benachrichtigungen) mit `.il-item-property-name` „Zeit“. Selektoren deshalb auf den Hauptinhalt begrenzen; „Zeit“ nie als Semester lesen.
- Offline-Markierung in der Kursliste: live nicht gesehen (Fixture-Annahme: Eigenschaft „Status“ = „Offline“). Leere Liste: live nicht gesehen (Fixture-Annahme: `.alert-info`).

### 13.3 Kurs-, Ordner- und Gruppenseiten: Markup
- `/go/crs/<ref>`, `/go/fold/<ref>`, `/go/grp/<ref>` → 302 → `ilias.php?baseClass=ilrepositorygui&ref_id=<ref>` (200). Tab `ul#ilTab > li#tab_view_content.active` war auf allen Seiten aktiv (kein Folgerequest nötig).
- **Legacy-Liste**, keine Kacheln, keine ILIAS-9-UI-Items: `#ilContentContainer #il_center_col` → `div.ilContainerBlock.form-inline#bl_cntr_<n>` → `div.ilContainerBlockHeader > h2.ilHeader.ilContainerBlockHeader` (Abschnittsname) → `div.ilContainerItemsContainer` → `div.ilCLI.ilObjListRow#item_row_<itgr|_other>-<ref>` → `div.ilContainerListItemOuter[data-list-item-id="lg_div_<ref>_pref_<parent_ref>"]`.
- Objektblöcke (`itgr`) haben `data-store-url="…cont_block_id=itgr_<ref>"` und stehen **vor** dem Restblock „Inhalt“ (ohne `data-store-url`, Zeilen-id `item_row__other-<ref>`). Abschnitte = Blöcke in Seitenreihenfolge.
- Im Item: `div.ilContainerListItemIcon > img.ilListItemIcon[alt][title]` und `div.ilContainerListItemContent > div.il_ContainerListItem` mit `div.il_ContainerItemTitle.form-inline > h3.il_ContainerItemTitle > a.il_ContainerItemTitle[href][target]`, Aktionen `div.ilFloatRight` (Dropdown `ul.dropdown-menu` mit „Download“, „Info“/„Information“, „Zu Favoriten hinzufügen“, „Notizen“/„Tags setzen“ mit `href="#"`), `div.ilListItemSection.il_Description`, `div.ilListItemSection.il_ItemProperties > span.il_ItemProperty`.
- **Doppel-Falle:** `div` und `h3` tragen beide die Klasse `il_ContainerItemTitle`, und bei Dateien mit Vorschau steht neben dem Titel ein `a.glyph[href="#"]`. Titel nur aus `a.il_ContainerItemTitle`; `href="#"`, `.glyph` und Dropdowns ignorieren; ein Eintrag pro ref_id (`test_ls_no_duplicate_entries_and_entities`).
- ref_id des Items: aus `data-list-item-id` (zuverlässig für alle Typen, auch Kurslinks), sonst aus dem Link.
- **Symbole sind nicht verlässlich:** viele Dateien haben ein eigenes Symbol (`img src="{base}/src/FileDelivery/deliver.php/…"`, `alt`/`title` „Inline Datei“) statt `icon_file.svg`. Typ primär aus dem Link (§13.5), Symbol nur als Fallback.
- Gesehene Typen: `fold`, `file`, `webr`, `exc`, `wiki`, `crsr` (Kurslink), in der Wurzel `cat`. Tests, Foren, Sitzungen, Plugins kamen in den geprüften Seiten nicht vor (Fixture nach ILIAS-Standard).

### 13.4 Eigenschaften
- Datei: `span.il_ItemProperty` in der Reihenfolge Endung (`pdf`, `html`), Größe mit **Punkt** als Dezimaltrenner (`NNN.NN KB`, `N.NN MB`, auch eine Nachkommastelle), Datum `D. Mon YYYY, HH:MM`. Keine Version gesehen.
- Übung: Eigenschaft `Abgabefrist: <n> Tage, <n> Stunden` (relativ; interessant für F4, für `ls` nur durchreichen oder ignorieren).
- Relative Datumsangaben (`Morgen, HH:MM`) kommen an der HHN vor (gesehen in der Kursliste); für Dateien ebenso zu erwarten.
- Offline-Objekte (`.il_ItemAlertProperty`) kamen nicht vor (Studierende sehen Offline-Objekte meist gar nicht).

### 13.5 Links und Typtabelle
`ilias_core.ilias_html.links.parse_link(href, base_url) -> (typ | None, ref_id | None)`, getestet in `test_parse_ref_from_all_link_styles`. Reihenfolge:
1. `/go/<typ>/<ref>` (HHN-Permalink, live für `crs`, `grp`, `fold`, `exc`, `cat`, `root`)
2. `goto.php/<typ>/<ref>`
3. `goto.php?target=<typ>_<ref>[_download]`
4. `ilias.php?…ref_id=<ref>` mit Typtabelle:

| Merkmal im Link | Typ |
|---|---|
| `cmdClass=ilObjFileGUI` oder `cmd=sendfile` | `file` |
| `baseClass=ilLinkResourceHandlerGUI` + `cmd=calldirectlink` | `webr` |
| `baseClass=ilWikiHandlerGUI` | `wiki` |
| `baseClass=ilExerciseHandlerGUI` | `exc` |
| `cmdClass=ilobjtestgui` | `tst` |
| `baseClass=ilrepositorygui` ohne weiteres Merkmal | `None` (Typ aus dem Symbol `icon_<typ>.svg`; Kurslink: `icon_crsr.svg`) |

Groß-/Kleinschreibung der Query-Werte ignorieren. `#` und leere Links → `(None, None)`. Unbekannte Typen → `other` (bzw. ihr Kürzel) und **nie** rekursiv laden (`test_ls_type_table_and_no_followup_for_non_containers`).

### 13.6 Sitzungen
Live nicht gesehen. Regel nach ILIAS-Standard: Sitzungen nicht aufklappen (`expand=` nie folgen), Ausgabe als `sess` mit `children: null` (`test_ls_session_not_expanded_children_null`).

### 13.7 Fehlerseiten
- Keine Berechtigung bzw. unbekannte ref_id: HHN antwortet **nicht** mit einer Fehlerseite, sondern mit 302 auf die Repository-Wurzel. Dort steht `div.ilAdminRow > div.alert.alert-danger[role=alert]` („Sie haben keine Berechtigung, auf das Objekt zuzugreifen.“) **über einer Kategorienliste**. Wer diese Liste parst, crawlt das halbe Repository. Darum: `.alert-danger` im Hauptinhalt → Exit 1 `permission_denied`, nichts parsen, nichts crawlen (`test_ls_permission_denied_page_with_category_list_exit1_no_crawl`). Zusätzlich: Endet die Weiterleitung auf einer anderen ref_id als angefragt, ist das kein Erfolg.
- Login-Merkmal: Abmelde-Link `logout.php?…cmd=doLogout` im Metabar (mit wechselndem Token in der Query, nie ausgeben). Metabar mit `login.php`-Link statt Abmelden → Session weg, Exit 3 (`test_ls_public_page_with_login_link_exit3`).
- `.il_ItemAlertProperty` an einem Item ist kein Seitenfehler, nur `visible: false`.

### 13.8 Crawl-Schutz
Rekursion nur in `fold`/`grp` der aktuellen Liste, nie in `cat`, `root` oder fremde `crs`. visited-Set über ref_id (`test_ls_cyclic_folders_terminate`), harte Obergrenze `ILIAS_CLI_MAX_REQUESTS` (Default 300) → Exit 5 `crawl_limit` ohne Teilausgabe (`test_ls_request_limit_exit5`).

### 13.9 Text
Titel und Suchbegriffe NFC-normalisieren (`unicodedata.normalize("NFC", …)`), Entities dekodieren, Leerraum normalisieren, nie kürzen (`test_ls_titles_nfc_normalized`).

### 13.10 Session
14 protokollierte GETs ohne `Set-Cookie: PHPSESSID` (keine Rotation); ILIAS setzt auf jeder Seite nur `ilClientId`. Nach ~10 min weiter gültig. Die Laufzeitmessung (15 min, 1 h, 4 h, 24 h) steht noch aus (§9 Frage 2).

### 13.11 Antworten auf §9
| # | Antwort |
|---|---|
| 1 | Nein, keine ref_ids (§13.1). Echte ref_ids und Titel liegen lokal in `loop/truth/hhn_courses.json`. |
| 2 | Teilweise: keine Rotation, ≥ 10 min gültig; Messung läuft weiter (§13.10). |
| 3 | Unverändert offen (TOTP-Formular wurde beim Login live durchlaufen, aber nicht mitgeschnitten). |
| 4 | `ilmembershipoverviewgui` liefert die vollständige Liste; Dashboard nur Favoriten. Klassen §13.2. Keine Zeitraum-Eigenschaft, Offline nicht gesehen. |
| 5 | Legacy-Liste (`ilContainerListItemOuter`/`il_ContainerItemTitle`) in `ilContainerBlock`s, Objektblöcke ja, keine Kacheln, keine Sitzungen gesehen (§13.3). |
| 6 | Endung, Größe mit Punkt, Datum `D. Mon YYYY, HH:MM` (§13.4). |
| 7 | Nur `calldirectlink`; Ziel erst per 302 (§6.2). |
| 8 | Nicht geprüft. |

### 13.12 Referenz: PFERD
Als Ideen-Quelle (nicht als Code-Vorlage für diese Runde) taugt **PFERD** (https://github.com/Garmelon/PFERD, Python, MIT-Lizenz, aktiv gepflegt, kann ILIAS 9): Typerkennung aus URL-Pfad, Query und Symbol, Login-Erkennung über den Metabar, Umgang mit Inhalts-Tab und Paginierung. Code aus GPL-lizenzierten ILIAS-Downloadern wird **nicht** übernommen; die Anforderungen oben sind eigenständig formuliert.

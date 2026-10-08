# ILIAS-CLI (später MCP): Anforderungen, Entwurf v0.1

Stand: 07.10.2026, 20:45 Uhr. Für: Samuel Fleig (HHN, AKIB, 1. Semester). Dieses Dokument beschreibt nur die Anforderungen, die Umsetzung macht jemand anderes.

Quellen-Kennzeichnung: **[V]** = selbst geprüft (öffentlich, ohne Login, 07.10.2026) · **[A]** = Annahme, muss noch bestätigt werden · **[P]** = aus Plaud-Aufnahme · **[S]** = Aussage von Samuel im Chat

---

## 1. Ziel & Scope

- **Ziel:** Alles, was im Studium über ILIAS läuft (Vorlesungsmaterial, Abgaben, Fristen), wird per Kommandozeile und später per Agent nutzbar. Fristen sollen nicht mehr verpasst werden.
  - [P] „Ein anderer wichtiger Connector für mein Leben wäre einer mit Ilias-Zugang. Also meine Uni-Sachen finden alle auf Ilias statt. Und dass das quasi alles Agent-möglich ist. Mit Vorlesungen, Abgaben und alles, was so anfällt mit der Uni.“ (Plaud, *10-07 Strategie-Note: Fokus auf vertikale MCP-Konnektoren …*, 07.10.2026, 14:36 Uhr)
- **Phase 1: CLI** [S]. Ein eigenständiges Kommandozeilen-Tool `ilias`.
- **Phase 2: MCP-Server** [S]. Er nutzt dieselben Kernfunktionen. Langfristig soll er auch auf Marketplaces erscheinen und an anderen Hochschulen mit ILIAS laufen [P, gleiche Aufnahme: „Connectoren auf den Marketplaces hochladen … im besten Fall 100.000 Leute“].
- **Architektur-Vorgabe (Muss):** Die Kernbibliothek `ilias_core` enthält Auth, Session, Datenmodell und alle Operationen. CLI und MCP sind nur dünne Hüllen ohne eigene Logik. Jede Operation liefert strukturierte Daten zurück, zum Beispiel als Pydantic-Modell oder Dataclass, und keinen formatierten Text.
- **Nicht im Scope von Phase 1:** hispro (Prüfungsanmeldung), splan/StarPlan (Stundenplan), BAföG, Lehrenden-Funktionen. hispro und splan sind als spätere Erweiterungen vorgesehen und bekommen eigene Adapter.

## 2. Nutzer & Use Cases

Erstnutzer ist Samuel. Er arbeitet auf mehreren Geräten (Mac und andere) und mit Agenten. Später kommen beliebige ILIAS-Studierende dazu.

| # | Use Case | Warum |
|---|---|---|
| UC1 | „Welche Abgaben sind in den nächsten 14 Tagen fällig?“ | Echter Schmerzpunkt: Die PM-Abgabe am 02.10. wurde verpasst (Kontext vom Parent-Agent, in Plaud nicht belegt) |
| UC2 | Neue Dateien in allen Kursen erkennen und lokal spiegeln | Vorlesungsmaterial offline und für Agenten verfügbar |
| UC3 | Datei zu einer Übung hochladen und den Erfolg prüfen | Abgabe ohne Browser, später durch einen Agenten |
| UC4 | Kursliste und Kursbeitritt per 6-stelliger Nummer | HHN: Studierende treten Kursen selbst bei (174021, 174041, 174061, 174081, 174101, 174102, BWL = 425011) |
| UC5 | Neuigkeiten und Forenbeiträge seit dem letzten Abruf | Ankündigungen von Lehrenden nicht verpassen |

## 3. Funktionale Anforderungen

| ID | Prio | Funktion | Vorgeschlagener Befehl |
|---|---|---|---|
| F1 | **Must** | Login mit HHN-Account inkl. 2FA, Session speichern, Status anzeigen, Logout | `ilias login` · `ilias status` · `ilias logout` |
| F2 | **Must** | Eigene Kurse und Gruppen auflisten (Titel, ref_id, Semester) | `ilias courses` |
| F3 | **Must** | Inhalt eines Kurses als Baum (Ordner, Dateien, Übungen, Foren) | `ilias ls <kurs\|ref_id> [--depth N]` |
| F4 | **Must** | Fristen aller Übungen/Tests kursübergreifend, sortiert, mit Status (abgegeben ja/nein) | `ilias deadlines [--days 14] [--open-only]` |
| F5 | **Must** | Dateien herunterladen, einzeln oder als Ordner | `ilias download <ref_id\|pfad> [-o DIR]` |
| F6 | **Should** | Inkrementeller Sync aller Kurse in ein lokales Verzeichnis, nur neue oder geänderte Dateien | `ilias sync [--dry-run]` |
| F7 | **Should** | Abgabe hochladen. Vorher Bestätigung (`--yes` zum Überspringen), danach den Abgabestatus erneut lesen und anzeigen | `ilias submit <übung> <datei…>` |
| F8 | **Should** | Fristen als iCal exportieren bzw. den ILIAS-Kalender-Feed nutzen | `ilias deadlines --ics > fristen.ics` |
| F9 | **Should** | Neuigkeiten und Forenbeiträge seit dem letzten Abruf | `ilias news [--since 7d]` |
| F10 | **Could** | Kurs per Nummer suchen und beitreten | `ilias join 174021` |
| F11 | **Could** | Suche im eigenen Material (Titel, später Volltext lokal) | `ilias search <begriff>` |
| F12 | **Could** | Erinnerungen (z. B. 72 h, 24 h vor Frist) über einen externen Scheduler | `ilias deadlines --due-within 24h --exit-code` |

Für alle Befehle gilt: `--json` gibt maschinenlesbare Daten aus, ohne Flag kommt eine Tabelle für Menschen. Exit-Codes sind dokumentiert (0 OK, 2 nicht eingeloggt, 3 Session abgelaufen, 4 Netzwerk/Server, 5 Parser-Fehler). Phase 2: Jeder Must- und Should-Befehl wird 1:1 zu einem MCP-Tool (`list_courses`, `list_deadlines`, `download_file`, `submit_assignment` …). Schreibende Tools wie `submit` und `join` brauchen eine ausdrückliche Bestätigung durch den Menschen (passt zum Owner-Gate-Konzept aus hai-mcp).

## 4. Schnittstellen: was erreichbar ist

Öffentliche Checks vom 07.10.2026, 20:35 Uhr, ohne Login **[V]**:

| Schnittstelle | Ergebnis | Bewertung |
|---|---|---|
| ILIAS-Version | Login-Seite zeigt **ILIAS v9.24 (2026-10-06)**. Gespeicherte Seiten vom Sept. zeigten noch v9.23 | Die Instanz wird regelmäßig aktualisiert, ein Scraper muss also robust sein |
| Client-ID | `iliashhn` (aus Links und Fehlermeldung) | Wird für calendar.php, WebDAV und SOAP gebraucht |
| **SOAP** `/webservice/soap/server.php?wsdl` | **HTTP 403** „Request forbidden by administrative rules“ (nginx) | Von außen gesperrt. Ob es aus dem Hochschulnetz/VPN geht, ist unbekannt. Außerdem erwartet die SOAP-`login()` Benutzername und Passwort, für OIDC-Konten ohne ILIAS-Passwort taugt sie also vermutlich nicht [A] |
| **REST** | Kein REST-Plugin gefunden (typische Pfade geben 404). ILIAS 9 hat **keine allgemeine REST-API im Kern** | Fällt aus |
| **WebDAV** `/webdav.php/iliashhn/ref_1/` | **HTTP 403** „Please enable the WebDAV plugin in the ILIAS Administration panel“ | **Deaktiviert** |
| **iCal** `/calendar.php?client_id=iliashhn&token=…` | Endpunkt antwortet (200, leer bei ungültigem Token) | **Vielversprechend.** In ILIAS 9 gibt es im Kalender die Funktion „Abonnieren“, die eine Token-URL erzeugt (`calendar.php?client_id=…&token=…`, liefert `text/calendar`). Ob das an der HHN aktiv ist und ob Übungsfristen darin auftauchen, muss Samuel nach dem Login prüfen [A] |
| **RSS** `/feed.php` / `/privfeed.php` | feed.php 200 (leerer öffentlicher Feed), privfeed.php **401** | Privater News-Feed ist möglich. In ILIAS braucht er ein eigenes Feed-Passwort im Profil [A] |
| **Login** | `login.php` → Startseite. `openidconnect.php` → **302 auf Keycloak** `login.hs-heilbronn.de/realms/hhn`, client_id `hhn_common_ilias`. Daneben gibt es ein lokales Formular „Ohne HHN-Konto anmelden“. `shib_login.php`: Shibboleth nicht konfiguriert. `saml.php` → error.php | **OIDC (Keycloak), kein Shibboleth/SAML.** Studierende melden sich über OIDC an, 2FA kommt von Keycloak |
| Keycloak-Discovery | Realm unterstützt u. a. `device_code` und `refresh_token` | Theoretisch ideal für eine CLI. Es braucht aber einen eigenen, vom Rechenzentrum freigegebenen Client. `hhn_common_ilias` ist ein Web-Client, und den zu „leihen“ ist tabu |
| robots.txt | `Disallow: /` | Scraping höflich und sparsam machen, nur mit eigenem Account und eigenen Daten |

**Folgerung:** Schneller Weg (API) heißt Fehlanzeige. Realistisch ist ein **Hybrid**:
1. **Web-Session + HTML-Parsing** als Hauptweg für Kurse, Inhalte, Übungen, Download und Upload. Die URL-Muster sind stabil: `goto.php?target=crs_<ref_id>`, `ilias.php?baseClass=ilrepositorygui&ref_id=<id>`, `goto.php?target=file_<id>_download` [A, Muster aus gespeicherten Seiten in /workspace/hhn/ und ILIAS-Standard].
2. **iCal-Token-Feed** für Fristen (F4/F8), wenn verfügbar. Er läuft ohne Session und ist robust.
3. **RSS** optional für News (F9).
4. **Mittelfristig:** Beim Rechenzentrum (ticket@hs-heilbronn.de) nach SOAP-Freigabe oder einem OIDC-Client mit Device-Flow fragen.

## 5. Authentifizierung & 2FA

- **A1 (Must):** Das Passwort wird **nie** in Klartext gespeichert, geloggt oder an einen Agenten/LLM übergeben. Eingabe nur über einen sicheren Prompt (verdeckte TTY-Eingabe) oder ein sicheres Formular [S: Samuel gibt Passwörter nur so ein].
- **A2 (Must):** 2FA (TOTP aus der Authenticator-App) wird interaktiv abgefragt. Das Tool speichert **kein TOTP-Secret**.
- **A3 (Must):** Login-Ablauf: ILIAS `openidconnect.php` → Keycloak-Formular → TOTP → Redirect → ILIAS-Session-Cookie. Alternative als Fallback: Der Login läuft im Browser (z. B. Playwright, sichtbar), danach wird nur das Session-Cookie übernommen.
- **A4 (Must):** Session-Cookies liegen im **OS-Schlüsselbund** (macOS Keychain, Linux Secret Service, Windows Credential Manager über `keyring`) oder in einer Datei mit `0600`. Sie werden nie ins Repo geschrieben, nie geloggt und nie in die MCP-Antwort gegeben.
- **A5 (Must):** Eine abgelaufene Session wird erkannt (Redirect auf login.php) und führt zu einer klaren Meldung und Exit-Code 3. Ohne Zustimmung wird kein Re-Login mit gespeichertem Passwort versucht.
- **A6 (Should):** Session pro Gerät. Kein Sync von Cookies zwischen Geräten. Jedes Gerät loggt sich einmal selbst ein.

## 6. Sprachempfehlung: **Python** (≥ 3.11)

| Kriterium | Python | TypeScript |
|---|---|---|
| Passt zu Samuels Stack | **hai-mcp ist Python** (GitHub smlfg/hai-mcp, verifiziert). Laut Plaud baut er gerade Git/Python-Skills auf (09-29), Anaconda ist geplant (10-06) | Kein Bezug gefunden |
| MCP-SDK | Offizielles `mcp` Python SDK (FastMCP), ausgereift | Offizielles TS SDK, ebenso ausgereift |
| Scraping/HTTP | `httpx` + `selectolax`/`BeautifulSoup`, `playwright` für Login-Fallback | `undici`/`cheerio`, `playwright` |
| CLI | `typer` + `rich` (Tabellen) | `commander`/`oclif` |
| Verteilung | `uv tool install` / `pipx` auf allen Geräten | `npx`, global per npm |

Empfehlung **Python**: gleiche Sprache wie hai-mcp und das Studium, gute Bibliotheken für Scraping und iCal (`icalendar`), Paketierung mit `uv`. TypeScript wäre nur sinnvoll, wenn später ein Marketplace ausdrücklich Node verlangt.

## 7. Nicht-funktionale Anforderungen

- **N1 Sicherheit:** siehe A1 bis A6. Keine Telemetrie in Phase 1. Logs ohne Cookies, Tokens oder Dateiinhalte.
- **N2 Schonender Zugriff:** höchstens ca. 1 Request/s, Retry mit Backoff, Caching (ETag/Last-Modified bzw. lokaler Index), kein paralleles Crawling. Eigener User-Agent (`ilias-cli/x.y`).
- **N3 Datenschutz:** Es werden nur Samuels eigene Daten verarbeitet, alles lokal. Inhalte anderer (Forum, Teilnehmerlisten) werden nicht massenhaft gespeichert. Vor einem Marketplace-Release: DSGVO-Prüfung und Klärung mit der HHN, ob automatisierter Zugriff erlaubt ist (Nutzungsordnung).
- **N4 Robustheit:** Parser sind gekapselt (ein Modul pro Seitentyp). Fixture-Tests mit gespeichertem HTML. Ein Smoke-Test erkennt Layout-Änderungen nach ILIAS-Updates (siehe 9.23 → 9.24).
- **N5 Ausgabe:** Text für Menschen standardmäßig, `--json` stabil und versioniert, Datumsangaben in ISO 8601 mit Zeitzone Europe/Berlin.
- **N6 Cross-Device:** macOS, Linux, Windows. Konfiguration unter `~/.config/ilias-cli/config.toml` (Basis-URL, Client-ID, Sync-Ordner) für mehrere Hochschulen.
- **N7 Konfigurierbarkeit:** Basis-URL und Client-ID sind nicht hart kodiert (HHN = `https://ilias.hs-heilbronn.de`, `iliashhn`). So geht der Weg zu anderen ILIAS-Instanzen offen.

## 8. Aufwand (Samuels Einschätzung [S], angepasst an die Checks)

Es gibt keine nutzbare API, deshalb gilt der **Scraping-Fall**: Prototyp mit F1 bis F5 in **2 bis 5 Tagen**, verlässlich und Marketplace-reif mit Tests, Fehlerbehandlung und Datenschutz in **2 bis 4 Wochen**. Der OIDC-Login mit 2FA ist das größte Einzelrisiko (geschätzt 1 bis 2 Tage). Funktioniert der iCal-Feed, wird F4 deutlich günstiger. Der MCP-Server auf fertigem Core kostet zusätzlich etwa 0,5 bis 1 Tag.

## 9. Offene Fragen

1. **iCal-Abo:** Gibt es nach dem Login unter *Kalender* den Button „Abonnieren“, und stehen Übungsfristen der Kurse darin? (Wenn ja, ist F4 fast geschenkt.)
2. **Login-Weg:** Soll der Login headless laufen (Formular nachbauen) oder über ein sichtbares Browserfenster (Playwright), aus dem nur das Cookie übernommen wird? Wie lange hält eine ILIAS-Session?
3. **Rechenzentrum fragen?** Sollen wir per ticket@hs-heilbronn.de nach SOAP-Freigabe oder einem OIDC-Client mit Device-Flow für eine Studierenden-CLI fragen? (Das wäre eine Mail in Samuels Namen und bräuchte seine Freigabe.)
4. **Prioritäten:** Ist die Reihenfolge Fristen → Download/Sync → Upload richtig? Sollen `submit` und `join` schon in Phase 1 dabei sein?
5. **Sync-Ziel:** Wohin sollen gespiegelte Dateien (lokaler Ordner, iCloud, Obsidian/„Gedankenpalast“)? Brauchen Agenten Volltext?
6. **Repo/Name:** Eigenes Repo (z. B. `smlfg/ilias-cli`) oder Teil von hai-mcp? Lizenz MIT wie hai-mcp?
7. **Reichweite:** Nur HHN oder von Anfang an generisch für andere ILIAS-Instanzen (betrifft N7 und den Auth-Adapter)?

---
*Grundlagen: öffentliche HTTP-Checks (07.10.2026), gespeicherte ILIAS-Seiten in /workspace/hhn/ (cj.txt nicht geöffnet), /workspace/studium/Stand_2026-09-27.md, Infos vom Agenten „ILIAS Heilbronn“, ILIAS-9-Quellcode-Doku (ildoc.hrz.uni-giessen.de), Plaud-Aufnahmen 14.09. bis 07.10.2026. Nur **eine** Aufnahme behandelt ILIAS ausdrücklich (10-07 Strategie-Note), Anforderungen im Detail stehen in Plaud nicht.*

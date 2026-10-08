# Vergleich Moodle-Branches (HS Mannheim), Stand 08.10.2026 ca. 10:30 Europe/Berlin

Moodle-Login (F1) und danach F2+F3 (`ilias courses`, `ilias ls <kurs>`), gebaut von den Gratis-Modellen aus OpenCode Zen plus `opencode-go/deepseek-v4.1-flash` (Go-Abo, für dieses Projekt freigegeben). Gleicher Prompt für alle: `moodle-task.md` für den Login, `F3_TASK.md` auf `moodle-f2f3/base` für F2+F3.

Lokal geprüft:
- `uv run pytest tests/moodle -q` und `ilias --help`.
- Login-Black-Box: eigener Fake-Moodle auf 127.0.0.1 mit `sitecustomize`-Guard, der jede externe Verbindung und jede DNS-Abfrage blockiert. Geprüft werden Exit-Codes 0/1/2/3, Leaks in Ausgaben und Dateien, Token-Datei 0600 und dass der Token nie in der URL steht. 19 Checks.
- F2+F3-Black-Box: ein gemeinsamer, unabhängiger Fake mit den Live-Bugs aus dem echten Test (doppelte Links, HTML-Entities, abgeschnittene URLs bei 80 Spalten, Semesterregel, natürliche Sortierung, Terminplaner). 23 Checks.

**Wichtig:** Alle Moodle-Branches basieren auf `7da74bb`. Seit PR #6 (SAML Uni Mannheim, 09:10) hat main eine andere Struktur, deshalb haben alle Moodle-PRs Merge-Konflikte mit main. Der Gewinner (DeepSeek `ef60408`) wird deshalb über den Branch `integrate/moodle` mit main zusammengeführt (siehe dortiger PR).

## Moodle-Login (PRs gegen main)

| PR | Modell | Erster Anlauf | Nach Fix | Tests | Black-Box | Live (Samuel 08:17) | Ruff |
|---|---|---|---|---|---|---|---|
| #10 | space-bunny | ✅ `9561580` | – | 60/60 | 19/19 | ✅ | 10 |
| #11 | muse-spark-1.3-contributor | ✅ `5f28913` | – | 40/40 | 19/19 | ✅ | 34 |
| #12 | fledge-alpha | ✅ `c25711f` | – | 17/17 | 19/19 (nur flache Konfig) | ✅ | 6 |
| #13 | deepseek-v4.1-flash | ✅ fachlich (36/36), aber nicht selbst committet (Abbruch am `/tmp`-Zugriff) | `5cb3c82` | 41/41 | 19/19 | – | 0 |
| #14 | nemotron-3-ultra | ❌ Timeout, 9 Tests rot, Exit 1 bei jedem Erfolg | `96cf73a` (1 Fix-Lauf) | 32/32 | 18/19 (`logout` human → Exit 1) | ⚠️ (WIP) | 46 |
| #15 | nemotron-3.5-lightning | ❌ Timeout, Paket importiert nicht | WIP `3c0c2aa` (2 Fix-Läufe, aufgegeben) | 17/24 | 12/19 | ❌ | – |
| – | longcat-2.5-preview | abgebrochen (doom_loop) | – | – | – | – | – |

**Empfehlung Login:** **space-bunny als Basis**: getrennte Backends, `service.py`, `http.py` mit `trust_env=False`, Secret-Scrubbing, Retry für site_info. Dazu per Cherry-pick:
- die Leak- und User-Agent-Tests aus muse-spark (#11)
- die `sitecustomize`-Sandbox im Subprozess aus fledge-alpha (#12)
- den Override über `[instances.<key>]` plus den Guard-Test aus DeepSeek (#13), optional

## F2+F3 courses + ls (PRs gegen `moodle-f2f3/base`)

| PR | Modell | Stand | Tests | F2+F3-Black-Box (23) | Bemerkung |
|---|---|---|---|---|---|
| #7 | deepseek-v4.1-flash | `a2979df` im ersten Anlauf, selbst committet; `ef60408` nach Bugfix-Runde 1 | 113 → **124** | 13 → **23/23** | Pionier, live getestet von IliasCLI/MCP. Nach Runde 1 sind alle Live-Bugs behoben |
| #16 | space-bunny | WIP `939f9d3` (3 Läufe ohne Commit: `/tmp`-Abbruch, dann Rate-Limit) | 128 | 17/23 | bester Gratis-Stand, dekodiert Entities. Doppelte Links, URLs abgeschnitten, MOODLE.md fehlt |
| #9 | muse-spark-1.3-contributor | `0a3a8b2` (2. Lauf nach `/tmp`-Abbruch) | 100 | 14/23 | lesbarster Baum, URLs vollständig. Entities, doppelte Links |
| #8 | fledge-alpha | `ac694ee` im ersten Anlauf | 97 | 13/23 | sauber, aber dieselben Live-Bugs plus abgeschnittene URLs |
| #17 | nemotron-3-ultra | WIP `4775929` (2× Upstream-503) | 60 (nur Login) | 7/24 | courses/ls ohne Funktion, keine neuen Tests |
| #18 | nemotron-3.5-lightning | WIP `0ff8de4` (Unsinnstext, Retry ohne Commit) | Collection-Error | 5/24 | nicht lauffähig |

Die falsche Semesterregel (April–September) stand in der ersten Fassung von `F3_TASK.md` und ist kein Modellfehler. Seit `367248c` ist sie korrigiert: März–August SoSe, September–Februar WiSe.

**Ergebnis F2+F3:** **deepseek-v4.1-flash (#7)** ist Gewinner (Live-Tabelle unten) und wird über `integrate/moodle` nach main gebracht.

## Live-Test F2+F3 (IliasCLI/MCP gegen moodle.hs-mannheim.de, 78 Prüfpunkte)

Durchgeführt vom Nutzer selbst bzw. dem IliasCLI/MCP-Agenten mit eigenen Zugangsdaten. Die Gratis-Modelle wurden auf dem jeweiligen PR-Stand geprüft.

| Modell | PR | Live | Abweichungen |
|---|---|---|---|
| deepseek-v4.1-flash | #7 (`ef60408`) | **78/78** | keine |
| fledge-alpha | #8 | 75/78 | doppelte Links („Link Link“), HTML-Entity `&gt;` sichtbar, URL abgeschnitten |
| space-bunny | #16 | 74/78 | doppelte Links („Link Link“), URL abgeschnitten, `ls 213` zeigt nur 1 von 3 Dateien |
| muse-spark-1.3-contributor | #9 | 74/78 | doppelte Links, `ls 213` zeigt nur 1 von 3 Dateien |

Hinweis: Abweichungen der Gratis-Modelle bei der Semesterangabe gehen auf die falsche Semesterregel in der ersten Fassung von `F3_TASK.md` zurück. Das ist ein Fehler des Orchestrators, nicht der Modelle.

Bekannte offene Punkte auch beim Gewinner (aus dem Live-Test, nicht behoben):
- Label-Texte kommen von der Moodle-API auf ~50 Zeichen mit `...` gekürzt an.
- In Kurs 6363 zeigen die URL-Module „SWT-Labor“ und „VPN Client“ auf `mod/url/view.php` statt auf die Ziel-URL (vermutlich liefert die API kein `externalurl`).

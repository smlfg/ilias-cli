# UX-Fixtures ilias-cli

Herkunft der Dateien in diesem Ordner:

- `login_keycloak.html`, `login_totp.html`, `dashboard.html`, `login_erfolg.html`:
  **synthetisch**. Konto- und Login-Seiten werden nie mit echten Zugangsdaten
  abgerufen. Die Feldnamen (`username`, `password`, `credentialId`, `otp`) und
  Formular-IDs (`kc-form-login`, `kc-otp-login-form`) entsprechen dem am
  04.11.2026 öffentlich sichtbaren HHN-Keycloak-Formular; Inhalte sind ausgedacht.
- `membership.html`, `container_900101.html`: **synthetisch**. Die echte Seite
  „Meine Kurse und Gruppen“ war am 04.11.2026 ohne Login leer; die Struktur
  (`.panel-body`, `li.il-std-item-container`, `.ilContainerBlock`,
  `.ilContainerListItemOuter`) folgt den live gesehenen Klassen und den
  dokumentierten Befunden in `docs/HHN_2FA_SPEC.md` §13. ref_id 900101 und
  Datei 900311 sind ausgedacht.
- `download_blatt10.pdf`: **synthetisch**, nur ein Platzhalter für den
  Datei-GET nach der Bestätigung.

Alle Namen, Kurse und Dateien sind fiktiv. Es sind keine echten Personen-,
Konto- oder Kursdaten enthalten.

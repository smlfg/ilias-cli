Captured 2026-10-08 ~07:30 Europe/Berlin with anonymous GETs (no credentials).
- ILIAS login page: https://ilias.uni-mannheim.de/login.php?client_id=ILIAS&cmd=force_login&lang=de -> contains link ./saml.php
- GET https://ilias.uni-mannheim.de/saml.php -> 3 redirects -> https://idp.uni-mannheim.de/idp/profile/SAML2/Redirect/SSO?execution=e1s1 (Shibboleth IdP, title "IdP Universität Mannheim Anmeldung")
- IdP form: id=login-form, action=/idp/profile/SAML2/Redirect/SSO?execution=e1s1, POST, fields: csrf_token (hidden), j_username, j_password, donotcache (checkbox), _shib_idp_revokeConsent (checkbox). Submit button name is likely _eventId_proceed (Shibboleth standard).
- No 2FA hints on the page.
- Expected after POST (Shibboleth standard, unverified): optional attribute-release consent page (form with _eventId_proceed and _shib_idp_consentOptions), then an auto-submit HTML form POSTing SAMLResponse (+ RelayState) to ILIAS ACS (likely https://ilias.uni-mannheim.de/saml.php or .../Services/Saml/lib/...), which sets ILIAS session cookies and redirects to the dashboard.

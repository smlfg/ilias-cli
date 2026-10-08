<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>Anmeldung - ILIAS</title>
</head>
<body>
  <main>
    <h1>Anmeldung</h1>
    <form id="login_form" name="login_form"
          action="https://ilias.hs-heilbronn.de/login.php?client_id=iliashhn"
          method="post">
      <input type="text" name="username" id="username">
      <input type="password" name="password" id="password">
      <input type="submit" name="cmd[login]" value="Anmelden">
    </form>
    <p><a href="openidconnect.php?client_id=iliashhn">Ohne HHN-Konto anmelden</a></p>
  </main>
</body>
</html>

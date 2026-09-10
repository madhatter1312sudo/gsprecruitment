# Google Sign-In: Cloud Console-checklist

Draaiboek voor de eigenaar, bij het inrichten of controleren van de
OAuth-cliënt achter `GET /api/auth/google/login` en
`GET /api/auth/google/callback` (`talent-os/backend/routers/auth.py`).

## 1. OAuth-cliënt aanmaken of controleren

Google Cloud Console → API's en services → Inloggegevens → OAuth 2.0-
client-ID's.

- **Type**: Webtoepassing (niet "Bureaubladtoepassing" of "Android/iOS" --
  dit is een server-side redirect-flow).
- **Geautoriseerde omleidings-URI's**: exact
  `https://api.gsprecruitment.nl/api/auth/google/callback`. Geen
  afwijkende poort, geen trailing slash, geen `http://`. Dit moet
  letterlijk gelijk zijn aan `GOOGLE_REDIRECT_URI` in `talent-os/.env`
  (`docker-compose.yml`, `.env.example`) -- een verschil van ook maar één
  teken geeft Google's foutmelding `redirect_uri_mismatch`, niet een van
  de acht foutcodes uit §4 hieronder (die fout gebeurt bij Google, vóór
  onze callback ooit wordt aangeroepen).
- **Geautoriseerde JavaScript-oorsprongen**: `https://gsprecruitment.nl`.
  (`https://www.gsprecruitment.nl` toevoegen als de site daar ook
  publiek op bereikbaar is en de knop daar ook moet werken.)

## 2. Toestemmingsscherm (OAuth consent screen)

Moet op **In production** staan, niet **Testing**.

In **Testing** verlopen refresh-tokens na zeven dagen. Dat raakt niet
alleen Google Sign-In (een gebruiker die inlogt krijgt gewoon een nieuwe
sessie, dat blijft werken) -- het breekt ook de bestaande
`GOOGLE_REFRESH_TOKEN` die de Gmail API gebruikt om transactionele mail
te versturen (`services/email_service.py`, `EMAIL_PROVIDER=gmail`): die
token verloopt dan elke week stilzwijgend, en verzending faalt tot iemand
hem handmatig vernieuwt. Zet het scherm op **In production** voordat dit
in productie draait.

- **Scopes**: `openid`, `.../auth/userinfo.email`,
  `.../auth/userinfo.profile`. Niets gevoeligers voor de inlogflow zelf.
- **Privacy-URL**: `https://gsprecruitment.nl/privacy`.
- Applicatienaam en logo naar smaak; geen persoonsnaam als contactpersoon
  in de publieke velden (faceless merk).

## 3. Advies: een tweede OAuth-cliënt voor `gmail.send`

De huidige inrichting hergebruikt `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`
voor twee dingen: Google Sign-In (dit document) en de Gmail API-token
achter `GOOGLE_REFRESH_TOKEN` (scope `gmail.send`,
`services/email_service.py`). Dat werkt, maar heeft een nadeel: elke
gebruiker die op "Inloggen met Google" klikt, ziet dezelfde cliënt-ID als
degene die ooit `gmail.send` heeft geautoriseerd, en een gevoelige
verzendscope op een publiek zichtbare inlogknop is nodeloos verwarrend
richting Google's eigen app-verificatie en richting een oplettende
gebruiker.

**Advies**: maak een tweede OAuth-cliënt (ook Webtoepassing, geen nieuwe
redirect-URI nodig want hij authenticeert alleen intern) die uitsluitend
de `gmail.send`-scope draagt en waarvan alleen de eigenaar zelf ooit de
toestemming heeft gegeven om `GOOGLE_REFRESH_TOKEN` te verkrijgen. De
inlogcliënt (dit document, stap 1-2) toont dan nooit meer dan
`openid`/`email`/`profile` aan een kandidaat of klant.

Dit is een advies, geen voorwaarde om te starten: de huidige, gedeelde
cliënt blijft functioneel werken voor beide doeleinden. Splits zodra
daar gelegenheid voor is, niet als blokkerende stap voor deze release.

## 4. Foutcodes (`?google_auth_error=`)

De callback stuurt bij een mislukte flow altijd een redirect naar
`{FRONTEND_URL}/?google_auth_error=<code>`, nooit een kale JSON-fout (een
top-level browsernavigatie kan geen JSON-response afvangen). De
frontend (`website/script.js`) toont voor elk van deze negen codes een
eigen NL/EN-tekst:

| Code | Betekenis |
|---|---|
| `not_configured` | `GOOGLE_CLIENT_ID` staat leeg op de backend -- Sign-In is niet ingericht. |
| `invalid_state` | De CSRF-state klopt niet (verlopen na 10 minuten, cookie ontbreekt, of een vervalste poging). |
| `missing_code` | Google gaf geen `code` terug op de callback. |
| `token_exchange_failed` | De uitwisseling van `code` tegen een token bij Google mislukte (verkeerde cliëntgegevens, netwerkfout, of `redirect_uri`-mismatch die Google zelf al blokkeerde vóór onze callback). |
| `email_not_verified` | Het Google-account zelf heeft een niet-geverifieerd e-mailadres. |
| `account_disabled` | Er bestaat al een account met dit e-mailadres, maar het is (zacht) verwijderd. |
| `admin_use_password` | Het Google-account hoort bij een beheerdersaccount. Beheerders loggen in met wachtwoord en TOTP, niet via Google Sign-In, zodat de TOTP-controle nooit wordt overgeslagen. |
| `server_error` | Onverwachte fout bij het verifiëren van het ID-token. |
| `access_denied` | Doorgegeven van Google zelf: de gebruiker heeft op het toestemmingsscherm op "Weigeren" geklikt. |

## 5. Verifiëren dat het werkt

```bash
curl -sI https://api.gsprecruitment.nl/api/auth/google/login \
  -H "User-Agent: gsp-ops" | grep -i location
```

De `Location`-header moet naar `accounts.google.com` wijzen en daarin
`redirect_uri=https%3A%2F%2Fapi.gsprecruitment.nl%2Fapi%2Fauth%2Fgoogle%2Fcallback`
bevatten (URL-gecodeerd, dus met `%3A%2F%2F` in plaats van `://`) --
komt die waarde niet overeen met de URI uit stap 1, dan staat
`GOOGLE_REDIRECT_URI` in `talent-os/.env` niet gelijk aan wat in Cloud
Console is geautoriseerd.

Om ook een rol/next-parameter te controleren (zie de contractbeschrijving
in `routers/auth.py`):

```bash
curl -sI "https://api.gsprecruitment.nl/api/auth/google/login?role=client&next=/client/vacatures" \
  -H "User-Agent: gsp-ops" | grep -i location
```

Zonder `User-Agent: gsp-ops` blokkeert de WAF de aanvraag met een 403
voordat de backend hem ooit ziet -- dat is geen fout in de Sign-In-
configuratie zelf, alleen een ontbrekende header in het testcommando.

## 6. Rollback

Google Sign-In is een aanvullend inlogpad naast het bestaande e-mail-
/wachtwoord-formulier, niet een vervanging. Bij problemen: zet
`GOOGLE_CLIENT_ID` leeg in `talent-os/.env` en herstart de backend.

```bash
ssh gsp@188.245.254.248
cd /home/gsp/projects/gsp-recruitment
docker compose restart backend
```

`GET /api/auth/google/login` geeft dan direct de `not_configured`-
redirect (§4) in plaats van naar Google te sturen; het gewone e-mail-
/wachtwoord-inloggen (`POST /api/auth/login`) blijft ongewijzigd werken.

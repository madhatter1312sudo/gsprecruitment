# App-release — Google Play Store

Stappenplan voor de eigenaar om de Expo-app (`app/`, GSP Recruitment,
SDK 57) via EAS naar de Google Play Store te krijgen. Alle commando's
hieronder draaien lokaal, met een eigen Expo- en Google-account — dit
zijn stappen die alleen de eigenaar kan zetten, geen agent.

## Wat vooraf nodig is

| Account | Kosten | Waarvoor |
|---|---|---|
| Expo-account | Gratis | `eas login`, bouwt de app in de cloud |
| Google Play Console-account | €25 eenmalig | Publiceren op de Play Store |
| Service-account JSON uit de Play Console | Gratis | Alleen nodig voor `eas submit` (automatisch uploaden); handmatig uploaden in de Play Console kan ook zonder |

De repo bevat bewust geen Expo- of Google-credentials. Log lokaal in met
je eigen account; er wordt niets van de repo naar Expo/Google gestuurd
buiten de broncode.

## Stap 0: begin vandaag, want twee dingen hebben doorlooptijd

Deze twee bepalen of een releasedatum haalbaar is. Ze staan bewust vóór
het stappenplan, want wie ze pas in de Play Console tegenkomt, is te laat.

**1. Twaalf testers, veertien aaneengesloten dagen.** Een persoonlijk
Play Console-account dat na 13 november 2023 is aangemaakt, krijgt pas
toegang tot productie na een closed test met minimaal twaalf testers die
veertien aaneengesloten dagen ingeschreven staan. Opt een tester uit en
weer in, dan begint zijn telling opnieuw. Daarna volgt nog de aanvraag
voor productietoegang, die tot zeven dagen duurt, en pas daarna de
gebruikelijke review. Werf die twaalf mensen dus nu, parallel aan al het
andere, en niet nadat de store listing klaar is. Een organisatieaccount
kent deze eis niet; controleer in de Play Console welk type account je
hebt voordat je op deze doorlooptijd plant.

**2. Echte vacatures in productie.** De publieke vacaturelijst sluit de
zes demo-vacatures uit migratie 012 uit
(`talent-os/backend/routers/jobs.py`, `list_public_jobs`). Staat er geen
echte opdracht open, dan geeft `GET /api/public/jobs` een lege lijst en
ziet de reviewer van Google een leeg hoofdscherm. Dat valt onder Google's
eis van minimale functionaliteit en is een reele afwijzingsgrond. Zorg
dat er drie tot vijf echte, niet-demo vacatures met status `open` in
productie staan voordat je de app indient, en ook al tijdens de closed
test, zodat de testers iets te zien krijgen. Anoniem mag: een vacature
zonder `company_display` toont "confidential", precies zoals het
gezichtsloze model bedoelt.

## De definitieve package-naam

`android.package` in `app/app.json` staat op **`nl.gsprecruitment.app`**.
Dit is de `applicationId` waarmee de app voor altijd op Google Play komt
te staan — na de eerste upload is deze **niet meer te wijzigen** zonder
de hele Play-listing (incl. reviews en installbasis) opnieuw te
beginnen. Verander deze waarde dus niet meer, tenzij er nog nooit een
build naar Play is geüpload.

De iOS `bundleIdentifier` staat op dezelfde naam (`nl.gsprecruitment.app`)
voor consistentie tussen de platforms; dat heeft geen invloed op Android.

## Versie en versionCode

- **`expo.version`** in `app/app.json` (`1.0.0`) is het door gebruikers
  zichtbare versienummer (semver). Verhoog deze handmatig bij elke
  release die je aan gebruikers wilt tonen (bijv. `1.0.1`, `1.1.0`).
- **`versionCode`** (het interne, altijd oplopende Android buildnummer)
  komt **niet** uit `app.json` — `app/eas.json` zet
  `"appVersionSource": "remote"`, wat betekent dat EAS het laatste
  versionCode bijhoudt op Expo's servers, en `"autoIncrement": true`
  staat op het `production`-profiel, dus elke productie-build verhoogt
  hem automatisch. Er staat geen `android.versionCode` in `app.json` —
  dat zou met `remote` conflicteren, dus laat dat veld leeg.
- Kortom: voor een nieuwe release pas je alleen `expo.version` aan (als
  je dat wilt) en draai je een nieuwe `production`-build; versionCode
  regelt EAS zelf.

## Stappenplan

```sh
npm install -g eas-cli
cd app
eas login                              # eigen Expo-account
eas build:configure                    # koppelt dit project aan je Expo-account/project-id
```

**1. Test-APK (installeren op een eigen Android-toestel, niet voor de Store):**

```sh
eas build --platform android --profile preview
```

Dit levert een `.apk` op die je rechtstreeks op een testtoestel
installeert (`internal`-distributie, geen Play Store nodig). Gebruik dit
om de release-configuratie op een echt toestel te controleren voordat je
naar productie gaat — met name CV-upload (document picker) en de share-
sheet voor data-export op het Profiel-scherm, want die paden zitten niet
in de geautomatiseerde testsuite (zie `app/README-APP.md`, sectie
"Manual smoke test checklist").

**2. Productie-build (Android App Bundle, voor de Play Store):**

```sh
eas build --platform android --profile production
```

Dit levert een `.aab` (App Bundle) op — het bestandstype dat de Play
Store voor nieuwe apps verplicht stelt. `versionCode` wordt automatisch
opgehoogd (zie hierboven).

**3. Uploaden naar de Play Console:**

Twee routes, kies er één:

- **Handmatig** (eerste keer aanbevolen): download de `.aab` na de build
  (link staat in de `eas build`-output of op expo.dev/accounts/.../builds)
  en upload hem zelf in de Play Console onder **Release → Testing →
  Gesloten test**. Bij een persoonlijk account is dat geen keuze maar de
  verplichte route: zie stap 0. De veertien dagen gaan lopen zodra de
  twaalf testers zijn ingeschreven, dus upload hier zo vroeg mogelijk,
  ook als de store listing nog niet af is.
- **Automatisch** via EAS, nadat je eenmalig een service-account hebt
  aangemaakt in de Play Console (**Setup → API access** → service-account
  JSON downloaden, rechten geven als "Release manager" of hoger):

  ```sh
  eas submit --platform android
  ```

  EAS vraagt de eerste keer naar het pad van de service-account JSON en
  onthoudt dat daarna in je EAS-projectconfiguratie (niet in deze repo).

**4. Play Console-formulieren invullen (verplicht vóór publicatie):**

Controleer eerst dat er drie tot vijf echte, niet-demo vacatures met
status `open` in productie staan (stap 0, punt 2). Een reviewer die een
leeg hoofdscherm ziet, kan de app afwijzen op minimale functionaliteit.
Snel te controleren:

```sh
curl -s -H "User-Agent: gsp-ops" https://api.gsprecruitment.nl/api/public/jobs
```

Een lege lijst `[]` betekent: nog niet indienen.

Dit zijn Play Console-schermen, geen commando's: content rating
(vragenlijst), data safety-formulier (welke gegevens de app verzamelt),
doelgroep, privacy policy-URL en de store listing (screenshots,
beschrijving NL en EN, iconen).

**Alles wat je in deze schermen moet invullen of uploaden staat kant en
klaar in `docs/PLAY-STORE-LISTING.md`**: de beschrijvingen in beide talen
binnen de tekenlimieten, de antwoorden op het data safety-formulier met
per regel de plek in de code waar dat uit blijkt, de verwachte content
rating en de stappen voor het reviewer-testaccount.

Gebruik voor de store listing de bestanden in `store/play/`, niet die in
`app/assets/`. Het icoon in `app/assets/icon.png` is 1024x1024 met een
alfakanaal en dient als app-icoon in de build zelf; Play weigert
transparantie in het store-icoon en wil daar exact 512x512 zonder
alfakanaal. Daarvoor staat `store/play/icon-512.png` klaar, samen met
`store/play/feature-graphic-1024x500.png`. Schermafbeeldingen moet je nog
zelf maken, zie de assets-checklist in `docs/PLAY-STORE-LISTING.md`.

Reken op een eerste review van Google van enkele dagen tot een week; plan
dit ruim voor 30 september in.

## Android-permissies

`app.json` bevat bewust **geen** `android.permissions`-lijst. De app
gebruikt geen camera, locatie, contacten of opslag-brede toegang; CV-
upload (`expo-document-picker`) gebruikt Android's Storage Access
Framework en de data-export (`Share.share` in het Profiel-scherm) deelt
platte tekst via het systeem — geen van beide vraagt een Android
runtime-permissie aan. Elke permissie die je later toevoegt (bijv. bij
duw-notificaties, zie onder) is een extra vraag in de Play-review, dus
voeg alleen toe wat een nieuwe functie daadwerkelijk gebruikt.

## Wat er NIET in zit

- **Duw-notificaties (push).** De backend heeft een endpoint dat push-
  tokens opslaat (`POST /api/v1/mobile/push-token`), maar er is geen
  verzendpijplijn (Expo Push/FCM/APNs) die er iets mee doet. De app
  registreert daarom bewust geen token (`registerPushToken()` in
  `app/lib/api.ts` bestaat, wordt nergens aangeroepen). Dit toevoegen
  vraagt later om: het pakket `expo-notifications`, een development
  build (Expo Go ondersteunt remote push niet meer sinds SDK 53), en
  FCM/Expo push-credentials — geen van die stappen is nu gezet.
- **iOS/App Store.** Dit document gaat alleen over Android/Play Store.
  Een iOS-release loopt via hetzelfde `eas build --platform ios` +
  `eas submit --platform ios`, maar vraagt een apart Apple Developer-
  account (€99/jaar) — zie `app/README-APP.md`, sectie "EAS builds".

## Verificatie vóór elke release (draai dit eerst)

```sh
cd app
npm ci
npx tsc --noEmit
npm test -- --ci
npx expo export --platform web
```

Deze vier commando's zijn non-interactief en horen groen te zijn vóór
elke `eas build --profile production`. Ze draaien niet in EAS zelf mee —
EAS bouwt alleen, het test niet.

# Google Play Store — listing & formulieren

Alles wat de eigenaar in de Google Play Console moet plakken of aanvinken
voor de eerste release van de GSP Recruitment kandidaten-app
(`nl.gsprecruitment.app`, versie 1.0.0). Bouw/upload-stappen staan in
`docs/APP-RELEASE.md` — dit document is uitsluitend de Play Console-kant:
store listing, data safety, content rating, app access en assets.

Kant-en-klare afbeeldingen staan in `store/play/` (zie sectie 6).

---

## 1. Store listing

### App-naam (max 30 tekens)

| Taal | Tekst | Tekens |
|---|---|---|
| NL | `GSP Recruitment – Vacatures` | 27 |
| EN | `GSP Recruitment – Vacancies` | 27 |

### Korte beschrijving (max 80 tekens)

| Taal | Tekst | Tekens |
|---|---|---|
| NL | `Vacatures embedded software, mechatronica en OT-cybersecurity in Brainport.` | 75 |
| EN | `Embedded software, mechatronics and OT cybersecurity jobs in Brainport, NL.` | 75 |

### Volledige beschrijving (max 4000 tekens)

**Nederlands (1893 tekens):**

```
GSP Recruitment bemiddelt in embedded software, mechatronica en besturingssoftware, en OT-cybersecurity in de Brainport-regio (Eindhoven en omgeving). Met deze app volg je het hele traject vanaf je telefoon.

Wat de app doet:

VACATURES BEKIJKEN
Blader door openstaande vacatures in embedded software (C/C++), mechatronica en OT-cybersecurity. Filter op discipline en senioriteit en bekijk per vacature het salarisbereik, standplaats en het gevraagde profiel.

DIRECT SOLLICITEREN
Upload je cv en solliciteer met één tik. Je cv blijft in je profiel staan, dus je hoeft het maar één keer te uploaden.

JE MATCHES EN SOLLICITATIES VOLGEN
Zie welke vacatures bij jouw profiel passen en volg de status van elke sollicitatie: van binnengekomen tot gesprek en aanbod.

SKILLSQUIZ MET SALARISINDICATIE
Doe de korte skillsquiz over embedded software, security en cloud/devops en krijg een niveau-indicatie plus, als je bent ingelogd, een salarisindicatie op basis van functie, senioriteit en regio.

JE PROFIEL EN GEGEVENS
Vul je profiel aan met werkervaring, vaardigheden en salarisverwachting. Bekijk, exporteer of verwijder je gegevens vanuit het profielscherm — dat kan altijd, zonder tussenkomst.

Voor wie
Voor software-, embedded- en mechatronica-engineers en OT-cybersecurityspecialisten die op zoek zijn naar een volgende stap in de Brainport-regio.

Gegevens en privacy
GSP Recruitment is een gezichtsloos, onafhankelijk wervingsbureau: geen naam- en faamcultuur, wel een directe lijn met wie de vacature daadwerkelijk beheert. Verbindingen met de server lopen via HTTPS. Je bepaalt zelf welke gegevens je invult en kunt je account op elk moment inzien, exporteren of verwijderen. Het volledige privacybeleid staat op gsprecruitment.nl/privacy.

De app is Nederlands/Engels omschakelbaar en werkt op elk moment als vertrekpunt naar een gesprek met GSP Recruitment over een concrete vacature.
```

**English (1796 characters):**

```
GSP Recruitment places embedded software, mechatronics and control software, and OT cybersecurity engineers in the Brainport region (Eindhoven, the Netherlands). This app lets you follow the whole process from your phone.

What the app does:

BROWSE VACANCIES
Browse open vacancies in embedded software (C/C++), mechatronics and OT cybersecurity. Filter by discipline and seniority, and see the salary range, location and required profile for each role.

APPLY DIRECTLY
Upload your CV and apply with one tap. Your CV stays attached to your profile, so you only upload it once.

TRACK YOUR MATCHES AND APPLICATIONS
See which vacancies fit your profile and follow the status of each application, from received through interview to offer.

SKILLS QUIZ WITH SALARY INDICATION
Take the short skills quiz on embedded software, security and cloud/devops and get a level indication, plus — when signed in — a salary indication based on role, seniority and region.

YOUR PROFILE AND DATA
Fill in your profile with work experience, skills and salary expectations. View, export or delete your data from the profile screen at any time, with no need to contact anyone first.

Who it's for
Software, embedded and mechatronics engineers, and OT cybersecurity specialists looking for their next step in the Brainport region.

Data and privacy
GSP Recruitment is a faceless, independent recruitment agency: no personal-brand culture, but a direct line to whoever actually manages the vacancy. Connections to the server use HTTPS. You decide what data you enter, and you can view, export or delete your account at any time. The full privacy policy is at gsprecruitment.nl/privacy.

The app switches between Dutch and English and is a starting point for a conversation with GSP Recruitment about a specific vacancy.
```

### Categorie, tags, contactgegevens (eigenaar vult in)

- **Categorie:** Business (er is geen aparte "Recruitment"-categorie in Play;
  "Business" is de gangbare keuze voor recruitment-/vacature-apps. Alternatief:
  "Lifestyle" — Business is de betere match).
- **Tags** (Play staat een beperkt aantal toe, kies uit): vacatures, banen,
  recruitment, embedded software, techniek, IT.
- **E-mail (verplicht, publiek zichtbaar):** `spganesh@gsprecruitment.nl`
- **Website:** `https://gsprecruitment.nl`
- **Privacybeleid-URL (verplicht):** `https://gsprecruitment.nl/privacy`
  (de canonical tag in `website/privacy.html` zelf wijst naar dit pad zonder
  `.html`-extensie — vermoedelijk een server-side rewrite. Controleer deze
  URL in de browser vóórdat je hem in Play plakt; als `.html` toch nodig
  blijkt, gebruik dan `https://gsprecruitment.nl/privacy.html`).
- **Telefoonnummer:** niet verplicht in Play zelf, maar laat leeg tenzij de
  eigenaar een nummer wil publiceren — geen nummer staat vast in de codebase.

---

## 2. Data safety-formulier

Afgeleid uit de code, niet uit aannames. Bronnen: `app/lib/api.ts`,
`app/lib/auth.ts` (niet gelezen, maar `expo-secure-store` wordt gebruikt
voor tokens — zie `app.json` plugin-lijst), de schermen in `app/app/`, en
`app/package.json` (geen analytics/crash-SDK aanwezig — geen Sentry,
Firebase, Crashlytics, Amplitude of Mixpanel in de dependencies).

### Verzamelt de app gegevens? **Ja**

### Wordt alle data versleuteld tijdens verzending? **Ja**

Elke aanroep gaat naar `https://api.gsprecruitment.nl/api` (`app/lib/api.ts`
regel 34-36, `buildUrl()`) — een `https://`-basis-URL, dus TLS voor al het
verkeer. Geen enkele endpoint in `api.ts` gebruikt `http://`.

### Kan de gebruiker om verwijdering van gegevens vragen? **Ja**

`gdprDeleteAccount()` roept `DELETE /v1/gdpr/account` aan (`app/lib/api.ts`
regel 407-409), aangeroepen vanuit het profielscherm
(`app/app/(tabs)/profile.tsx` regel 187-219: dubbele bevestiging, daarna
`deleteMutation.mutateAsync()` en uitloggen). Dit is een selfservice-functie
in de app zelf, geen "vraag het per e-mail"-proces — vink in Play aan: **"Users
can request that data be deleted"** met als methode "in-app".

### Per gegevenscategorie

Play vraagt per categorie: verzameld? gedeeld? verplicht of optioneel?
waarvoor gebruikt?

| Categorie | Verzameld | Gedeeld met derden | Verplicht/optioneel | Waarvoor | Bron |
|---|---|---|---|---|---|
| **Naam** | Ja | Nee | Verplicht (registratie) | Accountfunctionaliteit | `register(email, password, full_name)` — `api.ts` regel 285-290; `CandidateProfile.full_name` — regel 209 |
| **E-mailadres** | Ja | Nee | Verplicht (registratie/login) | Accountfunctionaliteit, inloggen | `login`/`register` — `api.ts` regel 281-290 |
| **Telefoonnummer** | Ja | Nee | Optioneel (profielveld) | Accountfunctionaliteit | `CandidateProfile.phone`, `CandidateProfileUpdate` — regel 210, 234 |
| **Adres/locatie (tekstveld, geen GPS)** | Ja | Nee | Optioneel (profielveld) | Matching met vacatures | `CandidateProfile.location`, `willing_to_relocate` — regel 216-217. Dit is een door de gebruiker getypt tekstveld, **geen** precieze of grove GPS-locatie — de app vraagt geen locatie-permissie (zie `docs/APP-RELEASE.md` "Android-permissies": geen `android.permissions`-lijst) |
| **Wachtwoord/inloggegevens** | Ja | Nee | Verplicht | Accountfunctionaliteit | `login`/`register` body — regel 281-290; opslag lokaal via `expo-secure-store` (plugin in `app.json`) |
| **Bestanden die de gebruiker uploadt (cv)** | Ja | Nee (zie hieronder) | Optioneel, maar nodig om te solliciteren | App-functionaliteit (sollicitatie) | `uploadCv()` — `api.ts` regel 379-387, multipart naar `/v1/candidate/cv` |
| **Werk-/opleidingsgegevens (functietitel, werkgever, skills, opleiding, jaren ervaring)** | Ja | Nee | Optioneel (profielvelden) | Matching, app-functionaliteit | `CandidateProfile`/`CandidateProfileUpdate` — regel 205-250 |
| **Financiële info (salarisverwachting)** | Ja | Nee | Optioneel (profielveld) | App-functionaliteit | `salary_expectation_min/max` — regel 218-219 |
| **App-activiteit (sollicitaties, matches, quizantwoorden)** | Ja | Nee | Verplicht voor die functies | App-functionaliteit | `applyToJob`, `getCandidateMatches`, `submitQuiz` — regel 326-399 |
| **App-interacties/diagnostiek (crashlogs, analytics)** | **Nee** | — | — | — | Geen analytics- of crash-SDK in `app/package.json`; geen `Sentry`, `Firebase`, `Crashlytics`, `Amplitude`, `Mixpanel` |
| **Advertentie-ID** | **Nee** | — | — | — | Geen advertentie-SDK in de app |
| **Precieze/grove locatie (GPS)** | **Nee** | — | — | — | Geen locatie-permissie aangevraagd (zie hierboven) |

### Delen met derden

**Antwoord: Nee, de app deelt geen gebruikersgegevens met derde partijen.**
Elke aanroep in `api.ts` gaat naar één eigen backend
(`api.gsprecruitment.nl`, GSP Recruitment zelf). Er zit geen SDK van een
derde partij (advertenties, analytics, social login) in de dependencies die
data zou doorsturen.

Let op: dit gaat over wat de **app** doet. Het bedrijf GSP Recruitment deelt,
volgens `website/privacy.html` §5, cv/profielgegevens wél met potentiële
werkgevers (na expliciete toestemming per rol) en met een backoffice-partner
voor IND-sponsorschap — maar dat gebeurt niet via een SDK in de app, en de
Play Data Safety-vragenlijst gaat over technische dataflows in de app, niet
over het recruitmentproces erachter. Vul "Nee" in bij "gedeeld met derden"
in de technische zin die Play bedoelt (SDK's/dataverwerkers die buiten de
app zelf data ontvangen bij gebruik); de zakelijke datadeling met werkgevers
staat al correct beschreven in het privacybeleid waarnaar de listing linkt.

### Eigenaar moet dit bevestigen

- **Of alle bovenstaande profielvelden daadwerkelijk optioneel zijn in de
  UI** (bijv. of het registratiescherm `full_name`/`email`/`password` als
  hard verplicht afdwingt vóór submit — dit document leidt "verplicht" af
  uit wat de backend als request-body verwacht, niet uit elke
  formuliervalidatie op elk scherm).
- **Of de hostingpartij van de backend/database data buiten de EU
  verwerkt** (Play vraagt hier apart naar bij "Data verwerkt in het
  buitenland") — dit is niet uit de app-code af te leiden.
- **Of er in de toekomst een analytics- of crash-reporting-SDK wordt
  toegevoegd** — als dat gebeurt, moet dit data safety-formulier opnieuw
  worden ingevuld vóór de eerstvolgende release.

---

## 3. Content rating-vragenlijst (IARC, via Play Console)

Verwachte antwoorden op basis van wat de app daadwerkelijk doet (een
vacature-/carrière-app zonder games, chat, geweld of volwassen content):

| Vraag | Antwoord | Toelichting |
|---|---|---|
| Geweld | Nee | Geen geweld in de app |
| Seksuele content | Nee | — |
| Grof taalgebruik | Nee | — |
| Gecontroleerde stoffen (alcohol/drugs/tabak) | Nee | — |
| Gokken (echt of gesimuleerd) | Nee | — |
| Door gebruikers gegenereerde content die door anderen zichtbaar is | Nee | Geen social features, geen openbare profielen, geen chat tussen gebruikers |
| Gebruikersinteractie (chat, messaging) | Nee | Geen messaging-functie in de app; sollicitaties en matches zijn eenrichtingsverkeer tussen kandidaat en backend |
| Deelt de app de locatie van de gebruiker | Nee | Geen locatie-permissie, geen GPS-gebruik |
| Deelt de app persoonlijke gegevens met derden | Nee (technisch, zie sectie 2) | Zelfde toelichting als het data safety-formulier |

**Verwachte uitkomst:** laagste ratingcategorie in elk regionaal systeem
(bijv. PEGI 3 in Europa, Everyone in de VS) — een app zonder geweld,
volwassen content of social/gok-functionaliteit krijgt standaard de
laagste classificatie. De Play Console berekent de exacte rating pas na
het invullen van de vragenlijst; dit is de verwachting, geen garantie.

---

## 4. App access (reviewer moet kunnen inloggen)

De Play-reviewer moet een werkend account hebben om voorbij het
inlogscherm te komen. Zet **geen** wachtwoord of testaccount in dit
document of ergens anders in de repo — dat zijn kandidaatgegevens/geheimen.

Stappen voor de eigenaar:

1. Installeer de productie- of preview-build op een toestel (zie
   `docs/APP-RELEASE.md` stap 1 of 2), of gebruik de web-preview
   (`npx expo start` → `w`).
2. Ga naar het registratiescherm in de app en maak een nieuw account aan
   met een e-mailadres dat alleen voor deze reviewer bedoeld is (bijv.
   `playstore-reviewer@gsprecruitment.nl`, als dat adres bestaat of
   aangemaakt kan worden) en een wachtwoord dat voldoet aan de eisen (≥8
   tekens, hoofdletter, kleine letter, cijfer — zie
   `app/lib/validation.ts`).
3. Log een keer in met dat account om te bevestigen dat het werkt.
4. Ga in de Play Console naar **Beleid → App-content → App access** (of
   **App content → Toegang tot apps**, exacte pad kan per Console-versie
   verschillen).
5. Kies **"Niet alle functies zijn beschikbaar zonder speciale toegang"**
   (of gelijkwaardig) en vul het e-mailadres en wachtwoord van het
   testaccount in de daarvoor bestemde velden in — **niet** in een los
   document, alleen in dat Play Console-formulier zelf.
6. Voeg een korte instructie toe voor de reviewer, bijvoorbeeld: "Log in
   met de meegegeven gegevens op het inlogscherm. Na inloggen zijn
   Vacatures, Matches, Carrière (skillsquiz + salarisdata) en Profiel
   bereikbaar via de onderste tabbalk."
7. Bewaar het wachtwoord van dit testaccount in een eigen wachtwoordkluis,
   niet in deze repo.

---

## 5. Assets-checklist

| Asset | Verplicht formaat | Status |
|---|---|---|
| App-icoon (store listing) | 512×512 PNG, 32-bit, **geen** alfakanaal (geen transparantie) | **Klaar** — `store/play/icon-512.png` (zie sectie 6) |
| Feature graphic | 1024×500 PNG of JPG | **Klaar** — `store/play/feature-graphic-1024x500.png` (zie sectie 6) |
| Telefoon-schermafbeeldingen | Minimaal 2, tussen 320px en 3840px (lange zijde max 2× de korte zijde), PNG of JPG | **Ontbreekt** — wordt door een andere agent gegenereerd, niet in deze levering |
| In-app adaptive icon (Android, los van de store-listing-asset hierboven) | Al aanwezig in de app zelf | Klaar — `app/assets/android-icon-foreground.png`, `android-icon-background.png`, `android-icon-monochrome.png` (gebruikt via `app.json` → `android.adaptiveIcon`) |
| Tablet-/Chromebook-schermafbeeldingen | Optioneel, niet verplicht voor launch | Niet gemaakt — optioneel |
| Promo-video (YouTube-link) | Optioneel | Niet gemaakt — optioneel |

De app-icoon en feature graphic in `store/play/` zijn samengesteld uit
bestaand merkmateriaal (`website/icon-512.png`, `website/logo.png`) — geen
nieuwe illustraties. Zie sectie 6 voor herkomst en afmetingen.

---

## 6. `store/play/` — gegenereerde assets

| Bestand | Afmeting | Bron | Opmerking |
|---|---|---|---|
| `icon-512.png` | 512×512, RGB (geen alfakanaal) | `website/icon-512.png`, gecomposit op een `#0A1628`-navy achtergrond en afgevlakt naar RGB | Play weigert transparantie in het store-icoon; het brongoud vult het canvas al volledig, dus de navy is niet zichtbaar maar het bestand voldoet aan de eis van geen alfakanaal |
| `feature-graphic-1024x500.png` | 1024×500, RGB | `#0A1628`-navy achtergrond, `website/logo.png` gecentreerd (geschaald naar 640px breed), tagline "Vacatures in embedded software en mechatronica" eronder in lichtgrijsblauw | Samengesteld met Pillow uit bestaande merkbestanden, geen nieuwe illustraties. Visueel gecontroleerd — logo staat gecentreerd, tekst is leesbaar tegen de navy achtergrond |

Geen schermafbeeldingen in deze levering — die worden apart gegenereerd.

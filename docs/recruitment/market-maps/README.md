# Market maps — methode

Status: eerste versie, 2026-09-23. Bijlage bij GitHub issue #115.

## Doel

Vier marktkaarten — embedded software, mechatronica en besturingssoftware,
OT-cybersecurity, test en verificatie — zodat recruiters starten vanaf een
gevulde, gesourcete lijst in plaats van een leeg vel. Elke kaart somt de
bedrijven op die in en rond Brainport/Eindhoven (en waar relevant breder
Nederland) in die discipline werven, plus een eerste long-list per top-
vacature: bedrijven en publieke community's waar kandidaten voor die rol
te vinden zijn. Een long-list bevat geen namen van personen.

## Methode

1. **Vacatures.** De "top vacatures" per discipline komen uit
   `talent-os/backend/data/pool_vacancies.json` (27 actieve poolvacatures,
   geraadpleegd 2026-09-23). Er staat geen expliciete rangorde in dat
   bestand; bij gebrek daaraan zijn per discipline de twee meest senior en
   meest gespecialiseerde rollen gekozen (architect/lead-niveau of een
   nichecombinatie), als redelijke eerste aanname voor "moeilijkst te
   vullen". Dit is een keuze van de opsteller, geen gemeten rangorde — de
   chief kan dit bij een volgende iteratie herzien met echte prioriteiten.
2. **Bedrijven.** Gevonden via publieke zoekopdrachten (bedrijfssites,
   Brainport Eindhoven-portaal, Brainport Industries-ledenlijst, DSPE,
   vakpers) en per bedrijf geverifieerd op de eigen publieke pagina (about-
   /carrières-/locatiepagina). Alleen publiek toegankelijke pagina's; geen
   pagina die inloggen vereist, geen LinkedIn-profielpagina's, geen
   individuen genoemd.
3. **Long-lists.** Voor de twee hoogst geprioriteerde vacatures per
   discipline: bedrijven die voor die rol een plausibele bron of
   concurrent zijn, plus publieke community's (meetups, conferenties,
   open-sourceprojecten, universitaire opleidingen) waar kandidaten met dat
   profiel te vinden zijn — dezelfde bronvermelding per regel.
4. **Bronvermelding.** Elk feit (wat een bedrijf bouwt, waar het zit, welke
   discipline) draagt de publieke bron-URL en de datum van raadpleging
   (2026-09-23 voor deze versie). Geen cijfer (headcount, omzet, aantal
   vacatures) dat niet met een publieke bron is te onderbouwen is
   opgenomen; ontbrekende cijfers zijn weggelaten in plaats van geschat.
5. **Niet-gedekt.** Bedrijven of community's die in de zoekopdrachten
   naar boven kwamen maar waarvan de publieke bron niet binnen deze ronde
   te verifiëren was (bijv. geen bereikbare eigen domeinpagina, alleen
   marktplaats-/directory-vermeldingen, of een adres dat niet uit een
   eigen bron te bevestigen was) zijn weggelaten in plaats van met een
   onzekere bron opgenomen. Zie het rapport bij issue #115 voor de lijst
   per discipline.

## Herhaalbaarheid

De zoekopdrachten waarmee deze versie is opgebouwd stonden in het
werkdocument bij issue #115: bedrijfsnaam + "Eindhoven"/"Brainport" +
discipline-trefwoord (bijv. "mechatronica bedrijven Brainport Eindhoven"),
gevolgd door een verificatiebezoek aan de eigen bedrijfspagina. Een
recruiter kan dezelfde zoekopdrachten herhalen om de kaart te verversen.

## Onderhoud

Deze kaarten zijn een momentopname op de datum in elk bestand. Volgens de
kwaliteitsnorm voor het "Market map"-deliverable (`STANDARDS.md`,
`madhatter1312sudo/vps-backup`) geldt een maandelijkse ververscadans: een
kaart die ouder is dan die cadans mag niet als actueel worden
gepresenteerd. Ververs door dezelfde zoekopdrachten opnieuw te lopen en
de datum "laatst gecontroleerd" per bedrijf bij te werken.

## Bestanden

- [`embedded-software.md`](./embedded-software.md)
- [`mechatronica-besturingssoftware.md`](./mechatronica-besturingssoftware.md)
- [`ot-cybersecurity.md`](./ot-cybersecurity.md)
- [`test-en-verificatie.md`](./test-en-verificatie.md)

## English summary

Method for the four market-map files in this folder: companies are drawn
from public search (company sites, the Brainport Eindhoven portal,
Brainport Industries' member list, DSPE, trade press) and verified on
their own public page. The two highest-priority vacancies per discipline
were picked from the 27 live pool vacancies in
`talent-os/backend/data/pool_vacancies.json` (no ranking field exists
there, so the most senior/specialised roles were used as a first,
explicitly-labelled assumption). Every fact carries its source URL and
the check date (2026-09-23). No figure without a public source is
included. Companies or communities found but not verifiable against
their own public page in this round were left out rather than listed
with a weak source. Refresh cadence: monthly, per `STANDARDS.md`'s
"Market map" row.

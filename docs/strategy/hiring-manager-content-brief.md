# Content brief: 12 hiring-manager blogonderwerpen

Voor de Hermes-editor (blog routine). Laatst gecontroleerd: 2026-09-23.
Doelgroep: hiring managers en teamleads bij machinebouwers, semicon-toeleveranciers
en engineeringdienstverleners in Brainport, die embedded software-, mechatronica-,
OT-security- of testrollen invullen. Register: NRC/FD, plain, geen hype, geen
verzonnen cijfers, elk cijfer in een post moet een bron hebben of wegblijven.

---

## 1. Wat kost een embedded C++-engineer in Brainport?

- **Search intent:** transactioneel/informatief. Hiring manager of HR wil een
  realistisch salarisbudget opstellen voor een vacature, vaak vóór het
  vrijgeven van een functieprofiel.
- **Bronnen te gebruiken:** `salary-guide-content.md` (deze levering), CAO
  Metalektro-context, eigen `pool_vacancies.json`-bandbreedtes.
- **Mag niet claimen:** geen precies "marktconform" bedrag zonder bronvermelding
  per cijfer; geen suggestie dat GSP's eigen bandbreedtes een landelijke
  standaard zijn.

## 2. Hoe schrijf je een OT-securityprofiel dat kandidaten niet afschrikt

- **Search intent:** informatief, probleemgericht. Hiring managers merken dat
  OT-securityvacatures moeilijk vervuld raken en zoeken naar wat mis is aan
  hun eigen vacaturetekst.
- **Bronnen te gebruiken:** `docs/recruitment/market-maps/ot-cybersecurity.md`
  (regionale schaarste), NCSC-NL en Cyber Weerbaarheidscentrum Brainport als
  publieke context over de discipline.
- **Mag niet claimen:** geen suggestie dat één type functietekst gegarandeerd
  meer reacties oplevert zonder dat GSP dat zelf heeft gemeten.

## 3. IEC 62443-competentie herkennen op een cv: waar let je op

- **Search intent:** informatief, vaardigheidsgericht. Hiring manager zonder
  security-achtergrond wil zelfstandig cv's kunnen beoordelen.
- **Bronnen te gebruiken:** IEC/ISA 62443-normdocumentatie (publieke
  samenvattingen van ISA of vergelijkbare certificerende instanties), eigen
  vacatureteksten (`ot-security-engineer-iec-62443-senior` e.a.) als
  praktijkvoorbeeld van gevraagde competenties.
- **Mag niet claimen:** geen bewering dat een certificaat alleen voldoende
  bewijs van competentie is; het gaat om herkenbare praktijkervaring.

## 4. RTOS versus embedded Linux: wat vraag je in een vacaturetekst

- **Search intent:** informatief, technisch. Hiring manager twijfelt tussen
  een RTOS-profiel en een embedded Linux/Yocto-profiel voor een nieuw project
  en wil weten wat dat betekent voor het gevraagde profiel.
- **Bronnen te gebruiken:** `docs/recruitment/market-maps/embedded-software.md`,
  eigen vacatureteksten `rtos-software-engineer-*` en
  `embedded-linux-yocto-engineer-*` als voorbeeldmateriaal.
- **Mag niet claimen:** geen advies dat één van de twee "beter" is in het
  algemeen; het is een architectuurkeuze die van het project afhangt.

## 5. Waarom mechatronica-engineers moeilijk te vinden zijn in Brainport

- **Search intent:** informatief/marktcontext. Hiring manager wil begrijpen
  waarom een mechatronicavacature lang openstaat, voor intern verwachtingsmanagement.
- **Bronnen te gebruiken:** UWV-Spanningsindicator (technische beroepen krap,
  Q1 2026), `docs/recruitment/market-maps/mechatronica-besturingssoftware.md`
  (dichtheid van vraag in de regio), DSPE als beroepsvereniging-context.
- **Mag niet claimen:** geen exact tekortcijfer voor mechatronica specifiek
  als dat niet apart gepubliceerd is; alleen het bredere technische-beroepen-cijfer
  citeren met bron, niet doorvertalen naar een eigen schatting.

## 6. Vast versus detachering: wat past bij welk type project

- **Search intent:** informatief, besluitvormingsgericht. Hiring manager of
  inkoper twijfelt over contractvorm voor een tijdelijk project versus een
  structurele uitbreiding van het team.
- **Bronnen te gebruiken:** eigen vacaturedata (`employment_type`-veld in
  `pool_vacancies.json`: vast, detachering, interim, als praktijkvoorbeelden
  zonder namen), CAO Metalektro-context voor vast dienstverband.
- **Mag niet claimen:** geen suggestie dat één contractvorm generiek goedkoper
  is; dat hangt af van projectduur en risico, niet van een vast getal.

## 7. Wat een testautomatiseringsengineer voor hardware-in-the-loop echt doet

- **Search intent:** informatief, rolverduidelijking. Hiring manager in
  machinebouw wil een HIL-testautomatiseringsrol goed afbakenen tegenover een
  reguliere softwaretester-rol.
- **Bronnen te gebruiken:** eigen vacaturetekst `hil-testautomatiseringsengineer-senior`,
  `docs/recruitment/market-maps/test-en-verificatie.md` (Thermo Fisher NanoPort
  als voorbeeld van praktijkomgeving).
- **Mag niet claimen:** geen namen van specifieke medewerkers of interne
  projecten van opdrachtgevers; alleen generieke functie-inhoud.

## 8. Sponsorschap van kennismigranten: wat GSP wel en niet zelf regelt

- **Search intent:** informatief, compliance-gericht. Hiring manager overweegt
  een internationale kandidaat en wil weten hoe sponsorschap in zijn werk gaat.
- **Bronnen te gebruiken:** IND.nl (officiële voorwaarden erkend referentschap),
  eigen procesbeschrijving (GSP is geen IND-erkend referent, sponsorschap loopt
  via een backoffice-partner, uit CLAUDE.md, huisregel).
- **Mag niet claimen:** geen suggestie dat GSP zelf IND-erkend referent is;
  dit moet letterlijk en expliciet gecorrigeerd worden in de post.

## 9. Hoe lang staat een embedded softwarevacature gemiddeld open in Brainport

- **Search intent:** informatief, benchmarkgericht. Hiring manager wil weten
  of zijn eigen doorlooptijd normaal is.
- **Bronnen te gebruiken:** UWV Regio in Beeld-rapporten (als een concreet,
  vandaag te verifiëren doorlooptijdcijfer voor de regio gevonden wordt),
  anders eigen ervaring uit de vacaturepool zonder cijfer te verzinnen.
- **Mag niet claimen:** als er geen publiek, vandaag geverifieerd doorlooptijdcijfer
  voor Brainport specifiek bestaat, mag de post geen eigen schatting als feit
  presenteren, dan wordt dit onderwerp herschreven naar "wat vertraagt een
  embedded softwarevacature" (kwalitatief, geen cijfer nodig).

## 10. MISRA-C en functionele veiligheid: wanneer vraag je het, wanneer niet

- **Search intent:** informatief, technisch-strategisch. Hiring manager
  overweegt of een vacature MISRA-C-ervaring of IEC 61508/ISO 13849-kennis
  moet vereisen, en wil voorkomen dat de vacature onnodig wordt versmald.
- **Bronnen te gebruiken:** eigen vacatureteksten met MISRA-C/IEC 61508 als
  nice-to-have (`rtos-software-engineer-senior`,
  `embedded-software-architect-senior`), publieke uitleg van MISRA
  (misra.org.uk) en IEC 61508 (iec.ch) over toepassingsgebied.
- **Mag niet claimen:** geen bewering dat MISRA-C wettelijk verplicht is
  buiten sectoren waar dat daadwerkelijk zo is; het is een keuze, geen
  automatische eis.

## 11. Wat DevOps/CI voor embedded teams anders maakt dan voor webteams

- **Search intent:** informatief, technisch. Hiring manager of tech lead wil
  een DevOps/CI-rol voor embedded projecten goed profileren tegenover een
  generieke DevOps-vacature, om de juiste kandidaten aan te trekken.
- **Bronnen te gebruiken:** eigen vacaturetekst `devops-ci-engineer-embedded-medior`,
  publieke documentatie van embedded toolchains/cross-compilatie (bijvoorbeeld
  Yocto Project-documentatie) als technische achtergrond.
- **Mag niet claimen:** geen suggestie dat embedded CI/CD principieel
  "moeilijker" is dan webCI/CD in het algemeen; het verschil zit in de
  toolchain en hardwareafhankelijkheid, niet in een waardeoordeel.

## 12. Semicon-toeleverancier of machinebouwer: wat dat betekent voor het gevraagde profiel

- **Search intent:** informatief, marktcontext. Hiring manager bij een nieuwe
  opdrachtgever in de regio wil begrijpen hoe zijn positionering (semicon
  versus bredere machinebouw) het gevraagde kandidaatprofiel beïnvloedt.
- **Bronnen te gebruiken:** alle vier `docs/recruitment/market-maps/*.md`-bestanden
  (bedrijvenlijsten per marktsegment), Brainport Industries-ledenlijst als
  publieke bron voor het onderscheid.
- **Mag niet claimen:** geen suggestie dat één marktsegment (semicon versus
  machinebouw) generiek beter betaalt of makkelijker te vervullen is zonder
  brongegeven per segment; dat verschilt per functie en wordt in de gids
  apart onderbouwd, niet als vuistregel gepresenteerd.

---

## Algemene aanwijzingen voor de editor

- Elke post: Nederlands eerst, Engelse versie volgt dezelfde brongegevens.
- Geen founder-naam, "wij" niet "ik" (faceless brand).
- Elk getal in de tekst krijgt een voetnoot of inline bronvermelding met URL
  en controle­datum; geen getal zonder bron.
- Geen kunstmatige schaarste-taal ("nu solliciteren, want het kan zo weg
  zijn"), dat is in strijd met de eerlijkheidsregel.
- Sluit elke post af met één duidelijke volgende stap: voor kandidaten een
  link naar openstaande vacatures, voor hiring managers een link naar een
  intakegesprek.

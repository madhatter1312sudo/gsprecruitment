# Interviewvragenbank: PLC/motion engineer (junior)

Discipline: Mechatronica en besturingssoftware
Slug/job-id: `plc-motion-engineer-junior`
Datum opgesteld: 23-09-2026

## Technische briefing voor de interviewer

Deze juniorrol combineert PLC-programmeren met motion control bij machinebouwers in de Brainport-regio, met expliciete inbedrijfstelling op locatie onder begeleiding. De briefing richt zich op basisbegrip van PLC-logica en motion control, en op realistische verwachtingen over het werk op locatie.

## Vijf indringende vragen met modelantwoord

### 1. Wat is het verschil tussen een digitale in-/uitgang en een analoge in-/uitgang op een PLC, en wanneer gebruik je welke?

**Modelantwoord (seniorniveau):** Een goed seniorniveau-antwoord legt uit dat digitale I/O aan/uit-signalen verwerkt (bijvoorbeeld een eindschakelaar) en analoge I/O een continue waarde (bijvoorbeeld een snelheids- of positiereferentie), en geeft een concreet voorbeeld van elk in een machinecontext.

### 2. Leg in eigen woorden uit wat een servo-as doet die je vanuit een PLC aanstuurt.

**Modelantwoord (seniorniveau):** Een sterk antwoord beschrijft dat de PLC een positie- of snelheidsreferentie naar de servoversterker stuurt, die op zijn beurt de motor aandrijft en via een encoder terugkoppelt of de gewenste positie is bereikt, een basaal maar correct beeld van de gesloten regellus, geen losse termen zonder samenhang.

### 3. Je test een machine op locatie en een beweging stopt onverwacht. Wat doe je als eerste?

**Modelantwoord (seniorniveau):** Een goed antwoord begint met veiligheid (bevestigen dat de machine veilig gestopt is, geen poging tot herstart zonder dat te controleren), gevolgd door het raadplegen van foutmeldingen of logging op de PLC, en pas daarna het escaleren naar een ervaren collega als de oorzaak niet duidelijk is.

### 4. Wat is EtherCAT, en waarom zou een machinebouwer dit gebruiken in plaats van een eenvoudiger protocol?

**Modelantwoord (seniorniveau):** Een sterk antwoord noemt dat EtherCAT een real-time industrieel ethernetprotocol is met lage latency en deterministische timing, geschikt voor het synchroon aansturen van meerdere servo-assen, in tegenstelling tot standaard ethernet dat geen timinggaranties biedt.

### 5. Hoe zorg je dat je PLC-code voor iemand anders leesbaar is, ook als je zelf niet meer op het project zit?

**Modelantwoord (seniorniveau):** Een goed antwoord noemt duidelijke naamgeving van variabelen en blokken, commentaar bij niet-triviale logica, en het volgen van een teamconventie in plaats van een eigen stijl; zelfs op juniorniveau een teken van professionaliteit.

## Twee risico's om op te testen

- Kandidaten die alleen theoretische PLC-kennis uit een cursus hebben en geen enkel praktijkproject kunnen noemen.
- Kandidaten die de reis- en locatiewerk-verwachting onderschatten; toets dit expliciet, niet impliciet.

---

## English summary

**Interview question bank: PLC/motion engineer (junior)**, slug `plc-motion-engineer-junior`.

Briefing: This junior role combines PLC programming with motion control at machine builders in the Brainport region, with explicit on-site commissioning under supervision. The briefing focuses on basic understanding of PLC logic and motion control, and on realistic expectations about on-site work.

Five probing questions with senior-level model answers are listed above, covering control-design trade-offs,
diagnosis on physical hardware, mechanical/control interaction, robustness over the machine's lifetime, and (for the
senior variant) mentoring and honest handling of unspecified safety requirements.

Risks to test:
- Candidates who only have theoretical PLC knowledge from a course and cannot name a single practical project.
- Candidates who underestimate the travel and on-site work expectation; test this explicitly, not implicitly.

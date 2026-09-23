# Interviewvragenbank — PLC/motion engineer (medior)

Discipline: Mechatronica en besturingssoftware
Slug/job-id: `plc-motion-engineer-medior`
Datum opgesteld: 23-09-2026

## Technische briefing voor de interviewer

Deze mediorrol combineert zelfstandig PLC-programmeren met motion control en inbedrijfstelling op locatie bij machinebouwers in de Brainport-regio. De briefing richt zich op zelfstandige probleemoplossing, protocolbegrip en de omgang met veiligheidsgerelateerde besturing als die aan de orde is.

## Vijf indringende vragen met modelantwoord

### 1. Een servo-as trilt bij lage snelheid maar niet bij hoge snelheid. Waar zoek je eerst?

**Modelantwoord (seniorniveau):** Een senior antwoord noemt stick-slip-wrijving of een te lage regelversterking bij lage snelheid als eerste hypothese, en beschrijft het testen met een stapresponsie bij lage snelheid om dit te bevestigen, in plaats van willekeurig parameters aan te passen.

### 2. Wat is het verschil tussen EtherCAT en Profinet, en wanneer zou je voor het een of het ander kiezen?

**Modelantwoord (seniorniveau):** Een sterk antwoord noemt dat EtherCAT doorgaans lagere cyclustijden en fijnere synchronisatie tussen assen biedt, terwijl Profinet breder gangbaar is in algemene procesautomatisering; de keuze hangt af van de precisie-eisen van de motion-toepassing en het bestaande ecosysteem bij de klant.

### 3. Hoe ga je te werk als een noodstopcircuit niet meer voldoet aan de vereiste Performance Level na een wijziging in de besturing?

**Modelantwoord (seniorniveau):** Een goed antwoord erkent dat een wijziging aan een veiligheidsfunctie een herbeoordeling volgens ISO 13849 vraagt, niet alleen een functionele test, en dat dit wordt teruggekoppeld aan de verantwoordelijke voor de veiligheidsanalyse in plaats van zelfstandig te worden 'opgelost' in de code.

### 4. Hoe pak je het inbedrijfstellen van een nieuwe machine op locatie aan als de documentatie van het ontwerp onvolledig is?

**Modelantwoord (seniorniveau):** Een sterk antwoord beschrijft het systematisch doorlopen van functies op basis van wat wél bekend is, het vastleggen van aannames en het actief navragen bij de ontwerpende collega's, in plaats van te gokken en pas bij een storing de documentatie te missen.

### 5. Wanneer kies je voor een gedistribueerde I/O-opstelling in plaats van bekabeling naar een centrale PLC?

**Modelantwoord (seniorniveau):** Een goed antwoord noemt bekabelingskosten en -complexiteit bij grote of verspreide machines, onderhoudbaarheid en de mogelijkheid tot modulaire uitbreiding als afwegingscriteria, met een concreet voorbeeld uit eigen ervaring.

## Twee risico's om op te testen

- Iemand die motion control alleen kent van geconfigureerde bibliotheekblokken en nooit zelf een as heeft afgesteld — vraag door op eigen afstelervaring.
- Iemand die veiligheidsgerelateerde besturing als 'gewone' logica behandelt — toets of de kandidaat het verschil in eisen herkent, ook zonder certificering te claimen.

---

## English summary

**Interview question bank — PLC/motion engineer (medior)**, slug `plc-motion-engineer-medior`.

Briefing: Deze mediorrol combineert zelfstandig PLC-programmeren met motion control en inbedrijfstelling op locatie bij machinebouwers in de Brainport-regio. De briefing richt zich op zelfstandige probleemoplossing, protocolbegrip en de omgang met veiligheidsgerelateerde besturing als die aan de orde is.

Five probing questions with senior-level model answers are listed above, covering control-design trade-offs,
diagnosis on physical hardware, mechanical/control interaction, robustness over the machine's lifetime, and (for the
senior variant) mentoring and honest handling of unspecified safety requirements.

Risks to test:
- Iemand die motion control alleen kent van geconfigureerde bibliotheekblokken en nooit zelf een as heeft afgesteld — vraag door op eigen afstelervaring.
- Iemand die veiligheidsgerelateerde besturing als 'gewone' logica behandelt — toets of de kandidaat het verschil in eisen herkent, ook zonder certificering te claimen.

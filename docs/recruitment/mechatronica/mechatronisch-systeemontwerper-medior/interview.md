# Interviewvragenbank — Mechatronisch systeemontwerper (medior)

Discipline: Mechatronica en besturingssoftware
Slug/job-id: `mechatronisch-systeemontwerper-medior`
Datum opgesteld: 23-09-2026

## Technische briefing voor de interviewer

De rol ontwerpt mechatronische deelsystemen waarin mechanica, elektronica en software samenkomen, bij machinebouwers en semicon-toeleveranciers. De briefing richt zich op systeemdenken over disciplines heen en op het vermogen om prototypes te bouwen, testen en de resultaten te vertalen naar ontwerpaanpassingen.

## Vijf indringende vragen met modelantwoord

### 1. Hoe kies je tussen een stappenmotor en een servomotor voor een positioneertaak?

**Modelantwoord (seniorniveau):** Een senior antwoord weegt vereiste nauwkeurigheid, dynamiek (versnelling/snelheid), kostprijs, en de noodzaak van terugkoppeling (encoder) af. Stappenmotoren zijn goedkoper en eenvoudiger maar kunnen stappen verliezen onder belasting zonder terugkoppeling; servomotoren zijn duurder maar bieden gesloten-lusnauwkeurigheid. De kandidaat noemt een concreet afwegingscriterium, geen voorkeur zonder onderbouwing.

### 2. Een prototype presteert in het lab goed maar faalt in het veld. Hoe ga je te werk om de oorzaak te vinden?

**Modelantwoord (seniorniveau):** Een sterk antwoord begint met het identificeren van omgevingsverschillen (temperatuur, trillingen, vervuiling, voeding) tussen lab en veld, gevolgd door gerichte metingen op de plek waar het verschil het grootst is, in plaats van het hele ontwerp te herzien op basis van aannames.

### 3. Hoe bepaal je welke sensor-resolutie nodig is voor een positioneertaak?

**Modelantwoord (seniorniveau):** Een senior antwoord redeneert terug van de systeemeis (bijvoorbeeld eindnauwkeurigheid) naar de benodigde resolutie, met marge voor ruis en kwantisatiefouten, en houdt rekening met de resolutie die na versterking of overbrenging effectief overblijft.

### 4. Wanneer zou je kiezen voor een gecentraliseerde regeleenheid versus gedistribueerde intelligentie dicht bij de sensoren/actuatoren?

**Modelantwoord (seniorniveau):** Een sterk antwoord noemt bekabelingscomplexiteit, latency-eisen, kosten per node en onderhoudbaarheid als afwegingscriteria, en illustreert dit met een eigen ontwerpkeuze in plaats van een algemene stelling.

### 5. Hoe leg je een mechanische beperking (bijvoorbeeld speling) uit aan een software-collega die het effect daarvan niet direct ziet?

**Modelantwoord (seniorniveau):** Een goed antwoord vertaalt de mechanische beperking naar het effect op softwaregedrag — bijvoorbeeld een dode zone in de regeling of een noodzaak tot compensatie in de aansturing — in plaats van alleen mechanische terminologie te herhalen.

## Twee risico's om op te testen

- Iemand die alleen binnen één discipline heeft gewerkt en 'systeemontwerp' op het CV heeft staan zonder concrete interfaces te kunnen noemen.
- Iemand die prototypes alleen laat testen door anderen — vraag door op wie de metingen deed en interpreteerde.

---

## English summary

**Interview question bank — Mechatronisch systeemontwerper (medior)**, slug `mechatronisch-systeemontwerper-medior`.

Briefing: De rol ontwerpt mechatronische deelsystemen waarin mechanica, elektronica en software samenkomen, bij machinebouwers en semicon-toeleveranciers. De briefing richt zich op systeemdenken over disciplines heen en op het vermogen om prototypes te bouwen, testen en de resultaten te vertalen naar ontwerpaanpassingen.

Five probing questions with senior-level model answers are listed above, covering control-design trade-offs,
diagnosis on physical hardware, mechanical/control interaction, robustness over the machine's lifetime, and (for the
senior variant) mentoring and honest handling of unspecified safety requirements.

Risks to test:
- Iemand die alleen binnen één discipline heeft gewerkt en 'systeemontwerp' op het CV heeft staan zonder concrete interfaces te kunnen noemen.
- Iemand die prototypes alleen laat testen door anderen — vraag door op wie de metingen deed en interpreteerde.

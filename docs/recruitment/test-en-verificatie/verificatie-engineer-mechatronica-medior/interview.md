# Interviewvragenbank — Verificatie-engineer mechatronica (medior)

Discipline: Test en verificatie
Slug/job-id: `verificatie-engineer-mechatronica-medior`
Datum opgesteld: 23-09-2026

## Technische briefing voor de interviewer

Deze mediorrol vertaalt systeemrequirements naar verificatietests en voert die uit op prototypes van mechatronische systemen. De briefing scheidt het opzetten van het verificatietraject (planning: welke test, welke meetmethode) van de uitvoering op de fysieke opstelling en het analyseren van resultaten.

## Vijf indringende vragen met modelantwoord

### 1. Hoe vertaal je de eis 'het systeem moet binnen 0,1 mm nauwkeurig positioneren' naar een concreet verificatietest?

**Modelantwoord (seniorniveau):** Een senior antwoord beschrijft het kiezen van een meetmethode met voldoende resolutie en bekende onzekerheid (bijvoorbeeld een laserinterferometer of hoogwaardige encoder als referentie), het definiëren van het aantal metingen en de omstandigheden (belasting, temperatuur), en het expliciet vaststellen van het acceptatiecriterium inclusief meetonzekerheid, niet alleen 'meten en kijken of het klopt'.

### 2. Een verificatietest toont een afwijking die zowel door mechanica als door software veroorzaakt kan zijn. Hoe herleid je de oorzaak?

**Modelantwoord (seniorniveau):** Een sterk antwoord beschrijft het isoleren van variabelen — bijvoorbeeld de software vastzetten en alleen mechanische parameters variëren, of andersom — en het samen met de betrokken disciplines interpreteren van de resultaten, in plaats van te gokken welke discipline verantwoordelijk is.

### 3. Je ontdekt tijdens het opstellen van verificatietests dat twee requirements elkaar tegenspreken. Wat doe je?

**Modelantwoord (seniorniveau):** Een goed antwoord beschrijft het vroeg terugkoppelen van de tegenstrijdigheid aan de betrokken disciplines of de systeemengineer, met een concrete beschrijving van het conflict, in plaats van zelf te kiezen welke requirement leidend is of door te werken met een aanname.

### 4. Hoe ga je om met meetonzekerheid bij het beoordelen of een systeem aan een requirement voldoet?

**Modelantwoord (seniorniveau):** Een sterk antwoord noemt het expliciet meenemen van de meetonzekerheid in het acceptatiecriterium (bijvoorbeeld een marge rond de grenswaarde), zodat een resultaat dat net binnen de tolerantie valt niet ten onrechte als 'geslaagd' of 'gefaald' wordt bestempeld.

### 5. Hoe documenteer je een verificatieresultaat zodat het traceerbaar is naar de oorspronkelijke requirement?

**Modelantwoord (seniorniveau):** Een goed antwoord noemt het expliciet koppelen van elk testresultaat aan het requirement-nummer of -omschrijving dat het toetst, inclusief de gebruikte meetmethode en acceptatiecriteria, zodat een auditor of collega de koppeling kan natrekken zonder de tester te hoeven raadplegen.

## Twee risico's om op te testen

- Kandidaten die verificatie behandelen als eenmalig 'werkt het wel of niet' zonder aandacht voor meetonzekerheid of acceptatiecriteria.
- Kandidaten die tegenstrijdige requirements zelf oplossen in plaats van te signaleren — dit ondermijnt de traceerbaarheid die de rol vereist.

---

## English summary

**Interview question bank — Verificatie-engineer mechatronica (medior)**, slug `verificatie-engineer-mechatronica-medior`.

Briefing: Deze mediorrol vertaalt systeemrequirements naar verificatietests en voert die uit op prototypes van mechatronische systemen. De briefing scheidt het opzetten van het verificatietraject (planning: welke test, welke meetmethode) van de uitvoering op de fysieke opstelling en het analyseren van resultaten.

Five probing questions with senior-level model answers are listed above, separating strategic test-design reasoning
from execution and diagnosis on the actual test setup.

Risks to test:
- Kandidaten die verificatie behandelen als eenmalig 'werkt het wel of niet' zonder aandacht voor meetonzekerheid of acceptatiecriteria.
- Kandidaten die tegenstrijdige requirements zelf oplossen in plaats van te signaleren — dit ondermijnt de traceerbaarheid die de rol vereist.

# Interviewvragenbank — HIL-testautomatiseringsengineer (medior)

Discipline: Test en verificatie
Slug/job-id: `hil-testautomatiseringsengineer-medior`
Datum opgesteld: 23-09-2026

## Technische briefing voor de interviewer

Deze mediorrol bouwt en onderhoudt geautomatiseerde tests op HIL-opstellingen voor embedded en mechatronische systemen, en werkt mee aan de testinfrastructuur zelf. De briefing scheidt de uitvoerende taak (tests draaien, resultaten analyseren) van de beperkte strategische taak (testdekking prioriteren binnen een gegeven kader).

## Vijf indringende vragen met modelantwoord

### 1. Hoe koppel je een Simulink-model aan de fysieke I/O van een HIL-opstelling?

**Modelantwoord (seniorniveau):** Een senior antwoord beschrijft het definiëren van signaalinterfaces tussen het model en de fysieke aansluitingen (bijvoorbeeld via een real-time target zoals dSPACE), het valideren van signaaltiming en -schaling, en het testen van de koppeling zelf voordat er functionele tests op draaien — niet alleen 'het model aansluiten' als black box behandelen.

### 2. Een testset groeit ongecontroleerd en duurt steeds langer om te draaien. Hoe pak je dit aan?

**Modelantwoord (seniorniveau):** Een sterk antwoord noemt het analyseren van welke tests overlappende dekking hebben, het prioriteren van tests op basis van risico en recente defecten, en mogelijk het parallelliseren of selectief draaien van tests, in plaats van gewoon te accepteren dat de testset langzamer wordt.

### 3. Hoe bepaal je of een gevonden defect een testinfrastructuurprobleem is of een echt probleem in het geteste systeem?

**Modelantwoord (seniorniveau):** Een goed antwoord beschrijft het isoleren van de testomgeving (bijvoorbeeld door een bekend-goede referentie te testen), het controleren van de testconfiguratie, en pas daarna het defect toeschrijven aan het geteste systeem.

### 4. Wanneer voeg je een test toe op basis van een requirement, en wanneer op basis van een eerder gevonden defect?

**Modelantwoord (seniorniveau):** Een sterk antwoord legt uit dat requirements-gebaseerde tests de basisdekking vormen (elke eis heeft minstens één test), terwijl defect-gebaseerde tests regressie voorkomen op specifieke, eerder gefaalde scenario's — beide zijn nodig, met een andere onderbouwing.

### 5. Hoe zorg je dat een collega die niet bij het bouwen van de testopstelling was, deze zelfstandig kan onderhouden?

**Modelantwoord (seniorniveau):** Een goed antwoord noemt gestructureerde documentatie van de testopzet (signaalinterfaces, afhankelijkheden, bekende beperkingen), niet alleen losse commentaarregels in de code.

## Twee risico's om op te testen

- Kandidaten die alleen bestaande tests hebben gedraaid en nooit zelf een testset hebben uitgebreid of onderhouden.
- Kandidaten die de infrastructuur-verantwoordelijkheid onderschatten en zichzelf puur als testuitvoerder zien.

---

## English summary

**Interview question bank — HIL-testautomatiseringsengineer (medior)**, slug `hil-testautomatiseringsengineer-medior`.

Briefing: Deze mediorrol bouwt en onderhoudt geautomatiseerde tests op HIL-opstellingen voor embedded en mechatronische systemen, en werkt mee aan de testinfrastructuur zelf. De briefing scheidt de uitvoerende taak (tests draaien, resultaten analyseren) van de beperkte strategische taak (testdekking prioriteren binnen een gegeven kader).

Five probing questions with senior-level model answers are listed above, separating strategic test-design reasoning
from execution and diagnosis on the actual test setup.

Risks to test:
- Kandidaten die alleen bestaande tests hebben gedraaid en nooit zelf een testset hebben uitgebreid of onderhouden.
- Kandidaten die de infrastructuur-verantwoordelijkheid onderschatten en zichzelf puur als testuitvoerder zien.

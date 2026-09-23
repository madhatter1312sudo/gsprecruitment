# Interviewvragenbank — Softwaretester C++ (medior)

Discipline: Test en verificatie
Slug/job-id: `softwaretester-cpp-medior`
Datum opgesteld: 23-09-2026

## Technische briefing voor de interviewer

Deze mediorrol test embedded en desktopsoftware in C++, met verantwoordelijkheid voor testplanning op projectniveau én uitvoering. De briefing scheidt het opstellen van testplannen en het vroeg signaleren van risicogebieden (planning) van het daadwerkelijk uitvoeren van handmatige en geautomatiseerde tests (uitvoering).

## Vijf indringende vragen met modelantwoord

### 1. Welke C++-specifieke foutcategorieën test je expliciet op die in bijvoorbeeld Python niet relevant zouden zijn?

**Modelantwoord (seniorniveau):** Een senior antwoord noemt geheugenlekken, use-after-free, buffer overflows, en ondefinieerd gedrag door bijvoorbeeld niet-geïnitialiseerde variabelen, en beschrijft concrete testtechnieken daarvoor (bijvoorbeeld met sanitizers of geheugenanalysetools), niet alleen de termen noemen zonder testaanpak.

### 2. Hoe leid je testgevallen af uit een requirement die alleen het gewenste gedrag beschrijft, zonder randgevallen te noemen?

**Modelantwoord (seniorniveau):** Een sterk antwoord beschrijft het systematisch toepassen van testontwerptechnieken zoals equivalentieklassen en grenswaardeanalyse om randgevallen af te leiden die de requirement zelf niet expliciet noemt, in plaats van alleen het beschreven happy path te testen.

### 3. Hoe rapporteer je een intermitterend defect dat niet elke keer reproduceerbaar is?

**Modelantwoord (seniorniveau):** Een goed antwoord noemt het vastleggen van de omstandigheden waaronder het defect wel en niet optrad, het proberen te isoleren van een patroon (timing, belasting, volgorde van operaties), en het transparant communiceren dat het defect niet consistent reproduceerbaar is in plaats van te doen alsof het dat wel is.

### 4. Hoe signaleer je een risicogebied vóórdat er code is om te testen?

**Modelantwoord (seniorniveau):** Een sterk antwoord beschrijft het beoordelen van requirements of ontwerpdocumenten op complexiteit, nieuwheid van de technologie, of eerdere problemen in vergelijkbare componenten, en het vroeg bespreken van een testaanpak voor die gebieden met de ontwikkelaars, in plaats van te wachten tot de code klaar is.

### 5. Wanneer kies je voor handmatig testen in plaats van het te automatiseren?

**Modelantwoord (seniorniveau):** Een goed antwoord noemt exploratief testen, eenmalige of zelden veranderende scenario's, of gevallen waar de kosten van automatisering niet opwegen tegen de baten, als situaties waarin handmatig testen de voorkeur heeft, in plaats van automatisering als altijd-beter te presenteren.

## Twee risico's om op te testen

- Kandidaten met generieke testervaring die geen C++-specifieke foutcategorieën kunnen noemen.
- Kandidaten die alleen reactief testen (wachten op code) en geen voorbeeld hebben van vroege risicosignalering.

---

## English summary

**Interview question bank — Softwaretester C++ (medior)**, slug `softwaretester-cpp-medior`.

Briefing: Deze mediorrol test embedded en desktopsoftware in C++, met verantwoordelijkheid voor testplanning op projectniveau én uitvoering. De briefing scheidt het opstellen van testplannen en het vroeg signaleren van risicogebieden (planning) van het daadwerkelijk uitvoeren van handmatige en geautomatiseerde tests (uitvoering).

Five probing questions with senior-level model answers are listed above, separating strategic test-design reasoning
from execution and diagnosis on the actual test setup.

Risks to test:
- Kandidaten met generieke testervaring die geen C++-specifieke foutcategorieën kunnen noemen.
- Kandidaten die alleen reactief testen (wachten op code) en geen voorbeeld hebben van vroege risicosignalering.

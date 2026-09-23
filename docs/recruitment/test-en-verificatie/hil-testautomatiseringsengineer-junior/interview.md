# Interviewvragenbank — HIL-testautomatiseringsengineer (junior)

Discipline: Test en verificatie
Slug/job-id: `hil-testautomatiseringsengineer-junior`
Datum opgesteld: 23-09-2026

## Technische briefing voor de interviewer

Deze junior, uitvoerende rol test embedded en mechatronische systemen op een HIL-opstelling onder begeleiding van ervaren collega's. De briefing richt zich op basisbegrip van scripting, het samenspel tussen simulatie en fysieke hardware, en leerhouding bij onverwachte resultaten.

## Vijf indringende vragen met modelantwoord

### 1. Wat is het verschil tussen een unittest en een test op een hardware-in-the-loop-opstelling?

**Modelantwoord (seniorniveau):** Een goed seniorniveau-antwoord (als ijkpunt) legt uit dat een unittest geïsoleerde code test zonder echte hardware, terwijl een HIL-test de software laat draaien tegen een gesimuleerde of deels fysieke omgeving die realistisch reageert op de output van het systeem, waardoor tijdgerelateerd en hardware-nabij gedrag zichtbaar wordt dat een unittest niet vangt.

### 2. Een geautomatiseerde test faalt onverwacht. Wat is je eerste stap?

**Modelantwoord (seniorniveau):** Een sterk antwoord beschrijft eerst controleren of het testscript zelf correct is (geen scriptfout), vervolgens de testomgeving en -data controleren, en pas daarna concluderen dat het systeem onder test een echte afwijking vertoont — in plaats van meteen een bug in het geteste systeem aan te nemen.

### 3. Waarom zou je dezelfde test meerdere keren herhalen voordat je een resultaat als betrouwbaar beschouwt?

**Modelantwoord (seniorniveau):** Een goed antwoord noemt dat HIL-opstellingen fysieke componenten bevatten die kleine variaties kunnen geven (timing, ruis, temperatuur), waardoor een eenmalig resultaat een toevalstreffer kan zijn; herhaling onderscheidt een structureel probleem van ruis.

### 4. Wat betekent het als je hoort dat een simulatiemodel en de fysieke hardware in een HIL-opstelling samenwerken?

**Modelantwoord (seniorniveau):** Een sterk antwoord legt uit dat delen van het systeem worden gesimuleerd (bijvoorbeeld sensoren of omgeving) terwijl andere delen echte hardware zijn (bijvoorbeeld een regelaar), zodat het geteste systeem realistisch reageert zonder dat het volledige fysieke systeem gebouwd hoeft te worden.

### 5. Hoe documenteer je een testresultaat zodat een collega het kan reproduceren?

**Modelantwoord (seniorniveau):** Een goed antwoord noemt het vastleggen van de exacte testconfiguratie, invoerdata, verwachte versus waargenomen uitkomst, en de versie van het geteste systeem — genoeg detail om de test exact te herhalen zonder de oorspronkelijke tester te hoeven raadplegen.

## Twee risico's om op te testen

- Kandidaten die alleen handmatig testen en 'automatisering' als buzzword gebruiken zonder eigen scriptvoorbeeld.
- Kandidaten die een falende test meteen als bug in het systeem bestempelen zonder eerst het testscript zelf te controleren.

---

## English summary

**Interview question bank — HIL-testautomatiseringsengineer (junior)**, slug `hil-testautomatiseringsengineer-junior`.

Briefing: Deze junior, uitvoerende rol test embedded en mechatronische systemen op een HIL-opstelling onder begeleiding van ervaren collega's. De briefing richt zich op basisbegrip van scripting, het samenspel tussen simulatie en fysieke hardware, en leerhouding bij onverwachte resultaten.

Five probing questions with senior-level model answers are listed above, separating strategic test-design reasoning
from execution and diagnosis on the actual test setup.

Risks to test:
- Kandidaten die alleen handmatig testen en 'automatisering' als buzzword gebruiken zonder eigen scriptvoorbeeld.
- Kandidaten die een falende test meteen als bug in het systeem bestempelen zonder eerst het testscript zelf te controleren.

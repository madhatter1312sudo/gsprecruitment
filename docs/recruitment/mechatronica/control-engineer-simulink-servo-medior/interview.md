# Interviewvragenbank: Control engineer Simulink/servo (medior)

Discipline: Mechatronica en besturingssoftware
Slug/job-id: `control-engineer-simulink-servo-medior`
Datum opgesteld: 23-09-2026

## Technische briefing voor de interviewer

De rol combineert modelgebaseerd regelontwerp in Simulink met het daadwerkelijk afstellen van servo-assen op een fysieke opstelling bij een machinebouwer of semicon-toeleverancier in de Brainport-regio. De briefing richt zich op het onderscheid tussen theoretische regeltechniek en de praktijk van meten, afstellen en documenteren op een opstelling die niet zich als een simulatiemodel gedraagt.

## Vijf indringende vragen met modelantwoord

### 1. Leg uit hoe je de bandbreedte van een positieregellus zou kiezen voor een servo-as, en welke fysieke grenzen die keuze beperken.

**Modelantwoord (seniorniveau):** Een senior antwoord noemt dat de bandbreedte wordt begrensd door de eerste mechanische resonantie in de aandrijflijn (doorgaans een factor vijf tot tien onder die resonantiefrequentie blijven), door de sample-tijd van de regelaar en door sensor-ruis die bij hoge bandbreedte wordt versterkt. De kandidaat noemt concrete getallen uit eigen ervaring, geen vuistregel zonder onderbouwing.

### 2. Een servo-as vertoont een kleine, herhaalbare volgfout die met de snelheid meeschaalt. Waar zoek je eerst?

**Modelantwoord (seniorniveau):** Dit wijst op een snelheidsafhankelijke fout, kenmerkend voor een te lage regelversterking of een feedforward-term die ontbreekt of verkeerd geschaald is. Een senior kandidaat noemt eerst feedforward voor snelheid/versnelling controleren voordat de PID-parameters worden opgehoogd, omdat ophogen van de versterking de stabiliteitsmarge aantast.

### 3. Hoe documenteer je regelparameters zodat een collega ze op een andere, vergelijkbare opstelling kan hergebruiken?

**Modelantwoord (seniorniveau):** Een goed antwoord noemt niet alleen de parameterwaarden, maar ook de context: sample-tijd, sensorresolutie, belastingscondities tijdens het afstellen, en de meetmethode waarmee de prestatie is geverifieerd. Zonder die context zijn parameters niet reproduceerbaar op andere hardware.

### 4. Wat is het verschil tussen een model dat in simulatie stabiel is en een systeem dat in de praktijk stabiel is, en hoe test je dat verschil?

**Modelantwoord (seniorniveau):** Simulatie mist doorgaans onmodelleerde dynamica: speling, wrijving, sensorvertraging, quantisatie. Een senior antwoord noemt het testen met stapresponsies en frequentieresponsies op de echte opstelling en het vergelijken van de fasemarge in de praktijk met die in het model, niet alleen visueel 'het lijkt goed' beoordelen.

### 5. Wanneer zou je Simulink Coder inzetten in plaats van handmatige C-implementatie, en wat is de prijs van die keuze?

**Modelantwoord (seniorniveau):** Codegeneratie versnelt de ontwikkeling en houdt model en implementatie synchroon, maar levert code op die moeilijker te reviewen en te debuggen is op de doelhardware, en vraagt discipline in modelconventies. Een senior antwoord weegt ontwikkelsnelheid af tegen onderhoudbaarheid en het certificeringsregime van de klant, in plaats van het als standaardkeuze te presenteren.

## Twee risico's om op te testen

- Iemand die alleen in Simulink heeft gesimuleerd en nooit zelf een opstelling heeft afgesteld; vraag expliciet naar meetdata, niet naar modelresultaten.
- Iemand die regeltechniek geïsoleerd bespreekt zonder de mechanische en software-context te kennen; toets of de kandidaat kan aangeven waar een regelkeuze een andere discipline raakt.

---

## English summary

**Interview question bank: Control engineer Simulink/servo (medior)**, slug `control-engineer-simulink-servo-medior`.

Briefing: The role combines model-based control design in Simulink with the actual tuning of servo axes on a physical rig at a machine builder or semicon supplier in the Brainport region. The briefing focuses on the distinction between theoretical control engineering and the practice of measuring, tuning and documenting on a rig that does not behave like a simulation model.

Five probing questions with senior-level model answers are listed above, covering control-design trade-offs,
diagnosis on physical hardware, mechanical/control interaction, robustness over the machine's lifetime, and (for the
senior variant) mentoring and honest handling of unspecified safety requirements.

Risks to test:
- Someone who has only simulated in Simulink and never tuned a rig themselves; ask explicitly for measurement data, not model results.
- Someone who discusses control engineering in isolation without knowing the mechanical and software context; test whether the candidate can point out where a control choice touches another discipline.

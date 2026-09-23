# Interviewvragenbank — OT security engineer IEC 62443 (medior)

Discipline: OT-cybersecurity (plant-side)
Slug/job-id: `ot-security-engineer-iec-62443-medior`
Datum opgesteld: 23-09-2026

## Technische briefing voor de interviewer

Deze plant-side rol beveiligt operationele technologie bij productieomgevingen en machinebouwers in de Brainport-regio, met IEC 62443 als leidraad. De briefing richt zich op het onderscheid tussen IT- en OT-beveiliging, het uitvoeren van risicoanalyses op bestaande installaties, en het balanceren van beveiliging met bedrijfscontinuïteit.

## Vijf indringende vragen met modelantwoord

### 1. Waarom kun je een IT-patchbeleid niet zomaar toepassen op een PLC-omgeving?

**Modelantwoord (seniorniveau):** Een senior antwoord noemt dat PLC's en SCADA-systemen vaak niet zijn gebouwd om reboots of onderbroken beschikbaarheid te verdragen, dat patches leverancierscertificering kunnen breken, en dat een productieonderbreking direct fysieke of financiële schade veroorzaakt — daarom vraagt patchen in OT een geplande onderhoudsstop en leveranciersvalidatie, niet automatische uitrol.

### 2. Hoe stel je een zonerings- en conduitmodel op voor een bestaand, ongesegmenteerd industrieel netwerk?

**Modelantwoord (seniorniveau):** Een sterk antwoord beschrijft het eerst in kaart brengen van functionele groepen (bijvoorbeeld per productielijn of veiligheidsfunctie), het bepalen van het risiconiveau per zone op basis van impact bij uitval, en het definiëren van conduits (gecontroleerde verbindingen) tussen zones, in lijn met het zone/conduit-model uit IEC 62443.

### 3. Een operator meldt afwijkend netwerkverkeer maar wil de lijn niet stilleggen voor onderzoek. Hoe handel je?

**Modelantwoord (seniorniveau):** Een goed antwoord weegt het risico van doorproduceren af tegen het risico van het incident, escaleert volgens een vooraf afgesproken proces in plaats van zelfstandig te besluiten, en zoekt naar niet-verstorende onderzoeksmethoden (bijvoorbeeld passieve monitoring) als eerste stap.

### 4. Wat is het verschil tussen een kwetsbaarheid en een risico in een OT-context?

**Modelantwoord (seniorniveau):** Een senior antwoord legt uit dat een kwetsbaarheid een technisch zwak punt is, terwijl risico de kans op misbruik combineert met de impact op productie, veiligheid of milieu — een kwetsbaarheid in een geïsoleerd, goed bewaakt systeem kan een laag risico zijn, en andersom.

### 5. Hoe documenteer je een bevinding zodat die bruikbaar is voor een audit én begrijpelijk voor een operator?

**Modelantwoord (seniorniveau):** Een goed antwoord noemt gelaagde documentatie: een technische bevinding met bewijs en verwijzing naar de relevante norm-eis voor de auditor, en een korte, praktische samenvatting van impact en voorgestelde maatregel voor de operator, in plaats van één document voor beide doelgroepen.

## Twee risico's om op te testen

- IT-security-achtergrond die OT-continuïteitseisen onderschat — toets expliciet met de vraag over patchen en stilleggen van een lijn.
- Kandidaten die IEC 62443 alleen kennen als naam, niet als toegepast zonerings- of risicomodel — vraag door op een concrete toepassing, niet op de norm in abstracto.

---

## English summary

**Interview question bank — OT security engineer IEC 62443 (medior)**, slug `ot-security-engineer-iec-62443-medior`, plant-side.

Briefing: Deze plant-side rol beveiligt operationele technologie bij productieomgevingen en machinebouwers in de Brainport-regio, met IEC 62443 als leidraad. De briefing richt zich op het onderscheid tussen IT- en OT-beveiliging, het uitvoeren van risicoanalyses op bestaande installaties, en het balanceren van beveiliging met bedrijfscontinuïteit.

Five probing questions with senior-level model answers are listed above, separating OT-specific reasoning from
IT-security habits applied uncritically to industrial systems.

Risks to test:
- IT-security-achtergrond die OT-continuïteitseisen onderschat — toets expliciet met de vraag over patchen en stilleggen van een lijn.
- Kandidaten die IEC 62443 alleen kennen als naam, niet als toegepast zonerings- of risicomodel — vraag door op een concrete toepassing, niet op de norm in abstracto.

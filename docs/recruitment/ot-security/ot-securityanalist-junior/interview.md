# Interviewvragenbank — OT-securityanalist (junior)

Discipline: OT-cybersecurity (plant-side)
Slug/job-id: `ot-securityanalist-junior`
Datum opgesteld: 23-09-2026

## Technische briefing voor de interviewer

Deze junior, plant-side rol monitort en onderzoekt afwijkingen in industriële netwerken bij productie-omgevingen, onder begeleiding van ervaren collega's. De briefing richt zich op basisbegrip van netwerken en beveiligingsconcepten, leerhouding, en het onderscheiden van IT- en OT-denken.

## Vijf indringende vragen met modelantwoord

### 1. Wat is het verschil tussen een firewall in een kantoornetwerk en een firewall in een OT-netwerk?

**Modelantwoord (seniorniveau):** Een goed seniorniveau-antwoord voor deze vraag (gebruikt als ijkpunt, ook al is de rol junior) noemt dat een OT-firewall rekening moet houden met real-time verkeer en protocollen die kantoorfirewalls niet kennen, en dat een verkeerd geconfigureerde regel in OT direct een productieproces kan raken, waar dat in IT doorgaans 'alleen' een dienst treft.

### 2. Je ziet ongebruikelijk verkeer tussen twee PLC's die normaal niet met elkaar communiceren. Wat doe je?

**Modelantwoord (seniorniveau):** Een sterk antwoord beschrijft het documenteren van de waarneming, het navragen bij een ervaren collega of dit verkeer een bekende, legitieme reden heeft (bijvoorbeeld een onderhoudswerkzaamheid), en het niet zelfstandig ingrijpen in de OT-omgeving zonder toestemming.

### 3. Wat betekent segmentatie in een netwerk, in je eigen woorden?

**Modelantwoord (seniorniveau):** Een goed antwoord legt uit dat segmentatie het netwerk opdeelt in kleinere, gecontroleerde delen zodat een probleem in het ene deel zich niet zomaar verspreidt naar het andere, met een eenvoudig voorbeeld zoals het scheiden van kantoor- en productienetwerk.

### 4. Waarom zou je in een OT-omgeving voorzichtiger zijn met actief scannen van het netwerk dan in een IT-omgeving?

**Modelantwoord (seniorniveau):** Een sterk antwoord noemt dat sommige industriële apparaten kwetsbaar zijn voor verstoring door actieve scans (bijvoorbeeld oudere PLC's die vastlopen bij onverwacht verkeer), waardoor passieve monitoring vaak de voorkeur heeft in OT.

### 5. Hoe zou je een bevinding documenteren zodat een collega die het later leest, precies begrijpt wat je hebt gezien?

**Modelantwoord (seniorniveau):** Een goed antwoord noemt tijdstip, betrokken systemen, wat er precies is waargenomen (met bewijs zoals een schermafbeelding of logregel), en wat al wel en nog niet is onderzocht — feitelijk en navolgbaar, geen interpretatie voorgesteld als vaststaand feit.

## Twee risico's om op te testen

- Kandidaten die OT-security zien als een label voor generieke IT-security-ambities zonder specifieke interesse in industriële systemen.
- Kandidaten die zelfstandig willen ingrijpen in plaats van te escaleren — dit past niet bij een beginnersrol in een omgeving waar een verkeerde ingreep de productie kan raken.

---

## English summary

**Interview question bank — OT-securityanalist (junior)**, slug `ot-securityanalist-junior`, plant-side.

Briefing: Deze junior, plant-side rol monitort en onderzoekt afwijkingen in industriële netwerken bij productie-omgevingen, onder begeleiding van ervaren collega's. De briefing richt zich op basisbegrip van netwerken en beveiligingsconcepten, leerhouding, en het onderscheiden van IT- en OT-denken.

Five probing questions with senior-level model answers are listed above, separating OT-specific reasoning from
IT-security habits applied uncritically to industrial systems.

Risks to test:
- Kandidaten die OT-security zien als een label voor generieke IT-security-ambities zonder specifieke interesse in industriële systemen.
- Kandidaten die zelfstandig willen ingrijpen in plaats van te escaleren — dit past niet bij een beginnersrol in een omgeving waar een verkeerde ingreep de productie kan raken.

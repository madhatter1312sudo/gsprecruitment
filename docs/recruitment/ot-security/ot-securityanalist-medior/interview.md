# Interviewvragenbank — OT-securityanalist (medior)

Discipline: OT-cybersecurity (plant-side)
Slug/job-id: `ot-securityanalist-medior`
Datum opgesteld: 23-09-2026

## Technische briefing voor de interviewer

Deze mediorrol analyseert en bewaakt de beveiliging van industriële netwerken bij productieomgevingen, met IEC 62443 als referentiekader voor audit-bestendige documentatie. De briefing richt zich op incidentanalyse, OT-specifieke tooling, en samenwerking tussen OT en IT bij opvolging.

## Vijf indringende vragen met modelantwoord

### 1. Wat verandert er aan een SIEM-configuratie als die van een kantooromgeving wordt overgezet naar een OT-netwerk?

**Modelantwoord (seniorniveau):** Een senior antwoord noemt het toevoegen van OT-specifieke protocolparsers (bijvoorbeeld Modbus, OPC UA), het aanpassen van alerting-drempels aan het voorspelbare, cyclische karakter van industrieel verkeer, en het voorkomen van alert-moeheid door alleen te alerteren op afwijkingen van een vastgestelde baseline.

### 2. Een incident wijst mogelijk op een gecompromitteerd systeem, maar isoleren zou de productie stilleggen. Hoe adviseer je?

**Modelantwoord (seniorniveau):** Een sterk antwoord weegt de kans en impact van voortgezette compromittering af tegen de kosten van stilstand, stelt eventueel een tussenoplossing voor (bijvoorbeeld verscherpte monitoring in plaats van volledige isolatie), en legt het besluit en de onderbouwing vast voor latere verantwoording.

### 3. Hoe onderscheid je een vals alarm van een echte afwijking in OT-netwerkverkeer?

**Modelantwoord (seniorniveau):** Een goed antwoord noemt het vergelijken met een vastgestelde baseline van normaal verkeer, het controleren of het patroon samenvalt met een bekende, geplande activiteit (zoals onderhoud), en het raadplegen van OT-collega's die de fysieke context kennen.

### 4. Hoe zorg je dat een bevinding herleidbaar en audit-bestendig is?

**Modelantwoord (seniorniveau):** Een sterk antwoord noemt tijdstempels, bronvermelding van de data, koppeling aan de relevante norm-eis, en een duidelijke scheiding tussen feit en interpretatie — zodat een auditor de bevinding kan natrekken zonder de analist te hoeven raadplegen.

### 5. Hoe stem je met een OT-collega af als jouw analyse een maatregel adviseert die zij als onwerkbaar zien?

**Modelantwoord (seniorniveau):** Een goed antwoord beschrijft het luisteren naar de operationele bezwaren, het samen zoeken naar een alternatieve maatregel die hetzelfde risico afdekt, en het escaleren met een onderbouwd voorstel als geen gezamenlijke oplossing wordt gevonden, in plaats van de maatregel eenzijdig door te zetten.

## Twee risico's om op te testen

- Kandidaten met puur IT-SIEM-ervaring die aannemen dat OT-alerting hetzelfde werkt — toets expliciet met de SIEM-aanpassingsvraag.
- Kandidaten die documentatie behandelen als bijzaak — vraag concreet door op een eerdere audit-ervaring.

---

## English summary

**Interview question bank — OT-securityanalist (medior)**, slug `ot-securityanalist-medior`, plant-side.

Briefing: Deze mediorrol analyseert en bewaakt de beveiliging van industriële netwerken bij productieomgevingen, met IEC 62443 als referentiekader voor audit-bestendige documentatie. De briefing richt zich op incidentanalyse, OT-specifieke tooling, en samenwerking tussen OT en IT bij opvolging.

Five probing questions with senior-level model answers are listed above, separating OT-specific reasoning from
IT-security habits applied uncritically to industrial systems.

Risks to test:
- Kandidaten met puur IT-SIEM-ervaring die aannemen dat OT-alerting hetzelfde werkt — toets expliciet met de SIEM-aanpassingsvraag.
- Kandidaten die documentatie behandelen als bijzaak — vraag concreet door op een eerdere audit-ervaring.

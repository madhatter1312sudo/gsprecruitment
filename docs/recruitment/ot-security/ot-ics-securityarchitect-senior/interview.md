# Interviewvragenbank — OT/ICS-securityarchitect (senior)

Discipline: OT-cybersecurity (plant-side)
Slug/job-id: `ot-ics-securityarchitect-senior`
Datum opgesteld: 23-09-2026

## Technische briefing voor de interviewer

Deze senior, plant-side rol ontwerpt de beveiligingsarchitectuur voor industriële besturingssystemen bij productieomgevingen en machinebouwers, en fungeert als poortwachter voor nieuwe systemen en leveranciers. De briefing richt zich op architectuurkeuzes, leveranciersbeoordeling en samenwerking tussen OT, IT en engineering.

## Vijf indringende vragen met modelantwoord

### 1. Welke criteria gebruik je om een nieuw industrieel systeem te beoordelen voordat het wordt opgenomen in de OT-omgeving?

**Modelantwoord (seniorniveau):** Een senior antwoord noemt onder meer: patchbaarheid en het leveranciersbeleid daarvoor, ondersteunde authenticatie- en toegangsmechanismen, of het systeem netwerksegmentatie ondersteunt, en of de leverancier kwetsbaarheden transparant meldt. De kandidaat noemt concrete criteria, geen vage 'security by design'-uitspraak.

### 2. Hoe zet je anomaly detection op in een OT-netwerk zonder valse meldingen die operators leren negeren?

**Modelantwoord (seniorniveau):** Een sterk antwoord beschrijft een baseline-periode om normaal verkeer vast te stellen, geleidelijke afstelling van detectiedrempels, en het prioriteren van meldingen op basis van kritikaliteit van het getroffen systeem, in plaats van elke afwijking gelijk te behandelen.

### 3. Een leverancier weigert details te geven over hoe hun systeem intern communiceert. Neem je het systeem toch op?

**Modelantwoord (seniorniveau):** Een goed antwoord weegt af of het gebrek aan transparantie kan worden gecompenseerd met externe maatregelen (bijvoorbeeld strikte netwerksegmentatie en monitoring rondom het systeem), en beschrijft dat volledige weigering van transparantie een zwaarwegend risico is dat expliciet wordt teruggekoppeld aan de opdrachtgever, niet stilzwijgend wordt geaccepteerd.

### 4. Hoe overtuig je een engineeringteam dat een architectuurkeuze noodzakelijk is als die extra complexiteit toevoegt aan hun ontwerp?

**Modelantwoord (seniorniveau):** Een senior antwoord beschrijft het vertalen van de beveiligingskeuze naar concrete risico's voor het engineeringteam zelf (bijvoorbeeld aansprakelijkheid bij een incident, stilstand die hun eigen werk raakt), en het samen zoeken naar de minst ingrijpende manier om het risico af te dekken.

### 5. Hoe borg je dat toegangsbeheer in een OT-omgeving werkbaar blijft voor operators die snel moeten kunnen ingrijpen bij een storing?

**Modelantwoord (seniorniveau):** Een goed antwoord noemt het onderscheid tussen dagelijkse toegang (strikt, rolgebonden) en noodtoegang (een vooraf gedefinieerde, gelogde escalatieroute), zodat beveiliging het ingrijpen bij een storing niet blokkeert maar wel traceerbaar maakt.

## Twee risico's om op te testen

- Architectuurkennis die alleen op papier bestaat, zonder ervaring met daadwerkelijke implementatie in een productieomgeving — vraag door op een concreet, opgeleverd voorbeeld.
- Onderschatting van de operationele impact van beveiligingsmaatregelen op productiecontinuïteit — toets met de vraag over noodtoegang.

---

## English summary

**Interview question bank — OT/ICS-securityarchitect (senior)**, slug `ot-ics-securityarchitect-senior`, plant-side.

Briefing: Deze senior, plant-side rol ontwerpt de beveiligingsarchitectuur voor industriële besturingssystemen bij productieomgevingen en machinebouwers, en fungeert als poortwachter voor nieuwe systemen en leveranciers. De briefing richt zich op architectuurkeuzes, leveranciersbeoordeling en samenwerking tussen OT, IT en engineering.

Five probing questions with senior-level model answers are listed above, separating OT-specific reasoning from
IT-security habits applied uncritically to industrial systems.

Risks to test:
- Architectuurkennis die alleen op papier bestaat, zonder ervaring met daadwerkelijke implementatie in een productieomgeving — vraag door op een concreet, opgeleverd voorbeeld.
- Onderschatting van de operationele impact van beveiligingsmaatregelen op productiecontinuïteit — toets met de vraag over noodtoegang.

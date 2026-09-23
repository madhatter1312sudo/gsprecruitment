# Interviewvragenbank — Security-testengineer OT (medior)

Discipline: OT-cybersecurity (plant-side)
Slug/job-id: `security-testengineer-ot-medior`
Datum opgesteld: 23-09-2026

## Technische briefing voor de interviewer

Deze mediorrol test de beveiliging van industriële besturingssystemen bij productieomgevingen, zonder de productiecontinuïteit te verstoren, en volgt op of gevonden kwetsbaarheden daadwerkelijk worden opgelost. De briefing richt zich op veilig testen in OT, testplannen afgeleid van IEC 62443, en heldere rapportage naar gemengde doelgroepen.

## Vijf indringende vragen met modelantwoord

### 1. Waarom zou je een actieve kwetsbaarhedenscan op een PLC anders aanpakken dan op een kantoorserver?

**Modelantwoord (seniorniveau):** Een senior antwoord noemt dat sommige oudere PLC's kunnen vastlopen of onverwacht gedrag vertonen bij onbekend netwerkverkeer, dat een scan buiten geplande onderhoudstijd productie kan raken, en dat daarom passieve technieken of een geplande, gecommuniceerde testvensters de voorkeur hebben boven ongeplande actieve scans.

### 2. Hoe stel je een testplan op dat aantoont of een geïmplementeerde zoneringsmaatregel daadwerkelijk werkt?

**Modelantwoord (seniorniveau):** Een sterk antwoord beschrijft het definiëren van testscenario's per conduit (bijvoorbeeld: probeer verkeer te sturen dat de zone niet zou mogen verlaten), het vooraf afstemmen van een testvenster met de installatiebeheerder, en het documenteren van zowel geslaagde blokkades als onverwacht doorgelaten verkeer.

### 3. Je vindt een kritieke kwetsbaarheid vlak voor een geplande productiestart. Wat doe je?

**Modelantwoord (seniorniveau):** Een goed antwoord beschrijft het direct escaleren van de bevinding met een heldere impact-inschatting, het samen met de verantwoordelijken afwegen of de productiestart kan doorgaan met een tijdelijke compenserende maatregel, en het niet zelfstandig besluiten om de start te vertragen of te negeren.

### 4. Hoe rapporteer je een technische bevinding zodat een productiemanager zonder security-achtergrond de urgentie begrijpt?

**Modelantwoord (seniorniveau):** Een sterk antwoord noemt het vertalen van de technische bevinding naar concrete bedrijfsimpact (bijvoorbeeld risico op productiestilstand of dataverlies), het vermijden van jargon, en het expliciet noemen van een aanbevolen vervolgstap met tijdslijn.

### 5. Hoe volg je op of een eerder gerapporteerde kwetsbaarheid daadwerkelijk is verholpen?

**Modelantwoord (seniorniveau):** Een goed antwoord beschrijft het herhalen van de gerichte test na de gemelde reparatie, het vastleggen van het resultaat, en het niet zomaar vertrouwen op de mededeling 'is opgelost' zonder eigen verificatie.

## Twee risico's om op te testen

- Kandidaten die testmethoden uit een IT-context ongewijzigd toepassen op OT zonder het verstoringsrisico te onderkennen — toets expliciet met de scanvraag.
- Kandidaten die kwetsbaarheden rapporteren maar de opvolging niet als eigen verantwoordelijkheid zien — vraag door op verificatie na reparatie.

---

## English summary

**Interview question bank — Security-testengineer OT (medior)**, slug `security-testengineer-ot-medior`, plant-side.

Briefing: Deze mediorrol test de beveiliging van industriële besturingssystemen bij productieomgevingen, zonder de productiecontinuïteit te verstoren, en volgt op of gevonden kwetsbaarheden daadwerkelijk worden opgelost. De briefing richt zich op veilig testen in OT, testplannen afgeleid van IEC 62443, en heldere rapportage naar gemengde doelgroepen.

Five probing questions with senior-level model answers are listed above, separating OT-specific reasoning from
IT-security habits applied uncritically to industrial systems.

Risks to test:
- Kandidaten die testmethoden uit een IT-context ongewijzigd toepassen op OT zonder het verstoringsrisico te onderkennen — toets expliciet met de scanvraag.
- Kandidaten die kwetsbaarheden rapporteren maar de opvolging niet als eigen verantwoordelijkheid zien — vraag door op verificatie na reparatie.

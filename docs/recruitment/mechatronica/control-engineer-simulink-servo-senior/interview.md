# Interviewvragenbank: Control engineer Simulink/servo (senior)

Discipline: Mechatronica en besturingssoftware
Slug/job-id: `control-engineer-simulink-servo-senior`
Datum opgesteld: 23-09-2026

## Technische briefing voor de interviewer

Deze senior rol draagt verantwoordelijkheid voor het regeltechnisch ontwerp van servoaandrijvingen én voor het begeleiden van mediorcollega's. De briefing richt zich op onderbouwde ontwerpkeuzes, vroege signalering van mechanisch-regeltechnische raakvlakken en het vermogen om kennis over te dragen, niet alleen zelf te presteren.

## Vijf indringende vragen met modelantwoord

### 1. Hoe bepaal je of een regelprobleem wordt veroorzaakt door de regelaar of door mechanische speling?

**Modelantwoord (seniorniveau):** Een senior antwoord beschrijft het isoleren van de mechanica door de regellus tijdelijk te vereenvoudigen of open-loop te testen, het meten van hysterese in de positie-respons, en het vergelijken met de verwachte mechanische specificatie (bijvoorbeeld speling in een tandwielkast). Puur op de PID-parameters blijven sleutelen zonder deze diagnose is een zwak antwoord.

### 2. Een mediorcollega presenteert een regelontwerp dat in simulatie stabiel is maar volgens jou een te kleine fasemarge heeft. Hoe pak je dat gesprek aan?

**Modelantwoord (seniorniveau):** Een sterk antwoord combineert inhoudelijke onderbouwing (concrete fasemarge-eis, bijvoorbeeld minimaal 45 graden als vuistregel, en waarom dat hier relevant is) met een coachende toon: eerst vragen hoe de collega tot de marge is gekomen, dan samen de meting of berekening doorlopen in plaats van het ontwerp direct af te keuren.

### 3. Hoe ontwerp je synchronisatie tussen twee servo-assen die mechanisch gekoppeld zijn via het werkstuk?

**Modelantwoord (seniorniveau):** Een senior antwoord noemt master-slave- of cross-coupling-regelstructuren, het belang van een gedeelde tijdbasis of synchronisatiesignaal tussen de assen, en het testen van faseverschil onder belasting, niet alleen onder nullast.

### 4. Wat is voor jou het verschil tussen een regelaar die 'werkt' en een regelaar die robuust is over de levensduur van de machine?

**Modelantwoord (seniorniveau):** Een sterk antwoord noemt marges voor slijtage, temperatuurdrift van componenten, en variatie tussen machine-exemplaren, en beschrijft hoe daarvoor wordt getest, bijvoorbeeld door parameters over een range van omstandigheden te valideren in plaats van eenmalig op één opstelling.

### 5. Hoe zou je functionele veiligheid meewegen in het ontwerp van een bewegingsas, ook als er geen expliciete norm is voorgeschreven?

**Modelantwoord (seniorniveau):** Een senior antwoord erkent dat zonder een voorgeschreven norm (zoals ISO 13849 voor machineveiligheid) de verantwoordelijkheid ligt bij het expliciet uitvragen bij de klant of veiligheidseisen elders in het systeem al zijn afgedekt, en beschrijft basisprincipes zoals begrensde snelheid of noodstopgedrag als voorzorg, zonder te doen alsof een norm is toegepast die niet is genoemd.

## Twee risico's om op te testen

- Iemand met zeven jaar ervaring die nooit collega's heeft begeleid; de rol vereist expliciet coaching, niet alleen senioriteit in jaren.
- Overclaimen van veiligheidscertificering: toets of de kandidaat 'functionele veiligheid' als brede affiniteit beschrijft of als concrete normkennis presenteert die het record niet onderbouwt.

---

## English summary

**Interview question bank: Control engineer Simulink/servo (senior)**, slug `control-engineer-simulink-servo-senior`.

Briefing: This senior role carries responsibility for the control-engineering design of servo drives and for mentoring medior colleagues. The briefing focuses on well-founded design choices, early flagging of mechanical/control interfaces, and the ability to transfer knowledge, not just to perform.

Five probing questions with senior-level model answers are listed above, covering control-design trade-offs,
diagnosis on physical hardware, mechanical/control interaction, robustness over the machine's lifetime, and (for the
senior variant) mentoring and honest handling of unspecified safety requirements.

Risks to test:
- Someone with seven years of experience who has never mentored colleagues; the role explicitly requires coaching, not just seniority in years.
- Overclaiming safety certification: test whether the candidate describes 'functional safety' as a broad affinity or presents specific standards knowledge that the record does not support.

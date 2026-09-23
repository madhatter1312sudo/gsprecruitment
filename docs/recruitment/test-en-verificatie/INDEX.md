# Test en verificatie — index vacatures

Datum: 23-09-2026
Bron: `talent-os/backend/data/pool_vacancies.json`, gefilterd op `department: "Test en verificatie"`. De
platform-API bevat nog geen vacatures; dit seedbestand is de bron, en de seed-slug is het interim job-id tot de seed
draait.

Aantal live vacatures in deze discipline: 6

- [`hil-testautomatiseringsengineer-junior`](hil-testautomatiseringsengineer-junior/requirements.md) — HIL-testautomatiseringsengineer (junior, Veldhoven, vast) — salaris: €38.000–€50.000 bruto per jaar, vast
- [`hil-testautomatiseringsengineer-medior`](hil-testautomatiseringsengineer-medior/requirements.md) — HIL-testautomatiseringsengineer (medior, Eindhoven, detachering) — salaris: €48.000–€65.000 bruto per jaar, detachering
- [`hil-testautomatiseringsengineer-senior`](hil-testautomatiseringsengineer-senior/requirements.md) — HIL-testautomatiseringsengineer (senior, Best, interim) — salaris: €62.000–€84.000 bruto per jaar, interim
- [`softwaretester-cpp-medior`](softwaretester-cpp-medior/requirements.md) — Softwaretester C++ (medior, Helmond, vast) — salaris: €48.000–€65.000 bruto per jaar, vast
- [`verificatie-engineer-mechatronica-medior`](verificatie-engineer-mechatronica-medior/requirements.md) — Verificatie-engineer mechatronica (medior, Eindhoven, detachering) — salaris: €48.000–€65.000 bruto per jaar, detachering
- [`qa-lead-embedded-senior`](qa-lead-embedded-senior/requirements.md) — QA-lead embedded (senior, Veldhoven, interim) — salaris: €62.000–€84.000 bruto per jaar, interim

Elke vacature heeft een `requirements.md` (teststrategie versus testuitvoering eerst, knock-outs, must-haves,
nice-to-haves, normen/certificeringen met wat ze impliceren, drie fit-vragen, salarisband, locatie,
shift/oproeppatroon, ongeschreven klantvoorkeuren) en een `interview.md` (briefing, vijf indringende vragen met
modelantwoord op seniorniveau, twee risico's). Alle zes records in deze discipline hebben een salarisband in het
seedbestand; geen enkele is null.

---

## English summary

Index of live test-and-verification vacancies (6 total), sourced from
`talent-os/backend/data/pool_vacancies.json` filtered on `department: "Test en verificatie"`. Each sheet states the
strategy/execution split explicitly. All six records carry a salary band in the seed data.

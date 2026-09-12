"""
Talent OS -- WS5 BV8: de canonieke faselijst van `pipeline_entries.stage`
vastleggen (SITE-DESIGN-SPEC.md §7.6 besluit 2, §7.7 BV8).

De zeven waarden zijn: sourced, new, screening, interview, offer, placed,
rejected. Tot deze migratie was de kolom VARCHAR(50) met default 'sourced'
en zonder enige constraint, dus elke tekenreeks van hooguit vijftig tekens
kon erin. Het klantportaal tekent vier vaste kolommen (new, screening,
interview, offer) en zet alles daarbuiten stil in "new"
(website/client/app.js regel 141-146), wat betekent dat een afwijkende
waarde jarenlang onzichtbaar kan hebben meegedraaid.

Volgorde, en waarom die niet omkeerbaar is:

  1. Normaliseren. Elke UPDATE hieronder is idempotent (hij selecteert op
     precies de waarde die hij wegschrijft, dus een tweede run raakt nul
     rijen) en verandert nooit een rij die al een van de zeven draagt.
  2. Pas daarna de CHECK-constraint, en dan als NOT VALID. NOT VALID zet
     de regel voor alles wat er vanaf nu in gaat, maar laat de bestaande
     rijen ongemoeid en scant de tabel niet. Een onbekende waarde die
     productie wel heeft en dit bestand niet kent, kan de deploy dus niet
     breken -- dat is het hele punt van deze vorm.
  3. VALIDATE CONSTRAINT is een aparte, latere eigenaarsstap. Het
     draaiboek staat onderaan dit bestand, inclusief de SQL-regel om de
     afwijkers vooraf te tellen.

De mappingtabel, met per regel waar de waarde vandaan komt. De regel die
elke semantische mapping volgt: nooit meer voortgang claimen dan de
bronwaarde bewijst, en nooit vastgelegde voortgang terugdraaien.

  | Gevonden waarde        | Wordt      | Herkomst en motivering                |
  |------------------------|------------|---------------------------------------|
  | hoofdletters/spaties   | TRIM+LOWER | De CHECK is hoofdlettergevoelig; geen |
  |   (' Screening ')      |            | enkele schrijver bedoelde ooit een    |
  |                        |            | hoofdletter. Puur vormverschil.       |
  | '' (leeg na trim)      | sourced    | De kolomdefault uit migrations/002.   |
  | 'applied'              | new        | matches.status-vocabulaire (baseline  |
  |                        |            | regel 316, app/app/(tabs)/career.tsx  |
  |                        |            | regel 12). Gesolliciteerd bewijst      |
  |                        |            | "in de pijplijn", niet meer.          |
  | 'contacted'            | new        | website/admin/js/admin.js regel 74    |
  |                        |            | ("Benaderd"). Benaderd bewijst wel    |
  |                        |            | contact, geen screening.              |
  | 'active'               | new        | website/admin/js/admin.js regel 75    |
  |                        |            | ("Actief"). Bewijst alleen dat de rij |
  |                        |            | loopt.                                |
  | 'suggested'            | sourced    | matches.status-default (baseline 316):|
  |                        |            | door de matcher voorgesteld, nog geen |
  |                        |            | menselijke handeling.                 |
  | 'interviewing'         | interview  | career.tsx regel 12, zelfde fase.     |
  | 'offered'              | offer      | career.tsx regel 12, zelfde fase.     |
  | 'hired'                | placed     | Zelfde eindfase onder een andere naam.|
  | 'declined', 'afgewezen'| rejected   | Zelfde eindfase onder een andere naam.|

Twee waarden worden bewust NIET gemapt. 'inactive' (admin.js regel 75)
heeft geen verdedigbaar doel: het is niet 'rejected' (dat is een besluit
dat iemand genomen heeft) en niet 'new' (dat zou een dode rij terugzetten
in een actieve kolom). En elke waarde die dit bestand niet kent, blijft
per definitie staan. Beide gevallen zijn precies waarvoor NOT VALID er
is; de telregel in het draaiboek maakt ze zichtbaar voordat iemand
VALIDATE draait.

`pipeline_stage_history.from_stage`/`to_stage` blijven ongemoeid. Dat is
een append-only logboek van wat er destijds gebeurd is; een historische
regel achteraf herschrijven zou het logboek onbetrouwbaar maken. Het
scherm toont daar de ruwe waarde wanneer het geen label kent (§7.3.4).

Patroon van 030/032/033/034/036/037/039/040/041/042: idempotent, geen
`DO $$ ... END $$`-blokken (migrations/_runner.py splitst op een
letterlijke ";"), geen DELETE/DROP van data. De DROP CONSTRAINT IF EXISTS
vlak voor de ADD is er alleen omdat Postgres geen ADD CONSTRAINT IF NOT
EXISTS kent: samen zijn die twee statements herhaalbaar.

Draaiboek voor de eigenaar, na deze deploy:

    -- 1. Tel wat de constraint nog niet accepteert (verwacht: 0).
    SELECT stage, COUNT(*) FROM pipeline_entries
     WHERE stage IS NOT NULL
       AND stage NOT IN ('sourced','new','screening','interview','offer','placed','rejected')
     GROUP BY stage ORDER BY COUNT(*) DESC;

    -- 2. Alleen als stap 1 niets teruggeeft:
    ALTER TABLE pipeline_entries VALIDATE CONSTRAINT pipeline_entries_stage_check;

Stap 2 neemt een SHARE UPDATE EXCLUSIVE lock en scant de tabel; hij
blokkeert geen lezers en geen schrijvers van andere tabellen.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "043_pipeline_stage_check"

MIGRATION_SQL = """
UPDATE pipeline_entries SET stage = TRIM(LOWER(stage))
 WHERE stage IS NOT NULL AND stage <> TRIM(LOWER(stage));

UPDATE pipeline_entries SET stage = 'sourced' WHERE stage = '';

UPDATE pipeline_entries SET stage = 'new' WHERE stage IN ('applied', 'contacted', 'active');

UPDATE pipeline_entries SET stage = 'sourced' WHERE stage = 'suggested';

UPDATE pipeline_entries SET stage = 'interview' WHERE stage = 'interviewing';

UPDATE pipeline_entries SET stage = 'offer' WHERE stage = 'offered';

UPDATE pipeline_entries SET stage = 'placed' WHERE stage = 'hired';

UPDATE pipeline_entries SET stage = 'rejected' WHERE stage IN ('declined', 'afgewezen');

ALTER TABLE pipeline_entries DROP CONSTRAINT IF EXISTS pipeline_entries_stage_check;

ALTER TABLE pipeline_entries ADD CONSTRAINT pipeline_entries_stage_check
    CHECK (stage IN ('sourced', 'new', 'screening', 'interview', 'offer', 'placed', 'rejected'))
    NOT VALID;
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))

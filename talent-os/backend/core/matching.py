"""
Talent OS — de matchscore-schaal en de suggestiedrempel, op één plek.

`matches.match_score` staat overal op de 0-100-schaal, terwijl
services/matcher.py intern met cosinusgelijkenis op 0-1 rekent en bij het
opslaan vermenigvuldigt (`round(score * 100, 2)`). Die twee getallen
horen bij elkaar en horen in een module te staan die iedereen mag
importeren: `routers/matches.py` (de schrijver), `services/matcher.py` (de
rekenaar) en `services/scheduler.py`'s job_alert_job (een lezer) hadden
ze anders alle drie nodig, terwijl alleen routers/* ze kende -- waardoor
de twee services ze met een lazy import in de functie moesten ophalen om
de importcyclus (routers importeren services) te ontwijken. Een constante
in core/ heeft dat probleem niet: core/ importeert niets uit routers/ of
services/.

MATCH_SUGGESTION_MIN_SCORE is de drempel waaronder de matcher een
kandidaat helemaal niet als 'suggested' wegschrijft;
MATCH_SUGGESTION_MIN_STORED_SCORE is diezelfde drempel op de schaal zoals
hij in de kolom staat. services/scheduler.py's job_alert_job leest die
tweede: een kandidaat krijgt alleen een alert over matches die minstens
zo goed zijn als wat deze codebase zelf een suggestie durft te noemen --
geen apart, verzonnen getal.

Wat die ondergrens NIET is: hij is geen poort op wat er in de kolom komt.
POST /api/matches (een externe routine achter dezelfde X-API-Key) schrijft
elke `match_score` weg die de aanroeper meestuurt, ook 1.0, en niets
weigert dat. De ondergrens zit uitsluitend aan de LEESKANT, in
services/scheduler.py's JOB_ALERT_MATCHES_SQL en in matcher.py's eigen
filter: zo'n rij bestaat, is zichtbaar in het admin-paneel, en telt alleen
niet mee voor een alert. Wie wil dat hij ook niet wordt opgeslagen, moet
dat in routers/matches.py's create_match afdwingen -- dat is een aparte
keuze en die is niet gemaakt.
"""

MATCH_SCORE_SCALE = 100
MATCH_SUGGESTION_MIN_SCORE = 0.3
MATCH_SUGGESTION_MIN_STORED_SCORE = MATCH_SUGGESTION_MIN_SCORE * MATCH_SCORE_SCALE

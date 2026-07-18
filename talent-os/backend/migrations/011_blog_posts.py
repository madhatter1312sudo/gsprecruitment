"""
Talent OS — Schema migration: blog_posts table for the marketing blog
content pipeline (AI-drafted, human-approved via routers/blog_admin.py).

Seeds the 3 existing static blog posts (previously hardcoded HTML on the
public website) so the site can serve them dynamically, and seeds the
system_settings feature flag the weekly AI blog-drafting scheduler job
checks before running.
"""
import asyncio
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "011_blog_posts"

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS blog_posts (
    id              SERIAL PRIMARY KEY,
    slug            VARCHAR(200) UNIQUE NOT NULL,
    title_nl        VARCHAR(300),
    title_en        VARCHAR(300),
    excerpt_nl      TEXT,
    excerpt_en      TEXT,
    body_nl         TEXT,
    body_en         TEXT,
    tags            TEXT[],
    read_time_min   INT DEFAULT 5,
    status          VARCHAR(20) DEFAULT 'draft',
    ai_model        VARCHAR(100),
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    published_at    TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_blog_posts_status_published ON blog_posts(status, published_at);

INSERT INTO system_settings (key, value) VALUES
    ('blog_drafting_enabled', 'true')
ON CONFLICT (key) DO NOTHING;
"""

SEED_POSTS = [
    {
        "slug": "001-embedded-cpp-boom-brainport",
        "title_nl": """Waarom embedded C++ developers de goudmijn van de Brainport zijn""",
        "title_en": """Why Embedded C++ Developers Are the Gold Mine of the Brainport Region""",
        "excerpt_nl": """De vraag naar embedded C++ developers in de Brainport Eindhoven regio is explosief. Lees waarom deze specialisten zo schaars zijn en wat je eraan kunt doen.""",
        "excerpt_en": """Demand for embedded C++ developers in the Brainport Eindhoven region is exploding. Read why these specialists are so scarce and what you can do about it.""",
        "body_nl": """<p>In Brainport Eindhoven is embedded C++ geen niche meer. Het is een strategische competentie. Waar veel softwaremarkten bewegen richting snelle webstacks, low-code of cloud-native tooling, blijft de high-tech maakindustrie afhankelijk van mensen die begrijpen wat er gebeurt op milliseconde-niveau: geheugen, timing, interfaces, real-time gedrag, foutafhandeling en de interactie tussen software, elektronica en mechanica. Precies daarom zijn embedded C++ developers de goudmijn van de regio.</p>
<p>De schaarste is niet nieuw, maar hij voelt scherper dan ooit. ASML groeit door in lithografie en metrologie. Prodrive bouwt compacte, hoogperformante elektronica en embedded systemen voor markten waar betrouwbaarheid niet optioneel is. VDL ontwikkelt modules, voertuigen, automatisering en complexe productiesystemen. NTS levert high-precision systems waarin motion, control en software samenkomen. Elk van deze organisaties — en de tientallen suppliers eromheen — concurreert om een relatief kleine groep engineers die moderne C++ kunnen combineren met hardwarebegrip.</p>
<h2>Waarom juist embedded C++ zo schaars is</h2>
<p>Een goede embedded C++ developer is zelden “alleen programmeur”. De beste kandidaten kunnen lezen wat een datasheet impliceert, begrijpen waarom een race condition pas na drie uur testtijd zichtbaar wordt, en schrijven code die over jaren onderhoudbaar blijft. Ze werken met C++17 of C++20, maar hebben ook gevoel voor bare-metal constraints, embedded Linux, RTOS, device drivers, communication protocols, diagnostics, safety en performance profiling.</p>
<p>Die combinatie leer je niet in zes weken. Veel starters kiezen voor Python, JavaScript, data of cloud omdat de instap zichtbaarder is en de feedback sneller komt. Embedded vraagt geduld: debuggen met oscilloscopen, hardware-in-the-loop testopstellingen, cross-compilers, build pipelines, CI voor firmware, en soms documentatie die minder vriendelijk is dan een moderne API. Daardoor is de toevoer beperkt, terwijl de vraag in Brainport juist stijgt.</p>
<h3>De kern van het probleem</h3>
<p>Brainport-bedrijven zoeken geen generieke C++ developers. Ze zoeken engineers die softwarekwaliteit kunnen leveren in fysieke systemen waar fouten duur, zichtbaar en soms veiligheidskritisch zijn.</p>
<h2>Waarom ASML, Prodrive, VDL en NTS ze nodig hebben</h2>
<p>Bij ASML zit embedded software diep in de keten van motion control, sensoren, actuatoren, metrologie en systeemdiagnostiek. Een kleine verbetering in timing of stabiliteit kan op systeemniveau enorme waarde hebben. Bij Prodrive draait het vaak om compacte elektronica, automotive-grade kwaliteit, high-performance computing en industrial control: software moet efficiënt, robuust en produceerbaar zijn.</p>
<p>VDL heeft embedded expertise nodig in voertuigen, modules, charging, manufacturing automation en mechatronische systemen. NTS werkt aan high-tech modules waar precisie, reproduceerbaarheid en lifecycle management belangrijk zijn. In al deze omgevingen is software geen laagje bovenop het product; software is onderdeel van het product. Een vacature blijft dus niet alleen “open” staan. Een open embedded vacature kan een roadmap vertragen, testcapaciteit blokkeren of een systeemarchitect dwingen zelf ontwikkelwerk te blijven doen.</p>
<h2>Wat hiring managers vandaag anders moeten doen</h2>
<p>De markt vraagt om meer dan een vacaturetekst online zetten. Embedded C++ specialisten zijn vaak niet actief zoekend. Ze worden benaderd door meerdere bedrijven, maar reageren alleen wanneer de inhoud klopt en het proces professioneel voelt.</p>
<ul><li><strong>Maak de technische uitdaging concreet.</strong> Noem het product, de constraints, de stack, de testomgeving en de impact van de rol. “Je werkt aan innovatieve systemen” is te vaag.</li><li><strong>Verkort het proces.</strong> Twee gesprekken en een gerichte technische verdieping werken beter dan vijf losse rondes. Goede kandidaten zijn snel van de markt.</li><li><strong>Laat engineers vroeg meepraten.</strong> Een senior kandidaat wil sparren over architectuur, kwaliteit en trade-offs. HR-only gesprekken missen vaak overtuigingskracht.</li><li><strong>Wees realistisch over must-haves.</strong> C++, embedded Linux, RTOS, Python tooling, safety, Dutch language, specifieke sectorervaring én vijf jaar in dezelfde niche is meestal te smal.</li><li><strong>Verkoop het team, niet alleen het merk.</strong> ASML, Prodrive, VDL en NTS hebben sterke namen, maar kandidaten kiezen uiteindelijk voor autonomie, technische diepgang en de mensen met wie ze bouwen.</li></ul>
<h2>Retentie begint vóór het aanbod</h2>
<p>In deze markt is hiring slechts de helft van de opdracht. Retentie begint bij een eerlijke intake: wat gaat iemand echt doen, hoeveel legacy is er, hoeveel architectuurvrijheid bestaat er, en hoe volwassen zijn build, test en release? Kandidaten prikken snel door te rooskleurige verhalen heen. Transparantie verlaagt misschien het aantal sollicitanten, maar verhoogt de kwaliteit van de match.</p>
<p>Voor hiring managers betekent dat: durf scherp te kiezen. Zoek je iemand die diep in device drivers duikt, of iemand die embedded applicaties bouwt bovenop Linux? Heb je een maintainer nodig voor bestaande code, of een architect voor een nieuw platform? Hoe duidelijker de opdracht, hoe beter de sourcing, screening en conversie.</p>
<p>Embedded C++ developers zijn de goudmijn van Brainport omdat zij de brug vormen tussen idee en fysiek werkend systeem. Wie ze wil aantrekken, moet ze benaderen als schaarse specialisten: inhoudelijk, snel, eerlijk en met respect voor hun vakmanschap.</p>""",
        "body_en": """<p>In Brainport Eindhoven, embedded C++ is no longer a niche. It is a strategic capability. While many software markets move toward web stacks, low-code, or cloud tooling, high-tech manufacturing still depends on people who understand millisecond-level memory, timing, interfaces, real-time behaviour, failure handling, and the interaction between software, electronics, and mechanics. That is why embedded C++ developers are the gold mine of the region.</p>
<p>The shortage is not new, but it feels sharper than ever. ASML grows in lithography and metrology. Prodrive builds compact, high-performance electronics for markets where reliability is not optional. VDL develops modules, vehicles, automation, and production systems. NTS delivers high-precision systems where motion, control, and software come together. Each organisation — and the suppliers around them — competes for a small group of engineers who combine modern C++ with hardware understanding.</p>
<h2>Why embedded C++ is so scarce</h2>
<p>A strong embedded C++ developer is rarely “just a programmer”. The best candidates can read what a datasheet implies, understand why a race condition appears only after hours of testing, and write code that remains maintainable for years. They work with C++17 or C++20, but also understand bare-metal constraints, embedded Linux, RTOS, device drivers, communication protocols, diagnostics, safety, and profiling.</p>
<p>You do not learn that combination in six weeks. Many graduates choose Python, JavaScript, data, or cloud because the entry point is more visible and feedback is faster. Embedded requires patience: debugging with oscilloscopes, hardware-in-the-loop setups, cross-compilers, firmware pipelines, CI for devices, and documentation that is often less friendly than a modern API. Supply is limited while demand in Brainport keeps increasing.</p>
<h3>The core problem</h3>
<p>Brainport companies are not looking for generic C++ developers. They need engineers who deliver software quality inside physical systems where mistakes are expensive, visible, and sometimes safety-critical.</p>
<h2>Why ASML, Prodrive, VDL, and NTS need them</h2>
<p>At ASML, embedded software sits deep inside motion control, sensors, actuators, metrology, and diagnostics. A small improvement in timing or stability can create enormous value at system level. At Prodrive, the challenge is often compact electronics, automotive-grade quality, high-performance computing, and industrial control: software must be efficient, robust, and producible.</p>
<p>VDL needs embedded expertise in vehicles, modules, charging, manufacturing automation, and mechatronic systems. NTS works on high-tech modules where precision, reproducibility, and lifecycle management matter. In all these environments, software is not a layer on top of the product; software is part of the product. An open vacancy therefore does not simply remain “open”. An unfilled embedded role can delay a roadmap, block test capacity, or force a system architect to keep doing development work that should be delegated.</p>
<h2>What hiring managers should do differently</h2>
<p>This market requires more than publishing a job description and waiting. Embedded C++ specialists are often not actively looking. They are approached by multiple companies, but they respond only when the technical substance is clear and the process feels professional.</p>
<ul><li><strong>Make the technical challenge concrete.</strong> Mention the product, constraints, stack, test environment, and impact of the role. “You will work on innovative systems” is too generic.</li><li><strong>Shorten the process.</strong> Two interviews and one focused technical deep dive usually work better than five separate rounds. Good candidates disappear quickly.</li><li><strong>Involve engineers early.</strong> Senior candidates want to discuss architecture, quality, and trade-offs. HR-only conversations often lack persuasive power.</li><li><strong>Be realistic about must-haves.</strong> C++, embedded Linux, RTOS, Python tooling, safety, Dutch language, specific sector experience, and five years in the same niche is often too narrow.</li><li><strong>Sell the team, not just the brand.</strong> ASML, Prodrive, VDL, and NTS have strong names, but candidates ultimately choose autonomy, technical depth, and the people they will build with.</li></ul>
<h2>Retention starts before the offer</h2>
<p>In this market, hiring is only half the challenge. Retention starts with an honest intake: what will the person really do, how much legacy exists, how much architectural freedom is available, and how mature are build, test, and release processes? Candidates quickly see through overly polished stories. Transparency may reduce the number of applicants, but it increases the quality of the match.</p>
<p>For hiring managers, that means making sharper choices. Do you need someone who goes deep into device drivers, or someone who builds embedded applications on top of Linux? Do you need a maintainer for existing code, or an architect for a new platform? The clearer the assignment, the better the sourcing, screening, and conversion.</p>
<p>Embedded C++ developers are the gold mine of Brainport because they form the bridge between an idea and a physically working system. If you want to attract them, treat them as scarce specialists: technically, quickly, honestly, and with respect for their craft.</p>""",
        "tags": ['embedded', 'C++', 'Brainport', 'recruitment', 'tech-talent'],
        "read_time_min": 5,
        "published_at": date(2026, 6, 26),
    },
    {
        "slug": "002-salaris-senior-software-engineer",
        "title_nl": """Wat verdient een senior software engineer in Eindhoven? Salarisbenchmark 2026""",
        "title_en": """What Does a Senior Software Engineer Earn in Eindhoven? Salary Benchmark 2026""",
        "excerpt_nl": """Een compleet overzicht van salarissen voor senior software engineers in de regio Eindhoven/Brainport. Inclusief data per specialisatie (embedded, C++, cloud, data).""",
        "excerpt_en": """A complete overview of salaries for senior software engineers in the Eindhoven/Brainport region. Including data per specialisation (embedded, C++, cloud, data).""",
        "body_nl": """<p><strong>Kort antwoord:</strong> een senior software engineer in Eindhoven verdient in 2026 meestal tussen <strong>€65.000 en €95.000 bruto per jaar</strong>. De exacte range hangt af van specialisatie, domeinkennis en of je werkt in high-tech hardware, cloud platforms of data/AI. Voor lead engineers en schaarse C++/real-time profielen loopt de markt richting €100k+.</p>
<p>Deze benchmark sluit aan op onze <a href="../kandidaten.html#salary">salary calculator</a>, gebaseerd op plaatsingen, marktgesprekken en actuele vraag. Eindhoven wijkt af door de Brainport-context: ASML, Prodrive, VDL, NTS, Sioux en suppliers concurreren om dezelfde senior engineers.</p>
<h2>Salarisdata senior software engineer Eindhoven 2026</h2>

<table>
<thead><tr><th>Rol / Role</th><th>P25</th><th>Mediaan / Median</th><th>P75</th><th>Top range</th></tr></thead>
<tbody>
<tr><td>Software Engineer</td><td>€65k</td><td>€74k</td><td>€82k</td><td>€90k</td></tr>
<tr><td>Embedded Software Engineer</td><td>€72k</td><td>€82k</td><td>€90k</td><td>€105k</td></tr>
<tr><td>Backend Developer</td><td>€68k</td><td>€77k</td><td>€85k</td><td>€98k</td></tr>
<tr><td>DevOps / Cloud Engineer</td><td>€75k</td><td>€85k</td><td>€95k</td><td>€110k</td></tr>
<tr><td>Data Engineer</td><td>€72k</td><td>€81k</td><td>€90k</td><td>€105k</td></tr>
<tr><td>Data Scientist / AI Engineer</td><td>€78k</td><td>€88k</td><td>€98k</td><td>€115k</td></tr>
</tbody>
</table>

<h2>Waarom embedded, cloud en data verschillend betalen</h2>
<p><strong>Embedded software</strong> betaalt in Eindhoven bovengemiddeld omdat software dicht tegen physics, mechatronica en real-time constraints aan zit. C++, Linux, RTOS, device drivers en safety-critical ervaring zijn schaars.</p>
<p><strong>Cloud en DevOps</strong> rollen zitten vaak hoger door platformverantwoordelijkheid: Kubernetes, Azure/AWS, CI/CD, security en reliability. <strong>Data engineers en AI engineers</strong> profiteren van manufacturing data, predictive maintenance en computer vision.</p>
<h2>De Brainport premium</h2>
<p>De Brainport premium is geen officieel percentage, maar voor senior nicheprofielen zien we vaak <strong>5–15% boven landelijke medianen</strong>. High-tech werkgevers hebben complexe systemen en weinig ruimte voor hiring mistakes; domeinervaring levert dus sterkere aanbiedingen op.</p>
<p>Kijk niet alleen naar basissalaris. €82k met sterke pensioenbijdrage, opleidingsbudget en hybride vrijheid kan beter zijn dan €88k zonder secundaire voorwaarden.</p>""",
        "body_en": """<p><strong>Short answer:</strong> a senior software engineer in Eindhoven typically earns between <strong>€65,000 and €95,000 gross per year</strong> in 2026. The range depends on specialisation, domain knowledge, and whether you work in high-tech hardware, cloud platforms, or data/AI. Lead engineers and scarce C++/real-time profiles move toward €100k+.</p>
<p>This benchmark connects to our <a href="../kandidaten.html#salary">salary calculator</a>, based on placements, market conversations, and current demand. Eindhoven differs because of Brainport: ASML, Prodrive, VDL, NTS, Sioux, and suppliers compete for the same senior engineers.</p>
<h2>Senior software engineer salary data Eindhoven 2026</h2>

<table>
<thead><tr><th>Rol / Role</th><th>P25</th><th>Mediaan / Median</th><th>P75</th><th>Top range</th></tr></thead>
<tbody>
<tr><td>Software Engineer</td><td>€65k</td><td>€74k</td><td>€82k</td><td>€90k</td></tr>
<tr><td>Embedded Software Engineer</td><td>€72k</td><td>€82k</td><td>€90k</td><td>€105k</td></tr>
<tr><td>Backend Developer</td><td>€68k</td><td>€77k</td><td>€85k</td><td>€98k</td></tr>
<tr><td>DevOps / Cloud Engineer</td><td>€75k</td><td>€85k</td><td>€95k</td><td>€110k</td></tr>
<tr><td>Data Engineer</td><td>€72k</td><td>€81k</td><td>€90k</td><td>€105k</td></tr>
<tr><td>Data Scientist / AI Engineer</td><td>€78k</td><td>€88k</td><td>€98k</td><td>€115k</td></tr>
</tbody>
</table>

<h2>Why embedded, cloud, and data pay differently</h2>
<p><strong>Embedded software</strong> pays above average in Eindhoven because software sits close to physics, mechatronics, and real-time constraints. C++, Linux, RTOS, device driver, and safety-critical experience are scarce.</p>
<p><strong>Cloud and DevOps</strong> roles often sit higher because of platform responsibility: Kubernetes, Azure/AWS, CI/CD, security, and reliability. <strong>Data engineers and AI engineers</strong> benefit from manufacturing data, predictive maintenance, and computer vision.</p>
<h2>The Brainport premium</h2>
<p>The Brainport premium is not official, but for senior niche profiles we often see <strong>5–15% above national medians</strong>. High-tech employers have complex systems and little room for hiring mistakes; domain experience drives stronger offers.</p>
<p>Do not evaluate base salary only. An €82k offer with strong pension contribution, training budget, and hybrid flexibility can beat €88k without benefits.</p>""",
        "tags": ['salaris', 'salary', 'software-engineer', 'Eindhoven', 'benchmark', '2026'],
        "read_time_min": 4,
        "published_at": date(2026, 6, 23),
    },
    {
        "slug": "003-brainport-tech-ecosysteem",
        "title_nl": """Navigeren in het Brainport tech ecosysteem: een gids voor hiring managers""",
        "title_en": """Navigating the Brainport Tech Ecosystem: A Guide for Hiring Managers""",
        "excerpt_nl": """ASML, Prodrive, VDL, NTS, Sioux, TNO — het Brainport ecosysteem is uniek in Europa. Hoe vind en behoud je toptalent in deze competitieve markt?""",
        "excerpt_en": """ASML, Prodrive, VDL, NTS, Sioux, TNO — the Brainport ecosystem is unique in Europe. How do you find and retain top talent in this competitive market?""",
        "body_nl": """<p>De Brainport Eindhoven regio is een van de meest geconcentreerde hightech ecosystemen van Europa. Maar voor hiring managers die nieuw zijn in de regio — of zelfs voor wie hier al jaren werft — kan de structuur ondoorzichtig aanvoelen. Wie concurreert met wie? Waar stroomt het talent naartoe? En hoe positioneer je jouw bedrijf om de beste embedded en C++ engineers aan te trekken?</p>
<p>In deze gids ontrafel ik de drie zones van Brainport, leg ik de talentdynamiek uit die elke laag definieert, en geef ik praktisch advies over positionering, employer branding en de cruciale rol van de 30%-regeling voor internationaal talent.</p>
<h2>Zone A: De Ankers — ASML &amp; NXP</h2>
<p>Aan de top van het ecosysteem zitten de wereldspelers. <strong>ASML</strong> — wellicht het meest strategisch belangrijke techbedrijf van Europa — en <strong>NXP Semiconductors</strong> zijn de zwaartekrachtcentra van Brainport. Samen werken er tienduizenden engineers en bepalen zij de benchmark voor beloning, projectcomplexiteit en carrièregroei.</p>
<p><strong>Talentdynamiek:</strong> ASML en NXP trekken een gestage stroom topafgestudeerden aan van de TU Eindhoven en andere universiteiten. Engineers werken hier aan baanbrekende lithografie en chipontwerp — de soort projecten die een CV definiëren en moeilijk te evenaren zijn. De keerzijde? Bureaucratie, vergadercultuur en trage besluitvorming zorgen voor een constante uitstroom van medior en senior engineers na 3–5 jaar.</p>
<p><strong>Kans voor jou:</strong> Die uitstroom is <em>jouw</em> talentpool. Engineers die ASML en NXP verlaten zijn goed opgeleid, gewend aan hoge standaarden en vaak op zoek naar meer eigenaarschap, snellere iteratie en een nauwere band met het product. Als je dát kunt bieden — en dat kenbaar maakt — is dit de rijkste bron van vooraf gescreend senior talent in de regio.</p>
<h2>Zone B: De Research &amp; Engineering-krachtpatsers — TNO, Sioux, VDL</h2>
<p>De middenlaag bestaat uit organisaties die deep-tech research combineren met hoogwaardige engineering. <strong>TNO</strong> werkt aan alles van fotonica tot quantum. <strong>Sioux</strong> is een hoogwaardig embedded &amp; software development house dat complexe systemen bouwt voor OEM's. <strong>VDL Groep</strong> is een productie- en technologiegigant met diepe wortels in Brainport.</p>
<p><strong>Talentdynamiek:</strong> Engineers in Zone B hebben doorgaans een diepe technische specialisatie. Sioux bijvoorbeeld werkt aan tientallen projecten per jaar, wat engineers blootstelling geeft aan zeer verschillende stacks en domeinen. VDL trekt productie- en mechatronicatalent aan. TNO trekt PhD-level onderzoekers aan die toegepaste wetenschap willen zonder Nederland te verlaten. Deze engineers zijn technisch diep, vaak polyglot (C++, C#, Python, FPGA) en zeer gewild.</p>
<p><strong>Kans voor jou:</strong> Zone B-talent waardeert technische uitdaging boven alles. Ze vertrekken voor een rol die interessantere problemen biedt — niet alleen meer geld. Als jouw bedrijf aan écht lastige engineeringuitdagingen werkt (real-time systemen, embedded Linux, computer vision, motion control), maak dat dan het middelpunt van je pitch.</p>
<h2>Zone C: De Hightech-uitdagers — Prodrive, NTS, Neways, KMWE, Simac</h2>
<p>De derde zone bestaat uit bedrijven die kleiner, wendbaarder en vaak gretiger zijn. <strong>Prodrive Technologies</strong> bouwt hightech elektronica en software voor missiekritische systemen. <strong>NTS</strong> ontwikkelt en produceert mechatronische systemen en modules. <strong>Neways</strong> is een EMS-leider. <strong>KMWE</strong> specialiseert in hoogprecisieproductie. <strong>Simac</strong> is een brede ICT- en tech-dienstverlener.</p>
<p><strong>Talentdynamiek:</strong> Deze bedrijven concurreren direct met elkaar om dezelfde embedded talentpool. Omdat ze kleiner zijn dan ASML/NXP, kunnen ze meer eigenaarschap en snellere carrièregroei bieden. Maar ze staan voor dezelfde talenttekorten: embedded C++ engineers met 3–7 jaar ervaring zijn het moeilijkst in te vullen profiel in de hele Brainport regio. Een senior embedded engineer kan hier rekenen op 3–5 inkomende recruiterberichten per week op LinkedIn.</p>
<p><strong>Kans voor jou:</strong> Als je concurreert in Zone C, zijn snelheid en authenticiteit je wapens. De beste kandidaten zijn off-market — ze solliciteren niet op jobboards. Je hebt een gerichte, relatiegebaseerde aanpak nodig. Een generieke functieomschrijving is niet genoeg. Je moet laten zien dat je begrijpt wat embedded engineers motiveert: echte technische uitdagingen, moderne tooling, een cultuur van technische excellentie en een helder groeipad.</p>
<h2>Hoe positioneer je jouw bedrijf voor embedded/C++ talent</h2>
<p>Op basis van honderden gesprekken met embedded engineers in alle drie de zones, hier wat hun beslissingen écht stuurt:</p>
<ol><li><strong>Technische inhoud staat voorop.</strong> Embedded engineers geven veel om de stack, de tools en de engineeringcultuur. Als je nog op C++03 zit zonder moderne tooling, of je code review-proces bestaat niet, dan lopen de beste engineers weg — ongeacht het salaris.</li><li><strong>Eigenaarschap is belangrijker dan titel.</strong> Engineers die Zone A verlaten noemen gebrek aan eigenaarschap als hun voornaamste frustratie. Beloof echte autonomie over subsystemen of features, en je valt op.</li><li><strong>Wees transparant over de 30%-regeling.</strong> Voor internationale kandidaten is de 30%-regeling vaak een dealbreaker. Dit belastingvoordeel — dat gekwalificeerde expats in staat stelt om 30% van hun salaris belastingvrij te ontvangen tot 5 jaar — is een van Nederlands sterkste wervingsassets. Als jouw bedrijf dit niet actief ondersteunt, sluit je een enorme talentpool uit. Zorg dat jouw wervingsproces begeleiding bij de 30%-regeling-aanvraag omvat, zelfs als je het niet zelf afhandelt.</li><li><strong>Toon, vertel niet.</strong> De beste manier om technisch talent aan te trekken is door technische geloofwaardigheid te tonen. Open-source projecten, tech talks, engineering blogs en whitepapers zijn belangrijker dan glossy employer branding campagnes.</li></ol>
<h2>Waarom de 30%-regeling belangrijker is dan ooit</h2>
<p>De 30%-regeling is al jaren een hoeksteen van Nederlands vermogen om internationaal tech talent aan te trekken. Voor embedded en C++ rollen — waar de binnenlandse talentpool simpelweg niet aan de vraag kan voldoen — is het geen nice-to-have; het is een concurrentiële noodzaak.</p>
<p>Hier is wat elke hiring manager moet weten:</p>
<ul><li><strong>Het voordeel:</strong> Tot 30% van het salaris belastingvrij voor maximaal 5 jaar. Dit kan €15.000–€30.000 extra netto inkomen per jaar betekenen voor een senior engineer.</li><li><strong>Voorwaarden:</strong> De kandidaat moet uit het buitenland zijn geworven en specifieke expertise hebben die niet direct in Nederland beschikbaar is. Een MSc of PhD in een technisch veld van een kwalificerende universiteit vereenvoudigt het proces.</li><li><strong>Rol van de werkgever:</strong> Je moet samen met de werknemer een aanvraag indienen bij de Belastingdienst. Sommige bedrijven besteden dit uit aan een expat-services bureau. Hoe dan ook, een duidelijk, ondersteund proces laat zien dat je een internationaal-vriendelijke werkgever bent.</li></ul>
<p>Als je embedded of C++ rollen wilt invullen en niet actief internationaal werft, concurreren je met één hand op je rug. De beste hiring managers in Brainport combineren een sterk binnenlands netwerk met een duidelijke waardepropositie voor internationaal talent — inclusief 30%-regeling ondersteuning, verhuisbegeleiding en hulp bij huisvesting.</p>
<h2>Alles op een rij</h2>
<p>Het Brainport ecosysteem is geen monoliet. Het is een gelaagd, dynamisch systeem waar talent stroomt van de grote ankers naar onderzoekshuizen naar wendbare uitdagers — en weer terug. Het begrijpen van deze stromen is de eerste stap naar een wervingsstrategie die werkt.</p>
<p>De bedrijven die de beste embedded en C++ talenten in Brainport binnenhalen, delen drie dingen: ze begrijpen de technische motivaties van hun kandidaten, ze bewegen snel in een krappe markt, en ze presenteren een duidelijk, authentiek werkgeversmerk dat hen onderscheidt van de ASML's en NXP's van de wereld.</p>""",
        "body_en": """<p>The Brainport Eindhoven region is one of the most concentrated high-tech ecosystems in Europe. But for hiring managers who are new to the region — or even for those who have been recruiting here for years — the structure can feel opaque. Who competes with whom? Where does the talent flow? And how do you position your company to win the best embedded and C++ engineers?</p>
<p>In this guide, I'll break down the three zones of Brainport, explain the talent dynamics that define each layer, and give you practical advice on positioning, employer branding, and the crucial role of the 30% ruling for international talent.</p>
<h2>Zone A: The Anchors — ASML &amp; NXP</h2>
<p>At the top of the ecosystem sit the global players. <strong>ASML</strong> — arguably the most strategically important tech company in Europe — and <strong>NXP Semiconductors</strong> are the gravitational centres of Brainport. Together, they employ tens of thousands of engineers and set the benchmark for compensation, project complexity, and career growth.</p>
<p><strong>Talent dynamic:</strong> ASML and NXP attract a steady stream of top graduates from TU Eindhoven and other universities. Engineers here work on cutting-edge lithography and chip design — the kind of resume-defining projects that are hard to match. The flip side? Bureaucracy, meeting culture, and slower decision-making drive a constant outflow of mid-level and senior engineers after 3–5 years.</p>
<p><strong>Opportunity for you:</strong> That outflow is <em>your</em> talent pool. Engineers leaving ASML and NXP are well-trained, accustomed to high standards, and often looking for more ownership, faster iteration, and a closer connection to the product. If you can offer those things — and you make it known — this is the richest source of pre-vetted senior talent in the region.</p>
<h2>Zone B: The Research &amp; Engineering Powerhouses — TNO, Sioux, VDL</h2>
<p>The middle layer consists of organisations that combine deep-tech research with high-end engineering. <strong>TNO</strong> (the Netherlands Organisation for Applied Scientific Research) works on everything from photonics to quantum. <strong>Sioux</strong> is a high-end embedded &amp; software development house that builds complex systems for OEMs. <strong>VDL Groep</strong> is a manufacturing and technology giant with deep roots in Brainport.</p>
<p><strong>Talent dynamic:</strong> Engineers in Zone B typically have deep technical specialisation. Sioux, for example, works across dozens of projects per year, giving its engineers exposure to vastly different stacks and domains. VDL attracts manufacturing and mechatronics talent. TNO pulls in PhD-level researchers who want applied science without leaving the Netherlands. These engineers are technically deep, often polyglot (C++, C#, Python, FPGA), and highly sought after.</p>
<p><strong>Opportunity for you:</strong> Zone B talent values technical challenge above all else. They will leave for a role that promises more interesting problems — not just more money. If your company works on genuinely hard engineering challenges (real-time systems, embedded Linux, computer vision, motion control), make that the centrepiece of your pitch.</p>
<h2>Zone C: The High-Tech Challengers — Prodrive, NTS, Neways, KMWE, Simac</h2>
<p>The third zone comprises companies that are smaller, more agile, and often hungrier. <strong>Prodrive Technologies</strong> builds high-tech electronics and software for mission-critical systems. <strong>NTS</strong> develops and produces mechatronic systems and modules. <strong>Neways</strong> is an EMS (Electronic Manufacturing Services) leader. <strong>KMWE</strong> specialises in high-precision manufacturing. <strong>Simac</strong> is a broad ICT and tech services group.</p>
<p><strong>Talent dynamic:</strong> These companies compete directly with each other for the same embedded talent pool. Because they're smaller than ASML/NXP, they can offer more ownership and faster career progression. But they also face the same talent shortages: embedded C++ engineers with 3–7 years of experience are the hardest profile to fill in the entire Brainport region. A senior embedded engineer here can reasonably expect to receive 3–5 inbound recruiter messages per week on LinkedIn.</p>
<p><strong>Opportunity for you:</strong> If you're competing in Zone C, speed and authenticity are your weapons. The best candidates are off-market — they're not applying to job boards. You need a targeted, relationship-based approach. A generic JD won't cut it. You need to show that you understand what motivates embedded engineers: real technical challenges, modern tooling, a culture of engineering excellence, and a clear growth path.</p>
<h2>How to Position Your Company for Embedded/C++ Talent</h2>
<p>Based on hundreds of conversations with embedded engineers across all three zones, here is what actually drives their decisions:</p>
<ol><li><strong>Technical substance comes first.</strong> Embedded engineers care deeply about the stack, the tools, and the engineering culture. If you're still on C++03 without modern tooling, or your code review process is non-existent, the best engineers will walk — regardless of salary.</li><li><strong>Ownership matters more than title.</strong> Engineers leaving Zone A often cite a lack of ownership as their primary frustration. Promise real autonomy over subsystems or features, and you'll stand out.</li><li><strong>Be transparent about the 30% ruling.</strong> For international candidates, the 30% ruling is often a dealbreaker. This tax advantage — which allows qualifying expats to receive 30% of their salary tax-free for up to 5 years — is one of the Netherlands' strongest recruiting assets. If your company doesn't actively support it, you're excluding a huge talent pool. Make sure your recruitment process includes guidance on the 30% ruling application, even if you don't handle it yourself.</li><li><strong>Show, don't tell.</strong> The best way to attract technical talent is to demonstrate technical credibility. Open-source projects, tech talks, engineering blogs, and white papers matter more than glossy employer branding campaigns.</li></ol>
<h2>Why the 30% Ruling Matters More Than Ever</h2>
<p>The 30% ruling has been a cornerstone of the Netherlands' ability to attract international tech talent. For embedded and C++ roles — where the domestic talent pool simply cannot meet demand — it's not a nice-to-have; it's a competitive necessity.</p>
<p>Here's what every hiring manager should know:</p>
<ul><li><strong>The benefit:</strong> Up to 30% of salary paid tax-free for a maximum of 5 years (recently reduced from 30% to 27% for 2025, then 30% again — check current rates). This can mean €15,000–€30,000 extra net income per year for a senior engineer.</li><li><strong>Eligibility:</strong> The candidate must have been recruited from abroad and have specific expertise not readily available in the Netherlands. A MSc or PhD in a technical field from a qualifying university simplifies the process.</li><li><strong>Employer role:</strong> You need to apply to the Dutch tax authority (Belastingdienst) together with the employee. Some companies outsource this to an expat services firm. Either way, having a clear, supported process signals that you're an international-friendly employer.</li></ul>
<p>If you're hiring for embedded or C++ roles and not actively recruiting internationally, you're competing with one hand tied behind your back. The best hiring managers in Brainport combine a strong domestic network with a clear value proposition for international talent — including 30% ruling support, relocation assistance, and housing guidance.</p>
<h2>Bringing It Together</h2>
<p>The Brainport ecosystem is not a monolith. It's a layered, dynamic system where talent flows from the large anchors to mid-tier research houses to agile challengers — and back again. Understanding these flows is the first step to building a recruitment strategy that works.</p>
<p>The companies that win the best embedded and C++ talent in Brainport share three things: they understand the technical motivations of their candidates, they move fast in a tight market, and they present a clear, authentic employer brand that differentiates them from the ASMLs and NXPs of the world.</p>""",
        "tags": ['Brainport', 'Eindhoven', 'hightech', 'ecosysteem', 'hiring', 'recruitment'],
        "read_time_min": 6,
        "published_at": date(2026, 6, 20),
    },
]


async def seed_blog_posts():
    """Seed the 3 existing static blog posts as published rows. Idempotent
    via ON CONFLICT (slug) DO NOTHING -- safe to re-run."""
    import asyncpg

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    db = os.getenv("POSTGRES_DB", "recruitment_db")
    user = os.getenv("POSTGRES_USER", "talentos_admin")
    password = os.getenv("POSTGRES_PASSWORD", "")

    conn = await asyncpg.connect(host=host, port=port, database=db, user=user, password=password)
    try:
        for post in SEED_POSTS:
            await conn.execute(
                """INSERT INTO blog_posts
                   (slug, title_nl, title_en, excerpt_nl, excerpt_en, body_nl, body_en,
                    tags, read_time_min, status, published_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'published', $10)
                   ON CONFLICT (slug) DO NOTHING""",
                post["slug"], post["title_nl"], post["title_en"],
                post["excerpt_nl"], post["excerpt_en"],
                post["body_nl"], post["body_en"],
                post["tags"], post["read_time_min"], post["published_at"],
            )
        print(f"Seeded {len(SEED_POSTS)} blog posts (ON CONFLICT DO NOTHING).")
    finally:
        await conn.close()


async def main():
    await run_migration(VERSION, MIGRATION_SQL)
    await seed_blog_posts()


if __name__ == "__main__":
    asyncio.run(main())

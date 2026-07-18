"""
Talent OS — Schema migration: mobile app growth features (M0).

Adds:
  - push_tokens: Expo/FCM/APNs push tokens per user, for the mobile app.
  - client_prospects: Apollo-sourced client leads for BD/growth outreach.
  - quiz_questions + quiz_submissions: the public technical skill quiz used
    as a lead-gen / growth funnel on the marketing site and mobile app.

Also seeds:
  - 24 hand-written, technically-verified quiz questions (9 embedded_cpp,
    5 general_swe, 5 cloud_devops, 5 security).
  - One internal "GSP Talent Pool" client + 6 realistic open Brainport
    vacancies, so the mobile app has real data to show candidates before
    the first real client job orders land in the pipeline.

All seed steps are idempotent (safe to re-run): rows are looked up by a
natural key before inserting.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "012_mobile_growth"

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS push_tokens (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token           VARCHAR(400) NOT NULL,
    platform        VARCHAR(20),
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (user_id, token)
);

CREATE INDEX IF NOT EXISTS idx_push_tokens_user ON push_tokens(user_id);

CREATE TABLE IF NOT EXISTS client_prospects (
    id                  SERIAL PRIMARY KEY,
    company_name        VARCHAR(255) NOT NULL,
    domain              VARCHAR(255),
    contact_name        VARCHAR(255),
    contact_title       VARCHAR(255),
    contact_email       VARCHAR(255),
    contact_linkedin    VARCHAR(500),
    location            VARCHAR(255),
    industry            VARCHAR(255),
    source              VARCHAR(50) DEFAULT 'apollo',
    intent_signal       TEXT,
    status              VARCHAR(20) DEFAULT 'new',
    created_at          TIMESTAMP DEFAULT NOW(),
    UNIQUE (company_name, contact_email)
);

CREATE INDEX IF NOT EXISTS idx_client_prospects_status ON client_prospects(status);

CREATE TABLE IF NOT EXISTS quiz_questions (
    id              SERIAL PRIMARY KEY,
    domain          VARCHAR(50) NOT NULL,
    difficulty      INTEGER NOT NULL,
    question_nl     TEXT,
    question_en     TEXT,
    options_nl      JSONB NOT NULL,
    options_en      JSONB NOT NULL,
    correct_index   INTEGER NOT NULL,
    explanation_nl  TEXT,
    explanation_en  TEXT,
    active          BOOLEAN DEFAULT TRUE,
    CONSTRAINT chk_quiz_domain CHECK (domain IN ('embedded_cpp', 'general_swe', 'cloud_devops', 'security')),
    CONSTRAINT chk_quiz_difficulty CHECK (difficulty IN (1, 2, 3)),
    CONSTRAINT chk_quiz_correct_index CHECK (correct_index BETWEEN 0 AND 3)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_quiz_questions_dedup ON quiz_questions (domain, question_nl);
CREATE INDEX IF NOT EXISTS idx_quiz_questions_domain_active ON quiz_questions(domain, active);

CREATE TABLE IF NOT EXISTS quiz_submissions (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(255),
    user_id         INTEGER REFERENCES users(id) ON DELETE SET NULL,
    answers         JSONB NOT NULL,
    score           INTEGER,
    max_score       INTEGER,
    tier            VARCHAR(20),
    domain_scores   JSONB,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_quiz_submissions_email ON quiz_submissions(email);
CREATE INDEX IF NOT EXISTS idx_quiz_submissions_user ON quiz_submissions(user_id);
"""


# ── Quiz questions (technically verified — see explanation_nl/en for the
#    reasoning behind each correct_index) ───────────────────────────────

SEED_QUESTIONS = [
    # ── embedded_cpp (9): pointers/references, RAII, ISR constraints,
    #    RTOS priority inversion, volatile, memory alignment, smart
    #    pointers, move semantics, stack vs heap on MCU ─────────────────
    {
        "domain": "embedded_cpp", "difficulty": 1,
        "question_nl": "Wat is een fundamenteel verschil tussen een pointer en een reference in C++?",
        "question_en": "What is a fundamental difference between a pointer and a reference in C++?",
        "options_nl": [
            "Een reference kan null zijn, een pointer niet",
            "Een reference moet bij declaratie geïnitialiseerd worden en kan daarna niet naar een ander object 'verwijzen' (rebind); een pointer kan wel worden aangepast",
            "Een pointer neemt altijd meer geheugen in beslag dan een reference",
            "Een reference ondersteunt pointer-arithmetic, een pointer niet",
        ],
        "options_en": [
            "A reference can be null, a pointer cannot",
            "A reference must be initialized at declaration and can never be rebound to another object afterwards; a pointer can be reassigned",
            "A pointer always takes up more memory than a reference",
            "A reference supports pointer arithmetic, a pointer does not",
        ],
        "correct_index": 1,
        "explanation_nl": "Een reference moet direct geïnitialiseerd worden en verwijst voor de rest van zijn levensduur naar hetzelfde object. Een pointer is een aparte variabele die een adres bevat: hij kan worden herwezen, op null gezet, en gebruikt voor pointer-arithmetic.",
        "explanation_en": "A reference must be initialized immediately and refers to the same object for its entire lifetime. A pointer is a separate variable holding an address: it can be reassigned, set to null, and used in pointer arithmetic.",
    },
    {
        "domain": "embedded_cpp", "difficulty": 1,
        "question_nl": "Waarom is het op een resource-constrained microcontroller vaak beter om dynamische heap-allocatie (new/malloc) te vermijden?",
        "question_en": "Why is it often better on a resource-constrained microcontroller to avoid dynamic heap allocation (new/malloc)?",
        "options_nl": [
            "Heap-allocatie is altijd langzamer dan een for-lus",
            "De heap bestaat niet op microcontrollers",
            "Heap-fragmentatie en niet-deterministische allocatietijd kunnen leiden tot geheugenuitputting en onvoorspelbaar timing-gedrag in een systeem met weinig RAM",
            "De compiler verwijdert automatisch alle heap-allocaties in release builds",
        ],
        "options_en": [
            "Heap allocation is always slower than a for-loop",
            "The heap does not exist on microcontrollers",
            "Heap fragmentation and non-deterministic allocation time can cause memory exhaustion and unpredictable timing behaviour on a low-RAM system",
            "The compiler automatically strips all heap allocations in release builds",
        ],
        "correct_index": 2,
        "explanation_nl": "Op MCU's met weinig, vaak niet-geheralloceerde RAM leidt heap-gebruik over tijd tot fragmentatie en kan de allocatietijd variëren, wat problematisch is voor real-time garanties. Stack-allocatie (of static allocatie) is deterministisch en heeft geen fragmentatierisico.",
        "explanation_en": "On MCUs with little, rarely-reclaimed RAM, heap use fragments over time and allocation time can vary, which is problematic for real-time guarantees. Stack (or static) allocation is deterministic and carries no fragmentation risk.",
    },
    {
        "domain": "embedded_cpp", "difficulty": 1,
        "question_nl": "Wat doet het `volatile` keyword in embedded C++?",
        "question_en": "What does the `volatile` keyword do in embedded C++?",
        "options_nl": [
            "Het maakt een variabele thread-safe",
            "Het vertelt de compiler dat de waarde buiten de normale programmaflow kan veranderen (bv. door hardware of een ISR), waardoor optimalisaties die reads/writes verwijderen of cachen worden voorkomen",
            "Het plaatst de variabele automatisch in flash-geheugen in plaats van RAM",
            "Het zorgt ervoor dat de variabele atomisch wordt gelezen en geschreven",
        ],
        "options_en": [
            "It makes a variable thread-safe",
            "It tells the compiler the value may change outside normal program flow (e.g. via hardware or an ISR), preventing optimizations that would cache or eliminate reads/writes",
            "It automatically places the variable in flash memory instead of RAM",
            "It guarantees the variable is read and written atomically",
        ],
        "correct_index": 1,
        "explanation_nl": "`volatile` voorkomt alleen compiler-optimalisaties rond geheugentoegang; het garandeert geen atomiciteit en geen thread-safety. Voor dat laatste zijn atomics of expliciete synchronisatie nodig.",
        "explanation_en": "`volatile` only prevents compiler optimizations around memory access; it does not guarantee atomicity or thread-safety. For that, atomics or explicit synchronization are required.",
    },
    {
        "domain": "embedded_cpp", "difficulty": 2,
        "question_nl": "Wat is het kernprincipe van RAII (Resource Acquisition Is Initialization) in C++?",
        "question_en": "What is the core principle of RAII (Resource Acquisition Is Initialization) in C++?",
        "options_nl": [
            "Resources worden verkregen in de constructor en gegarandeerd vrijgegeven in de destructor, gekoppeld aan de levensduur (scope) van het object",
            "Alle resources moeten globaal worden gealloceerd bij het opstarten van het programma",
            "RAII is een garbage collector die periodiek ongebruikt geheugen opruimt",
            "RAII vereist dat je expliciet delete aanroept aan het einde van elke functie",
        ],
        "options_en": [
            "Resources are acquired in the constructor and guaranteed to be released in the destructor, tied to the object's scope/lifetime",
            "All resources must be allocated globally at program startup",
            "RAII is a garbage collector that periodically frees unused memory",
            "RAII requires you to explicitly call delete at the end of every function",
        ],
        "correct_index": 0,
        "explanation_nl": "RAII koppelt resourcebeheer aan objectlevensduur: zodra het object uit scope gaat (ook bij een exception), ruimt de destructor de resource op. Dit is de basis van bv. std::unique_ptr en std::lock_guard.",
        "explanation_en": "RAII ties resource management to object lifetime: as soon as the object goes out of scope (even during an exception), the destructor cleans up the resource. This underlies e.g. std::unique_ptr and std::lock_guard.",
    },
    {
        "domain": "embedded_cpp", "difficulty": 2,
        "question_nl": "Wat is het belangrijkste verschil tussen `std::unique_ptr` en `std::shared_ptr`?",
        "question_en": "What is the key difference between `std::unique_ptr` and `std::shared_ptr`?",
        "options_nl": [
            "unique_ptr gebruikt reference counting, shared_ptr niet",
            "unique_ptr staat exclusief eigenaarschap toe (niet kopieerbaar, wel verplaatsbaar) en heeft vrijwel geen overhead; shared_ptr staat gedeeld eigenaarschap toe via atomic reference counting",
            "shared_ptr kan alleen worden gebruikt in single-threaded code",
            "unique_ptr kan niet worden gebruikt met arrays of custom deleters",
        ],
        "options_en": [
            "unique_ptr uses reference counting, shared_ptr does not",
            "unique_ptr allows exclusive ownership (non-copyable, movable) with near-zero overhead; shared_ptr allows shared ownership via atomic reference counting",
            "shared_ptr can only be used in single-threaded code",
            "unique_ptr cannot be used with arrays or custom deleters",
        ],
        "correct_index": 1,
        "explanation_nl": "unique_ptr is een lichtgewicht wrapper voor exclusief eigenaarschap zonder refcount-overhead. shared_ptr houdt een atomic reference count bij zodat meerdere eigenaren veilig hetzelfde object kunnen delen, tegen extra overhead in.",
        "explanation_en": "unique_ptr is a lightweight wrapper for exclusive ownership with no refcount overhead. shared_ptr maintains an atomic reference count so multiple owners can safely share the same object, at the cost of extra overhead.",
    },
    {
        "domain": "embedded_cpp", "difficulty": 2,
        "question_nl": "Waarom houdt de compiler rekening met memory alignment bij het layouten van een struct?",
        "question_en": "Why does the compiler take memory alignment into account when laying out a struct?",
        "options_nl": [
            "Om de struct kleiner te maken dan de som van zijn members",
            "Uitgelijnde toegang tot data (bv. een 4-byte int op een adres deelbaar door 4) is vereist of significant sneller op veel processorarchitecturen, dus wordt padding toegevoegd om members correct uit te lijnen",
            "Alignment is alleen relevant voor floating-point getallen",
            "De linker verwijdert automatisch alle padding in de uiteindelijke executable",
        ],
        "options_en": [
            "To make the struct smaller than the sum of its members",
            "Aligned access to data (e.g. a 4-byte int at an address divisible by 4) is required or significantly faster on many processor architectures, so padding is added to align members correctly",
            "Alignment only matters for floating-point numbers",
            "The linker automatically removes all padding in the final executable",
        ],
        "correct_index": 1,
        "explanation_nl": "Veel architecturen vereisen uitgelijnde toegang (of straffen misaligned access met een performanceverlies of zelfs een bus fault). De compiler voegt padding toe zodat elk member op een geldig, efficiënt adres staat.",
        "explanation_en": "Many architectures require aligned access (or penalize misaligned access with a performance hit or even a bus fault). The compiler inserts padding so each member sits at a valid, efficient address.",
    },
    {
        "domain": "embedded_cpp", "difficulty": 3,
        "question_nl": "Wat gebeurt er wanneer je `std::move` toepast op een object?",
        "question_en": "What happens when you apply `std::move` to an object?",
        "options_nl": [
            "Het object wordt onmiddellijk gekopieerd naar een nieuwe geheugenlocatie",
            "std::move cast het object naar een rvalue-reference, waardoor een move-constructor/move-assignment (indien beschikbaar) de resources kan 'stelen' in plaats van kopiëren; std::move zelf verplaatst niets",
            "Het object wordt automatisch vrijgegeven (destructor wordt aangeroepen)",
            "Het is enkel syntactische suiker voor `delete` gevolgd door een nieuwe allocatie",
        ],
        "options_en": [
            "The object is immediately copied to a new memory location",
            "std::move casts the object to an rvalue reference, allowing a move constructor/assignment (if available) to 'steal' its resources instead of copying; std::move itself moves nothing",
            "The object is automatically destroyed (its destructor is called)",
            "It is just syntactic sugar for `delete` followed by a new allocation",
        ],
        "correct_index": 1,
        "explanation_nl": "std::move voert zelf geen enkele operatie uit — het is een cast naar T&&. Pas wanneer dat resultaat aan een move-constructor of move-assignment wordt doorgegeven, worden de interne resources (bv. een heap-pointer) overgenomen in plaats van gekopieerd.",
        "explanation_en": "std::move performs no operation itself — it is a cast to T&&. Only when the result is passed to a move constructor or move-assignment operator are the internal resources (e.g. a heap pointer) taken over instead of copied.",
    },
    {
        "domain": "embedded_cpp", "difficulty": 3,
        "question_nl": "Wat is een belangrijke regel voor code die binnen een Interrupt Service Routine (ISR) draait?",
        "question_en": "What is an important rule for code running inside an Interrupt Service Routine (ISR)?",
        "options_nl": [
            "Een ISR mag zo lang duren als nodig is, zolang de logica maar correct is",
            "Een ISR moet kort en snel zijn, mag niet blokkeren (bv. geen dynamische allocatie, geen mutex-lock, geen blocking I/O) en moet gedeelde data met de main context alleen via atomic/volatile toegang of kortstondig uitgeschakelde interrupts benaderen",
            "Een ISR mag altijd printf/logging aanroepen zonder gevolgen voor timing",
            "Een ISR heeft automatisch de hoogste threadprioriteit in een RTOS en kan daarom nooit vertraagd worden",
        ],
        "options_en": [
            "An ISR may take as long as needed, as long as the logic is correct",
            "An ISR must be short and fast, must not block (e.g. no dynamic allocation, no mutex lock, no blocking I/O) and must access data shared with the main context only via atomic/volatile access or briefly-disabled interrupts",
            "An ISR can always call printf/logging with no timing consequences",
            "An ISR automatically has the highest thread priority in an RTOS and can therefore never be delayed",
        ],
        "correct_index": 1,
        "explanation_nl": "ISR's draaien buiten de normale taakscheduling en blokkeren vaak andere interrupts/taken. Blocking calls of langzame operaties in een ISR kunnen de hele systeemresponsiviteit verstoren; gedeelde data moet veilig (atomic/volatile of critical section) worden benaderd.",
        "explanation_en": "ISRs run outside normal task scheduling and often block other interrupts/tasks. Blocking calls or slow operations inside an ISR can wreck overall system responsiveness; shared data must be accessed safely (atomic/volatile or a critical section).",
    },
    {
        "domain": "embedded_cpp", "difficulty": 3,
        "question_nl": "Wat is priority inversion in een RTOS-context, en wat is een gangbare oplossing?",
        "question_en": "What is priority inversion in an RTOS context, and what is a common fix?",
        "options_nl": [
            "Een situatie waarin een lage-prioriteitstaak een resource (bv. mutex) vasthoudt die een hoge-prioriteitstaak nodig heeft, terwijl een medium-prioriteitstaak de lage-prioriteitstaak preempt — de hoge-prioriteitstaak wacht daardoor langer dan verwacht; priority inheritance lost dit op door de lage-prioriteitstaak tijdelijk de prioriteit van de wachtende taak te geven",
            "Het omdraaien van de prioriteit van alle taken bij het opstarten van het systeem",
            "Een compileertijdfout die optreedt wanneer twee taken dezelfde prioriteit hebben",
            "Het verschijnsel waarbij hoge-prioriteitstaken expres worden vertraagd om energie te besparen",
        ],
        "options_en": [
            "A situation where a low-priority task holds a resource (e.g. a mutex) that a high-priority task needs, while a medium-priority task preempts the low-priority one — so the high-priority task waits longer than expected; priority inheritance fixes this by temporarily raising the low-priority task's priority to that of the waiting task",
            "Reversing the priority of all tasks at system startup",
            "A compile-time error that occurs when two tasks have the same priority",
            "The phenomenon where high-priority tasks are deliberately slowed down to save power",
        ],
        "correct_index": 0,
        "explanation_nl": "Priority inversion ontstaat door mutex-contention tussen taken van verschillende prioriteit; een medium-prioriteitstaak kan het probleem verergeren door de lage-prioriteitshouder te preemten. Priority inheritance (of priority ceiling) is de klassieke RTOS-oplossing.",
        "explanation_en": "Priority inversion arises from mutex contention between tasks of different priority; a medium-priority task can worsen it by preempting the low-priority holder. Priority inheritance (or priority ceiling) is the classic RTOS fix.",
    },

    # ── general_swe (5): complexity, git, testing, REST, SOLID ────────
    {
        "domain": "general_swe", "difficulty": 1,
        "question_nl": "Wat is de tijdscomplexiteit van het zoeken naar een element in een gesorteerde array met binary search?",
        "question_en": "What is the time complexity of searching for an element in a sorted array using binary search?",
        "options_nl": ["O(n)", "O(log n)", "O(n log n)", "O(1)"],
        "options_en": ["O(n)", "O(log n)", "O(n log n)", "O(1)"],
        "correct_index": 1,
        "explanation_nl": "Binary search halveert de zoekruimte bij elke stap, wat resulteert in O(log n) vergelijkingen in het slechtste geval.",
        "explanation_en": "Binary search halves the search space at each step, resulting in O(log n) comparisons in the worst case.",
    },
    {
        "domain": "general_swe", "difficulty": 1,
        "question_nl": "Wat doet `git rebase` in essentie, in tegenstelling tot `git merge`?",
        "question_en": "What does `git rebase` essentially do, as opposed to `git merge`?",
        "options_nl": [
            "Rebase verwijdert de commit-historie volledig",
            "Rebase herschrijft commits door ze bovenop een andere branch te 'herspelen', wat een lineaire historie oplevert, terwijl merge een nieuwe merge-commit toevoegt die beide histories samenvoegt",
            "Rebase en merge doen exact hetzelfde, alleen de naam verschilt",
            "Rebase kan alleen gebruikt worden op de main branch",
        ],
        "options_en": [
            "Rebase permanently deletes the commit history",
            "Rebase rewrites commits by replaying them on top of another branch, producing a linear history, while merge adds a new merge commit combining both histories",
            "Rebase and merge do exactly the same thing, only the name differs",
            "Rebase can only be used on the main branch",
        ],
        "correct_index": 1,
        "explanation_nl": "Rebase geeft elke commit een nieuwe ouder en dus een nieuwe hash ('herschrijven'), wat een lineaire historie oplevert. Merge behoudt beide branches en voegt ze samen via een extra merge-commit.",
        "explanation_en": "Rebase gives each commit a new parent and therefore a new hash ('rewriting'), producing a linear history. Merge keeps both branches and joins them with an additional merge commit.",
    },
    {
        "domain": "general_swe", "difficulty": 2,
        "question_nl": "Wat is het belangrijkste verschil tussen een unit test en een integration test?",
        "question_en": "What is the key difference between a unit test and an integration test?",
        "options_nl": [
            "Unit tests testen een geïsoleerde eenheid code (bv. één functie/klasse), vaak met mocks voor dependencies; integration tests verifiëren dat meerdere componenten (bv. database, API's) correct samenwerken",
            "Integration tests zijn altijd sneller dan unit tests",
            "Unit tests vereisen altijd een draaiende database",
            "Er is geen praktisch verschil, de termen zijn inwisselbaar",
        ],
        "options_en": [
            "Unit tests test an isolated piece of code (e.g. one function/class), often mocking dependencies; integration tests verify that multiple components (e.g. database, APIs) work correctly together",
            "Integration tests are always faster than unit tests",
            "Unit tests always require a running database",
            "There is no practical difference, the terms are interchangeable",
        ],
        "correct_index": 0,
        "explanation_nl": "Unit tests isoleren gedrag van één component (dependencies gemockt) en zijn snel en gericht. Integration tests draaien over echte (of realistische) componentgrenzen heen en vangen problemen op die mocks kunnen verbergen.",
        "explanation_en": "Unit tests isolate the behaviour of one component (dependencies mocked) and are fast and targeted. Integration tests run across real (or realistic) component boundaries and catch issues that mocks can hide.",
    },
    {
        "domain": "general_swe", "difficulty": 2,
        "question_nl": "Welke uitspraak over REST APIs klopt?",
        "question_en": "Which statement about REST APIs is correct?",
        "options_nl": [
            "REST vereist altijd het gebruik van XML als dataformaat",
            "Een REST API moet stateless zijn: elke request van de client bevat alle informatie die de server nodig heeft, zonder dat de server client-sessiestatus tussen requests onthoudt",
            "PUT en POST zijn in REST altijd volledig uitwisselbaar en betekenen hetzelfde",
            "REST-endpoints mogen nooit HTTP statuscodes anders dan 200 teruggeven",
        ],
        "options_en": [
            "REST always requires XML as the data format",
            "A REST API must be stateless: every client request contains all the information the server needs, without the server remembering client session state between requests",
            "PUT and POST are always fully interchangeable in REST and mean the same thing",
            "REST endpoints must never return HTTP status codes other than 200",
        ],
        "correct_index": 1,
        "explanation_nl": "Statelessness is een van de kernconstraints van REST (Fielding). JSON is inmiddels de gangbare dataformaat-keuze, maar geen REST-vereiste; PUT (idempotent, volledige vervanging) en POST (niet per se idempotent, creatie) verschillen semantisch.",
        "explanation_en": "Statelessness is one of REST's core constraints (Fielding). JSON is the common data format today, but not a REST requirement; PUT (idempotent, full replacement) and POST (not necessarily idempotent, creation) differ semantically.",
    },
    {
        "domain": "general_swe", "difficulty": 3,
        "question_nl": "Waar staat de 'D' in de SOLID-principes voor, en wat houdt het in?",
        "question_en": "What does the 'D' in the SOLID principles stand for, and what does it mean?",
        "options_nl": [
            "Duplication — code mag nooit gedupliceerd worden",
            "Dependency Inversion — high-level modules mogen niet afhankelijk zijn van low-level modules; beide moeten afhankelijk zijn van abstracties (interfaces), niet van concrete implementaties",
            "Decoupling — alle classes moeten in aparte packages leven",
            "Delegation — elke class moet werk delegeren aan minstens één andere class",
        ],
        "options_en": [
            "Duplication — code must never be duplicated",
            "Dependency Inversion — high-level modules should not depend on low-level modules; both should depend on abstractions (interfaces), not concrete implementations",
            "Decoupling — every class must live in a separate package",
            "Delegation — every class must delegate work to at least one other class",
        ],
        "correct_index": 1,
        "explanation_nl": "Dependency Inversion is het vijfde SOLID-principe: door afhankelijkheden op abstracties te richten in plaats van concrete classes, worden modules losser gekoppeld en makkelijker te vervangen/testen (bv. via dependency injection).",
        "explanation_en": "Dependency Inversion is the fifth SOLID principle: by depending on abstractions rather than concrete classes, modules become more loosely coupled and easier to replace/test (e.g. via dependency injection).",
    },

    # ── cloud_devops (5): docker, CI/CD, k8s basics, observability, IaC
    {
        "domain": "cloud_devops", "difficulty": 1,
        "question_nl": "Wat is het belangrijkste verschil tussen een Docker container en een virtuele machine (VM)?",
        "question_en": "What is the main difference between a Docker container and a virtual machine (VM)?",
        "options_nl": [
            "Containers virtualiseren volledig hardware inclusief een eigen kernel per container, net als een VM",
            "Containers delen de kernel van het hostbesturingssysteem en isoleren processen op OS-niveau (namespaces/cgroups), wat lichter en sneller is dan een VM die een volledig gastbesturingssysteem met eigen kernel draait",
            "Een VM start altijd sneller op dan een container",
            "Containers en VM's zijn functioneel identiek en verschillen alleen in naam",
        ],
        "options_en": [
            "Containers fully virtualize hardware including their own kernel per container, just like a VM",
            "Containers share the host OS kernel and isolate processes at the OS level (namespaces/cgroups), which is lighter and faster than a VM running a full guest OS with its own kernel",
            "A VM always boots faster than a container",
            "Containers and VMs are functionally identical, differing only in name",
        ],
        "correct_index": 1,
        "explanation_nl": "Containers gebruiken kernelfeatures (namespaces, cgroups) om isolatie te bieden zonder een eigen kernel te draaien, waardoor ze veel lichter en sneller starten zijn dan een VM met een volledig gastbesturingssysteem en hypervisor.",
        "explanation_en": "Containers use kernel features (namespaces, cgroups) to provide isolation without running their own kernel, making them far lighter and faster to start than a VM with a full guest OS and hypervisor.",
    },
    {
        "domain": "cloud_devops", "difficulty": 1,
        "question_nl": "Wat is het doel van Continuous Integration (CI)?",
        "question_en": "What is the purpose of Continuous Integration (CI)?",
        "options_nl": [
            "Handmatig eens per maand alle code van het team samenvoegen",
            "Ontwikkelaars integreren hun codewijzigingen frequent (meerdere keren per dag) in een gedeelde branch, waarbij een geautomatiseerde build en testsuite direct feedback geeft over integratieproblemen",
            "CI betekent dat er nooit meer handmatig getest hoeft te worden",
            "CI is een synoniem voor het productie-deployment proces",
        ],
        "options_en": [
            "Manually merging all the team's code once a month",
            "Developers frequently integrate their code changes (multiple times a day) into a shared branch, with an automated build and test suite giving immediate feedback on integration problems",
            "CI means manual testing is never needed again",
            "CI is a synonym for the production deployment process",
        ],
        "correct_index": 1,
        "explanation_nl": "CI draait om vroeg en vaak integreren zodat integratieproblemen snel en goedkoop worden opgespoord, gevalideerd door een geautomatiseerde build/testpipeline — niet om het vervangen van alle handmatig testen.",
        "explanation_en": "CI is about integrating early and often so integration problems surface quickly and cheaply, validated by an automated build/test pipeline — not about replacing all manual testing.",
    },
    {
        "domain": "cloud_devops", "difficulty": 2,
        "question_nl": "Wat is een Kubernetes Pod?",
        "question_en": "What is a Kubernetes Pod?",
        "options_nl": [
            "Een fysieke server in het cluster",
            "De kleinste deploybare eenheid in Kubernetes: één of meerdere containers die samen worden gedeployed en netwerk/storage delen",
            "Een configuratiebestand voor DNS-instellingen",
            "Een synoniem voor een Docker image",
        ],
        "options_en": [
            "A physical server in the cluster",
            "The smallest deployable unit in Kubernetes: one or more containers deployed together, sharing network and storage",
            "A configuration file for DNS settings",
            "A synonym for a Docker image",
        ],
        "correct_index": 1,
        "explanation_nl": "Een Pod groepeert één of meer nauw samenwerkende containers die hetzelfde netwerk-namespace (IP-adres) en optioneel storage-volumes delen; het is de basiseenheid die Kubernetes scheduled.",
        "explanation_en": "A Pod groups one or more tightly-coupled containers that share the same network namespace (IP address) and optionally storage volumes; it is the basic unit Kubernetes schedules.",
    },
    {
        "domain": "cloud_devops", "difficulty": 2,
        "question_nl": "Wat zijn de drie klassieke 'pijlers' van observability?",
        "question_en": "What are the three classic 'pillars' of observability?",
        "options_nl": [
            "Logs, metrics en traces",
            "Firewalls, VPN's en load balancers",
            "Unit tests, integratietests en end-to-end tests",
            "CPU, RAM en schijfruimte",
        ],
        "options_en": [
            "Logs, metrics and traces",
            "Firewalls, VPNs and load balancers",
            "Unit tests, integration tests and end-to-end tests",
            "CPU, RAM and disk space",
        ],
        "correct_index": 0,
        "explanation_nl": "Logs (discrete gebeurtenissen), metrics (geaggregeerde tijdreeksen) en distributed traces (request-flow door services heen) vormen samen de klassieke drie pijlers waarmee je systeemgedrag kunt begrijpen.",
        "explanation_en": "Logs (discrete events), metrics (aggregated time series) and distributed traces (request flow across services) together form the classic three pillars used to understand system behaviour.",
    },
    {
        "domain": "cloud_devops", "difficulty": 3,
        "question_nl": "Wat is een kernvoordeel van Infrastructure as Code (bv. Terraform) ten opzichte van handmatige infrastructuurconfiguratie via een cloud console?",
        "question_en": "What is a key benefit of Infrastructure as Code (e.g. Terraform) over manually configuring infrastructure through a cloud console?",
        "options_nl": [
            "IaC-tools garanderen dat er nooit configuratiefouten kunnen optreden",
            "Infrastructuur wordt gedefinieerd in versioneerbare, herbruikbare configuratiebestanden, waardoor wijzigingen reviewbaar, reproduceerbaar en auditeerbaar zijn en omgevingen consistent opnieuw opgebouwd kunnen worden",
            "IaC vervangt de noodzaak van toegangsbeheer (IAM) volledig",
            "IaC-tools werken alleen binnen één specifieke cloudprovider en kunnen nooit multi-cloud worden ingezet",
        ],
        "options_en": [
            "IaC tools guarantee that configuration errors can never occur",
            "Infrastructure is defined in versionable, reusable configuration files, making changes reviewable, reproducible and auditable, and letting environments be rebuilt consistently",
            "IaC completely eliminates the need for access management (IAM)",
            "IaC tools only work within a single specific cloud provider and can never be used multi-cloud",
        ],
        "correct_index": 1,
        "explanation_nl": "Het kernvoordeel van IaC is niet foutloosheid maar versiebeheer, reviewability en reproduceerbaarheid: wijzigingen gaan door pull requests, omgevingen kunnen identiek worden herbouwd, en drift wordt zichtbaar via plan/diff.",
        "explanation_en": "The core benefit of IaC is not error-freeness but version control, reviewability and reproducibility: changes go through pull requests, environments can be rebuilt identically, and drift becomes visible via plan/diff.",
    },

    # ── security (5): OWASP, TLS, secrets handling, least privilege,
    #    OT/ICS basics ──────────────────────────────────────────────────
    {
        "domain": "security", "difficulty": 1,
        "question_nl": "Wat is SQL-injectie, zoals beschreven in de OWASP Top 10?",
        "question_en": "What is SQL injection, as described in the OWASP Top 10?",
        "options_nl": [
            "Een aanval waarbij niet-vertrouwde invoer ongefilterd in een SQL-query wordt opgenomen, waardoor een aanvaller de query-logica kan manipuleren (bv. data stelen of wijzigen); parameterized queries/prepared statements zijn de belangrijkste mitigatie",
            "Een techniek om databases sneller te maken door queries te cachen",
            "Een vorm van encryptie voor database-verbindingen",
            "Een methode om automatisch database-indexen aan te maken",
        ],
        "options_en": [
            "An attack where untrusted input is embedded unfiltered into a SQL query, letting an attacker manipulate the query logic (e.g. steal or alter data); parameterized queries/prepared statements are the primary mitigation",
            "A technique to make databases faster by caching queries",
            "A form of encryption for database connections",
            "A method to automatically create database indexes",
        ],
        "correct_index": 0,
        "explanation_nl": "SQL-injectie ontstaat wanneer user input direct in query-strings wordt geconcateneerd. Parameterized queries scheiden data van code en zijn de standaardmitigatie — precies zoals deze codebase overal $1/$2-placeholders gebruikt in plaats van string-interpolatie.",
        "explanation_en": "SQL injection arises when user input is directly concatenated into query strings. Parameterized queries separate data from code and are the standard mitigation — exactly like this codebase using $1/$2 placeholders everywhere instead of string interpolation.",
    },
    {
        "domain": "security", "difficulty": 1,
        "question_nl": "Wat is een best practice voor het beheren van API-keys en wachtwoorden in een applicatie?",
        "question_en": "What is a best practice for managing API keys and passwords in an application?",
        "options_nl": [
            "Ze hardcoded in de broncode zetten zodat ze makkelijk terug te vinden zijn",
            "Ze in een publieke Git-repository committen voor transparantie",
            "Ze buiten de broncode houden (bv. environment variables of een secrets manager) en nooit in versiebeheer committen",
            "Ze delen via een openbaar toegankelijk tekstbestand op de webserver",
        ],
        "options_en": [
            "Hardcode them in the source so they're easy to find",
            "Commit them to a public Git repository for transparency",
            "Keep them out of the source code (e.g. environment variables or a secrets manager) and never commit them to version control",
            "Share them via a publicly-accessible text file on the web server",
        ],
        "correct_index": 2,
        "explanation_nl": "Secrets horen buiten de broncode en buiten versiebeheer: environment variables, .env-bestanden (buiten git), of een dedicated secrets manager, met rotatie en least-privilege-toegang.",
        "explanation_en": "Secrets belong outside source code and outside version control: environment variables, .env files (excluded from git), or a dedicated secrets manager, with rotation and least-privilege access.",
    },
    {
        "domain": "security", "difficulty": 2,
        "question_nl": "Wat is het primaire doel van TLS (Transport Layer Security)?",
        "question_en": "What is the primary purpose of TLS (Transport Layer Security)?",
        "options_nl": [
            "Het versnellen van netwerkverkeer door compressie",
            "Het versleutelen en authenticeren van data die over een netwerk wordt verzonden, zodat vertrouwelijkheid en integriteit tussen client en server gewaarborgd zijn",
            "Het automatisch blokkeren van DDoS-aanvallen",
            "Het vervangen van wachtwoorden door biometrische authenticatie",
        ],
        "options_en": [
            "Speeding up network traffic through compression",
            "Encrypting and authenticating data sent over a network, ensuring confidentiality and integrity between client and server",
            "Automatically blocking DDoS attacks",
            "Replacing passwords with biometric authentication",
        ],
        "correct_index": 1,
        "explanation_nl": "TLS biedt versleuteling (vertrouwelijkheid), integriteitscontrole en servers-/clientauthenticatie via certificaten voor data-in-transit — het is geen DDoS-bescherming of compressietechniek.",
        "explanation_en": "TLS provides encryption (confidentiality), integrity checking, and server/client authentication via certificates for data in transit — it is not a DDoS protection or compression technique.",
    },
    {
        "domain": "security", "difficulty": 2,
        "question_nl": "Wat houdt het 'principle of least privilege' in?",
        "question_en": "What does the 'principle of least privilege' mean?",
        "options_nl": [
            "Elke gebruiker en elk systeemonderdeel krijgt alleen de minimale rechten/toegang die strikt noodzakelijk zijn om zijn taak uit te voeren, niets meer",
            "Alle gebruikers krijgen standaard adminrechten voor het gemak",
            "Het principe dat de laagst-bevoegde gebruiker het systeem beheert",
            "Een netwerkprotocol voor het prioriteren van laagprioriteitsverkeer",
        ],
        "options_en": [
            "Every user and system component is granted only the minimal rights/access strictly necessary to perform its task, nothing more",
            "All users are given admin rights by default for convenience",
            "The principle that the least-privileged user administers the system",
            "A network protocol for prioritizing low-priority traffic",
        ],
        "correct_index": 0,
        "explanation_nl": "Least privilege minimaliseert de impact van een gecompromitteerd account of component doordat het nooit meer toegang heeft dan strikt nodig — een kernprincipe in zowel IT- als OT-security, en zichtbaar in deze codebase in de gescheiden talentos_read/write/admin databaserollen.",
        "explanation_en": "Least privilege minimizes the blast radius of a compromised account or component by never granting more access than strictly required — a core principle in both IT and OT security, and visible in this codebase's separate talentos_read/write/admin database roles.",
    },
    {
        "domain": "security", "difficulty": 3,
        "question_nl": "Wat is een belangrijk verschil tussen security in traditionele IT-omgevingen en OT/ICS-omgevingen (Operational Technology / Industrial Control Systems)?",
        "question_en": "What is an important difference between security in traditional IT environments and OT/ICS (Operational Technology / Industrial Control Systems) environments?",
        "options_nl": [
            "OT/ICS-systemen prioriteren doorgaans beschikbaarheid en fysieke veiligheid (safety) boven vertrouwelijkheid, en patches/updates zijn vaak lastiger door te voeren omdat systemen continu moeten draaien en legacy-hardware met lange levenscycli gebruikt wordt",
            "OT/ICS-systemen hebben nooit netwerkverbindingen en zijn daarom per definitie veilig",
            "In OT/ICS-omgevingen is encryptie altijd verplicht op elk protocol",
            "IT- en OT-security zijn functioneel identiek en vereisen exact dezelfde aanpak",
        ],
        "options_en": [
            "OT/ICS systems typically prioritize availability and physical safety over confidentiality, and patching/updating is often harder because systems must run continuously and use legacy hardware with long lifecycles",
            "OT/ICS systems never have network connections and are therefore secure by definition",
            "In OT/ICS environments, encryption is always mandatory on every protocol",
            "IT and OT security are functionally identical and require exactly the same approach",
        ],
        "correct_index": 0,
        "explanation_nl": "In IT staat vertrouwelijkheid vaak voorop (CIA-triade: confidentiality first); in OT/ICS staat vaak beschikbaarheid en fysieke veiligheid voorop, omdat downtime of onverwacht gedrag een fabriek kan stilleggen of gevaarlijk kan zijn. Patchen is lastiger door 24/7-processen en verouderde, vaak niet-ondersteunde apparatuur.",
        "explanation_en": "In IT, confidentiality is often prioritized first (CIA triad); in OT/ICS, availability and physical safety usually come first, since downtime or unexpected behaviour can halt a plant or be dangerous. Patching is harder due to 24/7 processes and legacy, often-unsupported equipment.",
    },
]

assert len(SEED_QUESTIONS) == 24, f"expected 24 seed questions, got {len(SEED_QUESTIONS)}"
for _q in SEED_QUESTIONS:
    assert len(_q["options_nl"]) == 4 and len(_q["options_en"]) == 4
    assert 0 <= _q["correct_index"] <= 3
    assert _q["difficulty"] in (1, 2, 3)
_domain_counts = {}
for _q in SEED_QUESTIONS:
    _domain_counts[_q["domain"]] = _domain_counts.get(_q["domain"], 0) + 1
assert _domain_counts == {"embedded_cpp": 9, "general_swe": 5, "cloud_devops": 5, "security": 5}, _domain_counts


# ── Internal client + 6 Brainport vacancies ────────────────────────────

INTERNAL_CLIENT = {
    "company_name": "GSP Talent Pool",
    "domain": "gsprecruitment.nl",
    "industry": "Recruitment",
    "location": "Eindhoven",
}

SEED_JOBS = [
    {
        "title": "Senior Embedded C++ Engineer",
        "department": "Engineering",
        "seniority": "senior",
        "salary_min": 75000,
        "salary_max": 95000,
        "description": (
            "Voor een high-tech opdrachtgever in de Brainport-regio zoeken wij een Senior "
            "Embedded C++ Engineer voor de ontwikkeling van software die dicht op de hardware "
            "draait binnen precisiesystemen. Je werkt aan real-time firmware en applicatiesoftware "
            "in modern C++ (C++17/20), met aandacht voor timing, geheugengebruik en betrouwbaarheid "
            "op systemen die 24/7 moeten blijven presteren. Je bent betrokken bij architectuurkeuzes, "
            "code reviews en het opzetten van geautomatiseerde testomgevingen (hardware-in-the-loop). "
            "De opdrachtgever werkt met kleine, autonome teams waarin senior engineers direct "
            "meebeslissen over technische richting. Het gaat om een anonieme opdrachtgever; via GSP "
            "krijg je volledige inzage in het bedrijf en het team zodra er serieuze interesse is."
        ),
        "requirements": (
            "5+ jaar ervaring met C++ in een embedded of real-time context; sterke kennis van "
            "geheugenbeheer, concurrency en debugging op embedded targets; ervaring met RTOS of "
            "bare-metal ontwikkeling; goede beheersing van Engels of Nederlands."
        ),
        "nice_to_have": (
            "Ervaring met safety-critical software (bv. IEC 61508/62304), cross-compilation "
            "toolchains, of motion control/mechatronica-achtergrond."
        ),
    },
    {
        "title": "Embedded Linux Engineer",
        "department": "Engineering",
        "seniority": "mid",
        "salary_min": 60000,
        "salary_max": 80000,
        "description": (
            "Voor een high-tech opdrachtgever in de Brainport-regio zoeken wij een Embedded Linux "
            "Engineer die embedded Linux-platforms (bootloader, kernel, BSP, device drivers) "
            "opzet en onderhoudt voor industriële en high-tech apparatuur. Je werkt met Yocto of "
            "Buildroot, schrijft en debugt device drivers, en zorgt dat de software-stack "
            "betrouwbaar draait op custom hardware. Je werkt samen met elektronica- en "
            "systeemengineers om nieuwe hardwarerevisies te ondersteunen en bestaande platforms "
            "te optimaliseren op boot-tijd, geheugengebruik en stabiliteit. Anonieme opdrachtgever; "
            "GSP deelt bedrijfsnaam en teamdetails zodra je serieuze interesse toont."
        ),
        "requirements": (
            "3+ jaar ervaring met embedded Linux (kernel, drivers, BSP); ervaring met Yocto of "
            "Buildroot; kennis van C en shellscripting; affiniteit met crossplatform build-systemen."
        ),
        "nice_to_have": (
            "Ervaring met device tree, U-Boot, of industriële communicatieprotocollen (CAN, Modbus, "
            "EtherCAT)."
        ),
    },
    {
        "title": "Mechatronics System Architect",
        "department": "R&D",
        "seniority": "lead",
        "salary_min": 85000,
        "salary_max": 115000,
        "description": (
            "Voor een high-tech opdrachtgever in de Brainport-regio zoeken wij een Mechatronics "
            "System Architect die de brug slaat tussen mechanica, elektronica en software bij de "
            "ontwikkeling van complexe precisiesystemen. Je bepaalt de systeemarchitectuur, "
            "vertaalt requirements naar subsysteemontwerp, en begeleidt multidisciplinaire teams "
            "van mechanical, electrical en software engineers. Je bent het technische aanspreekpunt "
            "voor trade-offs tussen motion control, thermisch gedrag, elektronica en software-"
            "constraints. De rol vraagt ruime ervaring met complexe, mechatronische systemen in een "
            "high-mix, high-precision omgeving. Anonieme opdrachtgever via GSP; bedrijfsdetails na "
            "eerste kennismaking."
        ),
        "requirements": (
            "8+ jaar ervaring in mechatronica-systeemontwerp; aantoonbare ervaring als "
            "(system) architect op complexe precisiesystemen; sterke communicatieve vaardigheden "
            "richting multidisciplinaire teams en stakeholders."
        ),
        "nice_to_have": (
            "Ervaring in de semicon- of analytical-instruments industrie, of met model-based "
            "systems engineering (MBSE)."
        ),
    },
    {
        "title": "C++ Vision/Image Processing Engineer",
        "department": "Engineering",
        "seniority": "mid",
        "salary_min": 65000,
        "salary_max": 85000,
        "description": (
            "Voor een high-tech opdrachtgever in de Brainport-regio zoeken wij een C++ engineer die "
            "computer vision- en beeldverwerkingsalgoritmes ontwikkelt voor inspectie- en "
            "metrologiesystemen. Je implementeert en optimaliseert algoritmes (filtering, feature "
            "detection, calibratie) in modern C++, met oog voor performance op grote datastromen "
            "en real-time verwerkingseisen. Je werkt samen met optica- en systeemengineers om "
            "algoritmes te valideren tegen fysieke metingen. Anonieme opdrachtgever; via GSP krijg "
            "je volledig inzicht in het product en het team zodra er wederzijdse interesse is."
        ),
        "requirements": (
            "3+ jaar ervaring met C++ en beeldverwerking (bv. OpenCV of vergelijkbaar); kennis van "
            "lineaire algebra en beeldverwerkingsalgoritmes; ervaring met performance-optimalisatie "
            "van compute-intensieve code."
        ),
        "nice_to_have": (
            "Ervaring met GPU-versnelling (CUDA/OpenCL), machine vision-camera's, of metrologie-"
            "toepassingen."
        ),
    },
    {
        "title": "OT Cybersecurity Engineer",
        "department": "Security",
        "seniority": "senior",
        "salary_min": 70000,
        "salary_max": 90000,
        "description": (
            "Voor een high-tech opdrachtgever in de Brainport-regio zoeken wij een OT Cybersecurity "
            "Engineer die de beveiliging van industriële besturingssystemen en productienetwerken "
            "vormgeeft en versterkt. Je voert risicoanalyses uit op OT/ICS-omgevingen, adviseert "
            "over netwerksegmentatie, en werkt samen met engineering- en IT-teams om security-by-"
            "design in nieuwe systemen te borgen zonder de operationele beschikbaarheid in gevaar "
            "te brengen. Je begrijpt dat 'gewoon patchen' in een productieomgeving anders werkt dan "
            "in kantoor-IT. Anonieme opdrachtgever via GSP; bedrijfsnaam en teamdetails volgen na "
            "een eerste, vrijblijvend gesprek."
        ),
        "requirements": (
            "5+ jaar ervaring met security in industriële/OT-omgevingen; kennis van standaarden "
            "zoals IEC 62443; ervaring met netwerksegmentatie en risicoanalyses in productie-"
            "omgevingen."
        ),
        "nice_to_have": (
            "Relevante certificeringen (bv. GICSP, CISSP), of ervaring met SCADA/PLC-omgevingen."
        ),
    },
    {
        "title": "DevOps Engineer High-Tech",
        "department": "Engineering",
        "seniority": "mid",
        "salary_min": 60000,
        "salary_max": 85000,
        "description": (
            "Voor een high-tech opdrachtgever in de Brainport-regio zoeken wij een DevOps Engineer "
            "die CI/CD-pipelines, containerplatforms en infrastructure-as-code opzet en onderhoudt "
            "voor zowel embedded als cloud-gebonden softwareprojecten. Je bouwt en verbetert build- "
            "en testpipelines voor firmware en applicatiesoftware, beheert Kubernetes-omgevingen, en "
            "zorgt voor observability (logging, metrics, tracing) zodat problemen snel worden "
            "opgespoord. Je werkt nauw samen met software- en systeemengineers om releases "
            "betrouwbaar en reproduceerbaar te maken. Anonieme opdrachtgever; via GSP krijg je "
            "volledige bedrijfsinformatie zodra er serieuze interesse is."
        ),
        "requirements": (
            "3+ jaar ervaring met CI/CD (bv. GitLab CI, Jenkins, GitHub Actions); ervaring met "
            "Docker en Kubernetes; kennis van infrastructure-as-code (bv. Terraform, Ansible)."
        ),
        "nice_to_have": (
            "Ervaring met CI voor embedded/firmware builds, of met observability-stacks zoals "
            "Prometheus/Grafana."
        ),
    },
]

assert len(SEED_JOBS) == 6, f"expected 6 seed jobs, got {len(SEED_JOBS)}"


async def seed_quiz_questions(conn):
    """Seed the 24 quiz questions. Idempotent via ON CONFLICT (domain, question_nl)."""
    inserted = 0
    for q in SEED_QUESTIONS:
        result = await conn.execute(
            """INSERT INTO quiz_questions
               (domain, difficulty, question_nl, question_en, options_nl, options_en,
                correct_index, explanation_nl, explanation_en, active)
               VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, $9, TRUE)
               ON CONFLICT (domain, question_nl) DO NOTHING""",
            q["domain"], q["difficulty"], q["question_nl"], q["question_en"],
            json.dumps(q["options_nl"]), json.dumps(q["options_en"]),
            q["correct_index"], q["explanation_nl"], q["explanation_en"],
        )
        if result == "INSERT 0 1":
            inserted += 1
    print(f"Seeded {inserted}/{len(SEED_QUESTIONS)} quiz questions (ON CONFLICT DO NOTHING for the rest).")


async def seed_internal_client_and_jobs(conn):
    """Seed the internal 'GSP Talent Pool' client and its 6 vacancies.
    clients has no unique constraint, so we SELECT first and reuse the id
    if the row already exists; job_orders dedup is a WHERE NOT EXISTS on
    (title, client_id)."""
    client_row = await conn.fetchrow(
        "SELECT id FROM clients WHERE company_name = $1", INTERNAL_CLIENT["company_name"],
    )
    if client_row:
        client_id = client_row["id"]
        print(f"Internal client '{INTERNAL_CLIENT['company_name']}' already exists (id={client_id}).")
    else:
        client_row = await conn.fetchrow(
            """INSERT INTO clients (company_name, domain, industry, location, account_status)
               VALUES ($1, $2, $3, $4, 'active')
               RETURNING id""",
            INTERNAL_CLIENT["company_name"], INTERNAL_CLIENT["domain"],
            INTERNAL_CLIENT["industry"], INTERNAL_CLIENT["location"],
        )
        client_id = client_row["id"]
        print(f"Created internal client '{INTERNAL_CLIENT['company_name']}' (id={client_id}).")

    inserted = 0
    for job in SEED_JOBS:
        result = await conn.execute(
            """INSERT INTO job_orders
               (client_id, title, department, seniority, location_type,
                salary_min, salary_max, salary_currency, description, requirements,
                nice_to_have, status)
               SELECT $1::int, $2::varchar, $3, $4, 'hybrid', $5, $6, 'EUR', $7, $8, $9, 'open'
               WHERE NOT EXISTS (
                   SELECT 1 FROM job_orders WHERE title = $2::varchar AND client_id = $1::int
               )""",
            client_id, job["title"], job["department"], job["seniority"],
            job["salary_min"], job["salary_max"], job["description"],
            job["requirements"], job["nice_to_have"],
        )
        if result == "INSERT 0 1":
            inserted += 1
    print(f"Seeded {inserted}/{len(SEED_JOBS)} vacancies for client id={client_id}.")


async def seed_all():
    import asyncpg

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    db = os.getenv("POSTGRES_DB", "recruitment_db")
    user = os.getenv("POSTGRES_USER", "talentos_admin")
    password = os.getenv("POSTGRES_PASSWORD", "")

    conn = await asyncpg.connect(host=host, port=port, database=db, user=user, password=password)
    try:
        await seed_quiz_questions(conn)
        await seed_internal_client_and_jobs(conn)
    finally:
        await conn.close()


async def main():
    await run_migration(VERSION, MIGRATION_SQL)
    await seed_all()


if __name__ == "__main__":
    asyncio.run(main())

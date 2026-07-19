/**
 * Tech Match Quiz — OFFLINE FALLBACK question bank + local scoring, plus
 * growth-tips copy for both the offline and the (now live) server-graded
 * quiz.
 *
 * `GET /v1/public/quiz` + `POST /v1/public/quiz/submit` are LIVE in
 * production (see lib/api.ts `getQuiz`/`submitQuiz`) — the quiz screen
 * (app/(tabs)/quiz.tsx) fetches real questions and submits answers for
 * server-side grading by default. Everything in THIS file
 * (`QUIZ_QUESTIONS`, `scoreQuiz`, `GROWTH_TIPS`) is only used as an
 * "offline versie" fallback for when the fetch fails (no network, API
 * down), so the quiz still works end-to-end and is clearly labelled as
 * a locally-scored approximation. Its question bank predates the real
 * backend and uses its own 6-domain taxonomy (frontend/backend/
 * devops_cloud/data_ai/security/softskills) — a different set from the
 * server's domains (general_swe/security/cloud_devops/embedded_cpp), so
 * `SERVER_GROWTH_TIPS` below covers the server's domains separately.
 */
import type { Lang } from './i18n';

export type QuizDomain = 'frontend' | 'backend' | 'devops_cloud' | 'data_ai' | 'security' | 'softskills';
export type QuizDifficulty = 'junior' | 'medior' | 'senior';

export interface QuizOption {
  text_nl: string;
  text_en: string;
  points: 0 | 1 | 2 | 3;
}

export interface QuizQuestion {
  id: number;
  domain: QuizDomain;
  difficulty: QuizDifficulty;
  question_nl: string;
  question_en: string;
  options: QuizOption[];
  explanation_nl: string;
  explanation_en: string;
}

export const QUIZ_QUESTIONS: QuizQuestion[] = [
  {
    id: 1,
    domain: 'frontend',
    difficulty: 'junior',
    question_nl: 'Hoe reageer je op een bug die alleen in Safari optreedt?',
    question_en: 'How do you respond to a bug that only occurs in Safari?',
    options: [
      { text_nl: 'Ik negeer het, weinig gebruikers zitten op Safari', text_en: 'I ignore it, few users are on Safari', points: 0 },
      { text_nl: 'Ik zoek online naar een pasklare oplossing', text_en: 'I search online for a ready-made fix', points: 1 },
      { text_nl: 'Ik reproduceer het lokaal en debug met de devtools', text_en: 'I reproduce it locally and debug with devtools', points: 2 },
      { text_nl: 'Ik reproduceer, isoleer de root cause en schrijf een regressietest', text_en: 'I reproduce, isolate the root cause and add a regression test', points: 3 },
    ],
    explanation_nl: 'Cross-browser issues structureel oplossen (root cause + test) is een seniorsignaal; alleen googelen naar een fix is prima als startpunt maar geen eindpunt.',
    explanation_en: 'Structurally fixing cross-browser issues (root cause + test) is a senior signal; googling a fix is a fine starting point but not an end point.',
  },
  {
    id: 2,
    domain: 'frontend',
    difficulty: 'medior',
    question_nl: 'Een pagina laadt traag door een groot component. Wat doe je eerst?',
    question_en: 'A page loads slowly because of one large component. What do you do first?',
    options: [
      { text_nl: 'Niets, performance komt later wel', text_en: 'Nothing, performance can wait', points: 0 },
      { text_nl: 'Ik voeg loading spinners toe', text_en: 'I add loading spinners', points: 1 },
      { text_nl: 'Ik meet met de profiler wat precies traag is', text_en: 'I measure with the profiler what exactly is slow', points: 2 },
      { text_nl: 'Ik profileer, split code/lazy-load en meet het effect', text_en: 'I profile, code-split/lazy-load and measure the effect', points: 3 },
    ],
    explanation_nl: 'Meten voor je optimaliseert voorkomt dat je tijd steekt in de verkeerde plek.',
    explanation_en: 'Measuring before optimizing prevents wasting time on the wrong bottleneck.',
  },
  {
    id: 3,
    domain: 'backend',
    difficulty: 'junior',
    question_nl: 'Een endpoint moet data van twee tabellen combineren. Hoe pak je dat aan?',
    question_en: 'An endpoint needs to combine data from two tables. How do you approach it?',
    options: [
      { text_nl: 'Ik haal beide tabellen los op en combineer in de frontend', text_en: 'I fetch both tables separately and combine in the frontend', points: 0 },
      { text_nl: 'Ik doe twee losse queries in de API en combineer server-side', text_en: 'I run two separate queries in the API and combine server-side', points: 1 },
      { text_nl: 'Ik gebruik een JOIN-query met de juiste indexen', text_en: 'I use a JOIN query with the right indexes', points: 2 },
      { text_nl: 'Ik gebruik een JOIN, kijk naar de query-planner en cache waar zinvol', text_en: 'I use a JOIN, check the query planner and cache where it makes sense', points: 3 },
    ],
    explanation_nl: 'Data-combinatie hoort in de API-laag, niet in de client; query-planning en caching zijn senior-niveau overwegingen.',
    explanation_en: 'Combining data belongs in the API layer, not the client; query planning and caching are senior-level concerns.',
  },
  {
    id: 4,
    domain: 'backend',
    difficulty: 'senior',
    question_nl: 'Je API krijgt 10x zoveel verkeer volgende maand. Wat is je eerste stap?',
    question_en: 'Your API will get 10x the traffic next month. What is your first step?',
    options: [
      { text_nl: 'Wachten tot het probleem zich voordoet', text_en: 'Wait until it becomes a problem', points: 0 },
      { text_nl: 'De server specs vast verhogen', text_en: 'Just scale up the server specs', points: 1 },
      { text_nl: 'Een load test draaien om het echte knelpunt te vinden', text_en: 'Run a load test to find the real bottleneck', points: 2 },
      { text_nl: 'Load testen, knelpunten identificeren en horizontaal + caching plannen', text_en: 'Load test, identify bottlenecks and plan horizontal scaling + caching', points: 3 },
    ],
    explanation_nl: 'Capaciteit vergroten zonder te meten leidt vaak tot dezelfde bottleneck bij een hoger volume.',
    explanation_en: 'Scaling up without measuring often just moves the same bottleneck to a higher volume.',
  },
  {
    id: 5,
    domain: 'devops_cloud',
    difficulty: 'junior',
    question_nl: 'Wat hoort volgens jou standaard in een CI-pipeline?',
    question_en: 'What do you think should be standard in a CI pipeline?',
    options: [
      { text_nl: 'Alleen de build', text_en: 'Just the build', points: 0 },
      { text_nl: 'Build + lint', text_en: 'Build + lint', points: 1 },
      { text_nl: 'Build + lint + geautomatiseerde tests', text_en: 'Build + lint + automated tests', points: 2 },
      { text_nl: 'Build + lint + tests + security scan + gated deploy', text_en: 'Build + lint + tests + security scan + gated deploy', points: 3 },
    ],
    explanation_nl: 'Een volwassen pipeline test en beveiligt vóór deploy, niet alleen dat de code compileert.',
    explanation_en: 'A mature pipeline tests and secures before deploy, not just that the code compiles.',
  },
  {
    id: 6,
    domain: 'devops_cloud',
    difficulty: 'medior',
    question_nl: 'Een service in productie gebruikt steeds meer geheugen. Wat doe je?',
    question_en: 'A production service keeps using more memory over time. What do you do?',
    options: [
      { text_nl: 'Wekelijks handmatig herstarten', text_en: 'Manually restart it weekly', points: 0 },
      { text_nl: 'Autoscaling instellen zodat het vanzelf opschaalt', text_en: 'Set up autoscaling so it scales itself', points: 1 },
      { text_nl: 'Metrics en logs bekijken om de memory leak te vinden', text_en: 'Check metrics and logs to find the memory leak', points: 2 },
      { text_nl: 'Monitoring + profiling inzetten, leak fixen en een alert toevoegen', text_en: 'Use monitoring + profiling, fix the leak and add an alert', points: 3 },
    ],
    explanation_nl: 'Autoscaling en herstarts verbergen een leak, ze lossen hem niet op.',
    explanation_en: 'Autoscaling and restarts hide a leak, they do not fix it.',
  },
  {
    id: 7,
    domain: 'data_ai',
    difficulty: 'junior',
    question_nl: 'Je model presteert goed op de trainingsset maar slecht op nieuwe data. Wat is dit?',
    question_en: 'Your model performs well on training data but poorly on new data. What is this?',
    options: [
      { text_nl: 'Geen idee', text_en: 'No idea', points: 0 },
      { text_nl: 'Een databug', text_en: 'A data bug', points: 1 },
      { text_nl: 'Overfitting', text_en: 'Overfitting', points: 2 },
      { text_nl: 'Overfitting — ik zou regularisatie, meer data of cross-validatie inzetten', text_en: 'Overfitting — I would use regularization, more data or cross-validation', points: 3 },
    ],
    explanation_nl: 'Overfitting herkennen is de basis; weten welke tegenmaatregel je kiest is het senior-signaal.',
    explanation_en: 'Recognizing overfitting is the baseline; knowing which countermeasure to apply is the senior signal.',
  },
  {
    id: 8,
    domain: 'data_ai',
    difficulty: 'medior',
    question_nl: 'Hoe ga je om met een dataset met veel ontbrekende waarden?',
    question_en: 'How do you deal with a dataset that has a lot of missing values?',
    options: [
      { text_nl: 'Rijen met missende waarden verwijderen', text_en: 'Drop rows with missing values', points: 1 },
      { text_nl: 'Altijd met het gemiddelde opvullen', text_en: 'Always impute with the mean', points: 1 },
      { text_nl: 'Eerst het patroon van ontbrekendheid onderzoeken, dan een passende strategie kiezen', text_en: 'First investigate the pattern of missingness, then choose a fitting strategy', points: 3 },
      { text_nl: 'Negeren, het model corrigeert dat vanzelf wel', text_en: 'Ignore it, the model will correct for it anyway', points: 0 },
    ],
    explanation_nl: 'Ontbrekende data is zelden willekeurig — het patroon onderzoeken voorkomt bias in je model.',
    explanation_en: 'Missing data is rarely random — investigating the pattern prevents bias in your model.',
  },
  {
    id: 9,
    domain: 'security',
    difficulty: 'junior',
    question_nl: 'Waar sla je een API-sleutel voor een externe dienst op?',
    question_en: 'Where do you store an API key for a third-party service?',
    options: [
      { text_nl: 'Direct in de broncode', text_en: 'Directly in the source code', points: 0 },
      { text_nl: 'In een .env bestand dat wél wordt meegecommit', text_en: 'In a .env file that does get committed', points: 1 },
      { text_nl: 'In een .env bestand dat in .gitignore staat', text_en: 'In a .env file that is in .gitignore', points: 2 },
      { text_nl: 'In een secrets manager, nooit in de repo, met rotatie', text_en: 'In a secrets manager, never in the repo, with rotation', points: 3 },
    ],
    explanation_nl: 'Secrets horen buiten de repository, idealiter met rotatiebeleid.',
    explanation_en: 'Secrets belong outside the repository, ideally with a rotation policy.',
  },
  {
    id: 10,
    domain: 'security',
    difficulty: 'senior',
    question_nl: 'Een gebruiker meldt dat ze data van een andere gebruiker kan zien via de API. Eerste actie?',
    question_en: 'A user reports they can see another user’s data via the API. First action?',
    options: [
      { text_nl: 'Wachten op meer meldingen voor je iets doet', text_en: 'Wait for more reports before acting', points: 0 },
      { text_nl: 'Het endpoint uitzetten tot het is opgelost', text_en: 'Disable the endpoint until it is fixed', points: 2 },
      { text_nl: 'Direct reproduceren, scope vaststellen en autorisatiecontroles fixen', text_en: 'Reproduce immediately, establish scope and fix authorization checks', points: 3 },
      { text_nl: 'Alleen de melder een excuus sturen', text_en: 'Just send the reporter an apology', points: 0 },
    ],
    explanation_nl: 'Een autorisatielek (IDOR) vraagt om snelle scope-bepaling en een structurele fix, niet alleen symptoombestrijding.',
    explanation_en: 'An authorization leak (IDOR) needs fast scoping and a structural fix, not just symptom relief.',
  },
  {
    id: 11,
    domain: 'softskills',
    difficulty: 'junior',
    question_nl: 'Een teamgenoot geeft je feedback op je code die je niet meteen begrijpt. Wat doe je?',
    question_en: 'A teammate gives you code feedback you don’t immediately understand. What do you do?',
    options: [
      { text_nl: 'De feedback negeren', text_en: 'Ignore the feedback', points: 0 },
      { text_nl: 'De feedback verwerken zonder te vragen waarom', text_en: 'Apply it without asking why', points: 1 },
      { text_nl: 'Doorvragen om het "waarom" te begrijpen', text_en: 'Ask follow-up questions to understand the "why"', points: 2 },
      { text_nl: 'Doorvragen, het toepassen en het teruggeven aan het team als leerpunt', text_en: 'Ask follow-up questions, apply it and share it back with the team as a learning', points: 3 },
    ],
    explanation_nl: 'Feedback omzetten in gedeelde teamkennis is een teken van senioriteit buiten pure code-skills.',
    explanation_en: 'Turning feedback into shared team knowledge is a sign of seniority beyond pure coding skill.',
  },
  {
    id: 12,
    domain: 'softskills',
    difficulty: 'medior',
    question_nl: 'Een deadline komt in gevaar door scope die groeit. Wat doe je?',
    question_en: 'A deadline is at risk because scope keeps growing. What do you do?',
    options: [
      { text_nl: 'Stilzwijgend overuren maken', text_en: 'Quietly work overtime', points: 1 },
      { text_nl: 'Niets zeggen en hopen dat het goed komt', text_en: 'Say nothing and hope it works out', points: 0 },
      { text_nl: 'Vroeg escaleren met opties: scope, tijd of mensen', text_en: 'Escalate early with options: scope, time or people', points: 3 },
      { text_nl: 'Wachten tot de deadline is gemist om het te melden', text_en: 'Wait until the deadline is missed to report it', points: 0 },
    ],
    explanation_nl: 'Vroeg en met opties escaleren voorkomt verrassingen en toont eigenaarschap.',
    explanation_en: 'Escalating early with options prevents surprises and shows ownership.',
  },
];

export interface QuizAnswer {
  question_id: number;
  option_index: number;
}

export type QuizTier = 'junior' | 'medior' | 'senior';

export interface QuizDomainScore {
  domain: QuizDomain;
  score: number;
  maxScore: number;
  pct: number;
}

export interface QuizQuestionFeedback {
  question: QuizQuestion;
  selectedIndex: number;
  points: number;
  maxPoints: number;
}

export interface QuizResult {
  score: number;
  maxScore: number;
  pct: number;
  tier: QuizTier;
  domainScores: QuizDomainScore[];
  feedback: QuizQuestionFeedback[];
  weakestDomain: QuizDomain;
}

const DOMAINS: QuizDomain[] = ['frontend', 'backend', 'devops_cloud', 'data_ai', 'security', 'softskills'];

export function scoreQuiz(answers: QuizAnswer[]): QuizResult {
  const byId = new Map(QUIZ_QUESTIONS.map((q) => [q.id, q]));
  const feedback: QuizQuestionFeedback[] = [];
  const domainTotals = new Map<QuizDomain, { score: number; max: number }>();
  for (const d of DOMAINS) domainTotals.set(d, { score: 0, max: 0 });

  let score = 0;
  let maxScore = 0;

  for (const q of QUIZ_QUESTIONS) {
    const maxPoints = Math.max(...q.options.map((o) => o.points));
    maxScore += maxPoints;
    const answer = answers.find((a) => a.question_id === q.id);
    const points = answer ? q.options[answer.option_index]?.points ?? 0 : 0;
    score += points;
    const domainTotal = domainTotals.get(q.domain)!;
    domainTotal.score += points;
    domainTotal.max += maxPoints;
    feedback.push({ question: q, selectedIndex: answer?.option_index ?? -1, points, maxPoints });
  }

  const domainScores: QuizDomainScore[] = DOMAINS.map((domain) => {
    const { score: s, max } = domainTotals.get(domain)!;
    return { domain, score: s, maxScore: max, pct: max > 0 ? Math.round((s / max) * 100) : 0 };
  });

  const pct = maxScore > 0 ? Math.round((score / maxScore) * 100) : 0;
  const tier: QuizTier = pct < 40 ? 'junior' : pct < 70 ? 'medior' : 'senior';
  const weakestDomain = domainScores.reduce((min, d) => (d.pct < min.pct ? d : min), domainScores[0]).domain;

  return { score, maxScore, pct, tier, domainScores, feedback, weakestDomain };
}

/** Static coaching copy per domain — which skills to deepen, written by the GSP team. */
export const GROWTH_TIPS: Record<QuizDomain, { nl: string; en: string }> = {
  frontend: {
    nl: 'Verdiep je in performance (profiling, code-splitting, lazy loading) en toegankelijkheid. Bouw een klein project waarin je bewust een Lighthouse-score van 95+ nastreeft — dat leert je meer dan tien tutorials.',
    en: 'Deepen your knowledge of performance (profiling, code-splitting, lazy loading) and accessibility. Build a small project where you deliberately chase a 95+ Lighthouse score — it teaches more than ten tutorials.',
  },
  backend: {
    nl: 'Focus op databaseontwerp, query-optimalisatie (EXPLAIN-plannen lezen) en API-contracten. Leer wanneer je wél en niet moet cachen — dat onderscheidt medior van senior.',
    en: 'Focus on database design, query optimization (reading EXPLAIN plans) and API contracts. Learn when to cache and when not to — that is what separates medior from senior.',
  },
  devops_cloud: {
    nl: 'Bouw een volledige CI/CD-pipeline met tests, security scanning en gated deploys voor een eigen project. Leer infrastructure-as-code (Terraform of Pulumi) in plaats van handmatige cloud-configuratie.',
    en: 'Build a full CI/CD pipeline with tests, security scanning and gated deploys for a side project. Learn infrastructure-as-code (Terraform or Pulumi) instead of manual cloud configuration.',
  },
  data_ai: {
    nl: 'Oefen met cross-validatie, regularisatie en het herkennen van data leakage. Leer uitleggen waarom een model een voorspelling doet — uitlegbaarheid wordt steeds belangrijker bij klanten.',
    en: 'Practice cross-validation, regularization and recognizing data leakage. Learn to explain why a model makes a prediction — explainability matters more and more to clients.',
  },
  security: {
    nl: 'Leer de OWASP Top 10 uit je hoofd en oefen met een kwetsbare oefen-app (bv. OWASP Juice Shop). Autorisatie (wie mag wat zien) is de meest onderschatte categorie.',
    en: 'Learn the OWASP Top 10 by heart and practice with a deliberately vulnerable app (e.g. OWASP Juice Shop). Authorization (who can see what) is the most underestimated category.',
  },
  softskills: {
    nl: 'Oefen met vroeg escaleren: breng bij elk risico direct opties mee (scope, tijd, mensen) in plaats van alleen het probleem. Vraag actief om feedback in plaats van erop te wachten.',
    en: 'Practice escalating early: bring options (scope, time, people) with every risk instead of just the problem. Actively ask for feedback instead of waiting for it.',
  },
};

export const BLOG_URL = 'https://gsprecruitment.nl/blog';

/**
 * Growth-tips copy keyed by the REAL server domain values
 * (`GET /v1/public/quiz` items' `domain` field). Used to show a coaching
 * tip for the weakest domain reported by `POST /v1/public/quiz/submit`'s
 * `domain_scores`. Falls back to `SERVER_GROWTH_TIPS_DEFAULT` for any
 * domain value the backend adds later that isn't listed here yet, so a
 * new domain never breaks the results screen.
 */
export const SERVER_GROWTH_TIPS: Record<string, { nl: string; en: string }> = {
  general_swe: {
    nl: 'Verdiep je in software-engineeringfundamenten: testpiramides (unit vs. integration), SOLID-principes en git-workflows. Dit is de basis waarop alle andere vakgebieden bouwen.',
    en: 'Deepen your software-engineering fundamentals: test pyramids (unit vs. integration), SOLID principles and git workflows. This is the foundation every other domain builds on.',
  },
  security: {
    nl: 'Leer de OWASP Top 10 uit je hoofd en oefen met een kwetsbare oefen-app (bv. OWASP Juice Shop). Secrets-beheer en least-privilege zijn de meest onderschatte categorieën.',
    en: 'Learn the OWASP Top 10 by heart and practice with a deliberately vulnerable app (e.g. OWASP Juice Shop). Secrets management and least-privilege are the most underestimated categories.',
  },
  cloud_devops: {
    nl: 'Bouw een volledige CI/CD-pipeline met tests, security scanning en gated deploys voor een eigen project. Leer infrastructure-as-code (Terraform) in plaats van handmatige cloud-configuratie.',
    en: 'Build a full CI/CD pipeline with tests, security scanning and gated deploys for a side project. Learn infrastructure-as-code (Terraform) instead of manual cloud configuration.',
  },
  embedded_cpp: {
    nl: 'Verdiep je in RAII, geheugenbeheer zonder garbage collector en real-time constraints (interrupts, priority inversion). Bouw iets op een microcontroller om de theorie hard te maken.',
    en: 'Deepen your knowledge of RAII, memory management without a garbage collector and real-time constraints (interrupts, priority inversion). Build something on a microcontroller to make the theory concrete.',
  },
};

export const SERVER_GROWTH_TIPS_DEFAULT = {
  nl: 'Blijf actief leren op je zwakste vakgebied — kleine, regelmatige oefeningen verslaan lange leestheorie.',
  en: 'Keep actively learning in your weakest domain — small, regular exercises beat long reading sessions.',
};

export function growthTipFor(domain: string, lang: Lang): string {
  return (SERVER_GROWTH_TIPS[domain] ?? SERVER_GROWTH_TIPS_DEFAULT)[lang];
}

/**
 * Minimal dictionary-based i18n. No external i18n library — just a flat
 * key -> {nl, en} map and a `t()` lookup, backed by a tiny Zustand store so
 * any component can read/change the active language. Dutch is the default,
 * matching the public website.
 */
import { create } from 'zustand';
import * as SecureStore from 'expo-secure-store';

export type Lang = 'nl' | 'en';

const LANG_KEY = 'gsp_lang';

type Dict = Record<string, { nl: string; en: string }>;

export const dict: Dict = {
  // ── Common ──────────────────────────────────────────────────────────
  'common.loading': { nl: 'Laden...', en: 'Loading...' },
  'common.retry': { nl: 'Opnieuw proberen', en: 'Retry' },
  'common.cancel': { nl: 'Annuleren', en: 'Cancel' },
  'common.save': { nl: 'Opslaan', en: 'Save' },
  'common.continue': { nl: 'Doorgaan', en: 'Continue' },
  'common.back': { nl: 'Terug', en: 'Back' },
  'common.close': { nl: 'Sluiten', en: 'Close' },
  'common.error': { nl: 'Er ging iets mis', en: 'Something went wrong' },
  'common.errorGeneric': { nl: 'Controleer je verbinding en probeer het opnieuw.', en: 'Check your connection and try again.' },
  'common.confirm': { nl: 'Bevestigen', en: 'Confirm' },
  'common.optional': { nl: 'optioneel', en: 'optional' },
  'common.logout': { nl: 'Uitloggen', en: 'Log out' },
  'common.remote': { nl: 'Remote', en: 'Remote' },
  'common.hybrid': { nl: 'Hybride', en: 'Hybrid' },
  'common.onsite': { nl: 'Op kantoor', en: 'On-site' },

  // ── Tabs ────────────────────────────────────────────────────────────
  'tabs.jobs': { nl: 'Vacatures', en: 'Jobs' },
  'tabs.matches': { nl: 'Matches', en: 'Matches' },
  'tabs.quiz': { nl: 'Quiz', en: 'Quiz' },
  'tabs.career': { nl: 'Carrière', en: 'Career' },
  'tabs.profile': { nl: 'Profiel', en: 'Profile' },

  // ── Auth: shared ────────────────────────────────────────────────────
  'auth.email': { nl: 'E-mailadres', en: 'Email address' },
  'auth.password': { nl: 'Wachtwoord', en: 'Password' },
  'auth.fullName': { nl: 'Volledige naam', en: 'Full name' },
  'auth.passwordRules': { nl: 'Minimaal 8 tekens, met een hoofdletter, kleine letter en cijfer.', en: 'At least 8 characters, with an uppercase letter, lowercase letter and digit.' },
  'auth.invalidEmail': { nl: 'Vul een geldig e-mailadres in.', en: 'Enter a valid email address.' },
  'auth.passwordTooWeak': { nl: 'Wachtwoord voldoet niet aan de eisen.', en: 'Password does not meet the requirements.' },
  'auth.nameRequired': { nl: 'Vul je naam in.', en: 'Enter your name.' },

  // ── Auth: login ─────────────────────────────────────────────────────
  'login.title': { nl: 'Welkom terug', en: 'Welcome back' },
  'login.subtitle': { nl: 'Log in om te solliciteren en je matches te bekijken.', en: 'Log in to apply and view your matches.' },
  'login.submit': { nl: 'Inloggen', en: 'Log in' },
  'login.forgot': { nl: 'Wachtwoord vergeten?', en: 'Forgot password?' },
  'login.noAccount': { nl: 'Nog geen account?', en: "Don't have an account?" },
  'login.register': { nl: 'Registreren', en: 'Register' },
  'login.failed': { nl: 'Onjuist e-mailadres of wachtwoord.', en: 'Incorrect email or password.' },

  // ── Auth: register ──────────────────────────────────────────────────
  'register.title': { nl: 'Account aanmaken', en: 'Create account' },
  'register.subtitle': { nl: 'Maak een profiel aan om te solliciteren en matches te ontvangen.', en: 'Create a profile to apply and receive matches.' },
  'register.submit': { nl: 'Account aanmaken', en: 'Create account' },
  'register.haveAccount': { nl: 'Heb je al een account?', en: 'Already have an account?' },
  'register.login': { nl: 'Inloggen', en: 'Log in' },
  'register.emailInUse': { nl: 'Dit e-mailadres is al in gebruik.', en: 'This email address is already in use.' },
  'register.success': { nl: 'Account aangemaakt.', en: 'Account created.' },

  // ── Auth: forgot password ───────────────────────────────────────────
  'forgot.title': { nl: 'Wachtwoord vergeten', en: 'Forgot password' },
  'forgot.subtitle': { nl: 'Vul je e-mailadres in. We sturen je een link om je wachtwoord opnieuw in te stellen.', en: "Enter your email address. We'll send you a link to reset your password." },
  'forgot.submit': { nl: 'Verstuur link', en: 'Send link' },
  'forgot.success': { nl: 'Als dit adres bekend is, ontvang je een e-mail met instructies.', en: "If that address is known to us, you'll receive an email with instructions." },
  'forgot.backToLogin': { nl: 'Terug naar inloggen', en: 'Back to login' },

  // ── Jobs feed ───────────────────────────────────────────────────────
  'jobs.title': { nl: 'Vacatures', en: 'Jobs' },
  'jobs.empty': { nl: 'Op dit moment geen open vacatures. Kom snel terug.', en: 'No open vacancies right now. Check back soon.' },
  'jobs.loadError': { nl: 'Vacatures konden niet worden geladen.', en: 'Could not load vacancies.' },
  'jobs.salaryUnknown': { nl: 'Salaris in overleg', en: 'Salary negotiable' },

  // ── Job detail ──────────────────────────────────────────────────────
  'job.requirements': { nl: 'Wat we vragen', en: 'What we ask' },
  'job.description': { nl: 'Over de functie', en: 'About the role' },
  'job.apply': { nl: 'Solliciteer direct', en: 'Apply now' },
  'job.applied': { nl: 'Je hebt gesolliciteerd', en: "You've applied" },
  'job.applying': { nl: 'Bezig met solliciteren...', en: 'Submitting application...' },
  'job.applySuccessTitle': { nl: 'Sollicitatie verstuurd', en: 'Application sent' },
  'job.applySuccessBody': { nl: 'We nemen zo snel mogelijk contact met je op als er een match is.', en: "We'll be in touch as soon as possible if there's a match." },
  'job.alreadyApplied': { nl: 'Je hebt al gesolliciteerd op deze vacature.', en: 'You already applied to this job.' },
  'job.applyError': { nl: 'Solliciteren is niet gelukt. Probeer het opnieuw.', en: 'Applying failed. Please try again.' },
  'job.loginRequiredTitle': { nl: 'Log in om te solliciteren', en: 'Log in to apply' },
  'job.loginRequiredBody': { nl: 'Maak een profiel aan of log in om direct te solliciteren.', en: 'Create a profile or log in to apply directly.' },
  'job.cvRequiredTitle': { nl: 'Upload eerst je cv', en: 'Upload your CV first' },
  'job.cvRequiredBody': { nl: 'We hebben je cv nodig voordat je kan solliciteren.', en: 'We need your CV before you can apply.' },
  'job.uploadCv': { nl: 'CV uploaden', en: 'Upload CV' },
  'job.notFound': { nl: 'Vacature niet gevonden.', en: 'Job not found.' },
  'job.closed': { nl: 'Deze vacature staat niet meer open.', en: 'This vacancy is no longer open.' },

  // ── Matches ─────────────────────────────────────────────────────────
  'matches.title': { nl: 'Mijn matches', en: 'My matches' },
  'matches.empty': { nl: 'Nog geen matches — vul je profiel aan', en: 'No matches yet — complete your profile' },
  'matches.emptyBody': { nl: 'Hoe vollediger je profiel en cv, hoe beter we je kunnen matchen met vacatures.', en: 'The more complete your profile and CV, the better we can match you with jobs.' },
  'matches.completeProfile': { nl: 'Profiel aanvullen', en: 'Complete profile' },
  'matches.loginRequired': { nl: 'Log in om je matches te bekijken.', en: 'Log in to view your matches.' },
  'matches.applications': { nl: 'Sollicitaties', en: 'Applications' },
  'matches.score': { nl: 'match', en: 'match' },
  'matches.status.pending': { nl: 'Nieuw', en: 'New' },
  'matches.status.applied': { nl: 'Gesolliciteerd', en: 'Applied' },
  'matches.status.interviewing': { nl: 'In gesprek', en: 'Interviewing' },
  'matches.status.offered': { nl: 'Aanbod', en: 'Offer' },
  'matches.status.placed': { nl: 'Geplaatst', en: 'Placed' },
  'matches.status.rejected': { nl: 'Afgewezen', en: 'Rejected' },

  // ── Quiz ────────────────────────────────────────────────────────────
  'quiz.introTitle': { nl: 'Tech Match Quiz', en: 'Tech Match Quiz' },
  'quiz.introBody': { nl: '12 vragen over je vakgebied, ervaring en voorkeuren. Aan het eind krijg je een seniority-indicatie en persoonlijke groeitips — geen goed of fout.', en: '12 questions about your field, experience and preferences. At the end you get a seniority indication and personal growth tips — there are no right or wrong answers.' },
  'quiz.start': { nl: 'Start de quiz', en: 'Start the quiz' },
  'quiz.questionOf': { nl: 'Vraag {current} van {total}', en: 'Question {current} of {total}' },
  'quiz.next': { nl: 'Volgende', en: 'Next' },
  'quiz.submit': { nl: 'Bekijk resultaat', en: 'View result' },
  'quiz.resultTitle': { nl: 'Jouw resultaat', en: 'Your result' },
  'quiz.scoreLabel': { nl: 'punten', en: 'points' },
  'quiz.tier.junior': { nl: 'Junior-indicatie', en: 'Junior indication' },
  'quiz.tier.medior': { nl: 'Medior-indicatie', en: 'Medior indication' },
  'quiz.tier.senior': { nl: 'Senior-indicatie', en: 'Senior indication' },
  'quiz.domainScores': { nl: 'Per vakgebied', en: 'By domain' },
  'quiz.feedbackTitle': { nl: 'Per vraag', en: 'Per question' },
  'quiz.growthTitle': { nl: 'Groeitips', en: 'Growth tips' },
  'quiz.restart': { nl: 'Opnieuw doen', en: 'Try again' },
  'quiz.ctaProfile': { nl: 'Maak profiel aan', en: 'Create profile' },
  'quiz.ctaProfileBody': { nl: 'Sla je resultaat op en ontvang vacatures die aansluiten bij jouw niveau.', en: 'Save your result and receive vacancies that match your level.' },
  'quiz.emailPrompt': { nl: 'Wil je je resultaat per e-mail ontvangen?', en: 'Want your result emailed to you?' },
  'quiz.emailPlaceholder': { nl: 'jouw@email.nl', en: 'you@email.com' },
  'quiz.sendResult': { nl: 'Verstuur resultaat', en: 'Send result' },
  'quiz.emailSent': { nl: 'Verzonden! Check je inbox.', en: 'Sent! Check your inbox.' },
  'quiz.emailError': { nl: 'Verzenden mislukt, probeer het later opnieuw.', en: 'Sending failed, please try again later.' },
  'quiz.domain.frontend': { nl: 'Frontend', en: 'Frontend' },
  'quiz.domain.backend': { nl: 'Backend', en: 'Backend' },
  'quiz.domain.devops_cloud': { nl: 'Cloud & DevOps', en: 'Cloud & DevOps' },
  'quiz.domain.data_ai': { nl: 'Data & AI', en: 'Data & AI' },
  'quiz.domain.security': { nl: 'Security', en: 'Security' },
  'quiz.domain.softskills': { nl: 'Samenwerking & leiderschap', en: 'Collaboration & leadership' },
  // Server-reported domains (GET /v1/public/quiz) — a different set from the
  // offline fallback bank above.
  'quiz.domain.general_swe': { nl: 'Algemeen software engineering', en: 'General software engineering' },
  'quiz.domain.cloud_devops': { nl: 'Cloud & DevOps', en: 'Cloud & DevOps' },
  'quiz.domain.embedded_cpp': { nl: 'Embedded & C++', en: 'Embedded & C++' },

  'quiz.loading': { nl: 'Vragen laden...', en: 'Loading questions...' },
  'quiz.loadError': { nl: 'De quizvragen konden niet worden geladen.', en: 'Could not load the quiz questions.' },
  'quiz.useOffline': { nl: 'Ga verder met de offline versie', en: 'Continue with the offline version' },
  'quiz.offlineBadge': { nl: 'Offline versie', en: 'Offline version' },
  'quiz.offlineNotice': {
    nl: 'We konden geen verbinding maken met de server, dus je maakt nu de offline versie van de quiz. Je resultaat wordt lokaal berekend en niet naar ons verstuurd.',
    en: "We couldn't reach the server, so you're taking the offline version of the quiz. Your result is calculated locally and not sent to us.",
  },
  'quiz.emailStageTitle': { nl: 'Resultaat aan je e-mail koppelen?', en: 'Link this result to your email?' },
  'quiz.emailStageBody': {
    nl: 'Optioneel: vul je e-mailadres in zodat we dit resultaat aan je kunnen koppelen.',
    en: 'Optional: enter your email so we can link this result to you.',
  },
  'quiz.emailStageSkip': { nl: 'Overslaan', en: 'Skip' },
  'quiz.submitting': { nl: 'Bezig met versturen...', en: 'Submitting...' },
  'quiz.submitError': { nl: 'Versturen van je antwoorden is niet gelukt.', en: 'Could not submit your answers.' },

  // ── Career ──────────────────────────────────────────────────────────
  'career.title': { nl: 'Carrière', en: 'Career' },
  'career.salaryTitle': { nl: 'Salarisinzicht', en: 'Salary insights' },
  'career.role': { nl: 'Functie', en: 'Role' },
  'career.seniority': { nl: 'Senioriteit', en: 'Seniority' },
  'career.location': { nl: 'Locatie', en: 'Location' },
  'career.calculate': { nl: 'Bekijk salarisdata', en: 'View salary data' },
  'career.sampleSize': { nl: 'Gebaseerd op {n} datapunten', en: 'Based on {n} data points' },
  'career.noData': { nl: 'Geen benchmarkdata gevonden voor deze combinatie.', en: 'No benchmark data found for this combination.' },
  'career.pipelineTitle': { nl: 'Mijn traject', en: 'My pipeline' },
  'career.pipelineEmpty': { nl: 'Je hebt nog geen sollicitaties lopen.', en: "You don't have any applications yet." },
  'career.pipelineLoginRequired': { nl: 'Log in om je sollicitatietraject te bekijken.', en: 'Log in to view your application pipeline.' },
  'career.coachingTitle': { nl: 'Carrièretips', en: 'Career tips' },

  // ── Profile ─────────────────────────────────────────────────────────
  'profile.title': { nl: 'Profiel', en: 'Profile' },
  'profile.loginRequiredTitle': { nl: 'Log in om je profiel te beheren', en: 'Log in to manage your profile' },
  'profile.loginRequiredBody': { nl: 'Beheer je gegevens, upload je cv en pas je voorkeuren aan.', en: 'Manage your details, upload your CV and adjust your preferences.' },
  'profile.login': { nl: 'Inloggen', en: 'Log in' },
  'profile.createAccount': { nl: 'Account aanmaken', en: 'Create account' },
  'profile.personalInfo': { nl: 'Persoonlijke gegevens', en: 'Personal details' },
  'profile.currentTitle': { nl: 'Huidige functietitel', en: 'Current job title' },
  'profile.currentCompany': { nl: 'Huidige werkgever', en: 'Current employer' },
  'profile.location': { nl: 'Locatie', en: 'Location' },
  'profile.phone': { nl: 'Telefoonnummer', en: 'Phone number' },
  'profile.linkedin': { nl: 'LinkedIn-URL', en: 'LinkedIn URL' },
  'profile.yearsExperience': { nl: 'Jaren ervaring', en: 'Years of experience' },
  'profile.willingToRelocate': { nl: 'Open voor verhuizen', en: 'Open to relocating' },
  'profile.saveSuccess': { nl: 'Profiel opgeslagen.', en: 'Profile saved.' },
  'profile.saveError': { nl: 'Opslaan mislukt. Probeer het opnieuw.', en: 'Saving failed. Please try again.' },
  'profile.cvTitle': { nl: 'CV', en: 'CV' },
  'profile.cvUploaded': { nl: 'CV geüpload', en: 'CV uploaded' },
  'profile.cvMissing': { nl: 'Nog geen cv geüpload', en: 'No CV uploaded yet' },
  'profile.cvUpload': { nl: 'CV uploaden', en: 'Upload CV' },
  'profile.cvReplace': { nl: 'CV vervangen', en: 'Replace CV' },
  'profile.cvUploadSuccess': { nl: 'CV geüpload.', en: 'CV uploaded.' },
  'profile.cvUploadError': { nl: 'Uploaden mislukt. Gebruik pdf, doc, docx of txt (max 5 MB).', en: 'Upload failed. Use pdf, doc, docx or txt (max 5 MB).' },
  'profile.settings': { nl: 'Instellingen', en: 'Settings' },
  'profile.language': { nl: 'Taal', en: 'Language' },
  'profile.privacyTitle': { nl: 'Privacy & gegevens', en: 'Privacy & data' },
  'profile.exportData': { nl: 'Exporteer mijn gegevens', en: 'Export my data' },
  'profile.exportSuccess': { nl: 'Gegevens klaar om te delen.', en: 'Data ready to share.' },
  'profile.exportError': { nl: 'Exporteren mislukt. Probeer het opnieuw.', en: 'Export failed. Please try again.' },
  'profile.deleteAccount': { nl: 'Account verwijderen', en: 'Delete account' },
  'profile.deleteWarning1': { nl: 'Weet je zeker dat je je account wil verwijderen? Dit kan niet ongedaan worden gemaakt.', en: 'Are you sure you want to delete your account? This cannot be undone.' },
  'profile.deleteWarning2': { nl: 'Laatste bevestiging: al je profielgegevens en cv worden permanent gewist.', en: 'Final confirmation: all your profile data and CV will be permanently erased.' },
  'profile.deleteSuccess': { nl: 'Je account is verwijderd.', en: 'Your account has been deleted.' },
  'profile.deleteError': { nl: 'Verwijderen mislukt. Probeer het opnieuw.', en: 'Deletion failed. Please try again.' },
  'profile.logoutConfirm': { nl: 'Weet je zeker dat je wilt uitloggen?', en: 'Are you sure you want to log out?' },
};

interface LanguageState {
  lang: Lang;
  hydrated: boolean;
  setLang: (lang: Lang) => void;
  hydrate: () => Promise<void>;
}

export const useLanguageStore = create<LanguageState>((set) => ({
  lang: 'nl',
  hydrated: false,
  setLang: (lang: Lang) => {
    set({ lang });
    SecureStore.setItemAsync(LANG_KEY, lang).catch(() => {});
  },
  hydrate: async () => {
    try {
      const stored = await SecureStore.getItemAsync(LANG_KEY);
      if (stored === 'nl' || stored === 'en') {
        set({ lang: stored, hydrated: true });
        return;
      }
    } catch {
      // ignore — fall back to default language
    }
    set({ hydrated: true });
  },
}));

/** Look up a dictionary entry for the given language, with optional {placeholder} interpolation. */
export function translate(key: string, lang: Lang, params?: Record<string, string | number>): string {
  const entry = dict[key];
  let str = entry ? entry[lang] : key;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      str = str.replace(`{${k}}`, String(v));
    }
  }
  return str;
}

/** Hook form: const { t, lang, setLang } = useTranslation(); */
export function useTranslation() {
  const lang = useLanguageStore((s) => s.lang);
  const setLang = useLanguageStore((s) => s.setLang);
  const t = (key: string, params?: Record<string, string | number>) => translate(key, lang, params);
  return { t, lang, setLang };
}

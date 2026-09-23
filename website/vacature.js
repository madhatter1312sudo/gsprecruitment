// ─── JobPosting JSON-LD builder (WS-A.6) ───────────────────────────────
// Pure functions, no DOM access, so scripts/test_jobposting_ld.mjs can
// exercise them directly with fixture jobs (see module.exports guard at
// the bottom of this file).

const JOBPOSTING_EMPLOYMENT_TYPE = {
  vast: 'FULL_TIME',
  detachering: 'CONTRACTOR',
  interim: 'TEMPORARY',
};

function jobPostingEmploymentType(employmentType) {
  return JOBPOSTING_EMPLOYMENT_TYPE[employmentType] || undefined;
}

function jobPostingLocation(job) {
  // city comes from the public job order; when missing (confidential/
  // early-draft postings) fall back to GSP's home region rather than
  // dropping jobLocation, which Google's JobPosting validator requires.
  return {
    '@type': 'Place',
    address: {
      '@type': 'PostalAddress',
      addressLocality: job.city || 'Eindhoven',
      addressRegion: 'Noord-Brabant',
      addressCountry: 'NL',
    },
  };
}

function jobPostingValidThrough(job) {
  // job's own expiry wins when the field exists; otherwise created_at + 60
  // days; if created_at is itself missing/unparseable, fall back to now.
  const explicit = job.valid_through || job.expires_at;
  if (explicit) return explicit;
  const posted = job.created_at ? new Date(job.created_at) : new Date();
  const base = isNaN(posted.getTime()) ? new Date() : posted;
  const through = new Date(base.getTime());
  through.setUTCDate(through.getUTCDate() + 60);
  return through.toISOString();
}

function buildJobPostingLd(job) {
  // Vacancies whose client stays anonymous (see SITE-DESIGN-SPEC.md §3.7)
  // never get JobPosting JSON-LD: a rich-results job card next to an
  // anonymous employer reads as a listing for a job that doesn't concretely
  // exist yet, which is the spookvacature risk the owner's sign-off (Wet
  // OHP, ABU/NBBU-gedragscode) is conditional on avoiding.
  if (job.anonymous_client === true) return null;
  const ld = {
    '@context': 'https://schema.org',
    '@type': 'JobPosting',
    title: job.title || '',
    description: job.description || '',
    datePosted: job.created_at || new Date().toISOString(),
    validThrough: jobPostingValidThrough(job),
    hiringOrganization: {
      '@type': 'Organization',
      name: job.company_display || 'confidential',
    },
    jobLocation: jobPostingLocation(job),
    directApply: true,
  };

  if (job.location_type && String(job.location_type).toLowerCase() === 'remote') {
    ld.jobLocationType = 'TELECOMMUTE';
    ld.applicantLocationRequirements = { '@type': 'Country', name: 'Netherlands' };
  }

  const employmentType = jobPostingEmploymentType(job.employment_type);
  if (employmentType) ld.employmentType = employmentType;

  if (job.salary_min != null && job.salary_max != null) {
    ld.baseSalary = {
      '@type': 'MonetaryAmount',
      currency: job.salary_currency || 'EUR',
      value: {
        '@type': 'QuantitativeValue',
        minValue: job.salary_min,
        maxValue: job.salary_max,
        unitText: 'YEAR',
      },
    };
  }

  return ld;
}

// ─── Job body: Dutch/English text twin (issue #153) ────────────────────
// Pure function (no DOM access besides GSP.esc), same testing pattern as
// buildJobPostingLd() above -- scripts/test_job_body_html.mjs exercises it
// directly with fixture jobs. Requires GSP.esc (website/gsp-util.js,
// loaded before this file in vacature.html); a Node caller must
// require('../website/gsp-util.js') first, which defines global.GSP the
// same way the browser's <script src="gsp-util.js"> tag does.
const JOB_BODY_SECTIONS = [
  { nlKey: 'description', enKey: 'description_en', hEn: 'About the role', hNl: 'Over de rol' },
  { nlKey: 'requirements', enKey: 'requirements_en', hEn: "What we're looking for", hNl: 'Wat we zoeken' },
  { nlKey: 'nice_to_have', enKey: 'nice_to_have_en', hEn: 'Nice to have', hNl: 'Mooi meegenomen' },
];

const JOB_BODY_FALLBACK_EN = 'Only available in Dutch.';
const JOB_BODY_FALLBACK_NL = 'Alleen beschikbaar in het Engels.';

function buildJobBodyHtml(job) {
  const parts = [];
  for (const section of JOB_BODY_SECTIONS) {
    const nlText = job[section.nlKey];
    const enText = job[section.enKey];
    if (!nlText && !enText) continue; // nothing to say in either language

    // Each paragraph gets its own lang-en/lang-nl class (unlike the single
    // shared, language-less <p> this replaces) so the Dutch paragraph
    // never renders unmarked under the English heading when there is no
    // English text yet -- the defect this issue fixes.
    const enParagraph = enText
      ? `<p class="lang-en">${GSP.esc(enText)}</p>`
      : `<p class="lang-en gsp-lang-fallback">${JOB_BODY_FALLBACK_EN}</p>`;
    const nlParagraph = nlText
      ? `<p class="lang-nl">${GSP.esc(nlText)}</p>`
      : `<p class="lang-nl gsp-lang-fallback">${JOB_BODY_FALLBACK_NL}</p>`;

    parts.push(
      `<h2 class="lang-en">${section.hEn}</h2><h2 class="lang-nl">${section.hNl}</h2>` +
      enParagraph + nlParagraph
    );
  }
  return parts.join('');
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    buildJobPostingLd, jobPostingEmploymentType, jobPostingLocation, jobPostingValidThrough,
    buildJobBodyHtml,
  };
}

// ─── Anonymous-client apply panel (WS4) ────────────────────────────────
// Renders once per page load (called at most once from the job-fetch IIFE
// below), so the click listener it attaches to #vacancyOptinBtn can never
// double-bind the way a re-render-on-every-keystroke handler would
// (commit d0917af). Builds markup from fixed bilingual copy only -- no
// job.* field is interpolated into the HTML string, so there is nothing
// here that needs GSP.esc(); the one place a field is read (job.id) goes
// straight into a JSON POST body, never into markup.
function renderVacancyApplyPanel(job, lang) {
  const panel = document.getElementById('vacancyApplyPanel');
  if (!panel) return;
  panel.style.display = 'flex';
  const emailLabel = lang === 'nl' ? 'E-mailadres' : 'Email address';
  panel.innerHTML = `
    <div class="talentpool-optin-row">
      <input type="email" id="vacancyOptinEmail" placeholder="${emailLabel}" data-lang-en="Email address" data-lang-nl="E-mailadres" aria-label="${emailLabel}">
    </div>
    <p class="lang-nl">Ja, neem mij op in de talentpool van GSP Recruitment voor passende rollen. Bewaartermijn 12 maanden; een maand voor het einde vragen wij per e-mail of je wilt verlengen. Zonder verlenging verwijderen wij je gegevens uit de talentpool. Intrekken kan altijd via info@gsprecruitment.nl.</p>
    <p class="lang-en">Yes, add me to GSP Recruitment's talent pool for suitable roles. Retention period 12 months; one month before it ends we'll e-mail you to ask whether you want to renew. Without renewal we delete your data from the talent pool. You can withdraw at any time via info@gsprecruitment.nl.</p>
    <label class="talentpool-optin-check" for="vacancyOptinAlerts">
      <input type="checkbox" id="vacancyOptinAlerts">
      <span class="lang-nl">Stuur mij passende vacatures per e-mail</span><span class="lang-en">Send me matching vacancies by e-mail</span>
    </label>
    <button type="button" id="vacancyOptinBtn" class="btn btn-gold" style="width:100%">
      <span class="lang-nl">Solliciteer via de talentpool</span><span class="lang-en">Apply via the talent pool</span>
    </button>
    <div class="form-error" id="vacancyOptinError" role="alert" aria-live="polite"></div>
    <div class="form-success" id="vacancyOptinSuccess" role="status" aria-live="polite"></div>
  `;

  const emailInput = document.getElementById('vacancyOptinEmail');
  const alertsCheck = document.getElementById('vacancyOptinAlerts');
  const btn = document.getElementById('vacancyOptinBtn');
  const errEl = document.getElementById('vacancyOptinError');
  const successEl = document.getElementById('vacancyOptinSuccess');
  const originalBtnHtml = btn.innerHTML;

  btn.addEventListener('click', async () => {
    errEl.style.display = 'none';
    successEl.style.display = 'none';

    const email = emailInput.value.trim();
    if (!email || !email.includes('@')) {
      errEl.textContent = lang === 'nl' ? 'Voer een geldig e-mailadres in.' : 'Enter a valid email address.';
      errEl.style.display = 'block';
      return;
    }

    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000);
      const res = await fetch('https://api.gsprecruitment.nl/api/public/talentpool-optin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          email,
          consent: true,
          scope: 'matching_and_contact',
          source: 'vacancy_apply',
          job_id: job.id,
          job_alerts: !!alertsCheck.checked,
        }),
      });
      clearTimeout(timeoutId);

      if (res.ok) {
        // Replace the whole panel with the confirmation copy -- built with
        // createElement/textContent rather than innerHTML, so this stays
        // safe even though nothing here is actually user-controlled.
        panel.innerHTML = '';
        const p = document.createElement('p');
        const nl = document.createElement('span');
        nl.className = 'lang-nl';
        nl.textContent = 'Check je e-mail en bevestig je aanmelding; daarna is je sollicitatie geregistreerd.';
        const en = document.createElement('span');
        en.className = 'lang-en';
        en.textContent = 'Check your e-mail and confirm your sign-up; your application will then be registered.';
        p.appendChild(nl);
        p.appendChild(en);
        panel.appendChild(p);
        return;
      }

      if (res.status === 429) {
        errEl.textContent = lang === 'nl' ? 'Te veel pogingen. Probeer het later opnieuw.' : 'Too many attempts. Please try again later.';
      } else {
        const data = await res.json().catch(() => ({}));
        errEl.textContent = data.detail || (lang === 'nl' ? 'Aanmelden mislukt. Probeer opnieuw.' : 'Sign-up failed. Please try again.');
      }
      errEl.style.display = 'block';
      btn.disabled = false;
      btn.innerHTML = originalBtnHtml;
    } catch (_) {
      errEl.textContent = lang === 'nl' ? 'Netwerkfout. Probeer het opnieuw.' : 'Network error. Please try again.';
      errEl.style.display = 'block';
      btn.disabled = false;
      btn.innerHTML = originalBtnHtml;
    }
  });
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports.renderVacancyApplyPanel = renderVacancyApplyPanel;
}

// ─── Sticky mobile apply bar (design-spec-batch.md item 3) ─────────────
// Mobile-only (<768px, belt-and-suspenders with styles.css's own media
// query). Mirrors whichever apply action vacature.js's success branch
// picked: a direct apply link, or (anonymous client, no logged-in
// candidate) a scroll-to-panel action, never both at once.
function initApplySticky(job, lang, salaryLabel) {
  const bar = document.getElementById('applySticky');
  const cta = document.getElementById('applyStickyCta');
  const salaryEl = document.getElementById('applyStickySalary');
  if (!bar || !cta || !salaryEl) return;
  if (window.matchMedia('(min-width: 768px)').matches) return; // desktop: never shown

  salaryEl.textContent = salaryLabel || (lang === 'nl' ? 'Salaris niet opgegeven' : 'Salary not specified');

  const anonymousNoLogin = job.anonymous_client === true &&
    !(typeof Auth !== 'undefined' && Auth.getUser && Auth.getUser() && Auth.getUser().role === 'candidate');
  if (anonymousNoLogin) {
    // Mirror the talent-pool opt-in panel instead of a direct apply link --
    // scroll to the real panel rather than duplicating its form in the bar.
    cta.removeAttribute('href');
    cta.setAttribute('role', 'button');
    cta.addEventListener('click', (e) => {
      e.preventDefault();
      document.getElementById('vacancyApplyPanel')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      document.getElementById('vacancyOptinEmail')?.focus();
    });
  } else {
    cta.href = document.getElementById('applyBtn')?.href || `contact.html?job=${encodeURIComponent(job.id)}`;
  }

  // "The hero" for this page's purposes is the top eyebrow/breadcrumb --
  // vacature.html has no .page-hero, this sits immediately above the H1.
  const hero = document.querySelector('.job-detail .eyebrow');
  const ctaBox = document.querySelector('.cta-box');
  if (!hero || !ctaBox) return;

  const heroObserver = new IntersectionObserver((entries) => {
    bar.classList.toggle('apply-sticky--visible', !entries[0].isIntersecting);
  }, { threshold: 0 });
  heroObserver.observe(hero);

  // Hide once the real in-flow CTA box is on screen, so two apply actions
  // never show at once.
  const ctaObserver = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting) bar.classList.remove('apply-sticky--visible');
  }, { threshold: 0.3 });
  ctaObserver.observe(ctaBox);
}

// Guarded so scripts/test_jobposting_ld.mjs can `require()` this file for
// the pure builder functions above without running the page-fetch IIFE
// below (there's no `window`/DOM in that Node context).
if (typeof window !== 'undefined') {
(async () => {
  const params = new URLSearchParams(window.location.search);
  const jobId = params.get('id') || params.get('slug');
  if (!jobId) { document.getElementById('loadingSpinner').style.display = 'none'; document.getElementById('jobNotFound').style.display = 'block'; return; }
  try {
    // Prefer the single-job route: same public projection as a list item,
    // one request instead of downloading the whole open-vacancies list.
    // A miss here (job closed/demo/removed/unknown id, or the route not
    // deployed yet) falls back to the list route below rather than failing
    // the page outright -- this keeps vacature.html working through the
    // deploy window where the site ships before the API does.
    let job = null;
    try {
      const detailController = new AbortController();
      const detailTimeoutId = setTimeout(() => detailController.abort(), 10000);
      const detailRes = await fetch(`https://api.gsprecruitment.nl/api/public/jobs/${encodeURIComponent(jobId)}`, { signal: detailController.signal });
      clearTimeout(detailTimeoutId);
      if (detailRes.ok) job = await detailRes.json();
    } catch (_) { /* network error on the detail route -- fall back below */ }
    if (!job) {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000);
      const res = await fetch('https://api.gsprecruitment.nl/api/public/jobs', { signal: controller.signal });
      clearTimeout(timeoutId);
      if (!res.ok) throw new Error('API error');
      const jobs = await res.json();
      job = Array.isArray(jobs) ? jobs.find(j => j.id == jobId || j.slug === jobId) : null;
    }
    if (!job) throw new Error('Not found');
    document.getElementById('loadingSpinner').style.display = 'none';
    document.getElementById('jobDetail').style.display = 'block';
    const lang = localStorage.getItem('gsp_lang') || 'nl';
    document.title = lang === 'nl'
      ? `${job.title} — Vacature bij GSP Recruitment`
      : `${job.title} — Job at GSP Recruitment`;
    const company = job.company_display || job.company || 'confidential';
    const jobDescription = lang === 'nl'
      ? `${job.title} bij ${company !== 'confidential' ? company : 'een Brainport techbedrijf'}. Solliciteer direct of stuur je CV.`
      : `${job.title} at ${company !== 'confidential' ? company : 'a Brainport tech company'}. Apply directly or send your CV.`;
    document.querySelector('meta[name="description"]').content = jobDescription;
    document.querySelector('link[rel="canonical"]').href = window.location.href;
    document.getElementById('ogTitle').setAttribute('content', document.title);
    document.getElementById('ogDescription').setAttribute('content', jobDescription);
    document.getElementById('jobTitle').textContent = job.title;
    const EMPLOYMENT_TYPE_LABEL = { vast: { en: 'Permanent', nl: 'Vast' }, detachering: { en: 'Secondment', nl: 'Detachering' }, interim: { en: 'Interim', nl: 'Interim' } };
    const employmentTypeLabel = EMPLOYMENT_TYPE_LABEL[job.employment_type] ? EMPLOYMENT_TYPE_LABEL[job.employment_type][lang] : job.employment_type;
    // location_type label map (#152 defect E): keys are lowercase, lookup
    // is case-insensitive against the stored values ("On-site", "Hybride").
    // An unmapped value falls back to the raw value, same as before.
    const LOCATION_TYPE_LABEL = { 'on-site': { nl: 'Op locatie', en: 'On-site' }, hybride: { nl: 'Hybride', en: 'Hybrid' } };
    const locationTypeKey = job.location_type ? String(job.location_type).toLowerCase() : '';
    const locationLabel = locationTypeKey === 'remote'
      ? (lang === 'nl' ? 'Remote' : 'Remote')
      : [job.city, LOCATION_TYPE_LABEL[locationTypeKey] ? LOCATION_TYPE_LABEL[locationTypeKey][lang] : job.location_type].filter(Boolean).join(' · ');
    // Currency per STYLE.md (#152 defect F): no currency code, no "k" --
    // €1.234 in Dutch (period thousands separator), €1,234 in English.
    const salaryLabel = (job.salary_min != null && job.salary_max != null)
      ? `€${Number(job.salary_min).toLocaleString(lang === 'nl' ? 'nl-NL' : 'en-US')} – €${Number(job.salary_max).toLocaleString(lang === 'nl' ? 'nl-NL' : 'en-US')}`
      : '';
    // Salary line under the H1 (design-spec-batch.md item 1a): a second,
    // more prominent render of the same salaryLabel numbers, not a
    // duplicate fetch. Uses the same €-formatting as salaryLabel above
    // (no space after €, toLocaleString per language) rather than the
    // spec's own example markup, which had a space -- matching the
    // existing codebase pattern here, not the prompt's literal example.
    const hasSalaryRange = job.salary_min != null && job.salary_max != null;
    const salaryLineHtml = hasSalaryRange
      ? `<span class="lang-nl">€${Number(job.salary_min).toLocaleString('nl-NL')} – €${Number(job.salary_max).toLocaleString('nl-NL')} <span class="job-salary-line__unit">bruto per jaar</span></span>` +
        `<span class="lang-en">€${Number(job.salary_min).toLocaleString('en-US')} – €${Number(job.salary_max).toLocaleString('en-US')} <span class="job-salary-line__unit">gross per year</span></span>`
      : `<span class="lang-nl">Salaris niet opgegeven</span><span class="lang-en">Salary not specified</span>`;
    const jobSalaryLineEl = document.getElementById('jobSalaryLine');
    if (jobSalaryLineEl) {
      jobSalaryLineEl.innerHTML = salaryLineHtml;
      jobSalaryLineEl.classList.toggle('job-salary-line--unset', !hasSalaryRange);
    }
    const metaHtml = [];
    if (company !== 'confidential') metaHtml.push(`<div class="meta-item"><strong><span class="lang-en">Company</span><span class="lang-nl">Bedrijf</span></strong>${GSP.esc(company)}</div>`);
    if (locationLabel) metaHtml.push(`<div class="meta-item"><strong><span class="lang-en">Location</span><span class="lang-nl">Locatie</span></strong>${GSP.esc(locationLabel)}</div>`);
    if (job.seniority) metaHtml.push(`<div class="meta-item"><strong><span class="lang-en">Level</span><span class="lang-nl">Niveau</span></strong>${GSP.esc(job.seniority)}</div>`);
    if (job.department) metaHtml.push(`<div class="meta-item"><strong><span class="lang-en">Field</span><span class="lang-nl">Vakgebied</span></strong>${GSP.esc(job.department)}</div>`);
    if (salaryLabel) metaHtml.push(`<div class="meta-item"><strong><span class="lang-en">Salary</span><span class="lang-nl">Salaris</span></strong>${GSP.esc(salaryLabel)}</div>`);
    if (employmentTypeLabel) metaHtml.push(`<div class="meta-item"><strong><span class="lang-en">Type</span><span class="lang-nl">Type</span></strong>${GSP.esc(employmentTypeLabel)}</div>`);
    if (job.sponsorship_possible) metaHtml.push(`<div class="meta-item"><strong><span class="lang-en">Sponsorship</span><span class="lang-nl">Sponsoring</span></strong><span class="lang-en">Visa sponsorship possible</span><span class="lang-nl">Visumsponsoring mogelijk</span></div>`);
    document.getElementById('jobMeta').innerHTML = metaHtml.join('');
    // English text twin (issue #153): each section carries a Dutch field
    // (always the field the 27 pool vacancies and every earlier job order
    // have) and a nullable English twin (job.*_en, migrations/046). When
    // the English twin is present it is shown under the English heading;
    // when it is absent (every row today) the English heading gets a
    // visibly marked fallback instead of the Dutch paragraph unmarked --
    // the "current unmarked mix" the issue calls out is exactly a
    // language-less <p> shared between both headings, so every paragraph
    // below is built with its own explicit lang-en/lang-nl class.
    const bodyHtml = buildJobBodyHtml(job);
    document.getElementById('jobBody').innerHTML = bodyHtml;
    // Inject JSON-LD for Google. jobDetailJsonLd is a <script type="application/ld+json">
    // (not a div): textContent is never HTML-parsed, so job.* values here
    // cannot break out into markup even though they are not esc()'d.
    // buildJobPostingLd() returns null for an anonymous-client vacancy --
    // leave the element empty rather than writing the literal string "null".
    const jobLd = buildJobPostingLd(job);
    document.getElementById('jobDetailJsonLd').textContent = jobLd ? JSON.stringify(jobLd) : '';

    // Honest-paragraph line (SITE-DESIGN-SPEC.md §3.7): shown above the
    // apply CTA only for an anonymous-client vacancy. The full disclosure
    // already lives in job.description; this is the short, always-visible
    // reminder the owner's spookvacature mitigation requires.
    const anonNote = document.getElementById('anonClientNote');
    if (anonNote) anonNote.style.display = job.anonymous_client === true ? 'block' : 'none';

    // Smart apply: logged-in candidates apply in one click via the API,
    // exactly as before -- including for an anonymous-client vacancy, since
    // they already have an account relationship with us. Everyone else
    // normally goes to the contact form with the job reference attached;
    // for an anonymous-client vacancy that link is replaced with an inline
    // talent-pool opt-in panel instead (renderVacancyApplyPanel below),
    // since "contact us about this employer" doesn't fit when we can't
    // name the employer yet.
    const applyBtn = document.getElementById('applyBtn');
    const user = (typeof Auth !== 'undefined') && Auth.getUser && Auth.getUser();
    const isLoggedInCandidate = !!(user && user.role === 'candidate');

    if (job.anonymous_client === true && !isLoggedInCandidate) {
      if (applyBtn) applyBtn.style.display = 'none';
      renderVacancyApplyPanel(job, lang);
    } else if (applyBtn) {
      applyBtn.href = `contact.html?job=${encodeURIComponent(job.id)}&title=${encodeURIComponent(job.title)}`;
      if (isLoggedInCandidate) {
        applyBtn.addEventListener('click', async (e) => {
          e.preventDefault();
          applyBtn.style.pointerEvents = 'none';
          try {
            const res = await Auth.fetch('/v1/candidate/applications', {
              method: 'POST',
              body: JSON.stringify({ job_id: job.id }),
            });
            if (res && res.ok) {
              Auth.toast(lang === 'nl' ? 'Sollicitatie verstuurd!' : 'Application sent!', 'success');
              applyBtn.innerHTML = '<i class="fas fa-check"></i> ' + (lang === 'nl' ? 'Gesolliciteerd' : 'Applied');
            } else if (res) {
              const err = await res.json().catch(() => ({}));
              Auth.toast(err.detail || (lang === 'nl' ? 'Solliciteren mislukt' : 'Application failed'), 'error');
              applyBtn.style.pointerEvents = '';
            }
          } catch (_) {
            Auth.toast(lang === 'nl' ? 'Er ging iets mis' : 'Something went wrong', 'error');
            applyBtn.style.pointerEvents = '';
          }
        });
      }
    }

    // Sticky mobile apply bar (design-spec-batch.md item 3): mirrors
    // whichever apply action the branching above chose.
    initApplySticky(job, lang, salaryLabel);
  } catch(e) {
    document.getElementById('loadingSpinner').style.display = 'none';
    document.getElementById('jobNotFound').style.display = 'block';
  }
})();
}

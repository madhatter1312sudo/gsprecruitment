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
      sameAs: 'https://gsprecruitment.nl',
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

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { buildJobPostingLd, jobPostingEmploymentType, jobPostingLocation, jobPostingValidThrough };
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
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);
    const res = await fetch('https://api.gsprecruitment.nl/api/public/jobs', { signal: controller.signal });
    clearTimeout(timeoutId);
    if (!res.ok) throw new Error('API error');
    const jobs = await res.json();
    const job = Array.isArray(jobs) ? jobs.find(j => j.id == jobId || j.slug === jobId) : null;
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
    const locationLabel = job.location_type && String(job.location_type).toLowerCase() === 'remote'
      ? (lang === 'nl' ? 'Remote' : 'Remote')
      : [job.city, job.location_type].filter(Boolean).join(' · ');
    const salaryLabel = (job.salary_min != null && job.salary_max != null)
      ? `${job.salary_currency || 'EUR'} ${Number(job.salary_min).toLocaleString(lang === 'nl' ? 'nl-NL' : 'en-US')} – ${Number(job.salary_max).toLocaleString(lang === 'nl' ? 'nl-NL' : 'en-US')}`
      : '';
    const metaHtml = [];
    if (company !== 'confidential') metaHtml.push(`<div class="meta-item"><strong><span class="lang-en">Company</span><span class="lang-nl">Bedrijf</span></strong>${GSP.esc(company)}</div>`);
    if (locationLabel) metaHtml.push(`<div class="meta-item"><strong><span class="lang-en">Location</span><span class="lang-nl">Locatie</span></strong>${GSP.esc(locationLabel)}</div>`);
    if (job.seniority) metaHtml.push(`<div class="meta-item"><strong><span class="lang-en">Level</span><span class="lang-nl">Niveau</span></strong>${GSP.esc(job.seniority)}</div>`);
    if (job.department) metaHtml.push(`<div class="meta-item"><strong><span class="lang-en">Field</span><span class="lang-nl">Vakgebied</span></strong>${GSP.esc(job.department)}</div>`);
    if (salaryLabel) metaHtml.push(`<div class="meta-item"><strong><span class="lang-en">Salary</span><span class="lang-nl">Salaris</span></strong>${GSP.esc(salaryLabel)}</div>`);
    if (employmentTypeLabel) metaHtml.push(`<div class="meta-item"><strong><span class="lang-en">Type</span><span class="lang-nl">Type</span></strong>${GSP.esc(employmentTypeLabel)}</div>`);
    if (job.sponsorship_possible) metaHtml.push(`<div class="meta-item"><strong><span class="lang-en">Sponsorship</span><span class="lang-nl">Sponsoring</span></strong><span class="lang-en">Visa sponsorship possible</span><span class="lang-nl">Visumsponsoring mogelijk</span></div>`);
    document.getElementById('jobMeta').innerHTML = metaHtml.join('');
    const bodyHtml = [];
    if (job.description) bodyHtml.push(`<h2 class="lang-en">About the role</h2><h2 class="lang-nl">Over de rol</h2><p>${GSP.esc(job.description)}</p>`);
    if (job.requirements) bodyHtml.push(`<h2 class="lang-en">What we're looking for</h2><h2 class="lang-nl">Wat we zoeken</h2><p>${GSP.esc(job.requirements)}</p>`);
    if (job.responsibilities) bodyHtml.push(`<h2 class="lang-en">Responsibilities</h2><h2 class="lang-nl">Verantwoordelijkheden</h2><p>${GSP.esc(job.responsibilities)}</p>`);
    document.getElementById('jobBody').innerHTML = bodyHtml.join('');
    // Inject JSON-LD for Google. jobDetailJsonLd is a <script type="application/ld+json">
    // (not a div): textContent is never HTML-parsed, so job.* values here
    // cannot break out into markup even though they are not esc()'d.
    document.getElementById('jobDetailJsonLd').textContent = JSON.stringify(buildJobPostingLd(job));

    // Smart apply: logged-in candidates apply in one click via the API;
    // everyone else goes to the contact form with the job reference attached.
    const applyBtn = document.getElementById('applyBtn');
    if (applyBtn) {
      applyBtn.href = `contact.html?job=${encodeURIComponent(job.id)}&title=${encodeURIComponent(job.title)}`;
      const user = (typeof Auth !== 'undefined') && Auth.getUser && Auth.getUser();
      if (user && user.role === 'candidate') {
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
  } catch(e) {
    document.getElementById('loadingSpinner').style.display = 'none';
    document.getElementById('jobNotFound').style.display = 'block';
  }
})();
}

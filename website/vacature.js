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
    const jobDescription = lang === 'nl'
      ? `${job.title} bij ${job.company || 'een Brainport techbedrijf'}. Solliciteer direct of stuur je CV.`
      : `${job.title} at ${job.company || 'a Brainport tech company'}. Apply directly or send your CV.`;
    document.querySelector('meta[name="description"]').content = jobDescription;
    document.querySelector('link[rel="canonical"]').href = window.location.href;
    document.getElementById('ogTitle').setAttribute('content', document.title);
    document.getElementById('ogDescription').setAttribute('content', jobDescription);
    document.getElementById('jobTitle').textContent = job.title;
    const metaHtml = [];
    if (job.company) metaHtml.push(`<div class="meta-item"><strong><span class="lang-en">Company</span><span class="lang-nl">Bedrijf</span></strong>${GSP.esc(job.company)}</div>`);
    if (job.location) metaHtml.push(`<div class="meta-item"><strong><span class="lang-en">Location</span><span class="lang-nl">Locatie</span></strong>${GSP.esc(job.location)}</div>`);
    if (job.seniority) metaHtml.push(`<div class="meta-item"><strong><span class="lang-en">Level</span><span class="lang-nl">Niveau</span></strong>${GSP.esc(job.seniority)}</div>`);
    if (job.department) metaHtml.push(`<div class="meta-item"><strong><span class="lang-en">Field</span><span class="lang-nl">Vakgebied</span></strong>${GSP.esc(job.department)}</div>`);
    if (job.salary_range) metaHtml.push(`<div class="meta-item"><strong><span class="lang-en">Salary</span><span class="lang-nl">Salaris</span></strong>${GSP.esc(job.salary_range)}</div>`);
    if (job.employment_type) metaHtml.push(`<div class="meta-item"><strong><span class="lang-en">Type</span><span class="lang-nl">Type</span></strong>${GSP.esc(job.employment_type)}</div>`);
    document.getElementById('jobMeta').innerHTML = metaHtml.join('');
    const bodyHtml = [];
    if (job.description) bodyHtml.push(`<h2 class="lang-en">About the role</h2><h2 class="lang-nl">Over de rol</h2><p>${GSP.esc(job.description)}</p>`);
    if (job.requirements) bodyHtml.push(`<h2 class="lang-en">What we're looking for</h2><h2 class="lang-nl">Wat we zoeken</h2><p>${GSP.esc(job.requirements)}</p>`);
    if (job.responsibilities) bodyHtml.push(`<h2 class="lang-en">Responsibilities</h2><h2 class="lang-nl">Verantwoordelijkheden</h2><p>${GSP.esc(job.responsibilities)}</p>`);
    document.getElementById('jobBody').innerHTML = bodyHtml.join('');
    // Inject JSON-LD for Google. jobDetailJsonLd is a <script type="application/ld+json">
    // (not a div): textContent is never HTML-parsed, so job.* values here
    // cannot break out into markup even though they are not esc()'d.
    const ld = document.getElementById('jobDetailJsonLd');
    ld.textContent = JSON.stringify({
      "@context": "https://schema.org",
      "@type": "JobPosting",
      "title": job.title,
      "description": job.description || '',
      "datePosted": job.created_at || new Date().toISOString().split('T')[0],
      "hiringOrganization": { "@type": "Organization", "name": job.company || "GSP Recruitment", "sameAs": "https://gsprecruitment.nl" },
      "jobLocation": job.location ? { "@type": "Place", "address": { "@type": "PostalAddress", "addressLocality": job.location, "addressCountry": "NL" } } : undefined,
      "employmentType": job.employment_type || "FULL_TIME",
      "directApply": true
    });

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

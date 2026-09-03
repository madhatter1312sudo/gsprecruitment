(async () => {
  const params = new URLSearchParams(window.location.search);
  const slug = params.get('slug');
  const lang = localStorage.getItem('gsp_lang') || 'nl';

  const heroSection = document.getElementById('postHero');
  const bodySection = document.getElementById('postBody');
  const notFoundSection = document.getElementById('notFound');

  function showNotFound() {
    notFoundSection.style.display = 'block';
  }

  if (!slug) { showNotFound(); return; }

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);
    const res = await fetch(`https://api.gsprecruitment.nl/api/v1/public/blog/${encodeURIComponent(slug)}`, { signal: controller.signal });
    clearTimeout(timeoutId);
    if (!res.ok) throw new Error('not found');
    const p = await res.json();

    // Title / meta
    document.getElementById('titleNl').textContent = p.title_nl || '';
    document.getElementById('titleEn').textContent = p.title_en || '';
    const pageTitle = (lang === 'nl' ? p.title_nl : p.title_en) + ' — GSP Recruitment';
    document.title = pageTitle;
    document.getElementById('pageTitleTag').textContent = pageTitle;

    const canonicalHref = `https://gsprecruitment.nl/blog/post?slug=${encodeURIComponent(p.slug || slug)}`;
    document.getElementById('canonicalLink').setAttribute('href', canonicalHref);

    const metaDescTag = document.createElement('meta');
    metaDescTag.name = 'description';
    metaDescTag.content = (lang === 'nl' ? p.excerpt_nl : p.excerpt_en) || '';
    document.head.appendChild(metaDescTag);

    const postExcerpt = (lang === 'nl' ? p.excerpt_nl : p.excerpt_en) || '';
    document.getElementById('ogTitle').setAttribute('content', pageTitle);
    document.getElementById('ogDescription').setAttribute('content', postExcerpt);

    if (p.published_at) {
      const d = new Date(p.published_at);
      document.getElementById('metaDate').textContent = d.toLocaleDateString(lang === 'nl' ? 'nl-NL' : 'en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
    }
    document.getElementById('metaReadTimeNl').textContent = `${p.read_time_min || '—'} min leestijd`;
    document.getElementById('metaReadTimeEn').textContent = `${p.read_time_min || '—'} min read`;

    const tagsWrap = document.getElementById('tagsWrap');
    tagsWrap.innerHTML = (p.tags || []).map(t => `<span>${GSP.esc(t)}</span>`).join('');

    // Body — blog authors can enter raw HTML in the admin editor, and the
    // API does not sanitize it server-side yet (tracked as WS-C.3b), so
    // run it through the client-side allow-list sanitizer before render.
    document.getElementById('bodyNl').innerHTML = GSP.sanitizeHtml(p.body_nl || '');
    document.getElementById('bodyEn').innerHTML = GSP.sanitizeHtml(p.body_en || '');

    heroSection.style.display = 'block';
    bodySection.style.display = 'block';

    // JSON-LD structured data
    const ld = {
      "@context": "https://schema.org",
      "@type": "Article",
      "mainEntityOfPage": { "@type": "WebPage", "@id": canonicalHref },
      "headline": pageTitle,
      "description": p.excerpt_nl || p.excerpt_en || '',
      "image": "https://gsprecruitment.nl/og-image.png",
      "datePublished": p.published_at || undefined,
      "dateModified": p.published_at || undefined,
      "author": { "@type": "Organization", "name": "GSP Recruitment", "url": "https://gsprecruitment.nl/" },
      "publisher": {
        "@type": "Organization",
        "name": "GSP Recruitment",
        "url": "https://gsprecruitment.nl/",
        "logo": { "@type": "ImageObject", "url": "https://gsprecruitment.nl/logo.png" }
      },
      "keywords": p.tags || []
    };
    const ldScript = document.createElement('script');
    ldScript.type = 'application/ld+json';
    ldScript.textContent = JSON.stringify(ld);
    document.head.appendChild(ldScript);

  } catch (e) {
    showNotFound();
  }
})();

// Blog listing — reads posts.json and renders cards
(async () => {
  const grid = document.getElementById('blogGrid');
  if (!grid) return;
  const lang = localStorage.getItem('gsp_lang') || 'nl';

  function renderApiPosts(posts) {
    grid.innerHTML = posts.map(p => {
      const title = lang === 'nl' ? p.title_nl : p.title_en;
      const excerpt = lang === 'nl' ? p.excerpt_nl : p.excerpt_en;
      const date = p.published_at ? new Date(p.published_at).toLocaleDateString(lang === 'nl' ? 'nl-NL' : 'en-GB', { day: 'numeric', month: 'long', year: 'numeric' }) : '';
      const tags = (p.tags || []).map(t => `<span class="tag">${GSP.esc(t)}</span>`).join('');
      return `<article class="blog-card fade-in">
        ${tags}
        <h3>${GSP.esc(title)}</h3>
        <div class="meta">${GSP.esc(date)} · ${GSP.esc(p.read_time_min)} min ${lang === 'nl' ? 'leestijd' : 'read'}</div>
        <p>${GSP.esc(excerpt)}</p>
        <a href="post.html?slug=${encodeURIComponent(p.slug)}" class="read-more"><span class="lang-en">Read more</span><span class="lang-nl">Lees meer</span> <i class="fas fa-arrow-right"></i></a>
      </article>`;
    }).join('');
  }

  function renderLegacyPosts(posts) {
    grid.innerHTML = posts.map(p => {
      const title = lang === 'nl' ? p.title_nl : p.title_en;
      const date = lang === 'nl' ? p.date_nl : p.date_en;
      const excerpt = lang === 'nl' ? p.excerpt_nl : p.excerpt_en;
      const tags = (p.tags || []).map(t => `<span class="tag">${GSP.esc(t)}</span>`).join('');
      return `<article class="blog-card fade-in">
        ${tags}
        <h3>${GSP.esc(title)}</h3>
        <div class="meta">${GSP.esc(date)} · ${GSP.esc(p.read_time_min)} min read · by ${GSP.esc(p.author)}</div>
        <p>${GSP.esc(excerpt)}</p>
        <a href="${encodeURIComponent(p.id)}.html" class="read-more"><span class="lang-en">Read more</span><span class="lang-nl">Lees meer</span> <i class="fas fa-arrow-right"></i></a>
      </article>`;
    }).join('');
  }

  function fetchWithTimeout(url, ms) {
    const controller = new AbortController();
    const t = setTimeout(() => controller.abort(), ms);
    return fetch(url, { signal: controller.signal }).finally(() => clearTimeout(t));
  }

  function renderLoadError() {
    grid.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:60px 20px">
      <i class="fas fa-triangle-exclamation" style="font-size:1.6rem;color:var(--gold);margin-bottom:12px"></i>
      <p><span class="lang-nl">Kon niet laden — probeer opnieuw</span><span class="lang-en">Could not load — try again</span></p>
      <button class="btn btn-ghost btn-sm" id="blogRetryBtn" style="margin-top:16px"><i class="fas fa-redo"></i> <span class="lang-nl">Opnieuw proberen</span><span class="lang-en">Retry</span></button>
    </div>`;
    document.getElementById('blogRetryBtn')?.addEventListener('click', loadPosts);
  }

  async function loadPosts() {
    try {
      const res = await fetchWithTimeout('https://api.gsprecruitment.nl/api/v1/public/blog', 10000);
      if (!res.ok) throw new Error('bad response');
      const posts = await res.json();
      if (!Array.isArray(posts)) throw new Error('bad payload');
      renderApiPosts(posts);
    } catch (e) {
      try {
        const res = await fetchWithTimeout('posts.json', 10000);
        const data = await res.json();
        renderLegacyPosts(data.posts || []);
      } catch (e2) {
        renderLoadError();
      }
    }
  }

  await loadPosts();
})();

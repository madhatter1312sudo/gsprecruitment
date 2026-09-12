// Blog listing: reads posts.json and renders cards
//
// Cards render as archetype 2 (lichte inhoudskaart met rand,
// SITE-DESIGN-SPEC.md §8.x.1 / §8.x.2 shared .card class). The whole
// card is the link (same nesting pattern as the archetype-1 choice-card
// on index.html: <a class="card">...<span class="go-link">...</span></a>)
// so the existing .card:hover/.card:focus-visible rules in styles.css
// already give keyboard focus the identical outline+lift the mouse gets,
// with no new CSS selector needed. A nested <a> CTA would have required
// a `.card:focus-within` rule that does not exist yet for the bare
// `.card` class (see scratchpad/ws1-css-requests/cluster-D.md).
(async () => {
  const grid = document.getElementById('blogGrid');
  if (!grid) return;
  const lang = localStorage.getItem('gsp_lang') || 'nl';

  function tagChips(tags) {
    return (tags || []).map(t => `<span class="chip">${GSP.esc(t)}</span>`).join('');
  }

  function cardHTML(href, title, excerpt, metaLine, tags) {
    return `<a href="${href}" class="card fade-in">
        <div style="display:flex;flex-wrap:wrap;gap:var(--space-sm);margin-bottom:var(--space-sm)">${tagChips(tags)}</div>
        <div style="font-family:var(--font-mono);font-size:var(--font-size-xs);color:var(--gray-400);margin-bottom:var(--space-md)">${metaLine}</div>
        <h3>${GSP.esc(title)}</h3>
        <p class="card-clamp-3" style="margin:var(--space-sm) 0 0">${GSP.esc(excerpt)}</p>
        <span class="go-link"><span class="lang-nl">Lees meer →</span><span class="lang-en">Read more →</span></span>
      </a>`;
  }

  function renderApiPosts(posts) {
    grid.innerHTML = posts.map(p => {
      const title = lang === 'nl' ? p.title_nl : p.title_en;
      const excerpt = lang === 'nl' ? p.excerpt_nl : p.excerpt_en;
      const date = p.published_at ? new Date(p.published_at).toLocaleDateString(lang === 'nl' ? 'nl-NL' : 'en-GB', { day: 'numeric', month: 'long', year: 'numeric' }) : '';
      const readLabel = lang === 'nl' ? 'leestijd' : 'read';
      const metaLine = `${GSP.esc(date)}${date ? ' · ' : ''}${GSP.esc(p.read_time_min)} min ${readLabel}`;
      const href = `post.html?slug=${encodeURIComponent(p.slug)}`;
      return cardHTML(href, title, excerpt, metaLine, p.tags);
    }).join('');
  }

  function renderLegacyPosts(posts) {
    grid.innerHTML = posts.map(p => {
      const title = lang === 'nl' ? p.title_nl : p.title_en;
      const date = lang === 'nl' ? p.date_nl : p.date_en;
      const excerpt = lang === 'nl' ? p.excerpt_nl : p.excerpt_en;
      const metaLine = `${GSP.esc(date)} · ${GSP.esc(p.read_time_min)} min read · ${GSP.esc(p.author)}`;
      const href = `${encodeURIComponent(p.id)}.html`;
      return cardHTML(href, title, excerpt, metaLine, p.tags);
    }).join('');
  }

  function fetchWithTimeout(url, ms) {
    const controller = new AbortController();
    const t = setTimeout(() => controller.abort(), ms);
    return fetch(url, { signal: controller.signal }).finally(() => clearTimeout(t));
  }

  // Loading state (§8.x.1 archetype 2): the card frame (border/kader)
  // stays, kop/meta/excerpt positions become flat --gray-50 blocks via
  // the existing .card--loading h3/p rule in styles.css. No shimmer, no
  // real link inside an aria-hidden card.
  function cardSkeleton() {
    return `<div class="card card--loading" aria-hidden="true">
        <p style="width:140px;margin:0 0 var(--space-md)">&nbsp;</p>
        <h3 style="width:70%;height:1.4em;margin-bottom:var(--space-sm)">&nbsp;</h3>
        <p style="width:100%;margin-bottom:4px">&nbsp;</p>
        <p style="width:92%;margin-bottom:4px">&nbsp;</p>
        <p style="width:55%;margin-bottom:0">&nbsp;</p>
      </div>`;
  }

  function renderLoading() {
    grid.innerHTML = `${cardSkeleton()}${cardSkeleton()}${cardSkeleton()}`;
  }

  // Error state (§8.x.1 archetype 2): "Kon artikelen niet laden, probeer
  // opnieuw" with a text-link retry. Re-runs the fetch, not a full page
  // reload, so keyboard/screen-reader users keep their place.
  function renderLoadError() {
    grid.innerHTML = `<div class="card card--error" style="grid-column:1/-1;max-width:420px;margin-inline:auto;text-align:center;align-items:center">
        <p style="font-weight:600;margin-bottom:var(--space-md)">
          <span class="lang-nl">Kon artikelen niet laden</span><span class="lang-en">Could not load articles</span>
        </p>
        <button type="button" class="go-link" id="blogRetryBtn" style="background:none;border:none;padding:0;cursor:pointer;font-family:inherit">
          <span class="lang-nl">Opnieuw proberen →</span><span class="lang-en">Try again →</span>
        </button>
      </div>`;
    document.getElementById('blogRetryBtn')?.addEventListener('click', loadPosts);
  }

  async function loadPosts() {
    renderLoading();
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

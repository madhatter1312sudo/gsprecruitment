/**
 * gsp-util.js — shared XSS-safety helpers for the public site, portals and
 * admin panel. Load this before any script that renders API/user-derived
 * values as HTML.
 *
 * GSP.esc(s)        — escape a value for safe use as HTML text or inside a
 *                      quoted HTML attribute (& < > " ' `).
 * GSP.safeUrl(s)     — allow only http(s) URLs; anything else (javascript:,
 *                      data:, vbscript:, bare garbage) becomes ''.
 * GSP.sanitizeHtml(html) — conservative allow-list HTML sanitizer for rich
 *                      text fields (currently only blog post bodies) using
 *                      DOMParser. Allows headings, paragraphs, lists, basic
 *                      inline formatting, links and simple tables; drops
 *                      every other tag/attribute, all event handlers, and
 *                      the entire subtree of <script>/<style>/<iframe>/
 *                      <img>/<form> etc (DROP_TAGS below). Relative/
 *                      same-origin hrefs (/, ./, ../, #) pass through
 *                      verbatim; absolute links go through GSP.safeUrl().
 */
(function (global) {
  'use strict';

  var GSP = global.GSP = global.GSP || {};

  // ── esc: HTML/attribute-safe text escaping ────────────────────────────
  GSP.esc = function esc(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
      .replace(/`/g, '&#96;');
  };

  // ── safeUrl: http(s)-only URL allow-list ───────────────────────────────
  // esc() stops attribute breakout but not a javascript:/data: scheme, so
  // links built from candidate/user-supplied strings must go through this.
  GSP.safeUrl = function safeUrl(s) {
    if (!s) return '';
    var v = String(s).trim();
    if (!v) return '';
    // Sourced-pipeline rows may hold bare domains ("linkedin.com/in/x") —
    // treat those as https rather than resolving against a dummy base.
    if (!/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(v)) v = 'https://' + v;
    try {
      var u = new URL(v);
      if (u.protocol === 'http:' || u.protocol === 'https:') return u.href;
    } catch (e) { /* unparseable -> drop */ }
    return '';
  };

  // ── sanitizeHtml: allow-list sanitizer for rich text (blog bodies) ─────
  var ALLOWED_TAGS = {
    H2: true, H3: true, H4: true, P: true, UL: true, OL: true, LI: true,
    STRONG: true, EM: true, A: true, BR: true, BLOCKQUOTE: true,
    CODE: true, PRE: true,
    TABLE: true, THEAD: true, TBODY: true, TR: true, TH: true, TD: true
  };

  // Tags whose entire subtree (including text content) must be dropped —
  // unlike an unrecognized-but-harmless wrapper (e.g. <div>), the *content*
  // of these is either executable or not meant to ever render as text.
  var DROP_TAGS = {
    SCRIPT: true, STYLE: true, NOSCRIPT: true, TEMPLATE: true,
    IFRAME: true, OBJECT: true, EMBED: true, SVG: true, MATH: true,
    FORM: true, INPUT: true, TEXTAREA: true
  };

  // A same-origin/relative reference is safe to keep verbatim (it can't
  // carry a javascript:/data: scheme) and isn't a link "off" the site, so
  // it skips target=_blank/rel=noopener. Reject anything with a ":" before
  // the first "/" — that's a scheme, not a path.
  function relativeHref(v) {
    if (v.indexOf('//') === 0) return null; // protocol-relative -> not same-origin
    if (/^[/.#]/.test(v)) {
      var slash = v.indexOf('/');
      var colon = v.indexOf(':');
      if (colon === -1 || (slash !== -1 && colon > slash) || v.charAt(0) === '#') {
        return v;
      }
    }
    return null;
  }

  function sanitizeNode(node, out) {
    if (node.nodeType === Node.TEXT_NODE) {
      out.appendChild(document.createTextNode(node.nodeValue));
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return; // drop comments etc.

    var tag = node.tagName;

    if (DROP_TAGS[tag]) return; // drop tag AND its content, no recursion

    if (!ALLOWED_TAGS[tag]) {
      // Not an allowed element — drop the tag but keep sanitized children
      // (so e.g. a stripped <div> doesn't eat the paragraph inside it).
      for (var i = 0; i < node.childNodes.length; i++) {
        sanitizeNode(node.childNodes[i], out);
      }
      return;
    }

    var clean = document.createElement(tag);
    if (tag === 'A') {
      var raw = node.getAttribute('href') || '';
      var rel = relativeHref(raw.trim());
      if (rel !== null) {
        clean.setAttribute('href', rel);
      } else {
        var href = GSP.safeUrl(raw);
        if (href) {
          clean.setAttribute('href', href);
          clean.setAttribute('rel', 'noopener');
          clean.setAttribute('target', '_blank');
        }
      }
    }
    for (var j = 0; j < node.childNodes.length; j++) {
      sanitizeNode(node.childNodes[j], clean);
    }
    out.appendChild(clean);
  }

  GSP.sanitizeHtml = function sanitizeHtml(html) {
    if (!html) return '';
    var parser = new DOMParser();
    // DOMParser never executes scripts and never fetches external
    // resources for text/html documents, so parsing untrusted input here
    // is safe — the danger is only in what we do with the parsed tree.
    var doc = parser.parseFromString('<!doctype html><body>' + String(html) + '</body>', 'text/html');
    var frag = document.createDocumentFragment();
    var body = doc.body;
    for (var i = 0; i < body.childNodes.length; i++) {
      sanitizeNode(body.childNodes[i], frag);
    }
    var wrap = document.createElement('div');
    wrap.appendChild(frag);
    return wrap.innerHTML;
  };

})(typeof window !== 'undefined' ? window : this);

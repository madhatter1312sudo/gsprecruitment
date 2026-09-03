/* ============================================================
   GSP Recruitment — render.js  (WS-B.1)
   Minimal auto-escaping template helper for admin.js markup.

   GSP.html`...`      — tagged template: every interpolated value is
                         escaped via GSP.esc (strings, numbers, dates —
                         anything that isn't already marked raw()).
                         null/undefined interpolate to "". Arrays of
                         values (including nested html`` results) are
                         joined with no separator, each element escaped
                         (or preserved raw) independently — this is how
                         a row list becomes a <tbody> body: rows.map(r =>
                         html`<tr>...</tr>`) interpolates straight into
                         an outer html`` call.
   GSP.raw(value)      — wraps a string (or array of strings/html``
                         results) that is already safe HTML so html``
                         does not re-escape it. Use ONLY for markup you
                         built yourself out of static strings and other
                         html()/raw() results — never wrap a raw
                         API/user-derived string.
   GSP.mount(el, r)     — el.innerHTML = the html`` result (or raw()
                         result). Safe no-op when el is null/undefined,
                         matching the existing `if (el) el.innerHTML =
                         ...` call sites this replaces.

   Depends on GSP.esc from gsp-util.js — load that first.
   ============================================================ */
(function (root) {
  'use strict';

  var GSP = root.GSP = root.GSP || {};

  if (typeof GSP.esc !== 'function') {
    throw new Error('render.js requires GSP.esc (gsp-util.js) to be loaded first');
  }

  // Marker wrapper for a string that is already safe HTML and must not
  // be escaped again when it lands inside a surrounding html`` template.
  function RawHtml(value) {
    this.value = value;
  }
  RawHtml.prototype.toString = function () {
    return this.value;
  };

  // Turn one interpolated value into its final (already-safe) string.
  function interpolate(value) {
    if (value instanceof RawHtml) return value.value;
    if (Array.isArray(value)) return value.map(interpolate).join('');
    if (value == null) return '';
    return GSP.esc(value);
  }

  // Like interpolate(), but a plain string element is trusted verbatim
  // instead of being escaped — used only inside raw(), whose whole
  // contract is "the caller vouches this is already safe HTML".
  function rawJoin(value) {
    if (value instanceof RawHtml) return value.value;
    if (Array.isArray(value)) return value.map(rawJoin).join('');
    return value == null ? '' : String(value);
  }

  // raw(value) — mark a string, or an array of strings/RawHtml/html``
  // results, as pre-escaped HTML that should be inserted verbatim.
  function raw(value) {
    if (value instanceof RawHtml) return value;
    if (Array.isArray(value)) return new RawHtml(rawJoin(value));
    return new RawHtml(value == null ? '' : String(value));
  }

  // html`...` — tagged template. Every ${} interpolation is escaped
  // (GSP.esc) unless it is a RawHtml (from a nested html`` call or an
  // explicit raw()) or an array thereof.
  function html(strings) {
    var values = Array.prototype.slice.call(arguments, 1);
    var out = strings[0];
    for (var i = 0; i < values.length; i++) {
      out += interpolate(values[i]) + strings[i + 1];
    }
    return new RawHtml(out);
  }

  // mount(el, htmlResult) — set el.innerHTML from an html()/raw() result
  // (or a plain string, for call sites that build one without html``).
  function mount(el, htmlResult) {
    if (!el) return;
    el.innerHTML = htmlResult instanceof RawHtml ? htmlResult.value
      : (htmlResult == null ? '' : String(htmlResult));
  }

  GSP.html = html;
  GSP.raw = raw;
  GSP.mount = mount;
  // Exposed for the unit test only — not part of the public API surface
  // admin.js should use.
  GSP._RawHtml = RawHtml;

})(typeof window !== 'undefined' ? window : (typeof global !== 'undefined' ? global : this));

"""
Talent OS — Server-side HTML sanitizer for blog post bodies.

Self-written, allow-list based (stdlib `html.parser` only — bleach/nh3 are
not in requirements.txt and this doesn't need a heavy dependency for such
a small, fixed allow-list). Used at publish time in routers/blog_admin.py
so a compromised/careless admin session, or a bad AI draft, can't get
arbitrary HTML (script/style/event handlers/javascript: links) onto the
public site.

Allowed: h2, h3, p, ul, ol, li, strong, em, a (href, https:// only).
Everything else is stripped: disallowed tags are unwrapped (their text
content is kept, the tag itself is dropped); <script>/<style> have both
the tag AND their raw text content dropped; all attributes are dropped
except href on <a>, and only when it is an absolute https:// URL;
on* attributes and javascript:/data: URLs are never allowed through.
HTML comments are dropped.
"""
from html import escape
from html.parser import HTMLParser

ALLOWED_TAGS = {"h2", "h3", "p", "ul", "ol", "li", "strong", "em", "a"}
# Tags whose content must never be rendered as text either.
RAWTEXT_STRIP_TAGS = {"script", "style"}


def _safe_href(value: str) -> str | None:
    if not value:
        return None
    value = value.strip()
    if value.lower().startswith("https://"):
        return value
    return None


class _AllowListSanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        # Stack of (original_tag, emitted_bool) so end tags can be matched
        # even when many disallowed tags are unwrapped in between.
        self._stack: list[tuple[str, bool]] = []
        self._rawtext_skip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()

        if tag in RAWTEXT_STRIP_TAGS:
            self._rawtext_skip_depth += 1
            self._stack.append((tag, False))
            return

        if self._rawtext_skip_depth > 0:
            # Inside a <script>/<style> we don't otherwise track nested
            # tags for output, but we still push a placeholder so the
            # matching end tag doesn't underflow the stack.
            self._stack.append((tag, False))
            return

        if tag not in ALLOWED_TAGS:
            self._stack.append((tag, False))
            return

        if tag == "a":
            href = None
            for name, value in attrs:
                if name.lower() == "href":
                    href = _safe_href(value or "")
            if href:
                self.out.append(f'<a href="{escape(href, quote=True)}">')
            else:
                self.out.append("<a>")
        else:
            self.out.append(f"<{tag}>")
        self._stack.append((tag, True))

    def handle_startendtag(self, tag, attrs):
        # None of the allowed tags are void elements, so a self-closed
        # allowed tag (e.g. stray <p/>) is treated as open, no close --
        # handle_starttag already appends it; nothing else to do here for
        # allow-listed tags, and disallowed ones are simply dropped.
        tag = tag.lower()
        if tag in RAWTEXT_STRIP_TAGS or self._rawtext_skip_depth > 0 or tag not in ALLOWED_TAGS:
            return
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if not self._stack:
            return
        # Pop the most recent matching open tag (best-effort recovery from
        # malformed/unbalanced input rather than raising).
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                _, emitted = self._stack.pop(i)
                # Drop everything opened after this tag (unbalanced nesting).
                del self._stack[i:]
                if tag in RAWTEXT_STRIP_TAGS:
                    self._rawtext_skip_depth = max(0, self._rawtext_skip_depth - 1)
                elif emitted:
                    self.out.append(f"</{tag}>")
                return

    def handle_data(self, data):
        if self._rawtext_skip_depth > 0:
            return
        self.out.append(escape(data, quote=False))

    def handle_comment(self, data):
        pass  # comments dropped entirely

    def get_html(self) -> str:
        return "".join(self.out)


def sanitize_blog_html(raw: str | None) -> str | None:
    """Sanitize a blog post body to the allow-listed tag/attribute set.
    None/empty input passes through unchanged (nl or en body is optional
    -- a missing translation must stay NULL, not become '')."""
    if not raw:
        return raw
    parser = _AllowListSanitizer()
    parser.feed(raw)
    parser.close()
    return parser.get_html()

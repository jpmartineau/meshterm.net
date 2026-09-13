# SPDX-License-Identifier: Apache-2.0
"""Build meshterm.net: a landing page and MeshTerm's written pages, as static HTML.

Everything under ``docs/`` — the folder GitHub Pages serves — is generated here and is
never edited by hand. It is made from three sources:

- ``site.toml``, the links: the landing page's buttons, the donation buttons, socials.
- ``src/``, the look: the stylesheet and the two pieces of art, logo and splash.
- the MeshTerm checkout beside this repo, the words. ``meshterm/assets/pages/*.md`` are
  the very pages the app draws under *About MeshTerm*, so the site cannot say something
  the app doesn't, and their ``{version}`` / ``{author}`` / ``{copyright}`` placeholders
  are filled from ``meshterm/__init__.py`` exactly as the app fills them.

The pages were written for a console, and two of their conventions are translated for
the web rather than rewritten: an address spelled out in emphasis (``*https://…*``)
becomes a link — the bold name before it becomes the link text, where there is one —
and a ``qr`` fence becomes a scannable code, white on black as the app draws it.

Run it with MeshTerm's own virtualenv, which already holds every dependency
(markdown-it-py, segno, Pillow, tomli)::

    ..\\MeshTerm\\.venv\\Scripts\\python build.py
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

import segno
from markdown_it import MarkdownIt
from markdown_it.token import Token
from PIL import Image

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 — MeshTerm's venv carries tomli instead
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
OUT = ROOT / "docs"

#: The written pages the site publishes: (page file stem, URL slug, title, nav label).
#: The titles are the app's own names for them. ``discord.md`` is deliberately absent:
#: that page is an invite link and nothing more, which the landing page's button already is.
PAGES = (
    ("about", "about", "About MeshTerm", "About"),
    ("author", "author", "About the author", "Author"),
    ("support", "support", "Support MeshTerm", "Support"),
)

#: The splash art's drawing inside its 700×700 export: 640×250, one image pixel per art
#: pixel, on a black field. Cropped so the page decides the margins, and only ever scaled
#: by whole multiples so its pixels stay square.
SPLASH_BOX = (30, 225, 670, 475)

#: The parser, configured as the app's: CommonMark plus tables and strikethrough, the
#: typographer off so the text comes out exactly as written. Raw HTML stays off too.
_MD = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])

#: An emphasised run that is nothing but an address: the pages' console-safe link.
_BARE_ADDRESS = re.compile(r"^(?:https?://\S+|[\w.+-]+@[\w-]+(?:\.[\w-]+)+)$")

esc = html.escape


# -- the pages' words ------------------------------------------------------------------


def meshterm_facts(checkout: Path) -> dict[str, str]:
    """The live package facts the app fills its pages with, read from ``checkout``.

    Importing the package runs only ``meshterm/__init__.py``, which imports nothing but
    :mod:`datetime`, so this needs none of the app's own dependencies.
    """
    sys.path.insert(0, str(checkout))
    import meshterm

    return {
        "{version}": meshterm.__version__,
        "{author}": meshterm.__author__,
        "{copyright}": meshterm.copyright_notice(),
    }


def fill(source: str, facts: dict[str, str]) -> str:
    """Replace a page's placeholders, as ``meshterm.ui.about._page`` does."""
    for token, value in facts.items():
        source = source.replace(token, value)
    return source


def shown(href: str) -> str:
    """An address as it reads in running text: no scheme, no trailing slash."""
    for noise in ("https://", "http://", "mailto:"):
        if href.startswith(noise):
            href = href[len(noise) :]
    return href.rstrip("/")


def _is_gap(token: Token) -> bool:
    return token.type == "softbreak" or (token.type == "text" and token.content == " ")


def link_addresses(children: list[Token]) -> list[Token]:
    """Turn a run's spelled-out ``*https://…*`` addresses into links.

    Where the address follows a bold name (``**MeshCore** *https://meshcore.io/*``) the
    name becomes the link and the address, now redundant, is dropped; a lone address
    (a list item, an email) links itself.
    """
    out: list[Token] = []
    i = 0
    while i < len(children):
        run = children[i : i + 3]
        if [t.type for t in run] == ["em_open", "text", "em_close"] and _BARE_ADDRESS.match(
            run[1].content
        ):
            address = run[1].content
            href = address if "://" in address else f"mailto:{address}"
            link_open = Token("link_open", "a", 1, attrs={"href": href})
            link_close = Token("link_close", "a", -1)
            if len(out) >= 4 and _is_gap(out[-1]) and out[-2].type == "strong_close":
                out.pop()
                start = max(j for j, t in enumerate(out) if t.type == "strong_open")
                out[start:start] = [link_open]
                out.append(link_close)
            else:
                out += [link_open, Token("text", "", 0, content=shown(address)), link_close]
            i += 3
            continue
        out.append(children[i])
        i += 1
    return out


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"[*_`]", "", text).lower()).strip("-")


def _fence(self, tokens, idx, options, env) -> str:
    """Draw a ``qr`` fence as its code; any other fence as the renderer would."""
    token = tokens[idx]
    if token.info.strip() != "qr":
        return self.fence(tokens, idx, options, env)
    data = token.content.strip()
    code = segno.make(data, error="m")
    svg = code.svg_inline(
        scale=4, border=2, dark="#f2f2f2", light="#000000", title=f"QR code: {shown(data)}"
    )
    return f'<figure class="qr">{svg}</figure>\n'


_MD.add_render_rule("fence", _fence)


def render_page(source: str) -> tuple[str, bool]:
    """Render a page to HTML.

    Returns:
        The HTML, and whether the page carries its own ``#`` title (only *about* does;
        the others open on a section and take their title from :data:`PAGES`).
    """
    tokens = _MD.parse(source)
    has_title = False
    for i, token in enumerate(tokens):
        if token.type == "inline":
            token.children = link_addresses(token.children or [])
        elif token.type == "heading_open":
            token.attrSet("id", _slug(tokens[i + 1].content))
            if token.tag == "h1":
                has_title = True
                # The standfirst: the paragraph directly under the page's title.
                if i + 3 < len(tokens) and tokens[i + 3].type == "paragraph_open":
                    tokens[i + 3].attrSet("class", "standfirst")
    # The colophon: a closing paragraph with a rule standing before it.
    rules = [i for i, t in enumerate(tokens) if t.type == "hr"]
    if rules and len(tokens) - rules[-1] == 4 and tokens[rules[-1] + 1].type == "paragraph_open":
        tokens[rules[-1] + 1].attrSet("class", "colophon")
    return _MD.renderer.render(tokens, _MD.options, {}), has_title


def teaser(source: str) -> str:
    """A page's first paragraph under its first section, as plain text — its own words."""
    tokens = _MD.parse(source)
    in_section = False
    for i, token in enumerate(tokens):
        if token.type == "heading_open" and token.tag == "h2":
            in_section = True
        elif in_section and token.type == "inline" and tokens[i - 1].type == "paragraph_open":
            return "".join(" " if c.type == "softbreak" else c.content for c in token.children or [])
    return ""


# -- the art ---------------------------------------------------------------------------


def build_art() -> None:
    """Derive every image the site serves from the two originals in ``src/``."""
    assets = OUT / "assets"
    assets.mkdir(parents=True)

    splash = Image.open(SRC / "splash.png").convert("RGB").crop(SPLASH_BOX)
    splash.save(assets / "splash.png", optimize=True)

    # The link preview Discord and friends unfurl: the art doubled pixel-for-pixel, then
    # eased down to fit a 1200×630 card.
    doubled = splash.resize((splash.width * 2, splash.height * 2), Image.NEAREST)
    fitted = doubled.resize((1120, 1120 * splash.height // splash.width), Image.LANCZOS)
    card = Image.new("RGB", (1200, 630))
    card.paste(fitted, ((card.width - fitted.width) // 2, (card.height - fitted.height) // 2))
    card.save(assets / "og.png", optimize=True)

    logo = Image.open(SRC / "logo.png").convert("RGB")
    logo.resize((96, 96), Image.LANCZOS).save(assets / "logo-96.png", optimize=True)
    logo.resize((180, 180), Image.LANCZOS).save(assets / "apple-touch-icon.png", optimize=True)
    logo.save(OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])


# -- the frame -------------------------------------------------------------------------


def _external(link: dict, *, rel: str = "") -> str:
    rel_attr = f' rel="{rel}"' if rel else ""
    return f'<li><a href="{esc(link["url"])}"{rel_attr}>{esc(link["label"])}</a></li>'


def frame(site: dict, facts: dict[str, str], *, title: str, path: str, description: str, body: str) -> str:
    """Wrap ``body`` in the page every URL shares: head, top bar, footer."""
    base = site["site"]["url"].rstrip("/")
    if path != "/" and "MeshTerm" not in title:
        title = f"{title} · MeshTerm"
    current = ' aria-current="page"'
    internal = "\n".join(
        f'<li><a href="/{slug}/"{current if path == f"/{slug}/" else ""}>{esc(label)}</a></li>'
        for _, slug, _, label in PAGES
    )
    linked = [link for link in site.get("primary", []) if link.get("nav")]
    socials = site.get("social", [])
    outside = "\n".join(
        [_external(link) for link in linked] + [_external(link, rel="me") for link in socials]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<meta name="theme-color" content="#000000">
<meta name="color-scheme" content="dark">
<link rel="canonical" href="{base}{path}">
<link rel="icon" href="/favicon.ico" sizes="16x16 32x32 48x48">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
<link rel="stylesheet" href="/style.css">
<meta property="og:type" content="website">
<meta property="og:site_name" content="MeshTerm">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{base}{path}">
<meta property="og:image" content="{base}/assets/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site-head">
<div class="bar">
<a class="brand" href="/"><img src="/assets/logo-96.png" width="32" height="32" alt=""><span>MeshTerm</span></a>
<nav aria-label="Site"><ul>
{internal}
{outside}
</ul></nav>
</div>
</header>
<main id="main">
{body}
</main>
<footer class="site-foot">
<p>{esc(facts["{copyright}"])}</p>
<ul>
{outside}
</ul>
</footer>
</body>
</html>
"""


def _button(link: dict) -> str:
    note = f'<span class="btn-note">{esc(link["note"])}</span>' if link.get("note") else ""
    return (
        f'<li class="btn-wrap tone-{esc(link.get("tone", "cyan"))}">'
        f'<a class="btn" href="{esc(link["url"])}">'
        f'<span class="btn-label">{esc(link["label"])}</span>{note}'
        f'<span class="btn-url">{esc(shown(link["url"]))}</span></a></li>'
    )


def landing(site: dict, facts: dict[str, str], sources: dict[str, str]) -> str:
    """The front page: the splash, the one-liner, the buttons, the pages, the tip jar."""
    buttons = "\n".join(_button(link) for link in site.get("primary", []))
    donate = "\n".join(_button(link) for link in site.get("donate", []))
    cards = "\n".join(
        f'<li><a class="card" href="/{slug}/"><span class="card-title">{esc(title)}</span>'
        f'<span class="card-text">{esc(teaser(sources[stem]))}</span>'
        f'<span class="card-go" aria-hidden="true">Read →</span></a></li>'
        for stem, slug, title, _ in PAGES
        if stem != "support"
    )
    return f"""<section class="hero">
<h1 class="visually-hidden">MeshTerm</h1>
<div class="splash"><img src="/assets/splash.png" width="640" height="250" alt="MeshTerm, in ANSI art: a red sun setting behind a city skyline, over the wordmark"></div>
<div class="intro">
<p class="tagline"><span class="prompt" aria-hidden="true">&gt;</span>{esc(site["site"]["description"])}<span class="cursor" aria-hidden="true"></span></p>
<p class="meta"><span>v{esc(facts["{version}"])}</span><span>Apache-2.0</span></p>
</div>
</section>
<section class="block" aria-label="Links">
<ul class="buttons">
{buttons}
</ul>
</section>
<section class="block" aria-labelledby="read">
<h2 class="rule" id="read">About</h2>
<ul class="cards">
{cards}
</ul>
</section>
<section class="block" aria-labelledby="chip-in">
<h2 class="rule" id="chip-in">Support</h2>
<p class="lede">{esc(teaser(sources["support"]))} <a href="/support/">Why it needs support →</a></p>
<ul class="buttons compact">
{donate}
</ul>
</section>"""


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build meshterm.net into docs/.")
    parser.add_argument(
        "--meshterm",
        type=Path,
        default=ROOT.parent / "MeshTerm",
        help="the MeshTerm checkout whose pages and version the site carries (default: ../MeshTerm)",
    )
    args = parser.parse_args(argv)
    checkout = args.meshterm.resolve()
    pages_dir = checkout / "meshterm" / "assets" / "pages"
    if not pages_dir.is_dir():
        parser.error(f"no MeshTerm pages under {pages_dir}")

    site = tomllib.loads((ROOT / "site.toml").read_text(encoding="utf-8"))
    facts = meshterm_facts(checkout)
    sources = {
        stem: fill((pages_dir / f"{stem}.md").read_text(encoding="utf-8"), facts)
        for stem, *_ in PAGES
    }

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    build_art()
    shutil.copyfile(SRC / "style.css", OUT / "style.css")
    write(OUT / "CNAME", f"{urlparse(site['site']['url']).hostname}\n")
    write(OUT / ".nojekyll", "")

    write(
        OUT / "index.html",
        frame(
            site,
            facts,
            title=site["site"]["title"],
            path="/",
            description=site["site"]["description"],
            body=landing(site, facts, sources),
        ),
    )
    for stem, slug, title, _ in PAGES:
        body, has_title = render_page(sources[stem])
        heading = "" if has_title else f"<h1>{esc(title)}</h1>\n"
        write(
            OUT / slug / "index.html",
            frame(
                site,
                facts,
                title=title,
                path=f"/{slug}/",
                description=teaser(sources[stem]),
                body=f'<article class="page">\n{heading}{body}</article>',
            ),
        )
    write(
        OUT / "404.html",
        frame(
            site,
            facts,
            title="Page not found",
            path="/404.html",
            description=site["site"]["description"],
            body=(
                '<article class="page">\n<h1>404</h1>\n'
                '<p class="standfirst">No route to this page.</p>\n'
                '<p><a href="/">Back to meshterm.net</a></p>\n</article>'
            ),
        ),
    )
    print(f"built {OUT.relative_to(ROOT)}/ for MeshTerm v{facts['{version}']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

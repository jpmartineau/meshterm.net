# SPDX-License-Identifier: Apache-2.0
"""Build meshterm.net: a landing page and MeshTerm's written pages, as static HTML.

Everything under ``docs/`` — the folder GitHub Pages serves — is generated here and is
never edited by hand. It is made from three sources:

- ``site.toml``, the links and the screens: the landing page's buttons, the donation
  buttons, socials, and which of MeshTerm's ``docs/screenshots`` the landing page shows.
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
import json
import re
import shutil
import sys
import urllib.error
import urllib.request
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


# -- links that aren't open yet --------------------------------------------------------


def is_open(url: str) -> bool:
    """Whether ``url`` answers a logged-out visitor — the question a private repo fails.

    A link carrying ``opens`` in ``site.toml`` is probed at every build rather than
    trusted to a date: GitHub answers 404 for a private repository, so the first build
    after it goes public links it without anyone editing anything. Any other answer, or
    none, stops the build — guessing either way would publish the wrong page.
    """
    request = urllib.request.Request(
        url, method="HEAD", headers={"User-Agent": "meshterm.net build"}
    )
    try:
        with urllib.request.urlopen(request, timeout=15):
            return True
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise SystemExit(f"build.py: {url} answered {error.code}; is it open or not?") from error
    except urllib.error.URLError as error:
        raise SystemExit(f"build.py: couldn't reach {url} ({error.reason})") from error


def close_unopened(site: dict) -> set[str]:
    """Settle every ``opens`` link: drop the mark from the open ones, return the rest.

    Returns:
        The addresses still closed, trailing slash stripped — the pages leave these
        spelled out rather than linking a visitor to a 404.
    """
    closed = set()
    for group in ("primary", "donate", "social"):
        for link in site.get(group, []):
            if "opens" in link:
                if is_open(link["url"]):
                    del link["opens"]
                else:
                    closed.add(link["url"].rstrip("/"))
    return closed


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


def link_addresses(children: list[Token], closed: set[str]) -> list[Token]:
    """Turn a run's spelled-out ``*https://…*`` addresses into links.

    Where the address follows a bold name (``**MeshCore** *https://meshcore.io/*``) the
    name becomes the link and the address, now redundant, is dropped; a lone address
    (a list item, an email) links itself. An address in ``closed`` is left exactly as the
    app shows it, spelled out and unlinked, until it opens.
    """
    out: list[Token] = []
    i = 0
    while i < len(children):
        run = children[i : i + 3]
        if [t.type for t in run] == ["em_open", "text", "em_close"] and _BARE_ADDRESS.match(
            run[1].content
        ):
            address = run[1].content
            if address.rstrip("/") in closed:
                out += run
                i += 3
                continue
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


def render_page(source: str, closed: set[str]) -> tuple[str, bool]:
    """Render a page to HTML, leaving the ``closed`` addresses unlinked.

    Returns:
        The HTML, and whether the page carries its own ``#`` title (only *about* does;
        the others open on a section and take their title from :data:`PAGES`).
    """
    tokens = _MD.parse(source)
    has_title = False
    for i, token in enumerate(tokens):
        if token.type == "inline":
            token.children = link_addresses(token.children or [], closed)
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

    # The link previews: the art doubled pixel-for-pixel, then eased down onto a card and
    # centred, which leaves the black field above and below as the margin.
    doubled = splash.resize((splash.width * 2, splash.height * 2), Image.NEAREST)

    def card(size: tuple[int, int], art_width: int, name: str) -> None:
        fitted = doubled.resize((art_width, art_width * splash.height // splash.width), Image.LANCZOS)
        out = Image.new("RGB", size)
        out.paste(fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
        out.save(assets / name, optimize=True)

    # What Discord and friends unfurl from a link to the site.
    card((1200, 630), 1120, "og.png")
    # What they unfurl from a link to the *repository*: GitHub asks for 1280×640, and it
    # is uploaded by hand in the repo settings, which has no API. Built here anyway, so it
    # is derived from the same original as everything else rather than drawn once by hand
    # and then slowly diverging from the art it came from.
    card((1280, 640), 1180, "social-preview.png")

    logo = Image.open(SRC / "logo.png").convert("RGB")
    logo.resize((96, 96), Image.LANCZOS).save(assets / "logo-96.png", optimize=True)
    logo.resize((180, 180), Image.LANCZOS).save(assets / "apple-touch-icon.png", optimize=True)
    logo.save(OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])


#: The widest a device photo leaves at: the page never draws one wider than about 400px,
#: and the full-size view gets the rest.
DEVICE_WIDTH = 900


def build_screens(screens: list[dict], source: Path) -> list[dict]:
    """Copy the landing page's screens out of MeshTerm's ``docs/screenshots``.

    A terminal capture is text at one image pixel per screen pixel, so it keeps its size
    and stays a PNG — the very file, when nothing in it is transparent, since re-encoding
    only makes it bigger. A device photo carries a camera's worth of detail nobody needs at
    page size, so it leaves as a JPEG no wider than :data:`DEVICE_WIDTH`.

    Returns:
        Each screen's ``site.toml`` entry plus where the page finds it and its size.
    """
    out = OUT / "assets" / "screens"
    out.mkdir(parents=True, exist_ok=True)
    built = []
    for screen in screens:
        path = source / screen["file"]
        if not path.is_file():
            raise SystemExit(f"build.py: site.toml names a screen MeshTerm doesn't have: {path}")
        image = Image.open(path)
        stem = Path(screen["file"]).stem
        opaque = "A" not in image.getbands() or image.getchannel("A").getextrema()[0] == 255
        if not screen.get("device") and path.suffix.lower() == ".png" and opaque:
            shutil.copyfile(path, out / f"{stem}.png")
            built.append(
                {**screen, "src": f"/assets/screens/{stem}.png", "width": image.width, "height": image.height}
            )
            continue
        if "A" in image.getbands() or image.mode == "P":
            rgba = image.convert("RGBA")
            image = Image.new("RGB", rgba.size)
            image.paste(rgba, mask=rgba.getchannel("A"))
        else:
            image = image.convert("RGB")
        if screen.get("device"):
            if image.width > DEVICE_WIDTH:
                height = round(image.height * DEVICE_WIDTH / image.width)
                image = image.resize((DEVICE_WIDTH, height), Image.LANCZOS)
            name = f"{stem}.jpg"
            image.save(out / name, quality=82, optimize=True, progressive=True)
        else:
            name = f"{stem}.png"
            image.save(out / name, optimize=True)
        built.append(
            {**screen, "src": f"/assets/screens/{name}", "width": image.width, "height": image.height}
        )
    return built


def build_demo(demo: dict) -> dict:
    """Copy the demo recording and its poster frame out of ``src/``.

    The video is *copied*, never re-encoded. It is already H.264 High in ``yuv420p``
    with its ``moov`` box ahead of the media, which is what lets a browser start
    playing before the whole file has arrived; re-encoding here would cost quality and
    put ffmpeg in the build's way for nothing.

    Returns:
        The ``site.toml`` entry plus where the page finds each file, and the poster's
        pixel size -- which is also the widest the page will ever draw the video.
    """
    out = OUT / "assets"
    out.mkdir(parents=True, exist_ok=True)
    built = dict(demo)
    for key in ("file", "poster", "card"):
        path = SRC / demo[key]
        if not path.is_file():
            raise SystemExit(f"build.py: site.toml names a demo file src/ lacks: {path}")
        shutil.copyfile(path, out / path.name)
        built[key] = f"/assets/{path.name}"
    with Image.open(SRC / demo["poster"]) as poster:
        built["width"], built["height"] = poster.size
    return built


def _demo(demo: dict) -> str:
    """The recording, framed like everything else the page shows.

    ``preload="none"`` so the page costs nothing until someone asks for it -- the poster
    is a still of the thing itself, which is the whole of what a visitor needs to decide.
    """
    return (
        '<section class="block wide" aria-labelledby="demo">\n'
        f'<h2 class="rule" id="demo">{esc(demo["title"])}</h2>\n'
        '<figure class="demo">\n'
        '<div class="hud">'
        f'<video controls playsinline preload="none" poster="{demo["poster"]}"'
        f' width="{demo["width"]}" height="{demo["height"]}">'
        f'<source src="{demo["file"]}" type="video/mp4">'
        "<p>Your browser will not play this. "
        f'<a href="{demo["file"]}"{tracked("demo-download", "demo")}>Download the recording</a>.</p>'
        "</video></div>\n"
        f'<figcaption>{esc(demo["caption"])}</figcaption>\n'
        "</figure>\n"
        "</section>\n"
    )


def _screen(screen: dict) -> str:
    kind = " device" if screen.get("device") else ""
    title, caption = esc(screen["title"]), esc(screen["caption"])
    return (
        f'<figure class="screen{kind}">'
        f'<a class="hud" href="{screen["src"]}"{tracked("screen-" + slug(screen["title"]), "screens")} data-full data-caption="{title} — {caption}">'
        f'<img src="{screen["src"]}" width="{screen["width"]}" height="{screen["height"]}"'
        f' loading="lazy" alt="{title} screenshot"></a>'
        f'<figcaption><span class="screen-title">{title}</span> {caption}</figcaption></figure>'
    )


#: The full-size view: a ``<dialog>`` over the dimmed page, closed with Esc like everything
#: in MeshTerm. Without JavaScript each screen is a plain link to its image instead.
VIEWER = """<dialog class="viewer" aria-label="Screenshot">
<img alt="">
<div class="viewer-bar"><p class="viewer-caption"></p><form method="dialog"><button class="viewer-close">Esc close</button></form></div>
</dialog>
<script>
(() => {
  const viewer = document.querySelector(".viewer");
  if (!viewer || typeof viewer.showModal !== "function") return;
  const image = viewer.querySelector("img");
  const caption = viewer.querySelector(".viewer-caption");
  for (const link of document.querySelectorAll("a[data-full]")) {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      image.src = link.href;
      image.alt = link.querySelector("img").alt;
      caption.textContent = link.dataset.caption;
      viewer.showModal();
    });
  }
  viewer.addEventListener("click", (event) => {
    if (event.target === viewer) viewer.close();
  });
})();
</script>"""


# -- the frame -------------------------------------------------------------------------


def tracked(name: str, placement: str) -> str:
    """The attributes that name a link for PostHog, which sends them with every click on it.

    Autocapture already records each click, but it knows a link only by its text and its
    place in the page, and a chart built on either quietly stops counting the day the
    wording or the layout changes. ``button`` is the link's own name, the same wherever it
    appears; ``placement`` says which of its appearances was clicked.
    """
    return (
        f' data-ph-capture-attribute-button="{esc(name)}"'
        f' data-ph-capture-attribute-placement="{esc(placement)}"'
    )


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def link_name(link: dict) -> str:
    """A ``site.toml`` link's tracking name: its ``track`` key, else its label as a slug.

    Give a link ``track`` before renaming its label, so its clicks keep their old name.
    """
    return link.get("track") or slug(link["label"])


def _external(link: dict, placement: str, *, rel: str = "") -> str:
    rel_attr = f' rel="{rel}"' if rel else ""
    return (
        f'<li><a href="{esc(link["url"])}"{rel_attr}{tracked(link_name(link), placement)}>'
        f'{esc(link["label"])}</a></li>'
    )


#: PostHog's loader, as its setup page gives it: a stub that queues calls until array.js
#: arrives from the project's region. Session recording is switched off here, in the page,
#: so no replay of a visit is ever captured whatever the project's own settings say.
_POSTHOG = """<script>
!function(t,e){var o,n,p,r;e.__SV||(window.posthog&&window.posthog.__loaded)||(window.posthog=e,e._i=[],e.init=function(i,s,a){function g(t,e){var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}(p=t.createElement("script")).type="text/javascript",p.crossOrigin="anonymous",p.async=!0,p.src=s.api_host.replace(".i.posthog.com","-assets.i.posthog.com")+"/static/array.js",(r=t.getElementsByTagName("script")[0]).parentNode.insertBefore(p,r);var u=e;for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],u.toString=function(t){var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e},u.people.toString=function(){return u.toString(1)+".people (stub)"},o="init capture register register_once register_for_session unregister unregister_for_session getFeatureFlag getFeatureFlagPayload isFeatureEnabled reloadFeatureFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures on onFeatureFlags onSessionId getSurveys getActiveMatchingSurveys renderSurvey canRenderSurvey getNextSurveyStep identify setPersonProperties group resetGroups setPersonPropertiesForFlag resetPersonPropertiesForFlags setGroupPropertiesForFlags resetGroupPropertiesForFlags reset get_distinct_id getGroups get_session_id get_session_replay_url alias set_config startSessionRecording stopSessionRecording sessionRecordingStarted captureException loadToolbar get_property getSessionProperty createPersonProfile opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing clear_opt_in_out_capturing debug".split(" "),n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}(document,window.posthog||[]);
posthog.init(%s,{api_host:%s,defaults:"2025-05-24",person_profiles:"identified_only",disable_session_recording:true});
</script>"""


def analytics(site: dict) -> str:
    """PostHog's loader, once ``[analytics]`` carries a project key — nothing until then."""
    config = site.get("analytics", {})
    key = config.get("posthog_key")
    if not key:
        return ""
    host = config.get("posthog_host") or "https://us.i.posthog.com"
    return "\n" + _POSTHOG % (json.dumps(key), json.dumps(host))


def frame(site: dict, facts: dict[str, str], *, title: str, path: str, description: str, body: str) -> str:
    """Wrap ``body`` in the page every URL shares: head, top bar, footer."""
    base = site["site"]["url"].rstrip("/")
    if path != "/" and "MeshTerm" not in title:
        title = f"{title} · MeshTerm"
    current = ' aria-current="page"'
    internal = "\n".join(
        f'<li><a href="/{page}/"{current if path == f"/{page}/" else ""}{tracked(page, "nav")}>'
        f"{esc(label)}</a></li>"
        for _, page, _, label in PAGES
    )
    linked = [link for link in site.get("primary", []) if link.get("nav") and "opens" not in link]
    socials = [link for link in site.get("social", []) if "opens" not in link]

    def outside(placement: str) -> str:
        return "\n".join(
            [_external(link, placement) for link in linked]
            + [_external(link, placement, rel="me") for link in socials]
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
<!-- Cloudflare Web Analytics --><script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{{"token": "3122778111a44031ab688d821934c7ae"}}'></script><!-- End Cloudflare Web Analytics -->{analytics(site)}
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site-head">
<div class="bar">
<a class="brand" href="/"{tracked("home", "nav")}><img src="/assets/logo-96.png" width="32" height="32" alt=""><span>MeshTerm</span></a>
<nav aria-label="Site"><ul>
{internal}
{outside("nav")}
</ul></nav>
</div>
</header>
<main id="main">
{body}
</main>
<footer class="site-foot">
<p>{esc(facts["{copyright}"])}</p>
<ul>
{outside("footer")}
</ul>
</footer>
</body>
</html>
"""


def _button(link: dict, placement: str) -> str:
    """A neon button — or, for a link that hasn't opened, the same chip carrying its date."""
    color = link.get("color", "#61d6d6")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise SystemExit(f"site.toml: {link['label']} color {color!r} is not #rrggbb")
    style = f' style="--c: {color}"'
    note = f'<span class="btn-note">{esc(link["note"])}</span>' if link.get("note") else ""
    address = f'<span class="btn-url">{esc(shown(link["url"]))}</span>'
    if "opens" in link:
        return (
            f'<li class="btn-wrap is-soon"{style}><div class="btn">'
            f'<span class="btn-label">{esc(link["label"])}'
            f' <span class="btn-soon">Opens {esc(link["opens"])}</span></span>'
            f"{note}{address}</div></li>"
        )
    return (
        f'<li class="btn-wrap"{style}><a class="btn" href="{esc(link["url"])}"{tracked(link_name(link), placement)}>'
        f'<span class="btn-label">{esc(link["label"])}</span>{note}{address}</a></li>'
    )


def landing(
    site: dict,
    facts: dict[str, str],
    sources: dict[str, str],
    screens: list[dict],
    demo: dict | None,
) -> str:
    """The front page: the splash, the one-liner, the buttons, the screens, the pages, the tip jar."""
    captures = "\n".join(_screen(s) for s in screens if not s.get("device"))
    devices = "\n".join(_screen(s) for s in screens if s.get("device"))
    gallery = (
        '<section class="block wide" aria-labelledby="screens">\n'
        '<h2 class="rule" id="screens">Screens</h2>\n'
        f'<div class="screens">\n<div class="captures">\n{captures}\n</div>\n{devices}\n</div>\n'
        "</section>\n"
        if screens
        else ""
    )
    reel = _demo(demo) if demo else ""
    buttons = "\n".join(_button(link, "buttons") for link in site.get("primary", []))
    donate = "\n".join(_button(link, "donate") for link in site.get("donate", []))
    cards = "\n".join(
        f'<li><a class="card" href="/{slug}/"{tracked(slug, "card")}><span class="card-title">{esc(title)}</span>'
        f'<span class="card-text">{esc(teaser(sources[stem]))}</span>'
        f'<span class="card-go" aria-hidden="true">Read →</span></a></li>'
        for stem, slug, title, _ in PAGES
        if stem != "support"
    )
    return f"""<section class="hero">
<h1 class="visually-hidden">MeshTerm</h1>
<div class="splash hud"><img src="/assets/splash.png" width="640" height="250" alt="MeshTerm, in ANSI art: a red sun setting behind a city skyline, over the wordmark"></div>
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
{reel}{gallery}<section class="block" aria-labelledby="read">
<h2 class="rule" id="read">About</h2>
<ul class="cards">
{cards}
</ul>
</section>
<section class="block" aria-labelledby="chip-in">
<h2 class="rule" id="chip-in">Support</h2>
<p class="lede">{esc(teaser(sources["support"]))} <a href="/support/"{tracked("support", "lede")}>Why it needs support →</a></p>
<ul class="buttons compact">
{donate}
</ul>
</section>
{VIEWER if screens else ""}"""


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
    closed = close_unopened(site)
    facts = meshterm_facts(checkout)
    sources = {
        stem: fill((pages_dir / f"{stem}.md").read_text(encoding="utf-8"), facts)
        for stem, *_ in PAGES
    }

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    build_art()
    screens = build_screens(site.get("screen", []), checkout / "docs" / "screenshots")
    demo = build_demo(site["demo"]) if "demo" in site else None
    shutil.copyfile(SRC / "style.css", OUT / "style.css")
    # No trailing newline: GitHub writes the file that way whenever the custom domain is
    # saved in the repository settings, so matching it keeps a rebuild from diffing it.
    write(OUT / "CNAME", urlparse(site["site"]["url"]).hostname)
    write(OUT / ".nojekyll", "")

    write(
        OUT / "index.html",
        frame(
            site,
            facts,
            title=site["site"]["title"],
            path="/",
            description=site["site"]["description"],
            body=landing(site, facts, sources, screens, demo),
        ),
    )
    for stem, slug, title, _ in PAGES:
        body, has_title = render_page(sources[stem], closed)
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
    waiting = f", waiting on {', '.join(sorted(closed))}" if closed else ""
    print(f"built {OUT.relative_to(ROOT)}/ for MeshTerm v{facts['{version}']}{waiting}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

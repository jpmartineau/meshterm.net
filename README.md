# meshterm.net

The landing page for [MeshTerm](https://github.com/jpmartineau/MeshTerm), served by GitHub
Pages from `docs/`.

`docs/` is **generated** — never edit it by hand. `build.py` writes it from four sources:

| Source | What it holds |
|---|---|
| `site.toml` | the links — the landing page's buttons, the donation buttons, socials |
| `src/` | the look — `style.css`, and the logo and splash art every image is derived from |
| `../MeshTerm/meshterm/assets/pages/` | the words — `about.md`, `author.md` and `support.md`, the same files the app draws, plus the version and copyright line from `meshterm/__init__.py` |
| `../MeshTerm/docs/screenshots/` | the screens — the README's captures and the PicoCalc photo, whichever `site.toml` lists |

## Rebuild

From this folder, with MeshTerm's virtualenv (it already has every dependency):

```powershell
..\MeshTerm\.venv\Scripts\python build.py
```

Rebuild after editing anything above — including an About page in MeshTerm, and after a
release, since the version appears on the landing and About pages — then commit `docs/`
with its sources and push. Pages redeploys on its own within a minute or two.

A build on Windows writes the six derived images (`favicon.ico`, `apple-touch-icon.png`,
`logo-96.png`, `og.png`, `social-preview.png`, `splash.png`) with slightly different bytes
from the ones CI makes, even though they look the same. If you only changed words, restore
them before committing so the commit holds only the pages:

```powershell
git restore docs/favicon.ico docs/assets/apple-touch-icon.png docs/assets/logo-96.png docs/assets/og.png docs/assets/social-preview.png docs/assets/splash.png
```

To look before pushing (links are root-relative, so opening the files directly won't work):

```powershell
..\MeshTerm\.venv\Scripts\python -m http.server 8765 -d docs
```

and open <http://127.0.0.1:8765>.

## Add a social

Append a block to `site.toml` and rebuild — it appears in the top bar and the footer, marked
`rel="me"` so a profile that checks for a link back can verify the site:

```toml
[[social]]
label = "Mastodon"
url = "https://mastodon.social/@example"
```

## The demo recording

`[demo]` in `site.toml` points at two files in `src/`, and `build.py` copies both into
`docs/assets/` untouched. It never re-encodes: the mp4 is already H.264 High in
`yuv420p` with its `moov` box ahead of the media, which is what lets a browser start
playing before the whole file has arrived. Re-encoding would cost quality and put ffmpeg
in the release build's way for nothing.

The poster is a still lifted from the video, so the page shows the real thing before
anyone presses play, and the video is loaded with `preload="none"` so it costs a visitor
nothing until they ask for it. The frame never draws wider than the capture's own pixel
width, because a terminal recording is text at one image pixel per screen pixel and
scaling it up is exactly what turns that text to mush.

To replace it, drop a new `demo.mp4` and `demo-poster.png` into `src/` and rebuild. To
cut a fresh poster from a new recording:

```bash
ffmpeg -ss 30 -i src/demo.mp4 -frames:v 1 src/demo-poster.png
```

**GitHub is the one place this file cannot go.** The README on
[MeshTerm](https://github.com/jpmartineau/MeshTerm) cannot play it from here: GitHub
strips `<video>` out of markdown, and an mp4 behind an image link renders as a broken
image. An inline player there needs a `user-attachments` URL, which means uploading the
same file again through a comment box on that repo. This copy is the one the website
plays and the one that is actually ours.

## The repository's social preview

`build.py` also writes `docs/assets/social-preview.png` at 1280x640, the size GitHub
asks for. It is the same splash art as the site's own `og.png`, from the same original
and the same pipeline, so the two cards cannot drift apart.

Uploading it is the one step that is not automatable: GitHub has no API for a
repository's social preview, so it goes in by hand under **Settings -> General ->
Social preview -> Edit -> Upload an image**. Do it once; it survives everything after.

The art is deliberately the wordmark rather than a screenshot. A link card renders at
about 400px wide in Discord, and a terminal capture at that size is unreadable mush
while pixel art is still pixel art.

## Analytics

Every page carries Cloudflare Web Analytics for page counts. For how visitors behave, fill in
`[analytics]` in `site.toml` and rebuild. An empty key stays out of the pages.

- **PostHog** (`posthog_key`, `posthog_host`): events, funnels, recordings. The project API
  key (`phc_…`) is under Project settings; set the host to `https://eu.i.posthog.com` for an
  EU project.

## Releases update the site

Pushing a MeshTerm version tag runs `github-release.yml` in the MeshTerm repo. Once the
release is published, its `website` job checks out the tag and this repo, runs `build.py`,
and pushes `docs/` back here as a commit named after the version. A prerelease skips this
job.

The job builds from the tag, so it uses the About, Author and Support pages as they were
when the tag was made. If those pages have changed on MeshTerm's `main` since, rebuild by
hand instead.

It pushes with a deploy key that can write to this repository and nothing else, made once
**from Git Bash** — the third line feeds the private key in on stdin, and Windows
PowerShell has no `<` redirection operator at all.

Adding a deploy key needs a scope `gh` doesn't ask for by default, so do that first:

```bash
gh auth refresh -h github.com -s admin:public_key
```

Then the key itself. The first line clears out any key left over from an earlier attempt.
The rest are chained on `&&` on purpose: **the new key is deleted only if everything
before it worked.**

```bash
rm -f ~/site_deploy_key ~/site_deploy_key.pub
ssh-keygen -t ed25519 -N "" -C "MeshTerm releases" -f ~/site_deploy_key \
  && gh repo deploy-key add ~/site_deploy_key.pub --repo jpmartineau/meshterm.net --title "MeshTerm releases" --allow-write \
  && gh secret set SITE_DEPLOY_KEY --repo jpmartineau/MeshTerm < ~/site_deploy_key \
  && echo "BOTH HALVES INSTALLED" \
  && rm ~/site_deploy_key ~/site_deploy_key.pub
```

Run as four separate lines, this fails badly rather than loudly: if `deploy-key add` is
refused, the two lines after it still run, and you end up with a secret holding a private
key whose public half was never installed — and no local copy of either. That fails
*authentication* on the next release, which reads like a broken key rather than a missing
one. Check both ends with `gh repo deploy-key list --repo jpmartineau/meshterm.net` and
`gh secret list --repo jpmartineau/MeshTerm`.

## A link that isn't open yet

A `site.toml` link with `opens = "22 September"` is asked at every build whether it answers
a logged-out visitor. While it answers 404 (a private repository does), its button shows
*Opens 22 September* and links nowhere, the top bar and footer leave it out, and the pages
spell its address out unlinked. The first build after it opens links it everywhere.

Nothing runs that build for you. The v0.9.0 release has already rebuilt the site, while
the repository was still private, so after the repository goes public, rebuild by hand:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://github.com/jpmartineau/MeshTerm   # must print 200
cd /d/vibe/meshterm.net && git pull --ff-only
../MeshTerm/.venv/Scripts/python build.py     # must not print "waiting on"
git status --short                            # the five pages, plus images to restore (see Rebuild)
git add docs && git commit -m "GitHub is open" && git push
```

Then delete the `opens` line from `site.toml`, rebuild (nothing in `docs/` should change),
and commit. Pages caches for up to ten minutes, so give it that long before checking the
live site.

Re-running the release's `website` job would also work, but it builds the pages from the
`v0.9.0` tag and so would undo any fixes made to them on `main` since. Don't use
`workflow_dispatch` on `github-release.yml` for this either: it tries to create the release
again, fails, and never reaches the `website` job.

## Hosting

**GitHub Pages:** Settings → Pages → *Deploy from a branch* → `main`, folder `/docs`. The
custom domain comes from `docs/CNAME`. Tick *Enforce HTTPS* once the certificate is issued.

**Verify the domain first** (GitHub → your account Settings → Pages → *Add a domain*): it
adds a TXT record to prove ownership, so no other GitHub user can serve a site on
meshterm.net.

**DNS at Namecheap** (Domain List → meshterm.net → Advanced DNS):

| Type | Host | Value |
|---|---|---|
| A | `@` | `185.199.108.153` |
| A | `@` | `185.199.109.153` |
| A | `@` | `185.199.110.153` |
| A | `@` | `185.199.111.153` |
| CNAME | `www` | `jpmartineau.github.io.` |

Leave the Proton Mail records (MX, the SPF and verification TXTs, the DKIM CNAMEs) exactly as
they are, and remove any parking-page or URL-redirect record Namecheap put on `@` or `www`.

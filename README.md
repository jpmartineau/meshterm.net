# meshterm.net

The landing page for [MeshTerm](https://github.com/jpmartineau/MeshTerm), served by GitHub
Pages from `docs/`.

`docs/` is **generated** — never edit it by hand. `build.py` writes it from three sources:

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

## Analytics

Every page carries Cloudflare Web Analytics for page counts. For how visitors behave, fill in
`[analytics]` in `site.toml` and rebuild. An empty key stays out of the pages.

- **PostHog** (`posthog_key`, `posthog_host`): events, funnels, recordings. The project API
  key (`phc_…`) is under Project settings; set the host to `https://eu.i.posthog.com` for an
  EU project.

## Releases update the site

Pushing a MeshTerm version tag runs `github-release.yml` in the MeshTerm repo. Once the
release is published, its `website` job checks out the tag and this repo, runs `build.py`,
and pushes `docs/` back here as a commit named after the version — nothing to do by hand.

It pushes with a deploy key that can write to this repository and nothing else, made once
**from Git Bash** — the third line feeds the private key in on stdin, and Windows
PowerShell has no `<` redirection operator at all.

Adding a deploy key needs a scope `gh` doesn't ask for by default, so do that first:

```bash
gh auth refresh -h github.com -s admin:public_key
```

Then the key itself. The steps are chained on `&&` on purpose: **nothing is deleted
unless everything before it worked.**

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
spell its address out unlinked. The first build after it opens links it everywhere — a
release build, or a manual one — so launch day needs no edit; delete the line afterwards.

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

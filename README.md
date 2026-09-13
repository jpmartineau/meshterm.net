# meshterm.net

The landing page for [MeshTerm](https://github.com/jpmartineau/MeshTerm), served by GitHub
Pages from `docs/`.

`docs/` is **generated** — never edit it by hand. `build.py` writes it from three sources:

| Source | What it holds |
|---|---|
| `site.toml` | the links — the landing page's buttons, the donation buttons, socials |
| `src/` | the look — `style.css`, and the logo and splash art every image is derived from |
| `../MeshTerm/meshterm/assets/pages/` | the words — `about.md`, `author.md` and `support.md`, the same files the app draws, plus the version and copyright line from `meshterm/__init__.py` |

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

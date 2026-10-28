# panindo.app (marketing + legal site)

Plain static HTML and one stylesheet. No build step, no JavaScript, no cookies, no analytics, and no third-party requests: the Bricolage Grotesque font is self-hosted in `fonts/`.

```
site/
  index.html              marketing page
  privacy/index.html      Privacy Policy (draft)
  terms/index.html        Terms of Service (draft)
  delete-account/index.html  account deletion page (Google Play requirement, draft)
  support/index.html      support page
  404.html                not-found page (Netlify serves it automatically)
  styles.css              all styles; light and dark themes follow the system
  favicon.svg             logo mark (copy of frontend/public/favicon.svg)
  fonts/                  Bricolage Grotesque variable woff2 (latin, latin-ext) from @fontsource-variable
  og.jpg                  1200x630 Open Graph image
  robots.txt
  netlify.toml            headers (CSP, HSTS, ...) and a few redirects
```

## Legal text is a draft

**The Privacy Policy, Terms of Service, and Delete-account page are drafts written from product facts. They have not been reviewed by a lawyer.** Have a lawyer familiar with the Philippine Data Privacy Act (RA 10173), US state privacy laws, and Apple and Google store rules review them before launch. Each legal page shows a "Draft — pending legal review" notice at the top. Remove it only after review.

## Placeholders to fill

Every placeholder is shown highlighted on the page and listed in an HTML comment at the top of its file.

| Placeholder | Meaning | Files |
|---|---|---|
| `[OPERATOR LEGAL NAME]` | Legal name of the individual developer who operates Panindo | privacy, terms |
| `[MAILING ADDRESS]` | Postal address for privacy requests and legal notices (PhilPost P.O. box planned) | privacy, terms |
| `[EFFECTIVE DATE]` | Date each document takes effect | privacy, terms, delete-account |
| `[CITY]` | City whose courts are the venue for disputes, in the Philippines | terms |

Find them all with:

```sh
grep -rn "\[OPERATOR LEGAL NAME\]\|\[MAILING ADDRESS\]\|\[EFFECTIVE DATE\]\|\[CITY\]" site/
```

### Also confirm before publishing

- **delete-account:** the page says activity-log entries a deleted user made in stores they didn't own stay in that store's log. Confirm this matches the deletion code (PRD R10.2).
- **Android-only for now (2026-10-12):** all Apple/iOS wording was removed (App Store, Sign in with Apple, APNs, the Apple EULA section). When the iOS app is planned, re-add: the Apple processor row in privacy, Apple sign-in and relay-email wording, the Apple cancel link (https://support.apple.com/en-us/118428), and the App Store terms section (Apple's minimum EULA terms).
- **privacy, section 8:** the cross-border safeguard sentence is general. A lawyer may want specific wording (for example, data processing agreements with each provider).
- **FAQ and support:** Android 7+ comes from the PRD build floor. Update them if the floor changes.
- Prices on the home page and in the terms must match the Play Console price points.

## Deploy (Netlify)

1. In Netlify, add a new site from this Git repository. It's a separate site from the web app.
2. Set **Base directory** to `site`. Leave the build command empty. Netlify reads `site/netlify.toml`, which sets the publish directory to the base directory.
3. Add the custom domain `panindo.app` (and `www.panindo.app`, redirected to the apex) and let Netlify issue the HTTPS certificate.
4. After the first deploy, check the response headers (`curl -I https://panindo.app/`) and run the site through a header checker such as securityheaders.com.

No environment variables or secrets are needed.

### Notes

- Clean URLs come from the folder layout (`/privacy/`, `/terms/`, ...), not from Netlify's Pretty URLs setting.
- The CSP allows only this site (`style-src 'self'; font-src 'self'`). `img-src` also allows `data:` for the CSS paper texture. Inline `style="..."` attributes are blocked, so keep all styling in `styles.css`.
- HSTS is set without `preload`. Add `preload` and submit to hstspreload.org only once every subdomain (including app.panindo.app) is HTTPS-only for good.
- Deep links (PRD R10.5) need `/.well-known/assetlinks.json` (and `apple-app-site-association` once iOS exists) on `app.panindo.app`, the web app's domain, not on this site. They must be served without redirects and with `Content-Type: application/json`.
- To update `og.jpg`, render a 1200x630 card and save it as a JPEG under about 200 KB.

## Local preview

```sh
python3 -m http.server 8090 --directory site
```

Then open http://localhost:8090. Use absolute paths (`/styles.css`) in new pages so `404.html` works at any depth.

# Dark and light theme audit

Date: 26 Oct 2026. Scope: both themes on every page. Checked in a real browser (Chromium) against a local copy of the app with seeded scan data, never against the live site.

## What was checked

| Check                                                                                                                                                                        | Result                                                                                                                                                                                       |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Colour tokens against the surfaces they sit on (text, muted text, accent, status and severity colours) in both themes                                                        | All pass WCAG AA for text. Lowest is 4.9:1 (the "ok" green on the light page background). Borders and controls pass the 3:1 rule for interface parts                                         |
| Hard-coded colours outside the token blocks (76 found by search)                                                                                                             | All are either token definitions for another theme, chart palette entries with a dark and a light value, shadows, or fallbacks inside `var()`. None is an unthemed text or background colour |
| Axe accessibility rules (WCAG 2.1 A and AA, every impact level, not only serious) on 18 pages, in dark and light, at 1280 and 390 pixels wide, signed in with real scan data | 0 violations                                                                                                                                                                                 |
| Sideways scrolling on the same pages and widths                                                                                                                              | None                                                                                                                                                                                         |
| Screenshots of every page in both themes, read by eye                                                                                                                        | No unreadable text, invisible borders or wrong-theme images found                                                                                                                            |

## Gaps found and fixed

1. **Flash of the wrong theme.** A person whose saved choice differs from their system setting (system dark, saved light) saw the other theme for a moment on every load, because the choice was only applied once the app had started. A 12-line script, `public/theme-init.js`, now applies it from the page head before anything is painted. It only reads the saved choice; with no choice the page still follows the system setting through CSS. It is a same-origin file because the content security policy forbids inline scripts. Verified by blocking the app bundle and checking the theme is already set (all four system and saved combinations); 6 unit tests; an end-to-end test that fails without the script (checked by removing it).
2. **Accessibility tests did not cover six signed-in pages and four public pages in dark mode.** The end-to-end checks now include Account, Audit log, Analytics, Health, Clients, the agency features page and the three legal pages, in both themes.
3. **The home page's sample report preview was the old cover.** It is regenerated from the new PDF cover (see the PDF cover change on 26 Oct); its description was updated to match.

## Not changed, on purpose

- No colours or layouts were redesigned: nothing in the audit needed it.
- The service worker does not cache `theme-init.js`; offline, the app still applies the theme once it starts.
- The larger "dark editorial design system" project (shared components, screenshots at four widths for every page) stays on the roadmap as its own piece of work.

## Status

Local development, owned or authorised sites, controlled external pilot: READY. No unresolved security concern: the change adds one static same-origin script that reads a single local-storage key and writes two attributes; it handles blocked storage and ignores any value other than `light` or `dark`.

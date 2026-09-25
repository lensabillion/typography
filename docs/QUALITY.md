# Lensa Hand 0.2 quality record

Checked locally on macOS with Python 3.14.7 and the committed uv lockfile on 2026-09-25.

- Eight tests pass, with 90% statement coverage. Fixtures are synthetic and contain no private writing.
- Ruff lint and formatting checks pass.
- Wheel and source archive build successfully and exclude source photographs and the website checkout.
- TrueType and WOFF2 validate with matching character maps and advance metrics.
- Independent HarfBuzz shaping returns no missing glyphs for supported sample text.
- Repeated builds produce identical font and ZIP bytes.
- FontBakery universal audit: 75 PASS, 0 FAIL, 0 ERROR, 2 WARN, 3 INFO, 47 SKIP.
  Network checks were skipped. The optional Google Fonts glyphsets discovery warning
  does not affect the universal audit.
- The two audit warnings concern unconventional contour counts and no pair kerning.
  The contours were visually reviewed; no speculative kerning table was added.
- The website's production build and lint pass. Browser inspection confirmed the
  handwritten family on body/headings and no synthetic bold. Desktop homepage and
  a mobile article layout showed no horizontal overflow during inspection.
- Linux and Windows CI is configured, but has not been locally executed.

Audited TTF SHA-256:
`871512732125eacb215b5444befd1c85be890c87a54547f1b59c514a97abd046`

Audited WOFF2 SHA-256:
`a08f5a8deabb0d30638405470e013c8453914250dc47c5e0af1baa5437c6c778`

## Design limitations

One regular face, 76 traced glyphs plus space and missing-glyph symbol, 83 mapped
characters. No accented Latin, Ethiopic, full ASCII, cursive connections or contextual
alternates. The Q was overwritten on the source sheet. Stroke weight and spacing
remain candidates for visual refinement. These files are technically reusable, not
a claim that type design is finished. Unsupported characters need a fallback font.

## Rechecking a release

Run the README's build, test and audit commands. Inspect the PNG and interactive
specimen at reading and display sizes. Update `fonts/` only after validating the newly
built artifacts and testing a consuming project. Record any new limitations here.

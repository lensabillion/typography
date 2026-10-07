# Quality record

Checked locally on macOS with Python 3.14.7 and the committed uv lockfile on 2026-10-07.

## handfont 0.4: template and plain-paper workflows

- The tool was renamed from `lensa-hand` to `handfont`. It gained a printable template
  with corner markers, a plain-paper mode for people who do not print, automatic
  straightening and measurement, HEIC photo support and a review image, as described in
  the README. The Lensa Hand 0.3 fonts rebuilt with it are byte-identical to the files
  audited below, so the refactor changed nothing in the shipped typeface.
- 64 tests pass with 95% statement coverage. The template tests print a page, write the
  full 94-character set on it with a stock font, simulate a phone photograph (perspective,
  lower resolution, uneven light, blur, JPEG) and build a font from it; they also cover
  two-page sets in any order, a missing page, empty cells, ink running out of a cell,
  duplicate pages, an upside-down photo, a set that writes the curly quotes itself, and
  photos with no or partial markers. The plain-paper tests write the rows on a tilted
  sheet lying on a desk, with and without ruled lines, and check that every multi-part
  character (i, j, %, =, :, ;, !, ?, the double quote) was joined, that ruled lines were
  removed, that a wrong row length stops the build with a numbered review image, and
  that photos are routed by their markers.
- Fonts built from a complete template sheet and from plain paper both pass the
  FontBakery universal audit with 75 PASS, 0 FAIL, 0 ERROR and 3 WARN (capitals not
  vertically centred in the em box, no kerning, uneven math-sign widths), all expected
  for handwriting.
- The derived crop map rebuilds the identical font through the manual path in both
  modes, so an automatic build can be refined by hand without losing reproducibility.
- The template, the synthetic photographs, the straightened sheets, the review images,
  the tracing sheets and the specimens were inspected visually.
- An independent review of the first template implementation found one high-severity
  bug (a custom set containing both a curly and a straight quote failed validation) and
  too little room under the baseline for descenders; both were fixed, with tests, along
  with the smaller items it raised.

# Lensa Hand 0.3

## Changes since 0.2

- Every `hmtx` left side bearing now equals its outline's `xMin`, so rasterizers that
  position glyphs from the metrics table and those that use the outline agree. In 0.2
  the bearing was a constant 55 while outlines started anywhere from 45 to 68 units;
  fontTools had recorded the mismatch by clearing `head.flags` bit 1, which is now set.
  Advances moved by at most 16 units. The sampled letterforms are unchanged.
- A `gasp` table tells Windows rasterizers to antialias and grid-fit the unhinted
  outlines at every size, with symmetric smoothing below 8 ppem.
- Glyphs carry Adobe Glyph List names (`a`, `comma`, `quotedblleft`) instead of `uniXXXX`.
- The PANOSE family kind is Latin hand written.
- The font revision and version string derive from the package version (0.3.0 gives
  `Version 0.300`), so they cannot drift from `pyproject.toml`.
- x-height and cap height are read from the manifest's `x` and `H` entries, and vertical
  metrics come from the drawn outlines. Both reproduce the 0.2 values.
- Side bearings and the word space are manifest design controls with unchanged defaults.

## Verification

- 39 tests pass with 95% statement coverage; the suite fails below 90%. Fixtures are
  synthetic and contain no private writing. Seven tests check the committed `fonts/`
  files against the manifest, the build record, the package version and the checksums
  recorded here.
- Ruff lint and formatting checks pass.
- Wheel and source archive build and exclude source photographs and the website checkout.
- TrueType and WOFF2 validate with matching character maps and advance metrics, and every
  left side bearing matches its outline.
- Independent HarfBuzz shaping returns no missing glyphs for supported sample text.
- Repeated builds produce identical font and ZIP bytes.
- FontBakery universal audit: 76 PASS, 0 FAIL, 0 ERROR, 2 WARN, 3 INFO, 46 SKIP, with
  network checks skipped. The warnings are the same two as in 0.2: unconventional contour
  counts, which were visually reviewed, and no pair kerning, since none was invented.
- Text at 64, 36 and 22 px was rendered side by side with the 0.2 files through FreeType
  and is visually identical. The PNG specimen was inspected.
- The website's production build and lint pass with the new WOFF2 installed.
- The interactive specimen was opened in a Chromium-based browser served from `fonts/`;
  the WOFF2 loaded, rendered the handwritten family in the tester and alphabet rows,
  and produced no console errors.
- Linux and Windows CI is configured, but has not been locally executed.

Audited TTF SHA-256:
`03b9bea9baee942292e0a4b2d5b1746df806ebedc6bfcef01a18a90edd161156`

Audited WOFF2 SHA-256:
`54c2eec3e9c77d417851058cef853f87740cd88b303b3afc0f48e2374ec884d1`

## Design limitations

One regular face, 76 traced glyphs plus space and missing-glyph symbol, 83 mapped
characters. No accented Latin, Ethiopic, full ASCII, cursive connections or contextual
alternates. The Q was overwritten on the source sheet. Side bearings are a uniform
55 units and there is no kerning; per-glyph `left` and `right` values in the manifest are
the intended route for spacing refinement. Stroke weight remains a candidate for visual
refinement. These files are technically reusable, not a claim that type design is
finished. Unsupported characters need a fallback font.

## Rechecking a Lensa Hand release

Run the README's build, test and audit commands. Inspect the PNG and interactive
specimen at reading and display sizes. Update `fonts/` only after validating the newly
built artifacts and testing a consuming project, then record the new checksums here;
`tests/test_release.py` fails until this document and `fonts/` agree.

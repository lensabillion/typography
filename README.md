# handfont

Turn a photo of your handwriting into an installable TrueType font and a self-hosted
WOFF2 web font. Print a template, write one character per box, photograph the sheet,
build. Everything runs locally; photographs are never sent to a service.

**Lensa Hand**, the first typeface made with it, ships ready to use in [`fonts/`](fonts/).
See [the quality record](docs/QUALITY.md) for its verification results and limitations.

## Make a font from your handwriting

Install [uv](https://docs.astral.sh/uv/getting-started/installation/). Then, without
cloning anything:

```sh
uvx --from git+https://github.com/lensabillion/typography@v0.4.0 handfont template
```

That writes `template/template.pdf`, one A4 page that also fits US Letter, plus a PNG
copy. Print it at any scale. Write one character in each box with a black pen: rest
letters on the long tick and let small letters reach the short tick. Photograph the whole
sheet flat, in even light, with all four corner squares in view. Then:

```sh
uvx --from git+https://github.com/lensabillion/typography@v0.4.0 handfont build --photo IMG_0001.jpg --family "Ada Hand"
```

`output/` now holds `AdaHand-Regular.ttf` for desktop installation, `AdaHand-Regular.woff2`
with `fonts.css` for the web, PNG specimens, an interactive `preview.html` tester and a
ZIP of all of them. The build finds the corner markers, straightens the photo, cuts out
every box, measures each character against the printed baseline and x-height, builds the
font and validates it. Boxes left empty are skipped and listed. A photo taken at an
angle, upside down or printed on a different paper size is fine; resolution matters more,
so fill the frame with the sheet.

Inside a clone of this repository the same commands are `uv run --locked handfont ...`.
Photos may be JPEG, PNG or HEIC, the format iPhones use.

### No printer? Write on any paper

`handfont template` also prints the rows to copy. Write them on any paper, blank or
ruled, one row per line with nine characters each, exactly in the order listed, leaving
clear gaps between characters and between rows. Photograph the page and run the same
`build` command. Without corner markers, handfont straightens the photo from the rows
themselves, paints out ruled lines, joins the parts of characters such as i, %, = and
the double quote, and writes `layout-check.png` showing which mark became which
character. Look at that image before trusting the font. If a row holds the wrong number
of characters the build stops, says which row, and numbers the marks it found in the
same image.

### Refining a letter

Two more files appear in `output/`: `sheet.png`, the straightened photograph, and
`manifest.json`, the crop map derived from it, listing each character's box, height and
baseline offset. Edit the map, for example to nudge one baseline or exclude a stray mark,
and rebuild from it:

```sh
uv run --locked handfont build --photo output/sheet.png --manifest output/manifest.json --family "Ada Hand"
```

With `uvx`, prefix the command the same way as above.

Spacing lives in the same file. `metrics.sidebearing` sets the space on each side of every
glyph (default 55 font units) and `metrics.word_space` the width of a space (default 320).
Any glyph may override its own `left` and `right`. The `version` field becomes the font's
version string. Pair kerning is not generated.

### Other character sets

The default sheet holds the 94 printable ASCII characters. Pass `--characters` with any
set, in writing order, to both commands; curly quotes and dashes map onto the plain forms
automatically. Sets with more than 99 characters span several pages. Photograph each page
and pass every photo with `--photo`, in any order: the corner markers identify the page.

## Use the font in your projects

Every build also writes `output/package/`, a complete npm package: the WOFF2 and TTF, an
`index.css` with the `@font-face` rule, a small JS entry, a README, and a `SKILL.md` that
tells an AI coding agent how to apply the font. Copy that folder into a project (for
example `fonts/her-hand/`) or publish it with `npm publish`, then:

```sh
npm install ./fonts/her-hand        # or: npm install her-hand, once published
```

```js
import "her-hand/index.css";        // once, in the root layout or entry file
```

```css
body { font-family: "Her Hand", system-ui, sans-serif; }
```

That works in Vite, Next.js, Astro, SvelteKit and plain bundled sites. The package's
`SKILL.md` has the exact steps for Next.js with `next/font/local`, Tailwind, plain HTML
without a bundler, React Native, Flutter and desktop apps. For desktop apps right away:

```sh
handfont install output/HerHand-Regular.ttf
```

copies the TTF into your user font folder on macOS, Windows or Linux.

Every font has one **regular** face. Bold and italic are not separately drawn; browsers
may synthesize them. Keep a fallback font for unsupported characters, and start at 20px or
larger for extended reading.

### Let an AI coding agent do it

`handfont skill --install .` writes a skill into a project's `.claude/skills/handfont/`.
From then on, asking the agent to "make a font from this photo of my handwriting and use
it on the site" is enough: it runs the build, checks the review image, reports skipped or
clipped characters, wires the package in, and keeps the photograph out of Git. Agents that
do not read Claude Code skills can be pointed at the same file from `AGENTS.md`. Each
generated package also carries an `AGENTS.md` block to paste into the consuming project,
so later sessions know the font exists and how to use it.

### Updating a project that already uses the font

Projects keep their own copy of the font; nothing updates automatically. Rebuild, copy the
new `package/` over the old one (or publish a new version) and reinstall. The package
version follows the manifest's `version`, so `npm` sees it as an update. To tell which
release a project has, compare the font's checksum with the quality record or the version
string the font reports in Font Book. Each
release is a Git tag named after the package version (`v0.4.0`); the `uvx` commands in
this README and in the agent skill pin that tag, so tag every release before announcing it,
and attach the font files to a GitHub release for projects that are not npm-based.

## Lensa Hand

The shipped typeface predates the template, so it is built from a photographed alphabet
sheet and a hand-written crop map, `config/alphabet.json`. The photograph stays private in
`assets/source/` and is excluded from Git, distributions and font bundles; a different sheet
needs its own crop map, whose coordinates refer to a reference width of 1373 pixels.

```sh
uv sync --locked
uv run --locked handfont build --photo assets/source/alphabet.jpg --manifest config/alphabet.json --family "Lensa Hand"
uv run --locked handfont validate output/LensaHand-Regular.ttf --manifest config/alphabet.json
```

`fonts/package/` is the ready-made `lensa-hand` npm package; `npm install ./fonts/package`
from a project inside this repository, or copy the folder anywhere.

Its repertoire is Latin A–Z, a–z, digits and sampled punctuation, with no accented Latin,
Ethiopic, contextual alternates or cursive joining. The overwritten Q remains visible in
the source. A font that passes technical checks still needs visual judgment; the quality
record lists what was inspected. No open-source font license has been assigned on your
behalf.

## How it works

OpenCV's ArUco detector locates the four corner markers and a homography straightens the
page to the template's geometry. On plain paper there are no markers, so the rotation that
makes the row profile sharpest straightens the photo, long horizontal and vertical runs of
ink (ruled lines, page edges) are painted out, and marks are grouped into rows and then
joined left to right until each row holds its expected number of characters. Ink is
whatever is darker than the locally blurred paper, which tolerates uneven lighting. Potrace fits curves to each character and fontTools
converts them to TrueType outlines, with every outline placed exactly on its left side
bearing so the metrics and the outline agree. The writer's x-height, the median of the
x-height letters, becomes 430 font units; capitals, ascenders and descenders keep their
real proportions, and small baseline wobble is snapped so letters sit on the line. The
font gets a `gasp` table for Windows rendering, Adobe Glyph List names, and metrics
derived from the drawn outlines. Repeated builds are byte-for-byte identical.

## Quality checks

```sh
uv run --locked ruff check src tests scripts
uv run --locked ruff format --check src tests scripts
uv run --locked pytest --cov=handfont --cov-report=term-missing
uv build --no-sources
```

Tests print a template, write on it with a stock font, simulate a phone photograph and
build a font from it, so CI needs no private handwriting. `tests/test_release.py` also
checks that `fonts/`, `config/alphabet.json` and the quality record's checksums agree. CI
runs on Linux, macOS and Windows with pinned action commits, and a separate Linux job
validates the shipped fonts and runs the FontBakery universal audit, failing on FAIL or
ERROR. A configured workflow is not evidence that every platform has already run.

For the independent audit of any built font:

```sh
uv sync --locked --group audit
uv run --locked --group audit fontbakery check-universal output/LensaHand-Regular.ttf \
  --skip-network --json output/fontbakery-report.json
```

`--skip-network` omits online version and name-collision lookups; structural checks still
run. Inspect warnings instead of suppressing them wholesale: some checks assume
conventional typefaces and flag intentional handwritten features, while failures and tool
errors must be investigated.

To inspect a specimen in a browser, serve the directory and open `preview.html`:

```sh
uv run --locked python -m http.server 8765 --directory fonts
```

Python is pinned to **3.14.7** in `.python-version`. `uv` manages the environment;
`pyproject.toml` declares dependencies and `uv.lock` pins the complete graph. In a sandbox
that cannot write the normal uv cache, set `UV_CACHE_DIR` to a writable directory.

## Updating dependencies

```sh
uv lock --upgrade
uv sync --locked --group audit
uv run --locked pytest
uv run --locked ruff check src tests scripts
```

Rebuild the fonts, rerun the independent audit, and inspect the specimen before adopting
an upgrade. The project uses stable releases, not prereleases. Dependency versions were
checked against [PyPI](https://pypi.org/) on 2026-09-25; monthly Dependabot checks are
configured for uv and GitHub Actions.

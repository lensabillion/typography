# Lensa Hand

Your handwriting as an installable TrueType font and a self-hosted WOFF2 web font.
The source package traces the original alphabet photograph, builds previews, and
validates the generated files. It runs locally; photographs are never sent to a service.

## Ready-to-use font

The `fonts/` directory contains the validated 0.3 TTF, WOFF2, CSS and specimen.
Use those directly without rebuilding. See [the quality record](docs/QUALITY.md)
for verification results and known design limitations.

## Setup and build

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run from this directory:

```sh
uv sync --locked
uv run --locked lensa-hand build --source assets/source/alphabet.jpg
uv run --locked lensa-hand validate output/LensaHand-Regular.ttf --manifest config/alphabet.json
```

Python is pinned to **3.14.7** in `.python-version`. `uv` manages the environment;
there is no manual activation, `pip install`, or direct `.venv/bin/python` workflow.
`pyproject.toml` declares dependencies and `uv.lock` pins the complete dependency graph.
In a sandbox that cannot write the normal uv cache, set `UV_CACHE_DIR` to a writable directory.

The supplied photograph has been copied to `assets/source/alphabet.jpg` on this computer.
It is intentionally excluded from Git, Python distributions and font bundles. On another
computer, provide your copy of the same photograph, or supply a new crop manifest.

## Use in your projects

For desktop apps, open `output/LensaHand-Regular.ttf` and install it with your operating
system's font manager. Choose **Lensa Hand / Regular** in your application.

For a website, copy `LensaHand-Regular.woff2` into your public font directory:

```css
@font-face {
  font-family: "Lensa Hand";
  src: url("/fonts/LensaHand-Regular.woff2") format("woff2");
  font-style: normal;
  font-weight: 400;
  font-display: swap;
}

body {
  font-family: "Lensa Hand", system-ui, sans-serif;
  font-size: 1.25rem;
  line-height: 1.65;
}

code, pre, kbd, samp {
  font-family: ui-monospace, monospace;
}
```

Next.js projects can use `next/font/local` to self-host and preload this file. This
repository's `integrations/personal-website` checkout exercises that integration.
That is a separate Git repository and is excluded from the font project's packages.

### Updating a project that already uses the font

Projects keep their own copy of the font file; nothing updates automatically. To move a
project to a new release, copy the new `fonts/LensaHand-Regular.woff2` (or the TTF) over
its old copy, rebuild and redeploy. Next.js fingerprints the file, so visitors' caches
refresh on their own. To see which release a project has, compare the file's SHA-256
with [the quality record](docs/QUALITY.md), or check the version string the font
reports in Font Book (`Version 0.300` is release 0.3). Each release should also be a Git
tag and a GitHub release with the two font files attached, so other projects can fetch
them without cloning this repository.

There is one **regular** face. Bold and italic are not separately drawn faces;
browsers may synthesize them. Keep a fallback font for unsupported characters.
Start with 20px or larger for extended reading and review on your target screens.

## Source and design controls

`config/alphabet.json` holds each character's crop box, target height and baseline offset,
plus deliberate aliases for quotes, dashes and nonbreaking space. Its coordinates
refer to the reference width of 1373 pixels; the original photograph is traced at full
resolution. A replacement photograph needs a matching manifest.

Spacing is a design control too. An optional top-level `"metrics"` object sets the
uniform `"sidebearing"` (default 55 font units on each side) and the `"word_space"`
advance (default 320). Any glyph may override its own `"left"` and `"right"` bearings.
The builder places each outline exactly on its left bearing, so the metrics table and
the outline always agree. Pair kerning is not generated.

The font uses actual sampled letterforms. Target heights are optical adjustments,
not preservation of the photographed letters' original relative size. The journal
and note pages serve as visual references; their text is not included in the package.

The current repertoire is Latin A–Z, a–z, digits and sampled punctuation. It does not
include accented Latin, Ethiopic, full ASCII symbols, contextual alternates or cursive
joining. The overwritten Q remains visible in the source. A font that passes technical
checks still needs visual judgment; these limitations are not hidden by validation.
No open-source font license has been assigned on your behalf.

## Quality checks

```sh
uv run --locked ruff check src tests scripts
uv run --locked ruff format --check src tests scripts
uv run --locked pytest --cov=lensa_hand --cov-report=term-missing
uv build --no-sources
```

To inspect the specimen in a browser, serve the font directory and open `preview.html`:

```sh
uv run --locked python -m http.server 8765 --directory fonts
```

Tests use synthetic handwriting fixtures, so CI does not need your private photographs.
CI is configured for Linux, macOS and Windows with pinned action commits. A configured
workflow is not evidence that all three platforms have already run successfully.
A separate Linux job validates the shipped `fonts/` files against the manifest and
runs the FontBakery universal audit, failing on FAIL or ERROR and uploading its JSON
report. `tests/test_release.py` also checks that `fonts/`, `config/alphabet.json` and
the quality record's checksums agree, so a manifest edit without a rebuild fails tests.

For the independent font audit:

```sh
uv sync --locked --group audit
uv run --locked --group audit fontbakery check-universal output/LensaHand-Regular.ttf \
  --skip-network --json output/fontbakery-report.json
```

`--skip-network` omits online version and name-collision lookups; structural checks
still run. Omit that option for an online audit.

Inspect warnings instead of suppressing them wholesale. Some checks assume conventional
typefaces and may flag intentional handwritten features. Failures and tool errors must
be investigated. The font builder also validates coverage, metrics and web-font parity.

## Updating dependencies

```sh
uv lock --upgrade
uv sync --locked --group audit
uv run --locked pytest
uv run --locked ruff check src tests scripts
```

Rebuild the font, rerun the independent audit, and inspect the specimen before adopting
an upgrade. The project uses stable releases, not prereleases. Dependency versions were
checked against [PyPI](https://pypi.org/) on 2026-09-25; monthly Dependabot checks are
configured for uv and GitHub Actions.

---
name: handfont
description: Turn a photo of someone's handwriting into a font (TTF, WOFF2 and an npm package) and wire it into a project. Use when asked to make a handwriting font, build a font from a photo or a printed template, or add "my handwriting" to a website or app.
---

# Make a handwriting font with handfont

handfont runs locally through `uv`; photographs never leave the computer. The commands
below work from any directory. Inside a clone of the handfont repository, replace
`uvx --from git+https://github.com/lensabillion/typography@v0.4.0 handfont` with
`uv run --locked handfont`.

## 1. Check the tooling

Run `uv --version`. If uv is missing, stop and ask the person to install it from
https://docs.astral.sh/uv/getting-started/installation/ rather than installing it for them.

## 2. Get a photograph

If the person already has a photo of their handwriting sheet, use it (JPEG, PNG or HEIC).
Otherwise run

    uvx --from git+https://github.com/lensabillion/typography@v0.4.0 handfont template --output handfont-template

and tell them to either print `handfont-template/template.pdf` and write one character per
box, or copy the rows the command printed onto any paper, nine characters per row in that
order, with clear gaps between characters and rows. They should photograph the whole sheet
flat, in even light, filling the frame, and give you the photo's path.

## 3. Build

    uvx --from git+https://github.com/lensabillion/typography@v0.4.0 handfont build --photo PHOTO --family "NAME Hand" --output handfont-output

Repeat `--photo` for several pages. Use the family name the person chooses; it becomes the
CSS font-family and the file names.

## 4. Read the result before trusting it

- If the command stopped, its message says what went wrong: a row with the wrong number of
  characters, missing corner markers, an unreadable photo. For plain paper it also names
  `layout-check.png`, where the marks it found are numbered. Explain the problem, show the
  image when there is one, and ask for a corrected sheet or a better photo. Do not edit the
  crop map to force a result.
- If it succeeded, open `handfont-output/layout-check.png` (plain paper) or
  `handfont-output/tracing-check.png` (template) and confirm each label sits on the right
  mark. Report characters listed as skipped or clipped so the person can rewrite them.
- Open the `-preview.png` specimen and describe how the font looks.

## 5. Deliver

- `handfont-output/package/` is a complete npm package for websites and apps. Copy it into
  the project (for example `fonts/<package-name>/`) or publish it. Its `SKILL.md` explains
  how to apply the font in Next.js, plain HTML, Tailwind, React Native and Flutter; follow
  it to wire the font in, and copy it to `.claude/skills/use-<package-name>-font/SKILL.md`
  so later sessions find it. Paste its `AGENTS.md` block into the project's AGENTS.md.
- `uvx --from git+https://github.com/lensabillion/typography@v0.4.0 handfont install handfont-output/<Stem>-Regular.ttf`
  installs the font for desktop apps.
- `handfont-output/<Stem>-Draft.zip` holds everything for sharing.

## 6. Keep private things private

Never commit the photograph, `sheet.png` or `manifest.json`; they show the person's
handwriting. Add `handfont-output/` to `.gitignore` unless they ask to keep the package in
the repository. The files in `package/` contain only outlines and are fine to commit.

## Rules

- Do not invent characters that were not written. The font covers only what the build
  reports, so projects must keep a fallback font.
- There is one regular face. Never request bold or italic for this family; browsers would
  fake them.
- Keep code blocks in a monospace font and body text at 20px or larger.

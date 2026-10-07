---
name: use-lensa-hand-font
description: Apply the "Lensa Hand" handwriting font (npm package "lensa-hand") in this project. Use when asked to use the handwriting font, "my handwriting", or Lensa Hand on a website or in an app.
---

# Use the Lensa Hand handwriting font

The package `lensa-hand` holds one regular face: `fonts/LensaHand-Regular.woff2` for the web and
`fonts/LensaHand-Regular.ttf` for apps and desktops. Its CSS font-family name is `Lensa Hand`.

## Install

- From the npm registry, if it was published: `npm install lensa-hand`
- From a folder inside the repository: `npm install ./fonts/lensa-hand` (adjust the path)

Keep the folder inside the project. npm links a local folder rather than copying it, and
Next.js with Turbopack cannot read a linked folder that lives outside the project root.

## Any web project with a bundler (Vite, Next.js, Astro, SvelteKit, Create React App)

1. Import the stylesheet once, in the root layout or entry file: `import "lensa-hand/index.css";`
2. Use it: `font-family: "Lensa Hand", system-ui, sans-serif;`

## Next.js App Router

`import "lensa-hand/index.css";` in `app/layout.tsx` is enough. To preload the file and avoid
layout shift, use `next/font/local` instead:

    import localFont from "next/font/local";
    const hand = localFont({
      src: "../node_modules/lensa-hand/fonts/LensaHand-Regular.woff2",
      weight: "400",
      style: "normal",
      display: "swap",
      variable: "--font-hand",
    });

Put `hand.variable` on the `<html>` class and use `var(--font-hand)` in CSS. Adjust the
relative path to wherever the file lives.

## Tailwind

Tailwind 4: in the CSS that imports Tailwind, add `@theme { --font-hand: "Lensa Hand", system-ui, sans-serif; }`.
Tailwind 3: in the config, `theme.extend.fontFamily.hand = ['"Lensa Hand"', "system-ui", "sans-serif"]`.
Either way, use `class="font-hand"`.

## Plain HTML without a bundler

Copy `fonts/` and `index.css` next to the page and add `<link rel="stylesheet" href="index.css">`.

## React Native

Copy `fonts/LensaHand-Regular.ttf` into the app's font assets and link them (list the folder
under `assets` in `react-native.config.js`, then run `npx react-native-asset`). Use
`fontFamily: "LensaHand-Regular"` on both platforms; it is the font's PostScript name and the
file name without extension.

## Flutter

Copy `fonts/LensaHand-Regular.ttf` into the app and declare it in `pubspec.yaml`:

    flutter:
      fonts:
        - family: Lensa Hand
          fonts:
            - asset: fonts/LensaHand-Regular.ttf

then use `TextStyle(fontFamily: "Lensa Hand")`.

## Desktop apps (Word, Figma, Canva, Procreate)

Install `fonts/LensaHand-Regular.ttf` with the system font manager, or run
`uvx --from git+https://github.com/lensabillion/typography@v0.4.0 handfont install fonts/LensaHand-Regular.ttf`.

## Rules

- Covered characters, plus space and the aliases listed in README.md:

      abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,!?;:'“”()-&@

  Always keep a fallback font after `Lensa Hand`; any other character falls through to it.
- One regular weight only. Do not set bold or italic on this family; browsers would
  synthesize them badly.
- Keep code in a monospace font. Body text reads best at 20px or larger with a line height
  near 1.6.
- Do not rename the family in CSS; `Lensa Hand` is the name inside the font file.

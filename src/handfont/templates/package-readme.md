# $family

A handwriting font built with [handfont](https://github.com/lensabillion/typography).
One regular face, in `fonts/$stem-Regular.woff2` (web) and `fonts/$stem-Regular.ttf`
(apps and desktops). The CSS font-family name is `$family`.

## Use it on a website

    npm install $name            # or: npm install ./fonts/$name from a folder in your repo

Keep a local copy inside the project; npm links folders rather than copying them, and
Next.js cannot read a link that points outside the project root.

Then import `$name/index.css` once and write `font-family: "$family", system-ui, sans-serif;`.
`SKILL.md` has the exact steps for Next.js, Tailwind, plain HTML, React Native, Flutter and
desktop apps, written so an AI coding agent can follow them too: copy it to
`.claude/skills/use-$slug-font/SKILL.md` in your project, and paste `AGENTS.md` into your
project's AGENTS.md, and the agent will know how to use your handwriting.

## What it covers

    $characters

${aliases}Keep a fallback font for everything else. There is no bold or italic; browsers would fake
them. Body text reads best at 20px or larger.

## License

No license has been chosen yet (`UNLICENSED` in package.json). Pick one before sharing the
package with others, for example the SIL Open Font License, and record it here.

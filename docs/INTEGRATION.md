# Integration guide

The files in `mushaf-v4/` are complete SVG documents. They can be displayed as
ordinary images or loaded inline for themes, highlighting and word taps.

## Select a page

The corpus uses one-based, zero-padded filenames:

```js
function quranPagePath(page) {
  if (!Number.isInteger(page) || page < 1 || page > 604) {
    throw new RangeError("Quran page must be an integer from 1 through 604");
  }
  return `/quran/mushaf-v4/page-${String(page).padStart(3, "0")}.svg`;
}
```

Pin a repository release or commit when serving files from a Git host or CDN.
That keeps an application on a corpus whose manifest it has tested.

## Display or inline

Use `<img>`, CSS `background-image`, or a native image component when the page
only needs to be displayed. The SVG has no external font, image, stylesheet or
script dependency.

Use inline SVG when the application needs to manipulate internal classes:

```js
async function mountPage(page, container) {
  const response = await fetch(quranPagePath(page));
  if (!response.ok) throw new Error(`Unable to load Quran page ${page}`);

  const document = new DOMParser().parseFromString(
    await response.text(),
    "image/svg+xml",
  );
  const error = document.querySelector("parsererror");
  if (error) throw new Error(`Invalid Quran SVG: ${error.textContent}`);

  const svg = document.documentElement;
  container.replaceChildren(svg);
  return svg;
}
```

Only inline SVG files from a trusted, pinned copy of this repository. Generic
SVG is active document content and should be sanitized before insertion.

## Address ayahs and words

Ayah and word locations use Quran.com-style coordinates:

| Object | Element | ID | Metadata |
| --- | --- | --- | --- |
| Ayah | `g.q-ayah` | `q-a12-106` | `data-ayah="12:106"` |
| Word | `g.q-word` | `q-w12-106-3` | `data-loc="12:106:3"` |
| Ayah end | `g.q-mark` | `q-e12-106` | `data-ayah="12:106"` |

Every word also has `data-line` and `data-box="x y width height"`. Boxes use
the root viewBox coordinate system, including the recto/verso gutter offset.
They are suitable for hit regions or for scrolling a word into view.

```js
svg.addEventListener("click", (event) => {
  const word = event.target.closest?.(".q-word");
  if (!word) return;
  svg.querySelectorAll(".q-word.is-selected")
    .forEach((element) => element.classList.remove("is-selected"));
  word.classList.add("is-selected");
  console.log(word.dataset.loc, word.dataset.line, word.dataset.box);
});
```

Highlighting changes the letterforms. It does not place a rectangle over or
behind the Qur'anic text.

```js
svg.querySelector("#q-a12-106")?.classList.add("is-active");
svg.querySelector("#q-w12-106-3")?.classList.add("is-active");
```

A word highlight takes visual priority when both its word and ayah are active.
Remove `is-active` when playback advances.

## Tajweed and page layers

The v4 outlines carry named tajweed classes. Add classes to the root SVG to
change what is visible:

```js
svg.classList.toggle("q-tajweed", showTajweed);
svg.classList.toggle("q-tajweed-plain", showTajweed && ruleColoursOnly);
svg.classList.toggle("q-no-frame", hideFrame);
svg.classList.toggle("q-no-chrome", hideRunningHead);
svg.classList.toggle("q-no-illumination", hideOpeningDecoration);
```

`q-tajweed` enables recitation-rule colours. Adding `q-tajweed-plain` also
reduces ordinary vowel marks, pause marks and the divine-name treatment to the
base ink colour, leaving only rule segments coloured.

## Apply a bundled or custom theme

Colours live inside one replaceable CSS block:

```css
/* THEME:BEGIN green-pink */
/* class rules with literal colours */
/* THEME:END */
```

The CLI safely replaces this block without touching page geometry:

```bash
python tools/quransvg.py retheme page-248.svg --theme night --out page-248-night.svg
python tools/quransvg.py theme-block --theme sepia
```

For an application-defined palette, load `themes-v4/schema.json`. Its `tokens`
map each colour name to the selector and CSS property it controls. Require all
tokens, accept only CSS colour values your application trusts, generate the
rules in schema order, and replace everything from the begin marker through
the end marker.

Literal colours are intentional. Some native SVG engines do not resolve CSS
custom properties in all paint contexts, especially gradient stops.

## Hosting and native renderers

Serve files as `image/svg+xml` and enable compression. The pages are path-heavy
and compress well. Cache immutable release paths for a long duration; use the
SHA-256 values in `manifest.json` when an application needs integrity checks.

Most browser engines support the full contract. For native renderers, verify
support for embedded `<style>`, class selectors, `<defs>/<use>`, transforms and
`xlink:href`. If a renderer treats an SVG as an opaque image, apply root classes
or theme-block replacements to the SVG string before handing it to the image
component.

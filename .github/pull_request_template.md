## What changed

Describe the consumer-visible result and why it is needed.

## Quran rendering impact

List every affected page and `surah:ayah:word` location, or write “none”. Link
the authoritative source for any content or recitation change.

## Validation

- [ ] `python tools/validate_release.py`
- [ ] `python tools/quransvg.py verify 1,2,248,604` when generator output changed
- [ ] `manifest.json` regenerated when any published page changed
- [ ] Tested in relevant browser or native SVG renderer
- [ ] No QCF v1/v2 page set or downloaded font/cache was added

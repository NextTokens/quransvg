# Contributing

Thank you for helping make the QCF v4 SVG corpus easier and safer to use.

## Before opening an issue

Search existing issues, then choose the template that best matches the report.
For a Qur'anic text or rendering concern, include the page number and the exact
surah, ayah and word when known. Also include the renderer or application,
operating system, viewport size, and a screenshot that clearly marks the
problem. Avoid paraphrasing the affected Arabic text.

## Pull requests

Keep changes focused and explain their effect on consumers. The supported
corpus is QCF v4 under `mushaf-v4/`; do not add QCF v1 or v2 page sets.

Generated pages should never be edited by hand. Change the generator or theme,
rebuild the affected pages, regenerate the manifest, and run the release check:

```bash
python -m pip install -r requirements.txt
python tools/quransvg.py build 248 --out mushaf-v4
python tools/build_manifest.py
python tools/validate_release.py
```

For layout or text changes, also run the deeper generator verification on the
affected pages and representative opening/body/closing pages:

```bash
python tools/quransvg.py verify 1,2,248,604
```

A pull request that changes Qur'anic rendering should state:

- the source and reason for the correction;
- every affected page and location;
- how the before and after output was compared;
- which browsers or native renderers were checked.

Automated checks establish structure and consistency. Maintainers may ask for
additional scholarly review before accepting changes to Qur'anic content or
recitation colouring.

## Code style

Use Python 3.10 or newer, type annotations for new public functions, UTF-8 text,
and deterministic output. Do not add timestamps, machine-specific paths, or
network results to generated SVGs or the manifest.

Be patient and precise in discussions. Reports about Arabic typography and
recitation often need screenshots and domain context before they can be
reproduced.

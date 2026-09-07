# Rights, sources and attribution

This repository combines original software with religious text, derived glyph
outlines, fonts and source data that have separate owners and terms.

## Repository software

Unless a file says otherwise, the original Python, JavaScript, HTML, CSS and
documentation authored for this repository are available under the MIT License
in `LICENSE`.

The MIT License does **not** grant rights in Qur'anic text, QCF-derived glyph
outlines, upstream fonts, upstream datasets, names, marks, or other third-party
material.

## Published QCF v4 pages

The SVG files in `mushaf-v4/` contain outline geometry derived from the QCF v4
Tajweed fonts. Quran Foundation's current Mushaf source directory identifies
the providers for “QCF V4 Tajweed” as the King Fahd Glorious Qur'an Printing
Complex and Dar Al Maarifah:

- https://api-docs.quran.com/legal/mushaf-fonts-and-images/

Quran Foundation states that this directory identifies providers and delivery
sources but does not itself grant additional rights to font or image files. It
also directs developers to contact the listed provider for caching or offline
use. Its current developer terms are here:

- https://api-docs.quran.com/legal/developer-terms/

The King Fahd Complex historically published a usage statement allowing free
use of its complete digital Madinah Mushaf in personal, governmental and
private-sector work, digital publishing, websites, software and similar media,
subject to stated printing restrictions. An archived copy collected during
development is in `docs/licenses/kfgqpc-copyright-EN.txt`.

Another archived notice distributed with a KFGQPC Uthmanic font says that the
font may not be reproduced or modified without the Complex's express written
approval. That short notice is preserved in
`docs/licenses/kfgqpc-uthmanic-script-license.txt`.

Those statements do not resolve every jurisdiction, redistribution method, or
right that may apply to converted SVG outlines. Review the current provider
terms and obtain any permission your use requires before redistributing this
corpus or shipping it in a product.

## Build inputs

Downloaded build inputs are intentionally excluded from Git:

- QCF v4 page fonts and the associated word table;
- the QCF basmalah font;
- the Quranic Universal Library surah-name font;
- Quran Foundation chapter metadata;
- Amiri Regular and Bold.

Amiri is distributed under the SIL Open Font License 1.1; its license text is
in `docs/licenses/OFL-Amiri.txt`. The other font and data inputs remain subject
to their providers' terms. Running the fetch or build commands accesses those
external services directly.

## Attribution and independence

When using these pages, retain appropriate attribution to the King Fahd
Glorious Qur'an Printing Complex, Dar Al Maarifah, Quranic Universal Library,
and Quran Foundation as applicable to the resources used.

This is an independent community project. It is not affiliated with or endorsed
by those organizations.

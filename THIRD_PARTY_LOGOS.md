# Bundled logo assets

The picker uses local copies so it never needs to fetch logo images at runtime.

| Asset | Source |
| --- | --- |
| arXiv alternate primary logo | [arXiv logo library](https://info.arxiv.org/brand/logos.html) |
| GitHub mark | [GitHub logos](https://github.com/logos) |
| Hugging Face full-color icon | [Hugging Face brand assets](https://huggingface.co/brand) |
| Google Scholar | [Simple Icons 16.19.0](https://github.com/simple-icons/simple-icons/blob/16.19.0/icons/googlescholar.svg), filled #4285F4 |
| ORCID | [Simple Icons 16.19.0](https://github.com/simple-icons/simple-icons/blob/16.19.0/icons/orcid.svg), filled #A6CE39 |
| YouTube | [Simple Icons 16.19.0](https://github.com/simple-icons/simple-icons/blob/16.19.0/icons/youtube.svg), filled #FF0000 |

Simple Icons publishes its artwork under [CC0 1.0 Universal](https://github.com/simple-icons/simple-icons/blob/16.19.0/LICENSE.md). The full license is bundled in `static/logos/SIMPLE_ICONS_LICENSE.txt`.

Brand names, marks and associated rights remain with their respective owners. Inclusion identifies link destinations and does not imply endorsement. Brand usage guidance is available from the linked sources and the [Simple Icons disclaimer](https://github.com/simple-icons/simple-icons/blob/16.19.0/DISCLAIMER.md).

To add a preset, place a self-contained SVG in `static/logos/`, add an ID, label and filename to `catalog.json`, document its source here, and run the tests. The API only loads filenames from that catalog, never paths supplied by a request.

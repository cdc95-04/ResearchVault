# Third-party source inventory

The projects below inform behavior requirements. None is included as source code,
submodule, copied prose/template, vendored distribution or runtime prerequisite.

| Design source | Examined reference | Treatment |
| --- | --- | --- |
| cheneternity/Zotero-Analytical-Workflow-Skills | fb95dda1afb4b824aa3922b44bdbd4161e9e8ab9 | Prior audit found no explicit LICENSE; ideas/behaviors only |
| cdc95-04/Zotero-Analytical-Workflow-Skills | codex/researchvault-robotics-refactor at a699e64 | Prototype remains separate; no Git history or implementation transferred |
| YakarifromCN/Robotics-Research-Skill | 17f44a23782952c43203d779586bed3030ee0094 | Reference snapshot MIT; no code reuse chosen |
| miracleNico/auto-paper-collector | ad17ca80c51f08a5a62a462819bf6bd3ec6032c2 | Prior audit found no explicit LICENSE; intake behavior only |
| yananlong/codex-skills | 955fcc435e651834b03768c136dca6b16ccbae08 | Prior audit found no explicit LICENSE; systematic-review design only |
| leemager/codex-research-assistant | 00ab63ae66d33769e188efc3148d1dcf54c46003 | Prior audit found no explicit LICENSE; reproducibility/eval principles only |

Official protocol sources:

- [Zotero Local API](https://www.zotero.org/support/dev/web_api/v3/local_api)
- [Zotero write requests](https://www.zotero.org/support/dev/web_api/v3/write_requests)
- [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)
- [Unpaywall API](https://data.unpaywall.org/products/api)
- [arXiv API](https://info.arxiv.org/help/api/user-manual.html)

PyYAML and optional pypdf and fonttools are installed dependencies; their
distributions retain their own notices, including fonttools' `LICENSE.external`
for its bundled external components. ResearchVault does not vendor these packages
or relicense their contents. No reference project's license is asserted over this repository.
ResearchVault's own code and documentation use the [MIT license](LICENSE).
That choice does not relicense third-party dependencies, reference projects or
paper content. See [source review](PROVENANCE.md) and [license scope](LICENSE_STATUS.md).

Installed validation snapshot, 2026-09-27: PyYAML 6.0.3 declares MIT in package
metadata; pypdf 6.19.0 declares BSD-3-Clause. `pip-audit` found no known
vulnerabilities for those exact runtime versions at that check. This is a dated
dependency result, not a guarantee about future versions or vulnerabilities.

CI and dependency-audit contracts were checked against the official
[GitHub Python workflow guide](https://docs.github.com/en/actions/tutorials/build-and-test-code/python),
[checkout action](https://github.com/actions/checkout),
[setup-python action](https://github.com/actions/setup-python) and
[pip-audit documentation](https://github.com/pypa/pip-audit).
The workflow uses these tools as dependencies, not copied implementation source.

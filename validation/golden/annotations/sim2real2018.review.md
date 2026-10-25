# Paper C source annotation review: sim2real2018

Status: **agent_independent_pending_human**. No human approval is claimed. This review records source checks, not a passed ResearchVault evaluation or a benchmark score.

The annotation source is [arXiv v3](https://arxiv.org/pdf/1710.06537v3). Its version, byte hash and page count are recorded in [sim2real2018.json](sim2real2018.json). Evidence locators are one-based PDF page positions. The PDF and rendered inspection page remain in an ignored local validation workspace; neither is part of the committed annotations.

## Why this is the imperfect-metadata case

The [arXiv history](https://arxiv.org/abs/1710.06537) records an initial 2017 submission and a 2018 revision, while the [author project](https://xbpeng.github.io/projects/SimToReal/index.html) identifies the ICRA 2018 publication. The latter supplies the conference DOI, also present in arXiv's related-DOI metadata. The source year therefore needs an explicit meaning instead of silent replacement.

There is also a real pagination discrepancy: the author bibliography lists pages 1-8, while its [conference PDF](https://xbpeng.github.io/projects/SimToReal/SimToReal_2018.pdf) displays printed pages 3803-3810. This supports retaining manifestation-specific locators. It does not support inventing an identifier conflict or declaring the PDFs interchangeable. No scientific change between manuscript revisions was established.

The requested directory URL failed through the web reader; the explicit author index page worked. The IEEE landing page presented an anti-bot challenge, so DOI verification rests on two available primary sources above. The public arXiv PDF was obtained through Python's normal HTTPS verification after PowerShell's HTTP client failed authentication. These access observations are local to this validation run.

## Independent annotation procedure

This annotator previously implemented read-only guards and ran synthetic safety regressions in this repository. That earlier context included repository code and synthetic test output. For this annotation assignment, no ResearchVault paper-processing output, blind capture, retrieval result, validator result or Golden Set score was inspected. The JSON flag `implementation_outputs_seen: false` is scoped to this paper's annotation workflow, not a claim that the annotator has never worked on the project.

Claims were selected and paraphrased from the primary PDF, after metadata verification. `pypdf` extraction was checked against a Poppler rendering of PDF page 7. The comparison included table row labels, simulation versus real columns, displayed uncertainty and trial counts. The sampling-timescale claim was checked directly in Section IV-C, with the experimental details on the following pages available as context. No source quotations are included in the annotations.

Only neutral questions and claim IDs were supplied for a separate blind capture. The answer-bearing annotation file was authored without seeing that capture. Both retrieval queries and expected relevant claim IDs were fixed from the source before retrieval execution; no query was tuned to a system result.

## Human review checklist

| Annotation | Evidence | Review target | Status |
| --- | --- | --- | --- |
| sim2real2018-c1 | PDF page 7, Table II and caption | Correct row, environment, uncertainty and trial-count associations | Agent checked; human pending |
| sim2real2018-c2 | PDF page 7, Table III | Ablation conditions remain distinct and comparison scope stays local | Agent checked; human pending |
| sim2real2018-c3 | PDF page 4, Section IV-C | Episode-level parameters and timestep-level variation remain distinct | Agent checked; human pending |
| Identity | arXiv history, author bibliography, conference PDF | Preprint year, conference year and pagination are represented separately | Agent checked; human pending |
| Retrieval expectations | Queries in the annotation JSON | Relevance labels were defined before running retrieval | Predefined; execution not reviewed |

The table's plus/minus notation is preserved without assigning a statistical interpretation that was not established by this review. The annotations do not assert formal significance, general performance guarantees, or applicability to other robots and tasks. The experiment has not been reproduced. No automatic validator pass rate, false-positive rate or retrieval score is claimed here.

Human review should resolve any disputed interpretation before these annotations are promoted beyond provisional agent-created expectations. Availability of a public PDF and passing technical checks do not establish redistribution permission.

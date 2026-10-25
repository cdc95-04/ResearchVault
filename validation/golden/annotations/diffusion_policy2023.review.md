# Diffusion Policy RSS 2023 Golden annotation review

Status: `agent_independent_pending_human`. **Human review has not occurred.** This record is an independently prepared candidate Golden annotation, not a claim of human approval.

The factual basis is the [RSS conference entry](https://roboticsconference.org/2023/program/papers/026/), [publisher metadata and BibTeX](https://www.roboticsproceedings.org/rss19/p026.html), and the [publisher PDF](https://www.roboticsproceedings.org/rss19/p026.pdf). The publisher page's download target was checked. The downloaded PDF contains 16 pages and has SHA-256 `723a030b809be1958d03b06472ac79934fd64e5a890cdfeffd9508a353101a25`. Page locators are one-based PDF page indexes, including the title page.

The selected publication is the seven-author RSS 2023 proceedings version. Its publisher metadata and title-page author order agree. The publisher spells Benjamin Burchfiel's name with the additional `CM`; the PDF omits those initials. The [current arXiv metadata](https://arxiv.org/abs/2303.04137v5) was checked only for identity comparison: it describes a 2024 extended journal version with an additional author and different order. The unversioned arXiv ID must not cause this RSS record to acquire that version's metadata or evidence.

Three claims were paraphrased from separately locatable passages. They cover the method, a timing configuration, and a table comparison. Their evidence resides on PDF pages 3, 4, and 6; the table protocol is also supported by page 7. No prose quotation or extracted full text is included in the deliverables. Numerical conditions, observation type, demonstration type, table columns, and checkpoint aggregation remain explicit in the JSON.

Text extraction used `pypdf`. Visual inspection used Poppler renders of PDF page 3, containing the method figure and equations, and PDF page 6, containing the experiment tables and captions. The reviewed table cells and their headers were legible. Extraction reported `FloatObject (b'0.00-28645087') invalid; use 0.0 instead`, and the page-3 render reported `Syntax Warning (2397123): Badly formatted number`. The rendered evidence remained readable; these warnings are recorded as limitations rather than hidden. No inference of a clean PDF syntax check is made.

The annotation agent did not read `src/`, `tests/`, existing application outputs, capture outputs, or retrieval results. The two retrieval questions and expected claim IDs were chosen from the original paper before implementation results were available. A separate blind task list contains only neutral questions and claim IDs; no answers or scope conclusions were supplied through that list.

All source PDFs and rendering intermediates remain under ignored `.qa/phase2/papers/`. The review files contain no absolute local paths or private data. No Zotero account or real Vault was accessed, and no commit was created by this annotation agent.

Pending human review should confirm the source-version choice, evidence locators, aggregation interpretation, scope boundaries, and the suitability of the predefined retrieval queries. The status must remain pending until that review actually happens.

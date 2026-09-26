# Student-filter labeling guide (PR 4)

Label what the **posting states**, not what seems likely. When the text doesn't say, the
answer is `null` (unknown). Read the whole posting, including the footer: citizenship and
export-control language is often at the very end.

Input: `api/tests/fixtures/extraction_eval/postings.jsonl.gz`, one JSON object per line
(`id`, `title`, `location`, `ats_hints`, `text`).

Output: one JSON object per posting, keyed by `id`, with exactly these fields.

| Field | Values | Rule |
|---|---|---|
| `term_season` | `"summer"`, `"fall"`, `"spring"`, `"winter"`, or `null` | The internship/co-op term the role is for. Use the title first, then the text. If the posting offers several terms (e.g. "Fall 2026 or Spring 2027"), use the **first** one listed. `null` for non-internship roles or when no term is stated. "Year-round"/"part-time during the school year" → `null`. |
| `term_year` | an integer year, or `null` | The year that goes with `term_season` (e.g. "Summer 2027" → 2027). `null` if the season has no year. |
| `degree_levels` | a list drawn from `"bachelor"`, `"master"`, `"phd"`, or `null` | Degree programs the posting says it is **open to** (currently enrolled in, or required). "BS/MS in CS" → `["bachelor","master"]`. "Undergraduate" → `["bachelor"]`. "PhD students" → `["phd"]`. "Graduate students" → `["master","phd"]`. Associate's/high-school/MBA → ignore. `null` when no degree level is stated. Preferred-only mentions ("PhD preferred") do **not** count unless no other level is given — then list only what is required. |
| `grad_year_min`, `grad_year_max` | integers or `null` | Expected graduation years the posting requires ("graduating between Dec 2026 and June 2027" → 2026, 2027; "graduating in 2027" → 2027, 2027). `null` when not stated. |
| `us_citizen_required` | `true`, `false`, `null` | `true` only when U.S. **citizenship** is required (including "must be a U.S. citizen to obtain a clearance"). `false` when the posting explicitly says citizenship isn't required or that it sponsors/welcomes non-citizens. Otherwise `null`. Work authorization ("authorized to work in the U.S.") is **not** citizenship. |
| `us_person_required` | `true`, `false`, `null` | `true` when the role requires being a **U.S. person** (citizen, green-card holder, refugee/asylee) under ITAR/EAR export-control rules, or says access to export-controlled information requires U.S.-person status. `true` also when citizenship is required (a citizen is a U.S. person). Otherwise `null` unless explicitly `false`. |
| `clearance_required` | `true`, `false`, `null` | `true` when the role requires holding a security clearance **or** being able to obtain one (e.g. "must be able to obtain and maintain a Secret clearance"). "Clearance a plus/preferred" → `null`. |
| `workplace_type` | `"onsite"`, `"hybrid"`, `"remote"`, `null` | What the posting says about where the work happens. Use `ats_hints` if present and consistent with the text; the text wins on conflict. "In office 4 days a week" → hybrid. "In-person"/"on-site" → onsite. `null` if unstated. |
| `country` | ISO 3166-1 alpha-2 (e.g. `"US"`, `"GB"`, `"DE"`), or `null` | The country of the role's location (from `location`, `ats_hints` or the text). Several countries → the first listed. Remote with no country → `null`. |

Label independently: don't look at any extraction code in the repository, and don't
consult other labelers' files.

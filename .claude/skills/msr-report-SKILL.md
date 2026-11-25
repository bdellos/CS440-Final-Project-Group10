---
name: msr-report
description: Reporting standards for the GitSkills MSR study. Use when producing research tables, figures, descriptive statistics, cross-tabs, agreement results, codebook-evolution visuals, or paper-ready summaries from the project database. Keeps outputs reproducible, accurately denominated, accessible, and consistent with the study design.
---

# MSR report: tables and figures

Use this skill whenever preparing a table, figure, chart, or quantitative result for the GitSkills research paper. The goal is to make every result traceable to the data and understandable without guessing what a count, percentage, category, or comparison means.

## 1. Non-negotiable reporting rules

1. **Never invent results.** Every number must come from a reproducible query, script, or explicitly supplied result. If the data needed for a result are absent, report the gap rather than estimating it.
2. **Preserve the study design.** This project has two distinct taxonomies: purpose (what a skill codifies) and context (what kind of repository contains it). Do not merge them into one classification.
3. **Name the population and denominator.** State whether a result concerns the full dataset, a sample, a held-out set, a language-filtered subset, or completed annotations only. Give the numerator and denominator for percentages.
4. **Keep raters and runs distinct.** Identify the rater, run purpose, taxonomy, sample, and codebook version for every comparison. Do not compare labels from different codebook versions as though their category keys were equivalent.
5. **Make analysis reproducible.** Save the query or script that produced each result, record the database snapshot or input files, and keep generated artifacts in the analysis directory. Never modify the source dataset or labels database while analyzing it.
6. **Use neutral language.** Describe what the data show. Do not turn association into causation or claim that a sample represents the full population unless the sampling design supports that inference.
7. **Respect privacy and provenance.** Do not expose secrets, personal data, or unnecessary repository/user identifiers in the paper. Attribute dataset and external sources in the paper's references.

## 2. Tables

### Structure

- Give each table a sequential number and a concise, informative title/caption. Follow the target venue's template if it specifies caption placement or typography; otherwise put the title above the table.
- Make the table understandable on its own. Expand abbreviations in a note, define unusual measures, identify the unit of analysis, and state the denominator.
- Use descriptive row and column headings. Include units in headings where useful.
- Align numeric values by decimal place where practical. Use consistent precision within a column; do not show more decimal places than the data justify.
- Prefer counts with percentages, formatted as n (x.x%), when the denominator is meaningful. State the denominator in the column heading or a table note.
- Use a dash only for a true zero or not-applicable value, and explain the convention. Do not use blank cells ambiguously.
- Avoid vertical rules and decorative shading unless the venue template requires them. Use whitespace and restrained horizontal rules to communicate structure.
- Do not split a small table across pages. If a wide table is unavoidable, simplify columns or use the venue's landscape/wide-table mechanism rather than shrinking text until it is unreadable.

### Tables appropriate to this study

- **Dataset/sample profile:** report the number of repositories, skills, sampled items, excluded items, and relevant strata. Distinguish unique repositories from skill files; one repository may contribute multiple skills.
- **Purpose taxonomy:** report category key/name, definition summary if needed, number of assigned labels, and percentage with the denominator stated. Because annotations may be multi-label, category percentages can sum to more than 100%; state this explicitly.
- **Context taxonomy:** report repository-context categories with their own denominator. Do not use skill counts as the denominator if the unit is repository.
- **Agreement:** identify the two raters/runs, sample, taxonomy, codebook version, number of paired items, missing items, observed agreement, and Cohen's kappa with its uncertainty interval if calculated. State how multi-label annotations were converted into comparison units. Do not report a single multiclass kappa for multi-label sets without defining and justifying the transformation.
- **Purpose by context:** provide counts and row/column percentages with the conditioning direction stated. If a skill can have multiple purpose labels, disclose whether each skill contributes to multiple cells or whether the analysis uses a primary label only.
- **Codebook evolution:** report the version/round, category additions, merges, retirements, or other changes using the actual version history. Do not infer a change from filenames alone.

### Table checks

Before finalizing, verify:

- Totals reconcile with the underlying query and stated inclusion/exclusion rules.
- Percentages use the stated denominator and rounding does not imply false precision.
- Multi-label counting is explained wherever totals can exceed the number of items.
- Missing, excluded, pending, and unclassified records are not silently treated as zero.
- Category labels match the relevant frozen codebook exactly.
- The caption and notes define abbreviations, units, and any non-obvious calculation.

## 3. Figures

### General design

- Give each figure a sequential number and a descriptive caption. Follow venue-specific caption placement; otherwise put the caption below the figure.
- Use a clear axis title and units for every quantitative axis. Start bar-chart axes at zero unless a justified alternative is clearly marked.
- Prefer direct labels or a readable legend. Keep category names legible; wrap or shorten labels only if the mapping remains unambiguous.
- Use a colorblind-safe palette and ensure the figure remains interpretable in grayscale. Do not rely on color alone to distinguish groups; use labels, shapes, line styles, or patterns as needed.
- Avoid 3-D effects, perspective, decorative backgrounds, unnecessary gridlines, and chart junk.
- Use consistent category ordering and colors across figures. If categories have a meaningful codebook order, preserve it; otherwise state the sorting rule (for example, descending frequency).
- Include sample sizes and identify the population represented. Do not plot percentages without explaining the denominator.
- Export a vector format (PDF or SVG) for line art and charts when the paper workflow supports it. Use sufficiently high-resolution raster output only when vector export is unavailable or the figure contains raster imagery.
- Provide a concise text description or alt text that communicates the main visual comparison for accessibility.

### Figures appropriate to this study

- **Category frequencies:** horizontal bars are usually preferable for long category names. Show counts and, where useful, percentages. For multi-label data, label the measure as label assignments or items with category, not as mutually exclusive shares.
- **Purpose × context cross-tab:** use a heatmap only when cell values remain legible and the color scale is explained. State whether cells contain counts, row percentages, or column percentages. Consider a table instead when exact values matter more than pattern recognition.
- **Agreement:** use a confusion/agreement matrix only when the category mapping and multi-label treatment are explicit. Keep missing and proposed-new labels visible as appropriate rather than silently dropping them.
- **Codebook evolution:** a timeline or version-by-category matrix may show when categories were introduced, merged, or retired. Base it on committed codebook versions and document the event definitions.
- **Sampling overview:** a flow diagram may show the source population, filtering, deduplication, sampling, exclusions, and final analyzed set. Every transition must reconcile numerically.

### Figure checks

Before finalizing, verify:

- Every plotted value can be regenerated from saved analysis code or a documented query.
- Axes, units, denominators, sample sizes, and color scales are clear.
- No category or data point disappears because of sorting, truncation, or filtering without disclosure.
- The figure is readable at the size it will appear in the paper.
- Colors and symbols are consistent with related figures and remain distinguishable in grayscale.
- Caption, legend, and alt text describe the actual data, not an interpretation unsupported by the analysis.

## 4. Statistical reporting for this project

- Report descriptive counts before interpreting patterns. Give the number of observations behind every percentage or estimate.
- For Cohen's kappa, report the observed agreement and kappa, the compared sample size, the two raters, taxonomy, codebook version, and the method used to handle multi-label outputs. Include a confidence interval when the analysis computes one; do not invent one when it does not.
- Do not interpret kappa using universal qualitative labels (such as “moderate” or “substantial”) without citing and justifying the chosen interpretation scheme. Prefer the numeric estimate and its interval.
- Keep exact agreement, category-level agreement, and chance-corrected agreement distinct. They answer different questions.
- When reporting a cross-tab, state whether percentages are conditioned on rows or columns. Do not describe a cross-sectional association as a causal effect.
- When reporting language-specific results, show the language counts and disclose any English-only restriction or translation/spot-check procedure relevant to interpretation.
- Report missing labels, unfinished runs, proposals, and excluded items where they affect the denominator or interpretation.

## 5. Workflow for producing a paper artifact

1. **Identify the question.** Write down the research question, unit of analysis (skill, repository, annotation, label assignment), population/sample, taxonomy, and comparison.
2. **Check provenance.** Record the database path/snapshot, sample name, run IDs, codebook version(s), and any filters. For codebook evolution, use the actual Git history.
3. **Inspect completeness.** Check run status and missing annotations before computing results. Never treat an unfinished run as a complete dataset.
4. **Compute from read-only inputs.** Open the labels database read-only. Keep analysis scripts and generated tables/figures in the analysis directory. Do not update labels, codebooks, samples, or source dataset files during analysis.
5. **Validate the result.** Reconcile totals, denominators, and percentages independently. Check edge cases such as multiple labels per item, proposals, missing annotations, and duplicate repositories.
6. **Create the artifact.** Apply the table or figure conventions above and use the paper venue's official template when known. If the venue format is not specified, use the defaults in this skill and record that choice.
7. **Document it.** Give the artifact a stable filename and include a short note or script comment describing its source query, inputs, filters, and generation command.
8. **Review it as a reader.** Confirm that someone who has not seen the analysis code can understand the caption, axes, units, denominator, and main comparison without guessing.

## 6. Naming and organization

Store paper-ready analysis artifacts under the repository's analysis directory. Use stable, descriptive, lowercase filenames with an artifact type and topic, for example:

- table_dataset_profile.csv
- table_purpose_frequencies.csv
- table_agreement.csv
- figure_purpose_frequencies.pdf
- figure_purpose_context_heatmap.pdf
- figure_codebook_evolution.pdf

Keep generation scripts alongside the artifacts or in a clearly named scripts subdirectory within analysis. Do not overwrite raw inputs. If a result changes after a codebook, sample, or run changes, regenerate it and preserve enough provenance to explain the difference.

## 7. Limits and uncertainty

The repository plan describes the intended research questions and candidate analyses, but the final venue template, final codebook versions, held-out results, and statistical estimates may not yet exist. Do not assume them. Use placeholders only in drafts, label them clearly as placeholders, and replace them with verified results before submission. If the target venue imposes different formatting rules, its current author instructions take precedence over the visual defaults in this skill.

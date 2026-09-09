# montana-pac-spending-2026

Run the filter with Python 3.9 or newer:

```sh
python3 filter_pac_data.py
```

The script uses only the Python standard library; no dependencies or virtual
environment are required. It reads `input/pac-donations.csv` and writes:

- `output/montana-campaign-donations.csv`: donations received by the Montana
  candidates listed in `input/montana-candidates.json`. Match CSV `CAND_ID` to
  JSON `candidate_id`, or CSV `OTHER_ID` to JSON `candidate_pcc_id`. Matching
  either ID includes the row once, regardless of its `STATE`.
- `output/montana-donators.csv`: donations made by leadership PACs sponsored by
  those same listed politicians, regardless of the recipient. Identify PACs
  using `Sponsor Name` matched to JSON `candidate_name` and a populated
  `Leadership Pacs` field, then include all rows with those PACs' `CMTE_ID` values.

Both outputs keep only donations from traditional PACs by default. The donating
`CMTE_ID` is joined to `CMTE_TP` in the local FEC 2026 committee master snapshot,
`input/fec-committee-master-2026.zip`. The allowed types are `N` (nonqualified
PAC) and `Q` (qualified PAC). Super PACs (`O`), hybrids (`V`/`W`), single-candidate
independent expenditure committees (`U`), candidate committees, party committees,
and other non-PAC filers are excluded. The CSV's `Committee Designation` is a
different field: designation `U` means unauthorized and does not identify a
Super PAC. See the [FEC committee type definitions](https://www.fec.gov/campaign-finance-data/committee-type-code-descriptions/)
and [master file layout](https://www.fec.gov/campaign-finance-data/committee-master-file-description/).

The snapshot was downloaded on September 9, 2026 from the
[FEC 2026 committee master download](https://www.fec.gov/files/bulk-downloads/2026/cm26.zip).
Its source, retrieval timestamp, and SHA-256 checksum are recorded in
`input/fec-committee-master-2026.metadata.json`. Reruns use the local ZIP without
network access. These are snapshot classifications, not classifications as of
each transaction date. Download a fresh ZIP and pass `--committee-master path/to/cm26.zip`
to use an updated snapshot. If a Montana-related donor's classification is
missing, filtering stops before replacing outputs rather than guessing its type.

To include hybrid PACs as well as traditional PACs, run:

```sh
python3 filter_pac_data.py --committee-types N Q V W
python3 find-top-spenders.py
```

Sponsor matching uses the full name, ignoring capitalization and repeated
whitespace. It does not guess nicknames or match surnames alone. Name variants
that differ in other ways need to be reconciled before they will match.

The candidate JSON contains the race slugs, names, and IDs extracted from the
supplied JSON. Records without an ID are skipped when building the matching set.
The full original JSON can also be supplied with `--candidates path/to/file.json`.

Both outputs preserve all input columns, field values, row order, and duplicate
records. The filters run independently, so a row can appear in both files.
Rerunning the script replaces the output files. No numeric conversion is applied.

The default filter produces 699 donations to listed candidates and 61 donations
by their leadership PACs: Accountable Leaders for Montana's Excellence (Kurt
Alme), Conservative Service Action Results (CSAR) PAC (Troy Downing), and The
Montana Way PAC (Christi Jacobsen). Five of the 699 incoming donations match
only the campaign committee ID; their candidate ID is missing or differs from
the supplied candidate ID.

Use `--help` for input and output path options. Default paths are relative to the
script's directory; explicitly supplied relative paths use the working directory.

To generate spending rankings after filtering, run:

```sh
python3 find-top-spenders.py
```

This script also uses only the standard library. It writes seven reports, sorted
by cumulative `TRANSACTION_AMT` from highest to lowest:

- `analysis/leadership-funds.csv`: leadership PAC donations into Montana races
  from `output/montana-campaign-donations.csv`, grouped by donating `CMTE_ID`.
  Include only rows with a populated `Leadership Pacs` value other than `#N/A`.
  Sponsors can be from any state; missing sponsor names remain `#N/A`. Columns:
  `CMTE_ID,LEADERSHIP_PAC,SPONSOR_NAME,TOTAL_TRANSACTIONS`.
- `analysis/pacs.csv`: totals from `output/montana-campaign-donations.csv`,
  including only rows where `Leadership Pacs` is `#N/A` and `PAC Name` is
  populated and not `#N/A`, grouped by exact `PAC Name`.
  These totals cover transactions involving the
  listed Montana candidates, not each PAC's nationwide spending. Columns:
  `CMTE_ID,PAC_NAME,SPONSOR_NAME,TOTAL_TRANSACTIONS`.
- `analysis/by-candidate.csv`: totals from `output/montana-campaign-donations.csv`,
  grouped by candidate ID. Columns: `CAND_ID,NAME,TOTAL_RECEIVED`.
  `NAME` is the candidate's name from the JSON, since the source CSV's `NAME`
  can also identify vendors or other payees. Candidate IDs are resolved against
  the supplied JSON, falling back to the campaign committee's `OTHER_ID` when
  the source candidate ID is missing or unrecognized.

Four additional reports use the same columns and leadership-value filter as
`leadership-funds.csv`, but total only transactions for the specified candidate:

- `analysis/leadership-funds-to-bodnar.csv`: Seth Bodnar (`S6MT00287`).
- `analysis/leadership-funds-to-alme.csv`: Kurt Alme (`S6MT00295`).
- `analysis/leadership-fund-to-downing.csv`: Troy Downing (`H4MT02098`).
- `analysis/leadership-fund-to-flint.csv`: Aaron Flint (`H6MT01152`).

These reports use the same candidate ID resolution and campaign committee
fallback as `by-candidate.csv`. Each PAC's total includes only its transactions
for that candidate. A report with no matches contains just the column headers.

All rankings use `--campaign-input` (default:
`output/montana-campaign-donations.csv`). The leadership report currently covers
178 incoming transactions from 115 leadership PACs, totaling $622,700.
The PAC report covers 521 transactions from 271 PAC names, totaling $1,248,335.
The two reports classify each transaction using its `Leadership Pacs` value,
with surrounding whitespace removed. No transaction appears in both reports;
committee designation does not override this split. Blank leadership values
are omitted from both PAC rankings. Candidate totals still include every input
transaction. In particular, Commander Zinke Leadership Fund's three donations
are in `pacs.csv` because their `Leadership Pacs` value is `#N/A`.

`TOTAL_TRANSACTIONS` is a dollar sum, not a row count. Amounts use decimal
arithmetic and are written with two decimal places. All transaction types,
duplicates, and negative amounts are included as supplied; the reports do not
separate direct committee receipts from other candidate-related spending.
With the current input and default committee filter, all retained transactions
are `24K` (contributions to nonaffiliated committees) or `24Z` (in-kind
contributions). The filter classifies the donor, not the transaction; a future
input or the hybrid option can still include independent expenditures. See the
[FEC transaction definitions](https://www.fec.gov/campaign-finance-data/transaction-type-code-descriptions/).
Ties are sorted by the grouping key. If a PAC group has multiple IDs or sponsor
names, distinct values are joined with `; `; missing labels appear as `#N/A`.
Rerunning replaces the reports. Use `--help` to override input and output paths.

Analysis reports format candidate `NAME` and `SPONSOR_NAME` values for graphics:
`BODNAR, SETH` becomes `Seth Bodnar`. Person names use given-name-first order and
mixed case; courtesy titles are removed, and suffixes follow the surname.
Middle names and initials are retained. PAC names and the source data retain
their original formatting. This display formatting does not change ID matching,
grouping, amounts, or ranking order.

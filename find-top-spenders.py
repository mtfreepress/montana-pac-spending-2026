"""Rank PAC and leadership PAC donations into Montana races by amount."""

import argparse
import csv
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LEADERSHIP_CANDIDATE_REPORTS = {
    "S6MT00287": "leadership-funds-to-bodnar.csv",
    "S6MT00295": "leadership-funds-to-alme.csv",
    "H4MT02098": "leadership-fund-to-downing.csv",
    "H6MT01152": "leadership-fund-to-flint.csv",
}
PAC_CANDIDATE_REPORTS = {
    candidate_id: "pac-to-" + filename.rsplit("-to-", 1)[1]
    for candidate_id, filename in LEADERSHIP_CANDIDATE_REPORTS.items()
}
PAC_CANDIDATE_REPORTS["H6MT01137"] = "pac-to-forstag.csv"
SENATE_CANDIDATES = {
    "S6MT00295": ("Kurt Alme", "R"),
    "S6MT00287": ("Seth Bodnar", "I"),
    "S6MT00253": ("Alani Bankhead", "D"),
}
OVERALL_CANDIDATE_PARTIES = {
    "H6MT01152": "R",  # Aaron Flint
    "H4MT02098": "R",  # Troy Downing
    "S6MT00295": "R",  # Kurt Alme
    "S6MT00253": "D",  # Alani Bankhead
    "H6MT01137": "D",  # Samuel Kelley Forstag
    "H6MT02150": "D",  # Brian James Miller
    "S6MT00287": "I",  # Seth Bodnar
    "H6MT02168": "I",  # Michael D. Eisenhauer
    "H6MT01145": "D",  # Ryan Busse
    "H6MT01160": "R",  # Christi Jacobsen
}
GENERAL_CANDIDATE_PARTIES = {
    "H6MT01137": "D",  # Sam Forstag
    "H6MT01152": "R",  # Aaron Flint
    "S6MT00295": "R",  # Kurt Alme
    "H4MT02098": "R",  # Troy Downing
    "S6MT00287": "I",  # Seth Bodnar
    "H6MT02168": "I",  # Michael Eisenhauer
    "S6MT00261": "L",  # Kyle Austin
}
PARTY_TOTAL_CANDIDATE_PARTIES = {
    **OVERALL_CANDIDATE_PARTIES,
    **GENERAL_CANDIDATE_PARTIES,
    "H6MT01103": "D",  # Russell Cleveland
    "H6MT02143": "D",  # Sam Lux
    "H0MT00116": "D",  # Matthew Rains
    "H2MT02084": "R",  # Albert Olszewski
}


def format_person_name(name):
    """Display FEC person names in given-name-first order for graphics."""
    name = " ".join(name.split())
    if name in ("", "#N/A"):
        return name
    if "," in name:
        surname, given = name.split(",", 1)
        tokens = given.replace(",", " ").split()
    else:
        surname = ""
        tokens = name.split()
    titles = {"MR", "MRS", "MS", "DR", "SEN", "REP", "HON"}
    tokens = [token for token in tokens if token.upper().rstrip(".") not in titles]
    suffixes = []
    while tokens and tokens[-1].upper().rstrip(".") in {"JR", "SR", "II", "III", "IV"}:
        suffixes.insert(0, tokens.pop())
    words = tokens + surname.split() + suffixes
    formatted = []
    for word in words:
        if word.upper().rstrip(".") in {"II", "III", "IV"}:
            formatted.append(word.upper())
        elif word.upper() == "LAHOOD":
            formatted.append("LaHood")
        else:
            formatted.append(re.sub(r"\bMc([a-z])", lambda match: "Mc" + match[1].upper(), word.title()))
    return " ".join(formatted)


def read_transactions(path, required):
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        missing = (set(required) | {"TRANSACTION_AMT"}) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: missing columns {', '.join(sorted(missing))}")
        rows = []
        for row in reader:
            try:
                amount = Decimal(row["TRANSACTION_AMT"])
            except (InvalidOperation, TypeError):
                raise ValueError(f"{path}, line {reader.line_num}: invalid TRANSACTION_AMT")
            if not amount.is_finite():
                raise ValueError(f"{path}, line {reader.line_num}: nonfinite TRANSACTION_AMT")
            rows.append((row, amount))
    return rows


def add_transaction(groups, key, labels, amount):
    if key not in groups:
        groups[key] = {"total": Decimal("0"), "labels": {name: set() for name in labels}}
    group = groups[key]
    group["total"] += amount
    for name, value in labels.items():
        if value and value.strip() not in ("", "#N/A"):
            group["labels"][name].add(value.strip())


def write_ranking(path, groups, fields, total_field):
    ranked = sorted(groups.items(), key=lambda item: (-item[1]["total"], item[0]))
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields + [total_field])
        writer.writeheader()
        for _, group in ranked:
            row = {
                field: "; ".join(
                    format_person_name(value) if field in {"NAME", "SPONSOR_NAME"} else value
                    for value in sorted(group["labels"][field])
                ) or "#N/A"
                for field in fields
            }
            row[total_field] = format(group["total"], ".2f")
            writer.writerow(row)
    print(f"{path}: {len(ranked):,} rows")


def write_top_twenty_senate(path, groups):
    """Rank committees by combined spending, retaining each recipient's amount."""
    totals = {}
    for (committee_id, _), group in groups.items():
        totals[committee_id] = totals.get(committee_id, Decimal("0")) + group["total"]
    top_ids = sorted(totals, key=lambda committee_id: (-totals[committee_id], committee_id))[:20]
    fields = ["CMTE_ID", "PAC", "SPONSOR_NAME", "AMOUNT", "CANDIDATE", "PARTY"]
    count = 0
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        for committee_id in top_ids:
            for candidate_id in sorted(SENATE_CANDIDATES):
                group = groups.get((committee_id, candidate_id))
                if group is None:
                    continue
                name, party = SENATE_CANDIDATES[candidate_id]
                writer.writerow({
                    "CMTE_ID": committee_id,
                    "PAC": "; ".join(sorted(group["labels"]["PAC"])) or "#N/A",
                    "SPONSOR_NAME": "; ".join(
                        format_person_name(value)
                        for value in sorted(group["labels"]["SPONSOR_NAME"])
                    ) or "0",
                    "AMOUNT": format(group["total"], ".2f"),
                    "CANDIDATE": name,
                    "PARTY": party,
                })
                count += 1
    print(f"{path}: {count:,} rows ({len(top_ids)} PACs)")


def write_top_overall(path, groups, limit):
    """Select the top committees across races and split amounts by party."""
    totals = {}
    for (committee_id, _), group in groups.items():
        totals[committee_id] = totals.get(committee_id, Decimal("0")) + group["total"]
    top_ids = sorted(totals, key=lambda committee_id: (-totals[committee_id], committee_id))[:limit]
    fields = ["CMTE_ID", "PAC", "SPONSOR_NAME", "AMOUNT", "PARTY"]
    count = 0
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        for committee_id in top_ids:
            for party in sorted(set(OVERALL_CANDIDATE_PARTIES.values())):
                group = groups.get((committee_id, party))
                if group is None:
                    continue
                writer.writerow({
                    "CMTE_ID": committee_id,
                    "PAC": "; ".join(sorted(group["labels"]["PAC"])) or "#N/A",
                    "SPONSOR_NAME": "; ".join(
                        format_person_name(value)
                        for value in sorted(group["labels"]["SPONSOR_NAME"])
                    ) or "0",
                    "AMOUNT": format(group["total"], ".2f"),
                    "PARTY": party,
                })
                count += 1
    print(f"{path}: {count:,} rows ({len(top_ids)} PACs)")


def write_party_totals(path, totals):
    """Write dollar totals by recipient party, largest amount first."""
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=["party", "amount"])
        writer.writeheader()
        for party, amount in sorted(totals.items(), key=lambda item: (-item[1], item[0])):
            writer.writerow({"party": party, "amount": format(amount, ".2f")})
    print(f"{path}: {len(totals)} rows")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--campaign-input", type=Path,
        default=ROOT / "output/montana-campaign-donations.csv",
    )
    parser.add_argument(
        "--candidates", type=Path, default=ROOT / "input/montana-candidates.json"
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "analysis")
    args = parser.parse_args()

    try:
        campaign_rows = read_transactions(
            args.campaign_input,
            ["CMTE_ID", "PAC Name", "Sponsor Name", "CAND_ID", "OTHER_ID",
             "Leadership Pacs"],
        )
        with args.candidates.open(encoding="utf-8") as source:
            candidates = [
                candidate
                for race in json.load(source)
                for candidate in race["finances"]["results"]
                if candidate.get("candidate_id")
            ]
        by_id = {candidate["candidate_id"]: candidate for candidate in candidates}
        by_committee = {
            candidate["candidate_pcc_id"]: candidate
            for candidate in candidates if candidate.get("candidate_pcc_id")
        }

        leadership = {}
        leadership_by_candidate = {candidate_id: {} for candidate_id in LEADERSHIP_CANDIDATE_REPORTS}
        pacs_by_candidate = {candidate_id: {} for candidate_id in PAC_CANDIDATE_REPORTS}
        combined_by_candidate = {candidate_id: {} for candidate_id in LEADERSHIP_CANDIDATE_REPORTS}
        pacs = {}
        senate = {}
        overall = {}
        recipients = {}
        party_totals = {party: Decimal("0") for party in GENERAL_CANDIDATE_PARTIES.values()}
        general_party_totals = party_totals.copy()
        for row, amount in campaign_rows:
            candidate = by_id.get(row["CAND_ID"]) or by_committee.get(row["OTHER_ID"])
            if candidate is None:
                raise ValueError(
                    f"Cannot identify candidate for CAND_ID={row['CAND_ID']!r}, "
                    f"OTHER_ID={row['OTHER_ID']!r} in {args.campaign_input}"
                )
            leadership_name = row["Leadership Pacs"].strip()
            pac_name = row["PAC Name"].strip()
            is_leadership = leadership_name not in ("", "#N/A")
            is_pac = leadership_name == "#N/A" and pac_name not in ("", "#N/A")
            candidate_id = candidate["candidate_id"]
            recipient_party = PARTY_TOTAL_CANDIDATE_PARTIES.get(candidate_id)
            if recipient_party is None:
                raise ValueError(
                    f"Missing party label for {candidate['candidate_name']} ({candidate_id}); "
                    "add it to PARTY_TOTAL_CANDIDATE_PARTIES before generating reports"
                )
            party_totals[recipient_party] += amount
            if candidate_id in GENERAL_CANDIDATE_PARTIES:
                general_party_totals[recipient_party] += amount
            if is_leadership or is_pac:
                donor_labels = {
                    "CMTE_ID": row["CMTE_ID"],
                    "PAC_NAME": leadership_name if is_leadership else pac_name,
                    "SPONSOR_NAME": row["Sponsor Name"],
                }
                if candidate_id in combined_by_candidate:
                    add_transaction(
                        combined_by_candidate[candidate_id], row["CMTE_ID"], donor_labels, amount
                    )
                if is_pac and candidate_id in pacs_by_candidate:
                    add_transaction(
                        pacs_by_candidate[candidate_id], row["CMTE_ID"], donor_labels, amount
                    )
            party = OVERALL_CANDIDATE_PARTIES.get(candidate["candidate_id"])
            if party and (is_leadership or is_pac):
                add_transaction(overall, (row["CMTE_ID"], party), {
                    "PAC": leadership_name if is_leadership else pac_name,
                    "SPONSOR_NAME": row["Sponsor Name"],
                }, amount)
            if candidate["candidate_id"] in SENATE_CANDIDATES and (is_leadership or is_pac):
                add_transaction(senate, (row["CMTE_ID"], candidate["candidate_id"]), {
                    "PAC": leadership_name if is_leadership else pac_name,
                    "SPONSOR_NAME": row["Sponsor Name"],
                }, amount)
            if leadership_name not in ("", "#N/A"):
                labels = {
                    "CMTE_ID": row["CMTE_ID"],
                    "LEADERSHIP_PAC": leadership_name,
                    "SPONSOR_NAME": row["Sponsor Name"],
                }
                add_transaction(leadership, row["CMTE_ID"], labels, amount)
                candidate_id = candidate["candidate_id"]
                if candidate_id in leadership_by_candidate:
                    add_transaction(
                        leadership_by_candidate[candidate_id], row["CMTE_ID"], labels, amount
                    )
            elif leadership_name == "#N/A" and row["PAC Name"].strip() not in ("", "#N/A"):
                add_transaction(pacs, row["PAC Name"], {
                    "CMTE_ID": row["CMTE_ID"],
                    "PAC_NAME": row["PAC Name"],
                    "SPONSOR_NAME": row["Sponsor Name"],
                }, amount)
            add_transaction(recipients, candidate["candidate_id"], {
                "CAND_ID": candidate["candidate_id"],
                "NAME": candidate["candidate_name"],
            }, amount)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_party_totals(args.output_dir / "total-donations-by-party.csv", party_totals)
    write_party_totals(
        args.output_dir / "total-donations-by-party-general-only.csv", general_party_totals
    )
    write_top_twenty_senate(args.output_dir / "topTwentySenate.csv", senate)
    write_top_overall(args.output_dir / "topTwentyOverall.csv", overall, 20)
    write_top_overall(args.output_dir / "top-50-spenders.csv", overall, 50)
    write_ranking(
        args.output_dir / "leadership-funds.csv", leadership,
        ["CMTE_ID", "LEADERSHIP_PAC", "SPONSOR_NAME"], "TOTAL_TRANSACTIONS",
    )
    for candidate_id, filename in LEADERSHIP_CANDIDATE_REPORTS.items():
        write_ranking(
            args.output_dir / filename, leadership_by_candidate[candidate_id],
            ["CMTE_ID", "LEADERSHIP_PAC", "SPONSOR_NAME"], "TOTAL_TRANSACTIONS",
        )
        candidate_slug = filename.rsplit("-to-", 1)[1]
        write_ranking(
            args.output_dir / f"pac-and-leadership-to-{candidate_slug}",
            combined_by_candidate[candidate_id],
            ["CMTE_ID", "PAC_NAME", "SPONSOR_NAME"], "TOTAL_TRANSACTIONS",
        )
    for candidate_id, filename in PAC_CANDIDATE_REPORTS.items():
        write_ranking(
            args.output_dir / filename, pacs_by_candidate[candidate_id],
            ["CMTE_ID", "PAC_NAME", "SPONSOR_NAME"], "TOTAL_TRANSACTIONS",
        )
    write_ranking(
        args.output_dir / "pacs.csv", pacs,
        ["CMTE_ID", "PAC_NAME", "SPONSOR_NAME"], "TOTAL_TRANSACTIONS",
    )
    write_ranking(
        args.output_dir / "by-candidate.csv", recipients,
        ["CAND_ID", "NAME"], "TOTAL_RECEIVED",
    )


if __name__ == "__main__":
    main()

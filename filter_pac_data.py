"""Find donations to Montana candidates and by their leadership PACs."""

import argparse
import csv
import io
import json
import zipfile
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
COMMITTEE_MASTER_URL = "https://www.fec.gov/files/bulk-downloads/2026/cm26.zip"


def load_committee_types(path):
    """Read CMTE_ID (column 1) and CMTE_TP (column 10) from the FEC master."""
    types = {}
    with zipfile.ZipFile(path) as archive:
        with archive.open("cm.txt") as raw:
            for row in csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig"), delimiter="|"):
                if len(row) != 15:
                    raise ValueError("Expected 15 columns in the FEC committee master file")
                if row[0] in types:
                    raise ValueError(f"Duplicate committee ID in master file: {row[0]}")
                types[row[0]] = row[9]
    if not types:
        raise ValueError("The FEC committee master file is empty")
    return types


def normalize_name(name):
    """Ignore capitalization and repeated whitespace, but require the full name."""
    return " ".join(name.upper().split())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "input/pac-donations.csv")
    parser.add_argument(
        "--candidates", type=Path, default=ROOT / "input/montana-candidates.json"
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output")
    parser.add_argument(
        "--committee-master", type=Path,
        default=ROOT / "input/fec-committee-master-2026.zip",
        help="Local FEC committee master ZIP containing cm.txt",
    )
    parser.add_argument(
        "--committee-types", nargs="+", choices=("N", "Q", "V", "W"),
        default=["N", "Q"],
        help="Donor committee types to keep: N/Q traditional PACs; V/W hybrid PACs",
    )
    args = parser.parse_args()
    try:
        committee_types = load_committee_types(args.committee_master)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        parser.error(
            f"Cannot read committee types: {error}. "
            f"Download {COMMITTEE_MASTER_URL} to {args.committee_master}."
        )
    allowed_types = set(args.committee_types)

    with args.candidates.open(encoding="utf-8") as source:
        races = json.load(source)
    candidates = [
        candidate
        for race in races
        for candidate in race["finances"]["results"]
    ]
    candidate_ids = {
        candidate["candidate_id"]
        for candidate in candidates
        if candidate.get("candidate_id")
    }
    committee_ids = {
        candidate["candidate_pcc_id"]
        for candidate in candidates
        if candidate.get("candidate_pcc_id")
    }
    candidate_names = {
        normalize_name(candidate["candidate_name"])
        for candidate in candidates
        if candidate.get("candidate_name")
    }
    if not candidate_ids and not committee_ids:
        parser.error(f"No candidate or campaign committee IDs found in {args.candidates}")
    if not candidate_names:
        parser.error(f"No candidate names found in {args.candidates}")

    campaign_path = args.output_dir / "montana-campaign-donations.csv"
    donators_path = args.output_dir / "montana-donators.csv"
    if args.input.resolve() in (campaign_path.resolve(), donators_path.resolve()):
        parser.error("The input file cannot also be an output file.")

    total = campaign_count = donators_count = 0
    with args.input.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        required = {"CAND_ID", "OTHER_ID", "CMTE_ID", "Sponsor Name", "Leadership Pacs"}
        if not required.issubset(reader.fieldnames or []):
            parser.error(f"Input must contain columns: {', '.join(sorted(required))}")

        # Identify each leadership PAC by its sponsor, then include all of that
        # committee's transactions even if another row omits the sponsor name.
        leadership_pacs = {}
        unknown_committees = set()
        for row in reader:
            is_leadership_pac = (
                normalize_name(row["Sponsor Name"]) in candidate_names
                and row["Leadership Pacs"].strip() not in ("", "#N/A")
                and row["CMTE_ID"]
            )
            is_candidate_donation = (
                row["CAND_ID"] in candidate_ids or row["OTHER_ID"] in committee_ids
            )
            if (is_leadership_pac or is_candidate_donation) and not committee_types.get(row["CMTE_ID"]):
                unknown_committees.add(row["CMTE_ID"])
            if is_leadership_pac:
                leadership_pacs[row["CMTE_ID"]] = (
                    row["Sponsor Name"], row["Leadership Pacs"]
                )
        if unknown_committees:
            parser.error(
                "Missing committee types for Montana-related donors: "
                + ", ".join(sorted(unknown_committees))
                + ". Refresh the committee master file before filtering."
            )
        source.seek(0)
        reader = csv.DictReader(source)
        excluded_campaign_types = Counter()
        excluded_leadership_types = Counter()
        args.output_dir.mkdir(parents=True, exist_ok=True)
        with (
            campaign_path.open("w", encoding="utf-8", newline="") as campaign_file,
            donators_path.open("w", encoding="utf-8", newline="") as donators_file,
        ):
            campaigns = csv.DictWriter(campaign_file, fieldnames=reader.fieldnames)
            donators = csv.DictWriter(donators_file, fieldnames=reader.fieldnames)
            campaigns.writeheader()
            donators.writeheader()
            for row in reader:
                total += 1
                donor_type = committee_types.get(row["CMTE_ID"])
                if row["CAND_ID"] in candidate_ids or row["OTHER_ID"] in committee_ids:
                    if donor_type in allowed_types:
                        campaigns.writerow(row)
                        campaign_count += 1
                    else:
                        excluded_campaign_types[donor_type] += 1
                if row["CMTE_ID"] in leadership_pacs:
                    if donor_type in allowed_types:
                        donators.writerow(row)
                        donators_count += 1
                    else:
                        excluded_leadership_types[donor_type] += 1

    print(f"Read {total:,} rows.")
    print(f"Donor committee types retained: {', '.join(sorted(allowed_types))}")
    print(f"{campaign_path}: {campaign_count:,} rows (donations to listed candidates)")
    print(f"{donators_path}: {donators_count:,} rows (donations by their leadership PACs)")
    print(f"Excluded incoming rows by committee type: {dict(sorted(excluded_campaign_types.items()))}")
    print(f"Excluded leadership PAC rows by committee type: {dict(sorted(excluded_leadership_types.items()))}")
    for committee_id, (sponsor, pac_name) in sorted(leadership_pacs.items()):
        if committee_types[committee_id] in allowed_types:
            print(f"  {committee_id}: {pac_name} (sponsor: {sponsor})")


if __name__ == "__main__":
    main()

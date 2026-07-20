#!/usr/bin/env python3
"""Regenerate the full yeast gene-identifier + description knowledge base.

Idempotent: rerunning overwrites data/knowledge/{gene_alias,gene_desc}.json
and coverage_report.txt from the local SGD / GAF / UniProt / seed sources.

    python src/knowledge/build_all.py
"""
import build_gene_alias
import build_gene_desc
import coverage_report


def main():
    print(">>> build_gene_alias")
    build_gene_alias.main()
    print("\n>>> build_gene_desc")
    build_gene_desc.main()
    print("\n>>> coverage_report")
    coverage_report.main()


if __name__ == "__main__":
    main()

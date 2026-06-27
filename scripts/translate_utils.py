#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
InVesalius translation management script

Structure:
-----------
project_root/
├── invesalius/
├── po/
│   ├── pt_BR.po
│   ├── es.po
│   └── ...
└── locale/
    ├── pt_BR/
    │   └── LC_MESSAGES/
    │       └── invesalius.mo
    └── es/
        └── LC_MESSAGES/
            └── invesalius.mo

Usage:
------
# Update .po files
python translate.py --po

# Update .po files without fuzzy matching
python translate.py --po --no-fuzzy-matching

# Compile .mo files
python translate.py --mo

# Specific languages
python translate.py --po pt_BR es
python translate.py --mo pt_BR es

# Update and compile
python translate.py --po --mo
"""

import argparse
import subprocess
import tempfile
from pathlib import Path

# -------------------------------------------------------------------------
# CONFIGURATION
# -------------------------------------------------------------------------

PROJECT_NAME = "InVesalius"
DOMAIN = "invesalius"

# Source directories to scan
SOURCE_DIRS = [
    "invesalius",
]

# File extensions to extract translations from
EXTENSIONS = [
    "*.py",
]

# Directory containing .po files
PO_DIR = Path("po")

# Directory containing compiled .mo files
LOCALE_DIR = Path("locale")

# Default languages
DEFAULT_LANGUAGES = [
    "pt_BR",
]

# Translation keywords
KEYWORDS = [
    "_",
    "N_",
    "gettext",
    "ngettext:1,2",
]

# -------------------------------------------------------------------------
# UTILITIES
# -------------------------------------------------------------------------

def run_command(cmd):
    """
    Execute a shell command.
    """

    print(f"\n[CMD] {' '.join(cmd)}\n")

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    print(result.stdout)

    if result.returncode != 0:
        raise RuntimeError(
            f"Error while executing command:\n{' '.join(cmd)}"
        )


def collect_files():
    """
    Collect all source files recursively.
    """

    files = []

    for source_dir in SOURCE_DIRS:

        source_path = Path(source_dir)

        if not source_path.exists():
            continue

        for ext in EXTENSIONS:
            files.extend(source_path.rglob(ext))

    return sorted([str(f) for f in files])


# -------------------------------------------------------------------------
# .PO GENERATION / UPDATE
# -------------------------------------------------------------------------

def generate_temp_pot(files):
    """
    Generate a temporary POT file.
    """

    temp_pot = tempfile.NamedTemporaryFile(
        suffix=".pot",
        delete=False,
    )

    temp_pot.close()

    cmd = [
        "xgettext",
        "--from-code=UTF-8",
        "--language=Python",
        f"--package-name={PROJECT_NAME}",
        "--output",
        temp_pot.name,
    ]

    for kw in KEYWORDS:
        cmd.append(f"--keyword={kw}")

    cmd.extend(files)

    run_command(cmd)

    return temp_pot.name


def create_or_update_po(
    language,
    temp_pot,
    no_fuzzy_matching=False,
):
    """
    Create or update a .po file.
    """

    PO_DIR.mkdir(exist_ok=True)

    po_file = PO_DIR / f"{language}.po"

    if po_file.exists():

        print(f"[UPDATE] {po_file}")

        cmd = [
            "msgmerge",
            "--update",
            "--backup=none",
        ]

        if no_fuzzy_matching:
            cmd.append("--no-fuzzy-matching")

        cmd.extend([
            str(po_file),
            temp_pot,
        ])

    else:

        print(f"[CREATE] {po_file}")

        cmd = [
            "msginit",
            "--no-translator",
            "--input",
            temp_pot,
            "--locale",
            language,
            "--output-file",
            str(po_file),
        ]

    run_command(cmd)


def process_po(
    languages,
    no_fuzzy_matching=False,
):
    """
    Update all .po files.
    """

    print("\n==================================================")
    print(" Updating .po files")
    print("==================================================")

    files = collect_files()

    if not files:
        raise RuntimeError("No source files found.")

    print(f"\nFiles found: {len(files)}")

    temp_pot = generate_temp_pot(files)

    for lang in languages:

        print("\n--------------------------------------------------")
        print(f"Language: {lang}")
        print("--------------------------------------------------")

        create_or_update_po(
            lang,
            temp_pot,
            no_fuzzy_matching=no_fuzzy_matching,
        )

    # Remove temporary POT file
    Path(temp_pot).unlink(missing_ok=True)

    print("\n[OK] .po files updated.")


# -------------------------------------------------------------------------
# .MO COMPILATION
# -------------------------------------------------------------------------

def compile_mo(language):
    """
    Compile a .po file into a .mo file.
    """

    po_file = PO_DIR / f"{language}.po"

    if not po_file.exists():
        print(f"[SKIP] File does not exist: {po_file}")
        return

    mo_dir = (
        LOCALE_DIR
        / language
        / "LC_MESSAGES"
    )

    mo_dir.mkdir(parents=True, exist_ok=True)

    mo_file = mo_dir / f"{DOMAIN}.mo"

    print(f"[COMPILE] {po_file}")

    cmd = [
        "msgfmt",
        str(po_file),
        "-o",
        str(mo_file),
    ]

    run_command(cmd)

    print(f"[OK] {mo_file}")


def process_mo(languages):
    """
    Compile all .mo files.
    """

    print("\n==================================================")
    print(" Compiling .mo files")
    print("==================================================")

    for lang in languages:

        print("\n--------------------------------------------------")
        print(f"Language: {lang}")
        print("--------------------------------------------------")

        compile_mo(lang)

    print("\n[OK] .mo files compiled.")


# -------------------------------------------------------------------------
# MAIN
# -------------------------------------------------------------------------

def main():

    parser = argparse.ArgumentParser(
        description="InVesalius translation manager"
    )

    parser.add_argument(
        "--po",
        action="store_true",
        help="Update .po files"
    )

    parser.add_argument(
        "--mo",
        action="store_true",
        help="Compile .mo files"
    )

    parser.add_argument(
        "--no-fuzzy-matching",
        action="store_true",
        help="Disable fuzzy matching in msgmerge"
    )

    parser.add_argument(
        "languages",
        nargs="*",
        help="Optional language list"
    )

    args = parser.parse_args()

    if not args.po and not args.mo:
        parser.error(
            "Choose at least one option: --po or --mo"
        )

    languages = (
        args.languages
        if args.languages
        else DEFAULT_LANGUAGES
    )

    if args.po:
        process_po(
            languages,
            no_fuzzy_matching=args.no_fuzzy_matching,
        )

    if args.mo:
        process_mo(languages)


if __name__ == "__main__":
    main()

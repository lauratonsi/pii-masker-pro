"""Command-line interface for PII Masker Pro.

Examples
--------
    pii-masker -f notes.txt                  # mask a file, print to stdout
    cat notes.txt | pii-masker --lang en     # read from stdin
    pii-masker "Scrivi a a@b.it" -o out.txt   # mask inline text to a file
    pii-masker -f log.txt --reversible --map-out map.json
    pii-masker -f notes.txt --report          # show detected entities as JSON
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional, Sequence

from .config import DEFAULT_ENTITIES, MaskConfig, SUPPORTED_LANGUAGES
from .masker import get_masker


def _read_input(args: argparse.Namespace) -> str:
    if args.text is not None:
        return args.text
    if args.file:
        with open(args.file, "r", encoding="utf-8") as fh:
            return fh.read()
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("No input given. Pass text, -f FILE, or pipe via stdin.")


def _write_output(text: str, out_path: Optional[str]) -> None:
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pii-masker",
        description="Local, multilingual PII anonymization (Presidio + Italian recognizers).",
    )
    parser.add_argument("text", nargs="?", help="Inline text to mask.")
    parser.add_argument("-f", "--file", help="Read input from this file.")
    parser.add_argument("-o", "--output", help="Write masked text here (default: stdout).")
    parser.add_argument(
        "-l", "--lang", default="it", choices=SUPPORTED_LANGUAGES,
        help="Language of the input (default: it).",
    )
    parser.add_argument(
        "-e", "--entities", nargs="+", default=None,
        help="Restrict masking to these entity types (default: all supported).",
    )
    parser.add_argument(
        "--threshold", type=float, default=0.35,
        help="Minimum confidence for NER detections (default: 0.35).",
    )
    parser.add_argument(
        "--reversible", action="store_true",
        help="Use unique restorable tokens instead of static placeholders.",
    )
    parser.add_argument(
        "--map-out", help="With --reversible: write the token->value map as JSON here.",
    )
    parser.add_argument(
        "--report", action="store_true",
        help="Print detected entities as JSON to stderr.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    text = _read_input(args)

    entities = tuple(args.entities) if args.entities else DEFAULT_ENTITIES
    config = MaskConfig(
        language=args.lang, entities=entities, score_threshold=args.threshold
    )

    masker = get_masker()

    if args.reversible:
        result = masker.mask_reversible(text, language=args.lang, config=config)
        if args.map_out:
            with open(args.map_out, "w", encoding="utf-8") as fh:
                json.dump(result.mapping, fh, ensure_ascii=False, indent=2)
    else:
        result = masker.mask_detailed(text, language=args.lang, config=config)

    _write_output(result.text, args.output)

    if args.report:
        sys.stderr.write(
            json.dumps(result.entities, ensure_ascii=False, indent=2) + "\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

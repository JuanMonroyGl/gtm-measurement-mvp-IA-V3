"""Argument parser for the main CLI."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CLI simple para inspeccionar y ejecutar casos de medición.")
    subparsers = parser.add_subparsers(dest="command")

    inspect_parser = subparsers.add_parser("inspect", help="Valida estructura y prerequisitos del caso.")
    inspect_parser.add_argument("--case-path", required=True, help="Ruta del caso. Ej: inputs/case_001")

    run_parser = subparsers.add_parser("run", help="Ejecuta el pipeline completo para un caso.")
    run_parser.add_argument("--case-path", required=True, help="Ruta del caso. Ej: inputs/case_001")

    batch_parser = subparsers.add_parser(
        "run-batch",
        help="Ejecuta varios casos consecutivos y genera un resumen del lote.",
    )
    batch_parser.add_argument("--prefix", default="case_demo", help="Prefijo de case_id. Default: case_demo")
    batch_parser.add_argument("--from", dest="start", type=int, required=True, help="Primer número de caso.")
    batch_parser.add_argument("--to", dest="end", type=int, required=True, help="Último número de caso.")
    batch_parser.add_argument(
        "--clean-outputs",
        action="store_true",
        help="Borra outputs/<case_id> antes de ejecutar cada caso.",
    )
    batch_parser.add_argument(
        "--strict-checks",
        action="store_true",
        help="Ejecuta core.checks.check_case_output después de cada caso exitoso.",
    )
    batch_parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Detiene el lote en el primer caso fallido.",
    )

    ai_images_parser = subparsers.add_parser(
        "ai-images",
        help="Extrae texto/estructura desde imagenes con IA en outputs/<case_id>/IA/imagenes.",
    )
    ai_images_parser.add_argument("--case-path", required=True, help="Ruta del caso. Ej: inputs/case_001")

    parser.add_argument(
        "--repo-root",
        default=".",
        help="Raíz del repo que contiene inputs/ y outputs/. Default: .",
    )
    parser.add_argument(
        "--case-id",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--inspect-only",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser

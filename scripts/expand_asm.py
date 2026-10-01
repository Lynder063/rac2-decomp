"""Adapt splat assembly to Ps2EeAs, retaining the RAC1 measured VU/float fixes.

RAC2 validation is the exact byte gate in build.py, not the RAC1 measurements.
Only generated local assembly is processed; this script includes no retail code.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
LABEL_MACROS = {"glabel", "alabel", "dlabel", "jlabel", "ehlabel"}
NOOP_MACROS = {"endlabel", "enddlabel", "nonmatching"}

RE_INCLUDE = re.compile(r'^\s*\.include\s+"macro\.inc"\s*$')
RE_CONSTANTE = re.compile(r"^D_[0-9A-F]+$")
RE_VADDA = re.compile(
    r"^(?P<tete>.*?\bvadda(?:\.\w+)?\s+\$ACC\s*,\s*)"
    r"(?P<a>\$vf\d+)(?P<virg>\s*,\s*)(?P<b>\$vf\d+)"
    r"(?P<queue>\s*(?:/\*.*)?)$")


def corrige_vadda(ligne: str) -> str:
    """Inverse les deux registres sources d'un `vadda` (voir RE_VADDA).

    Applique a TOUTE ligne d'entree, y compris celles prefixees d'un commentaire
    `/* offset vram octets */` : c'est justement la forme que splat produit.
    """
    match = RE_VADDA.match(ligne)
    if not match:
        return ligne
    return f"{match['tete']}{match['b']}{match['virg']}{match['a']}{match['queue']}"
RE_FLOAT_MOINS_ZERO = re.compile(
    r"^(?P<tete>.*?)\.float\s+-0(?:\.0+)?(?P<queue>\s*(?:/\*.*)?)$")


def corrige_float_moins_zero(ligne: str) -> str:
    """`.float -0` -> `.word 0x80000000` (voir RE_FLOAT_MOINS_ZERO)."""
    match = RE_FLOAT_MOINS_ZERO.match(ligne)
    if not match:
        return ligne
    return f"{match['tete']}.word 0x80000000{match['queue']}"


def corrige_encodage(ligne: str) -> str:
    """Les corrections de DIALECTE mesurees, appliquees a toute ligne d'entree.

    Une seule porte d'entree, pour qu'une nouvelle correction mesuree n'ait
    qu'un endroit ou se brancher.
    """
    return corrige_float_moins_zero(corrige_vadda(ligne))


def expand_line(line: str, local: bool = False,
                vus: set[str] | None = None) -> list[str]:
    """Traduit une ligne ; retourne la ou les lignes a ecrire (vide = supprimee).

    `local` force les symboles a rester LOCAUX (pas de .globl).
    `vus`   est l'ensemble des symboles deja declares DANS CE FICHIER.

    POURQUOI LA DEDUPLICATION
    -------------------------
    splat emet plusieurs etiquettes pour une meme adresse : une fonction peut
    porter un `glabel` ET un `alabel` (autre point d'entree), une donnee un
    `dlabel` ET un `jlabel` (cible de saut). Une fois les macros developpees en
    clair, cela produit deux fois le meme label dans le meme fichier, et
    l'assembleur refuse -- ou le linkeur signale « multiple definition » avec
    les deux references dans le MEME objet, ce qui est le signe distinctif de
    ce cas (et non d'un vrai conflit entre deux fichiers).
    """
    if vus is None:
        vus = set()
    if RE_INCLUDE.match(line):
        return []

    stripped = line.strip()
    if not stripped or stripped.startswith(("#", "/*")):
        return [line]

    parts = stripped.split(None, 1)
    mot = parts[0] if parts else ""
    arg = parts[1].strip() if len(parts) > 1 else ""

    if mot in NOOP_MACROS:
        return []

    if mot in LABEL_MACROS:
        if not arg:
            return [line]
        nom = arg.split(",")[0].strip()
        if RE_CONSTANTE.match(nom):
            return []

        if nom in vus:
            return []          # deja declaree dans ce fichier : on saute
        vus.add(nom)
        return [f"{nom}:"] if local else [f".globl {nom}", f"{nom}:"]

    return [line]


def process(src: Path, dst: Path) -> tuple[int, int]:
    """Traduit un fichier. Retourne (lignes lues, lignes ecrites)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    PREFIXES_NON_CHARGEES = (
        "DVP_overlay_",     # 43 overlays
        "DVP_ovlytab",      # table des overlays
        "DVP_ovlystrtab",   # chaines des overlays
        "shstrtab",         # table des noms de sections
    )
    local = src.name.startswith(PREFIXES_NON_CHARGEES)

    lignes_in = src.read_text(encoding="utf-8", errors="replace").splitlines()
    lignes_out: list[str] = []
    vus: set[str] = set()
    for ligne in lignes_in:
        lignes_out.extend(expand_line(corrige_encodage(ligne), local=local, vus=vus))
    dst.write_text("\n".join(lignes_out) + "\n", encoding="ascii", errors="replace")
    return len(lignes_in), len(lignes_out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Traduit la sortie de splat vers le dialecte de ps2eeas.")
    ap.add_argument("--src", required=True, type=Path, help="arbre produit par splat")
    ap.add_argument("--dst", required=True, type=Path, help="arbre de sortie")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    if not args.src.is_dir():
        print(f"ERREUR : {args.src} n'est pas un dossier", file=sys.stderr)
        return 1

    fichiers = sorted(args.src.rglob("*.s"))
    if not fichiers:
        print(f"ERREUR : aucun .s sous {args.src}", file=sys.stderr)
        return 1

    total_in = total_out = 0
    for source_file in fichiers:
        rel = source_file.relative_to(args.src)
        n_in, n_out = process(source_file, args.dst / rel)
        total_in += n_in
        total_out += n_out
        if args.verbose:
            print(f"  {rel}  {n_in} -> {n_out} lignes")

    print(f"OK  {len(fichiers)} fichiers traduits")
    print(f"    {args.src}  ->  {args.dst}")
    print(f"    {total_in:,} lignes lues, {total_out:,} ecrites".replace(",", " "))
    print(f"    supprimees : {total_in - total_out} (macros de fin et marqueurs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



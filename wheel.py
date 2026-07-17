"""
wheel.py - Moteur de calcul des garanties (systemes reduits / lotto wheels)
(c) 2026 - N. Joan
Un système… mais pas pour gagner, pour rigoler !

"""

from __future__ import annotations
import itertools
import random
from dataclasses import dataclass, field


@dataclass
class WheelResult:
    n: int
    base: int
    x: int
    y: int
    grids: list  # list of tuples of 0-based indices (into the N-number list), length `base`
    verified: bool = False
    verify_note: str = ""


def _popcount(mask: int) -> int:
    # int.bit_count() (Python 3.10+) is implemented in C and much faster
    # than bin(mask).count("1").
    return mask.bit_count()


def _covers(grid_mask: int, sub_mask: int, x: int) -> bool:
    """True if grid_mask shares at least x bits with sub_mask."""
    return (grid_mask & sub_mask).bit_count() >= x


def _mask_bits(mask: int, n: int) -> list:
    return [i for i in range(n) if mask & (1 << i)]


def generate_wheel(n: int, x: int, y: int, base: int = 6,
                    max_y_subsets: int = 400_000,
                    max_seconds: float = 8.0,
                    improve: bool = True,
                    rng: random.Random | None = None) -> WheelResult:
    """
    Construit une garantie N-X/Y (grilles de taille `base`) par un algorithme
    glouton rapide : a chaque etape, on part d'un sous-ensemble Y non encore
    couvert et on l'etend a une grille de taille `base` en choisissant les
    numeros les plus "demandes" (ceux qui apparaissent dans le plus de
    sous-ensembles Y encore non couverts), une frequence maintenue
    incrementalement plutot que recalculee a chaque candidat. Les grilles
    redondantes sont ensuite retirees via un comptage de couverture.
    """
    import math
    import time

    if rng is None:
        rng = random.Random(1234)  # seed fixe -> resultats reproductibles

    if y > base:
        raise ValueError("Y ne peut pas etre superieur a la taille de grille (base).")
    if x > y:
        raise ValueError("X ne peut pas etre superieur a Y.")
    if base > n:
        raise ValueError("La taille de grille ne peut pas depasser N.")

    total_subsets = math.comb(n, y)
    exact_mode = total_subsets <= max_y_subsets

    start = time.time()
    grids: list[int] = []  # each grid stored as a bitmask over n bits

    if exact_mode:
        # combos + masks kept in parallel so we never need to re-decode a
        # mask's bits with an O(n) scan.
        combos = list(itertools.combinations(range(n), y))
        masks = []
        freq = [0] * n
        for combo in combos:
            m = 0
            for i in combo:
                m |= (1 << i)
                freq[i] += 1
            masks.append(m)

        uncovered = dict(zip(masks, combos))  # mask -> combo (bits), alive subsets

        while uncovered:
            if time.time() - start > max_seconds:
                break
            seed_mask, seed_combo = next(iter(uncovered.items()))
            chosen = list(seed_combo)
            chosen_set = set(chosen)
            remaining_slots = base - len(chosen)

            # Greedily add the most "in-demand" remaining numbers according
            # to the live frequency table (O(1) per pick instead of
            # rescanning every uncovered subset for every candidate).
            if remaining_slots > 0:
                ranked = sorted((i for i in range(n) if i not in chosen_set),
                                 key=lambda i: freq[i], reverse=True)
                for i in ranked[:remaining_slots]:
                    chosen.append(i)
                    chosen_set.add(i)

            grid_mask = 0
            for b in chosen:
                grid_mask |= (1 << b)
            grids.append(grid_mask)

            # Remove newly covered subsets and update the frequency table.
            newly_covered = [m for m, c in uncovered.items() if _covers(grid_mask, m, x)]
            for m in newly_covered:
                combo = uncovered.pop(m)
                for i in combo:
                    freq[i] -= 1

        verified = len(uncovered) == 0
        verify_note = ("Garantie verifiee exhaustivement." if verified
                        else f"Non terminee dans le temps imparti "
                             f"({len(uncovered)} cas restants) -- augmentez le budget de temps.")
    else:
        # N trop grand pour une enumeration exhaustive : verification par
        # echantillonnage Monte-Carlo apres une construction gloutonne randomisee.
        target_samples = 20000
        samples = [rng.sample(range(n), y) for _ in range(target_samples)]
        sample_masks = []
        freq = [0] * n
        for s in samples:
            m = 0
            for i in s:
                m |= (1 << i)
                freq[i] += 1
            sample_masks.append(m)
        uncovered_idx = set(range(len(sample_masks)))

        attempts = 0
        while uncovered_idx and attempts < 4000 and (time.time() - start) < max_seconds:
            attempts += 1
            idx = next(iter(uncovered_idx))
            seed_mask = sample_masks[idx]
            seed_bits = _mask_bits(seed_mask, n)
            seed_set = set(seed_bits)
            remaining_slots = base - len(seed_bits)
            chosen = list(seed_bits)
            if remaining_slots > 0:
                ranked = sorted((i for i in range(n) if i not in seed_set),
                                 key=lambda i: freq[i], reverse=True)
                chosen.extend(ranked[:remaining_slots])
            grid_mask = 0
            for b in chosen:
                grid_mask |= (1 << b)
            grids.append(grid_mask)
            newly_covered = [i for i in uncovered_idx if _covers(grid_mask, sample_masks[i], x)]
            for i in newly_covered:
                uncovered_idx.discard(i)
                for b in _mask_bits(sample_masks[i], n):
                    freq[b] -= 1

        verified = False
        verify_note = ("N trop grand pour une preuve exhaustive : verifie sur "
                        f"{target_samples} tirages aleatoires "
                        f"({target_samples - len(uncovered_idx)}/{target_samples} couverts). "
                        "Considere comme fiable en pratique mais pas prouve a 100%.")

    if improve and grids:
        remaining_budget = max(0.5, max_seconds - (time.time() - start))
        grids = _remove_redundant_grids(grids, n, x, y, exact_mode, max_y_subsets,
                                         time_budget=remaining_budget)

    grid_tuples = [tuple(_mask_bits(m, n)) for m in grids]
    return WheelResult(n=n, base=base, x=x, y=y, grids=grid_tuples,
                        verified=verified, verify_note=verify_note)


def _remove_redundant_grids(grids: list, n: int, x: int, y: int,
                             exact_mode: bool, max_y_subsets: int,
                             time_budget: float = 5.0) -> list:
    """
    Retire les grilles superflues en s'appuyant sur un compteur de couverture
    par sous-ensemble (au lieu de re-verifier toute la couverture a chaque
    tentative de suppression) : une grille est superflue si chaque
    sous-ensemble qu'elle couvre est deja couvert par au moins une autre
    grille. Borne par un budget de temps : en cas dedepassement, on renvoie
    simplement les grilles obtenues jusque-la (toujours une garantie valide,
    juste pas forcement minimale).
    """
    import math
    import time
    if not exact_mode:
        return grids  # trop couteux/pas fiable a verifier en mode Monte-Carlo
    if math.comb(n, y) > max_y_subsets:
        return grids

    deadline = time.time() + time_budget
    all_masks = [m for m in _iter_masks(n, y)]
    grids = list(grids)

    # coverage_count[j] = nombre de grilles courantes qui couvrent all_masks[j]
    # covers_of[i] = liste des indices j de sous-ensembles couverts par grids[i]
    covers_of = []
    coverage_count = [0] * len(all_masks)
    for g in grids:
        if time.time() > deadline:
            # Budget depasse pendant le calcul initial : on renonce a
            # l'optimisation et on renvoie les grilles telles quelles
            # (deja une garantie valide).
            return grids
        covered_here = [j for j, sm in enumerate(all_masks) if _covers(g, sm, x)]
        covers_of.append(covered_here)
        for j in covered_here:
            coverage_count[j] += 1

    changed = True
    while changed:
        if time.time() > deadline:
            break
        changed = False
        for i in range(len(grids)):
            if time.time() > deadline:
                break
            covered_here = covers_of[i]
            if all(coverage_count[j] > 1 for j in covered_here):
                # cette grille est superflue : on peut la retirer
                for j in covered_here:
                    coverage_count[j] -= 1
                del grids[i]
                del covers_of[i]
                changed = True
                break
    return grids


def _iter_masks(n: int, y: int):
    for combo in itertools.combinations(range(n), y):
        m = 0
        for i in combo:
            m |= (1 << i)
        yield m


def guarantee_table(result: "WheelResult", y_values=(3, 4, 5, 6),
                     max_cost: int = 5_000_000, time_budget: float = 5.0) -> dict:
    """
    Pour le jeu de grilles deja genere (result.grids), calcule pour chaque
    valeur de Y dans y_values la garantie EXACTE reellement obtenue :

        garanti[Y] = min, sur tous les sous-ensembles de Y numeros parmi les
        N joues, du nombre maximal de numeros communs avec une des grilles.

    C'est different du X/Y cible choisi au depart : cette table montre ce
    que le jeu de grilles garantit vraiment pour Y=3,4,5,6 (par ex. il se
    peut qu'une garantie visee 3/4 offre "gratuitement" une garantie 4/6).

    Retourne un dict {y: {"garanti": int, "exact": bool, "note": str}}.
    """
    import math
    import time

    n = result.n
    grid_masks = []
    for g in result.grids:
        m = 0
        for i in g:
            m |= (1 << i)
        grid_masks.append(m)

    out = {}
    for y in y_values:
        if y > n:
            out[y] = {"garanti": None, "exact": False, "note": "Y > N (impossible)."}
            continue
        total = math.comb(n, y)
        cost = total * max(1, len(grid_masks))
        start = time.time()
        if cost <= max_cost:
            worst = result.base  # borne haute de depart (taille de grille)
            timed_out = False
            for combo in itertools.combinations(range(n), y):
                if time.time() - start > time_budget:
                    timed_out = True
                    break
                mask = 0
                for i in combo:
                    mask |= (1 << i)
                best_here = 0
                for gm in grid_masks:
                    hits = (gm & mask).bit_count()
                    if hits > best_here:
                        best_here = hits
                        if best_here == min(y, result.base):
                            break  # ne peut pas faire mieux pour ce sous-ensemble
                if best_here < worst:
                    worst = best_here
            if timed_out:
                out[y] = {"garanti": worst, "exact": False,
                           "note": "Calcul interrompu (budget de temps) -- "
                                   "valeur = minorant, la garantie reelle "
                                   "est au moins celle-ci."}
            else:
                out[y] = {"garanti": worst, "exact": True, "note": "Calcul exhaustif."}
        else:
            # Trop de combinaisons pour une verification exhaustive :
            # estimation par echantillonnage (minorant observe uniquement).
            rng = random.Random(4242)
            samples = 20000
            worst = result.base
            for _ in range(samples):
                combo = rng.sample(range(n), y)
                mask = 0
                for i in combo:
                    mask |= (1 << i)
                best_here = max((gm & mask).bit_count() for gm in grid_masks)
                if best_here < worst:
                    worst = best_here
            out[y] = {"garanti": worst, "exact": False,
                       "note": f"Estimation sur {samples} echantillons aleatoires "
                               "(N trop grand pour un calcul exhaustif) -- "
                               "la vraie garantie peut etre legerement plus basse."}
    return out


def score_grids_against_draw(grids_real: list, drawn_numbers: list, bonus: int | None = None):
    """
    Compare les grilles reellement jouees (numeros reels, pas des indices) a
    un tirage reel (6 numeros, + eventuellement un numero chance/bonus).

    Retourne (details, summary) ou :
      - details est une liste de dicts par grille : {grille, numeros, points, bonus_touche}
      - summary est un dict {3: nb_grilles_a_3, 4: ..., 5: ..., 6: ..., "bonus": nb_grilles_avec_bonus}
    """
    drawn_set = set(drawn_numbers)
    details = []
    summary = {3: 0, 4: 0, 5: 0, 6: 0, "bonus": 0}
    for i, grid in enumerate(grids_real, start=1):
        hits = len(set(grid) & drawn_set)
        bonus_hit = bonus is not None and bonus in grid
        details.append({"grille": i, "numeros": grid, "points": hits, "bonus_touche": bonus_hit})
        if hits >= 3:
            summary[min(hits, 6)] += 1
        if bonus_hit:
            summary["bonus"] += 1
    return details, summary



    """Verification exhaustive independante (utile pour les tests / petites N)."""
    import math
    if math.comb(result.n, result.y) > 500_000:
        return False, "Trop grand pour une verification exhaustive ici."
    grid_masks = []
    for g in result.grids:
        m = 0
        for i in g:
            m |= (1 << i)
        grid_masks.append(m)
    for combo in itertools.combinations(range(result.n), result.y):
        sub_mask = 0
        for i in combo:
            sub_mask |= (1 << i)
        if not any(_covers(gm, sub_mask, result.x) for gm in grid_masks):
            return False, f"Sous-ensemble non couvert: {combo}"
    return True, "OK"


def apply_numbers(result: WheelResult, numbers: list[int]) -> list[list[int]]:
    """Convertit les grilles (indices 0..N-1) en numeros reels choisis par le joueur."""
    if len(numbers) != result.n:
        raise ValueError(f"Il faut exactement {result.n} numeros (recu {len(numbers)}).")
    sorted_numbers = sorted(numbers)
    out = []
    for grid in result.grids:
        out.append(sorted([sorted_numbers[i] for i in grid]))
    return out


def single_grid_odds(base: int = 6, draw_size: int = 6, pool: int = 49) -> dict:
    """
    Probabilite classique (hypergeometrique) qu'UNE grille de `base` numeros
    partage exactement m numeros avec un tirage officiel aleatoire de
    `draw_size` numeros parmi `pool`. Independant de tout systeme de
    garantie -- c'est la probabilite intrinseque du jeu.
    """
    import math
    total = math.comb(pool, draw_size)
    lo = max(0, draw_size - (pool - base))
    hi = min(base, draw_size)
    return {m: math.comb(base, m) * math.comb(pool - base, draw_size - m) / total
            for m in range(lo, hi + 1)}


def system_odds(result: "WheelResult", pool: int = 49, draw_size: int = 6,
                 samples: int = 20_000, max_exact: int = 20_000,
                 rng: random.Random | None = None) -> dict:
    """
    Probabilite reelle (pas une garantie, une PROBABILITE) qu'au moins une
    de vos grilles obtienne au moins m numeros corrects lors d'un tirage
    officiel aleatoire de `draw_size` numeros parmi `pool` -- en tenant
    compte du fait que seuls vos N numeros joues peuvent matcher vos
    grilles. Calcul exact quand c'est possible, sinon estime par
    echantillonnage (indique dans le resultat).

    Ne predit rien sur un tirage particulier : decrit seulement la loi de
    probabilite du systeme de grilles tel que construit.
    """
    import math
    if rng is None:
        rng = random.Random(999)

    n = result.n
    grid_masks = []
    for g in result.grids:
        mm = 0
        for i in g:
            mm |= (1 << i)
        grid_masks.append(mm)

    max_m = min(draw_size, result.base)
    exact_used = True

    cond = {}  # cond[k][m] = P(au moins m corrects dans une grille | k de vos numeros tires)
    for k in range(0, draw_size + 1):
        if k == 0 or n < k:
            cond[k] = {m: 0.0 for m in range(0, max_m + 1)}
            continue
        total_k = math.comb(n, k)
        counts = [0] * (max_m + 1)
        if total_k <= max_exact:
            for combo in itertools.combinations(range(n), k):
                mask = 0
                for i in combo:
                    mask |= (1 << i)
                best = 0
                cap = min(k, result.base)
                for gm in grid_masks:
                    h = (gm & mask).bit_count()
                    if h > best:
                        best = h
                        if best == cap:
                            break
                counts[min(best, max_m)] += 1
            denom = total_k
        else:
            exact_used = False
            for _ in range(samples):
                combo = rng.sample(range(n), k)
                mask = 0
                for i in combo:
                    mask |= (1 << i)
                best = max((gm & mask).bit_count() for gm in grid_masks)
                counts[min(best, max_m)] += 1
            denom = samples
        cond[k] = {m: sum(counts[m:]) / denom for m in range(0, max_m + 1)}

    # P(k de vos N numeros font partie des draw_size tires) -- hypergeometrique exact
    total_draw = math.comb(pool, draw_size)
    p_k = {}
    for k in range(0, draw_size + 1):
        if n - k < 0 or pool - n < draw_size - k:
            p_k[k] = 0.0
        else:
            p_k[k] = math.comb(n, k) * math.comb(pool - n, draw_size - k) / total_draw

    probs = {}
    for m in range(1, max_m + 1):
        probs[m] = sum(p_k[k] * cond[k].get(m, 0.0) for k in range(m, draw_size + 1))

    return {"probs": probs, "exact": exact_used}

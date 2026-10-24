"""
Data loading for the Ember evaluation.

Real data
---------
PROSPIE (Loughborough University), the one openly downloadable dataset with
rectal core temperature, heart rate and a sex-balanced sample:

    DOI 10.17028/rd.lboro.26076577
    V3 has 40 participants (not 16 as first thought), 9 conditions,
    one row per minute, rectal temperature, heart rate, 11 skin sites.
    Heart rate comes from three different sensors (column HRtype):
    1 = finger photoplethysmography, 2 = Equivital chest ECG,
    3 = Polar chest strap. Conditions 1-3 only have HR every 5 minutes.
    9999 = missing.
    Licence: CC BY-NC 4.0  <-- fine for a project, blocks commercial use.

Download the .xlsx yourself and point --data at it. The loader below does
fuzzy column matching and PRINTS WHAT IT FOUND, because the exact column
names in the released file are not documented anywhere and you should see
the mapping it chose rather than trust it.

Second dataset worth adding if you have time:
    Circadian timing and heat stress in firefighters, DOI 10.17632/7ghxcsd9sz.1
    21 firefighters, ingestible capsule at 30 s, beat-to-beat Polar H10 HR,
    live-fire exposures. CC BY 4.0. All male, so use it for the
    cross-dataset generalisation test, not the sex analysis.

Synthetic
---------
make_synthetic() produces a dataset with the same SHAPE so you can build and
test the whole pipeline before the download finishes. It is a simulation,
not evidence. Any number it produces is a property of my generator, and the
only honest use of it is to check that your code runs.
"""

import os
import re
import sys

import numpy as np
import pandas as pd

STANDARD_COLS = ["subject", "sex", "condition", "minute", "hr", "core_c", "hr_type"]

# HRtype codes in the PROSPIE key sheet
HR_TYPE_NAMES = {1: "finger PPG", 2: "Equivital chest ECG", 3: "Polar chest strap"}
CHEST_HR_TYPES = (2, 3)   # Ember uses a Polar H10 chest strap

# Candidate name fragments, in priority order.
PATTERNS = {
    "subject":   [r"^subject", r"^participant", r"^pp?t?[_ ]?id", r"^id$", r"^subj"],
    "sex":       [r"^sex", r"^gender"],
    "condition": [r"^condition", r"^trial", r"^setting", r"^exposure", r"^session"],
    "minute":    [r"^time[_ ]?\(?min", r"^minute", r"^time$", r"^t[_ ]?min", r"^elapsed"],
    "hr":        [r"heart[_ ]?rate", r"^hr$", r"^hr[_ ]", r"\bbpm\b", r"\bhr$"],
    "hr_type":   [r"hr[_ ]?type"],
    "core_c":    [r"rectal", r"^t[_ ]?re\b", r"\btre\b", r"core[_ ]?temp",
                  r"^core$", r"gastro", r"\btgi\b"],
}

# Things that look like core temperature but are not. Skin temperature is
# the classic trap: it is in almost every physiological dataset and it is
# not what you need.
NEGATIVE = [r"skin", r"insulat", r"mean[_ ]?t?sk", r"ambient", r"air",
            r"climatic", r"microclimate", r"globe", r"operative"]


def _match(cols, key):
    neg = [re.compile(p, re.I) for p in NEGATIVE]
    for pat in PATTERNS[key]:
        rx = re.compile(pat, re.I)
        for c in cols:
            name = str(c).strip()
            if key == "hr" and re.search(r"hr[_ ]?type", name, re.I):
                continue
            if rx.search(name):
                if key == "core_c" and any(n.search(name) for n in neg):
                    continue
                return c
    return None


def _flatten_columns(cols):
    """Flatten a MultiIndex column list to plain strings.

    The PROSPIE workbook uses a two-row merged header (e.g. 'Corerectal' in
    row 0, blank in row 1; blank in row 0, 'HR' in row 1).  pandas reads
    those as (level0, level1) tuples.  We keep whichever level is
    informative: if level0 looks like 'Unnamed: N_level_0' we use level1,
    otherwise level0.  When both are real text we join them with a space.
    """
    flat = []
    for c in cols:
        if not isinstance(c, tuple):
            flat.append(str(c).strip())
            continue
        l0, l1 = str(c[0]).strip(), str(c[1]).strip()
        l0_unnamed = l0.startswith("Unnamed:")
        l1_unnamed = l1.startswith("Unnamed:")
        if l0_unnamed and not l1_unnamed:
            flat.append(l1)
        elif l1_unnamed and not l0_unnamed:
            flat.append(l0)
        elif not l0_unnamed and not l1_unnamed:
            flat.append(f"{l0} {l1}")
        else:
            flat.append(l0)   # both unnamed — keep level0 as fallback
    return flat


def load_prospie(path, sheet="Data", verbose=True, hr_types=CHEST_HR_TYPES):
    """Load the PROSPIE workbook into the standard frame.

    The PROSPIE Data sheet uses a two-row merged header, so we read it with
    header=[0,1] and then flatten the MultiIndex to plain strings before
    doing the normal pattern matching.

    Every minute of every trial is kept. Missing HR stays NaN so the filter
    does a predict-only step (dropping those rows would make the filter
    treat a 5-minute gap as 1 minute). Rows without core temperature stay
    in for the filter and are left out only when scoring.

    hr_types: HR readings from other sensor types are set to NaN (the
    filter predicts through them); trials left with no HR at all are
    dropped. None keeps every type.
    """
    if not os.path.exists(path):
        sys.exit(f"no such file: {path}\n"
                 "Download it from DOI 10.17028/rd.lboro.26076577")
    try:
        raw = pd.read_excel(path, sheet_name=sheet, header=[0, 1])
    except Exception as e:
        sys.exit(f"could not read {path}: {e}\n"
                 "pip install openpyxl")

    # Flatten the two-row header into plain column names.
    flat_names = _flatten_columns(raw.columns)
    raw.columns = flat_names

    if verbose:
        print(f"loaded {path}")
        print(f"  {raw.shape[0]} rows x {raw.shape[1]} columns")
        print(f"  columns: {flat_names[:25]}"
              f"{' ...' if raw.shape[1] > 25 else ''}")

    mapping = {k: _match(raw.columns, k) for k in PATTERNS}
    if verbose:
        print("\n  column mapping chosen:")
        for k, v in mapping.items():
            print(f"    {k:10s} <- {v!r}")

    missing = [k for k in ("hr", "core_c") if mapping[k] is None]
    if missing:
        sys.exit(
            f"\ncould not find column(s) for {missing}.\n"
            "Open the workbook, look at the headers, and either rename them "
            "or add the right pattern to PATTERNS at the top of this file.\n"
            "Be careful not to map a SKIN temperature column to core_c - "
            "the loader refuses obvious ones, but check."
        )

    df = pd.DataFrame()
    for k in STANDARD_COLS:
        src = mapping.get(k)
        df[k] = raw[src] if src is not None else np.nan

    if mapping["subject"] is None:
        sys.exit("no subject column found; leave-one-subject-out needs one")

    if mapping["minute"] is None:
        # No minute column found — assign sequential minute index per trial.
        df["minute"] = df.groupby(["subject", "condition"]).cumcount()
    else:
        # The Time column may be datetime.time objects (HH:MM:SS from Excel).
        # Convert to elapsed minutes (integer).
        import datetime as _dt
        def _to_min(v):
            if isinstance(v, _dt.time):
                return v.hour * 60 + v.minute
            try:
                return float(v)
            except (TypeError, ValueError):
                return np.nan
        df["minute"] = df["minute"].apply(_to_min)

    df["subject"] = df["subject"].astype(str).str.strip()
    if mapping["sex"] is not None:
        df["sex"] = (df["sex"].astype(str).str.strip().str[0].str.upper()
                     .replace({"1": "M", "2": "F", "0": "F"}))
        df.loc[~df["sex"].isin(["M", "F"]), "sex"] = np.nan
    df["condition"] = df["condition"].astype(str).str.strip()

    for c in ("minute", "hr", "core_c", "hr_type"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
        df[c] = df[c].replace([9999, 9999.0], np.nan)   # 9999 = missing (key sheet)

    # Out-of-range values become missing, not dropped rows, so minutes stay contiguous
    df.loc[~df.hr.between(30, 230), "hr"] = np.nan
    df.loc[~df.core_c.between(34.0, 42.0), "core_c"] = np.nan
    df = df.dropna(subset=["minute"])

    # Participants whose sex code differs between rows (17 and 18 in V3):
    # same age/mass/height each time, so a data-entry error. Don't guess.
    nsex = df.groupby("subject").sex.nunique()
    bad_sex = sorted(nsex[nsex > 1].index.tolist())
    if bad_sex:
        df.loc[df.subject.isin(bad_sex), "sex"] = np.nan
        if verbose:
            print(f"\n  WARNING: inconsistent sex code for participant(s) "
                  f"{bad_sex}; sex set to missing (left out of the by-sex analysis)")

    # Heart-rate sensor type. Each trial gets the type of most of its HR readings.
    n_all_trials = df.groupby(["subject", "condition"]).ngroups
    if hr_types is not None and df["hr_type"].notna().any():
        keep = df.hr_type.isin(hr_types)
        n_masked = int((df.hr.notna() & ~keep).sum())
        df.loc[~keep, "hr"] = np.nan
        has_hr = df.groupby(["subject", "condition"]).hr.transform(lambda s: s.notna().any())
        df = df[has_hr]
        if verbose:
            names = ", ".join(HR_TYPE_NAMES.get(t, str(t)) for t in hr_types)
            print(f"\n  HR sensor types kept: {names}")
            print(f"  {n_masked} HR readings from other sensors set to missing; "
                  f"{n_all_trials - df.groupby(['subject', 'condition']).ngroups} "
                  f"trials left with no HR dropped")
    # Count only readings actually used (after masking), so a trial isn't
    # labelled by a sensor whose readings were thrown away.
    df["_used_type"] = df.hr_type.where(df.hr.notna())
    df["trial_hr_type"] = df.groupby(["subject", "condition"])._used_type.transform(
        lambda s: s.dropna().mode().iloc[0] if s.notna().any() else np.nan)
    df = df.drop(columns="_used_type")

    df = df.sort_values(["subject", "condition", "minute"]).reset_index(drop=True)

    # ---- sampling check: every trial must be one row per minute ----------
    # evaluate.py runs the filter with step_seconds=60, one row = one minute.
    gaps = df.groupby(["subject", "condition"])["minute"].diff().dropna()
    bad = gaps[(gaps - 1.0).abs() > 1e-6]
    if len(bad):
        bad_trials = df.loc[bad.index, ["subject", "condition"]].drop_duplicates()
        sys.exit(
            f"\nSAMPLING MISMATCH: {len(bad)} gaps that are not 1 minute, in "
            f"{len(bad_trials)} trials, e.g.\n{bad_trials.head(10).to_string(index=False)}\n"
            f"evaluate.py expects one row per minute (step_seconds=60). "
            f"Investigate the Time column; do NOT resample silently."
        )

    if verbose:
        scored = df.core_c.notna()
        print(f"\n  {len(df)} minutes kept, {int(scored.sum())} with core temp (scored), "
              f"{int(df.hr.notna().sum())} with HR")
        print(f"  {df.subject.nunique()} subjects, "
              f"{df.groupby(['subject', 'condition']).ngroups} trials, "
              f"{df.condition.nunique()} conditions; every trial is 1-minute spaced")
        if df["sex"].notna().any():
            print(f"  sex: {df.dropna(subset=['sex']).groupby('sex').subject.nunique().to_dict()}")
        else:
            print("  sex: NOT FOUND - the stratified analysis will be skipped")
        if df["trial_hr_type"].notna().any():
            print("  trials by HR sensor: " + ", ".join(
                f"{HR_TYPE_NAMES.get(int(t), t)} {n}" for t, n in
                df.groupby(["subject", "condition"]).trial_hr_type.first().value_counts().sort_index().items()))
        print(f"  core temp range {df.core_c.min():.2f} - {df.core_c.max():.2f} C")

    return df


# ------------------------------------------------------------- synthetic

def make_synthetic(n_per_sex=8, n_conditions=6, seed=0,
                   sex_hr_offset=0.0, sex_gain=1.0):
    """
    A stand-in with PROSPIE's shape: 1-minute samples, several chamber
    conditions, rest/work alternation, rectal-like core temperature.

    Core temperature follows first-order dynamics toward a setpoint driven
    by workload and ambient conditions. Heart rate is generated FROM core
    temperature using the published observation model, plus a per-subject
    offset and gain, plus non-thermal drivers. That structure is what makes
    leave-one-subject-out genuinely hard, which is the point.

    sex_hr_offset / sex_gain inject a systematic difference between groups
    so you can confirm your stratified analysis would detect one. They
    DEFAULT TO NONE. Do not leave them on and then report a finding.
    """
    rng = np.random.default_rng(seed)
    from ectemp import hr_from_ct

    rows = []
    for sex in ("M", "F"):
        for i in range(n_per_sex):
            sid = f"{sex}{i+1:02d}"
            # Per-subject physiology
            base_ct = rng.normal(36.95, 0.18)
            tau = rng.uniform(9.0, 20.0)              # thermal time constant, min
            hr_off = rng.normal(0, 9.0)               # HR offset at given CT
            hr_gain = rng.normal(1.0, 0.10)
            if sex == "F":
                hr_off += sex_hr_offset
                hr_gain *= sex_gain

            for c in range(n_conditions):
                amb = 25.0 + 3.0 * c                  # 25 to 40 C
                work = rng.uniform(0.45, 0.95)
                drive = 0.55 * work + 0.040 * (amb - 25.0)
                ct = base_ct
                n_min = 90
                for t in range(n_min):
                    # 15 min rest, 40 min work, rest, work
                    working = (15 <= t < 55) or (70 <= t < 90)
                    target = base_ct + (drive * 2.4 if working else 0.15)
                    ct += (target - ct) / tau
                    ct += rng.normal(0, 0.006)

                    hr = hr_gain * hr_from_ct(ct) + hr_off
                    if working:
                        hr += 14.0 * work             # non-thermal exercise drive
                    hr += 0.06 * (amb - 25.0) * 10
                    hr += rng.normal(0, 3.2)
                    hr = float(np.clip(hr, 42, 205))

                    rows.append((sid, sex, f"cond{c+1}", t, hr, float(ct)))

    df = pd.DataFrame(rows, columns=STANDARD_COLS[:6])
    df["hr_type"] = np.nan          # one generator, no sensor types
    df["trial_hr_type"] = np.nan
    return df


if __name__ == "__main__":
    df = make_synthetic()
    print("synthetic dataset")
    print(f"  {len(df)} rows, {df.subject.nunique()} subjects, "
          f"{df.condition.nunique()} conditions")
    print(f"  sex: {df.groupby('sex').subject.nunique().to_dict()}")
    print(f"  core {df.core_c.min():.2f}-{df.core_c.max():.2f} C, "
          f"HR {df.hr.min():.0f}-{df.hr.max():.0f} bpm")
    print(f"  samples above 38.0 C: {(df.core_c >= 38.0).mean()*100:.1f}%")

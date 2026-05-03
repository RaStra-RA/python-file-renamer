import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

INVALID_CHARS = r'<>:"/\\|?*\n\r\t'
INVALID_RE = re.compile(f"[{re.escape(INVALID_CHARS)}]")

def sanitize_name(name: str) -> str:
    name = INVALID_RE.sub("_", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name.rstrip(". ")
    if not name:
        name = "file"
    return name

def normalize_orig(name: str) -> str:
    # remove any full date blocks like 2025-12-09_
    name = re.sub(r"\d{4}-\d{2}-\d{2}", "", name)

    # remove any short date blocks like 5-12-09 or 05-12-09
    name = re.sub(r"\d{1,2}-\d{2}-\d{2}", "", name)

    # remove ANY standalone 3-digit sequence blocks
    name = re.sub(r"(?:^|[_ -])\d{3}(?=$|[_ -])", "_", name)

    # cleanup separators
    name = re.sub(r"[_ -]{2,}", "_", name).strip(" _-")

    parts = name.split("_")
    cleaned = []
    prev = None

    for part in parts:
        if part and part != prev:
            cleaned.append(part)
            prev = part

    return "_".join(cleaned)



def list_files(root: Path, recursive: bool) -> list[Path]:
    if recursive:
        return [p for p in root.rglob("*") if p.is_file()]
    return [p for p in root.iterdir() if p.is_file()]

def pick_date(p: Path, use: str) -> datetime:
    st = p.stat()
    ts = st.st_mtime if use == "mtime" else st.st_ctime
    return datetime.fromtimestamp(ts)

def ensure_unique(target: Path) -> Path:
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    parent = target.parent
    i = 2
    while True:
        cand = parent / f"{stem}_{i}{suffix}"
        if not cand.exists():
            return cand
        i += 1

def should_skip(p: Path, log_path: Path) -> bool:
    name = p.name.lower()

    # skip Windows locked/system registry hive files
    if name.startswith("ntuser.dat"):
        return True
    if name.endswith(".regtrans-ms") or name.endswith(".blf"):
        return True
    if name == "ntuser.ini":
        return True


    # skip the tool files themselves
    try:
        if p.resolve() == Path(__file__).resolve():
            return True
    except Exception:
        pass

    if name == "readme.txt":
        return True

    try:
        if log_path and p.resolve() == log_path.resolve():
            return True
    except Exception:
        pass

    return False

def build_new_name(
    p: Path,
    seq: int,
    pattern: str,
    date_fmt: str,
    date_use: str,
    prefix: str,
    suffix: str,
    keep_ext: bool
) -> str:
    dt = pick_date(p, date_use)
    date_str = dt.strftime(date_fmt)

    ext = p.suffix.lower() if keep_ext else ""
    orig = normalize_orig(p.stem)

    new_base = pattern.format(date=date_str, seq=seq, orig=orig)
    new_base = sanitize_name(new_base)

    pre = sanitize_name(prefix) if prefix else ""
    suf = sanitize_name(suffix) if suffix else ""

    if pre:
        new_base = f"{pre}_{new_base}"
    if suf:
        new_base = f"{new_base}_{suf}"

    return f"{new_base}{ext}"

def write_log_row(log_path: Path, old_path: Path, new_path: Path, status: str, note: str) -> None:
    new_file = not log_path.exists()
    with log_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["timestamp", "status", "old_path", "new_path", "note"])
        w.writerow([datetime.now().isoformat(timespec="seconds"), status, str(old_path), str(new_path), note])

def do_rename(files: list[Path], args) -> int:
    ok = 0
    seq = args.start

    for p in files:
        if should_skip(p, args.log):
            continue

        if args.ext and p.suffix.lower() not in args.ext:
            continue

        new_name = build_new_name(
            p=p,
            seq=seq,
            pattern=args.pattern,
            date_fmt=args.date_format,
            date_use=args.date_use,
            prefix=args.prefix,
            suffix=args.suffix,
            keep_ext=not args.no_ext
        )

        target = p.with_name(new_name)
        if target == p:
            write_log_row(args.log, p, target, "SKIP", "same name")
            continue

        target = ensure_unique(target)

        if args.dry_run or not args.apply:
            mode = "DRY" if args.dry_run else "PREVIEW"
            print(f"{mode}  {p.name}  ->  {target.name}")
            write_log_row(args.log, p, target, mode, "no changes")
            ok += 1
            seq += 1
            continue

        try:
            p.rename(target)
            print(f"OK   {p.name}  ->  {target.name}")
            write_log_row(args.log, p, target, "OK", "")
            ok += 1
            seq += 1
        except Exception as e:
            print(f"ERR  {p}  ->  {target}  |  {e}")
            write_log_row(args.log, p, target, "ERR", str(e))

    return ok

def undo_from_log(log_path: Path, dry_run: bool) -> int:
    if not log_path.exists():
        print("Log file not found.")
        return 0

    rows = []
    with log_path.open("r", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            if row.get("status") == "OK":
                rows.append(row)

    if not rows:
        print("Nothing to undo.")
        return 0

    rows.reverse()
    ok = 0

    for row in rows:
        old_path = Path(row["old_path"])
        new_path = Path(row["new_path"])

        if not new_path.exists():
            print(f"SKIP missing: {new_path}")
            continue

        if old_path.exists():
            alt = ensure_unique(old_path)
            print(f"NOTE target exists, restore to: {alt}")
            old_path = alt

        if dry_run:
            print(f"DRY  {new_path.name}  ->  {old_path.name}")
            ok += 1
            continue

        try:
            new_path.rename(old_path)
            print(f"OK   {new_path.name}  ->  {old_path.name}")
            ok += 1
        except Exception as e:
            print(f"ERR  {new_path}  ->  {old_path}  |  {e}")

    return ok

def parse_args():
    p = argparse.ArgumentParser(
        prog="Python File Renamer Tool",
        description="Batch rename with patterns/date/sequence. Safe skip. Log. Undo. Apply switch."
    )

    p.add_argument("--dir", default=".", help="Target folder")
    p.add_argument("--recursive", action="store_true", help="Scan subfolders")
    p.add_argument("--ext", nargs="*", help="Filter by extensions, example: .jpg .png .pdf")
    p.add_argument("--start", type=int, default=1, help="Sequence start")
    p.add_argument("--pattern", default="{date}_{seq:03d}_{orig}", help="Name pattern: {date} {seq} {orig}")
    p.add_argument("--date-format", default="%Y-%m-%d", help="Date format for {date}")
    p.add_argument("--date-use", choices=["mtime", "ctime"], default="mtime", help="Use file mtime or ctime")
    p.add_argument("--prefix", default="", help="Prefix text")
    p.add_argument("--suffix", default="", help="Suffix text")
    p.add_argument("--no-ext", action="store_true", help="Remove extension")
    p.add_argument("--dry-run", action="store_true", help="Preview without renaming")
    p.add_argument("--apply", action="store_true", help="Actually rename (required for changes)")
    p.add_argument("--log", default="rename_log.csv", help="CSV log file name or path")
    p.add_argument("--undo", action="store_true", help="Undo using log file")
    return p.parse_args()

def main():
    args = parse_args()
    args.dir = Path(args.dir).expanduser().resolve()

    if args.ext:
        args.ext = [e.lower() if e.startswith(".") else "." + e.lower() for e in args.ext]

    log_in = Path(args.log).expanduser()
    if log_in.name == "rename_log.csv" and not log_in.is_absolute():
        args.log = (Path(__file__).resolve().parent / "rename_log.csv").resolve()
    else:
        args.log = log_in.resolve()

    if args.undo:
        done = undo_from_log(args.log, args.dry_run)
        print(f"Undo restored: {done}")
        return

    if not args.dir.exists() or not args.dir.is_dir():
        print("Folder not found.")
        sys.exit(1)

    files = list_files(args.dir, args.recursive)
    files.sort(key=lambda x: x.name.lower())

    done = do_rename(files, args)
def main():
    args = parse_args()
    args.dir = Path(args.dir).expanduser().resolve()

    if args.ext:
        args.ext = [e.lower() if e.startswith(".") else "." + e.lower() for e in args.ext]

    log_in = Path(args.log).expanduser()
    if log_in.name == "rename_log.csv" and not log_in.is_absolute():
        args.log = (Path(__file__).resolve().parent / "rename_log.csv").resolve()
    else:
        args.log = log_in.resolve()

    if args.undo:
        done = undo_from_log(args.log, args.dry_run)
        print(f"Undo restored: {done}")
        return

    if not args.dir.exists() or not args.dir.is_dir():
        print("Folder not found.")
        sys.exit(1)

    files = list_files(args.dir, args.recursive)
    files.sort(key=lambda x: x.name.lower())

    done = do_rename(files, args)

def do_rename(files: list[Path], args) -> int:
    ok = 0
    seq = args.start

    for p in files:
        if should_skip(p, args.log):
            continue

        if args.ext and p.suffix.lower() not in args.ext:
            continue

        new_name = build_new_name(
            p=p,
            seq=seq,
            pattern=args.pattern,
            date_fmt=args.date_format,
            date_use=args.date_use,
            prefix=args.prefix,
            suffix=args.suffix,
            keep_ext=not args.no_ext
        )

        target = p.with_name(new_name)

        if target == p:
            write_log_row(args.log, p, target, "SKIP", "same name")
            continue

        target = ensure_unique(target)

        if not args.apply:
            print(f"DRY  {p.name}  ->  {target.name}")
            write_log_row(args.log, p, target, "DRY", "no changes")
            ok += 1
            seq += 1
            continue

        try:
            p.rename(target)
            print(f"OK   {p.name}  ->  {target.name}")
            write_log_row(args.log, p, target, "OK", "")
            ok += 1
            seq += 1
        except Exception as e:
            print(f"ERR  {p}  ->  {target}  |  {e}")
            write_log_row(args.log, p, target, "ERR", str(e))

    return ok





if __name__ == "__main__":
    main()

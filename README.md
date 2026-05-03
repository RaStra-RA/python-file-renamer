# 🗂️ Python File Renamer Tool

Renames files in a folder by normalizing their names — removes old dates/counters and applies today's date with a clean sequential number.

## ✨ What It Does

- Removes existing date prefixes like `2025-12-12_`
- Removes leading sequence numbers like `_001_`
- Applies today's date in format `YYYY-MM-DD`
- Adds a clean sequence number `_001`, `_002`, etc.
- Preserves original filename and extension
- Prevents overwriting existing files

## 📋 Example

**Before:**
2025-12-12_001_report.txt
2025-12-12_report.txt
report.txt

**After:**
2025-12-13_001_report.txt
2025-12-13_002_report.txt
2025-12-13_003_report.txt

## ▶️ How to Use

**Step 1 — Preview (recommended):**
```bash
python renamer.py --dir "C:\Path\To\Your\Folder" --ext .txt .csv .pdf
```

**Step 2 — Apply changes:**
```bash
python renamer.py --dir "C:\Path\To\Your\Folder" --ext .txt .csv .pdf --apply
```

## ⚙️ Requirements

- Python 3.9 or newer
- Windows, macOS, or Linux

## ⚠️ Important

- Always preview before applying
- Run once per set of files
- Test on a sample folder first

## 👩‍💻 Author
Built by [RaStra](https://github.com/RaStra-RA) · Available for custom Python tools on [Fiverr](https://www.fiverr.com/ra_stra)

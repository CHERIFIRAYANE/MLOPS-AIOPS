#!/usr/bin/env python3
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    'PRIVATE_KEY': re.compile(r'-----BEGIN (?:RSA |OPENSSH |)PRIVATE KEY-----'),
    'AWS_KEY': re.compile(r'AKIA[0-9A-Z]{16}'),
    'AWS_SECRET': re.compile(r'AWS[_-]?SECRET', re.I),
    'GITHUB_TOKEN': re.compile(r'ghp_[0-9A-Za-z_]{36}'),
    'PASSWORD_ASSIGN': re.compile(
        r'password\s*[=:]\s*(?![\'\"]?[$<{])'
        r'(?![\'\"]?(?:CHANGE_ME|YOUR_|EXAMPLE|REPLACE_ME)\b)'
        r'[\'\"]?\S+',
        re.I,
    ),
}


def scan_file(path: Path):
    try:
        text = path.read_text(errors='ignore')
    except Exception:
        return []
    hits = []
    for name, rx in PATTERNS.items():
        if rx.search(text):
            hits.append(name)
    return hits


def main():
    findings = {}
    for p in ROOT.rglob('*'):
        if p.is_file():
            # Do not match the scanner's own detection rules as credentials.
            if p.resolve() == Path(__file__).resolve():
                continue
            if any(part.startswith('.') or part == '__pycache__' for part in p.parts):
                continue
            if p.suffix in {'.png', '.jpg', '.jpeg', '.gif', '.woff', '.woff2', '.zip', '.pyc'}:
                continue
            hits = scan_file(p)
            if hits:
                findings[str(p.relative_to(ROOT))] = hits

    if not findings:
        print('No probable secrets found.')
        return 0

    print('Possible secret matches:')
    for path, hits in findings.items():
        print(f'- {path}: {",".join(hits)}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())

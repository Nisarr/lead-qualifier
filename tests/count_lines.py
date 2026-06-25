import os

for root, dirs, files in os.walk('.'):
    if '.venv' in root or '__pycache__' in root:
        continue
    for f in sorted(files):
        if f.endswith('.py'):
            path = os.path.join(root, f)
            with open(path, encoding='utf-8', errors='ignore') as fh:
                count = sum(1 for _ in fh)
            print(f"{os.path.relpath(path):<55} {count} lines")

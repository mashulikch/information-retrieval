"""Execute the notebook in a fresh Python process and retain real cell output."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import traceback


root = Path(__file__).resolve().parent.parent
os.chdir(root)
sys.path.insert(0, str(root))
path = root / "ma.chegodaeva@innopolis.university.ipynb"
notebook = json.loads(path.read_text(encoding="utf-8"))
namespace = {"__name__": "__main__"}
for index, cell in enumerate(notebook["cells"]):
    if cell["cell_type"] == "code":
        compile("".join(cell["source"]), f"cell-{index}", "exec")


def save():
    path.write_text(json.dumps(notebook, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


count = 0
try:
    for index, cell in enumerate(notebook["cells"]):
        if cell["cell_type"] != "code":
            continue
        count += 1
        cell["execution_count"] = count
        output = io.StringIO()
        print(f"Running cell {index} ...", flush=True)
        try:
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                exec(compile("".join(cell["source"]), f"cell-{index}", "exec"), namespace)
        except Exception as exc:
            cell["outputs"] = [{"output_type": "error", "ename": type(exc).__name__,
                                "evalue": str(exc), "traceback": traceback.format_exc().splitlines()}]
            save()
            raise
        text = output.getvalue()
        cell["outputs"] = [{"output_type": "stream", "name": "stdout", "text": text.splitlines(keepends=True)}] if text else []
        save()
        print(text, end="", flush=True)
finally:
    if "SITE" in namespace:
        namespace["SITE"].stop()

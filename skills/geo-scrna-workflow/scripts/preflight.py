#!/usr/bin/env python3
"""Run static, configuration, and optional R checks before the pipeline."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def run_command(command: list[str], cwd: Path) -> dict[str, Any]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout[-12000:],
        "stderr": result.stderr[-12000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    parser.add_argument("--config")
    parser.add_argument("--output")
    args = parser.parse_args()

    project = Path(args.project_dir).expanduser().resolve()
    required = [
        project / "run_pipeline.R",
        project / "config" / "default_config.R",
        project / "R" / "00_validation.R",
        project / "R" / "99_pipeline.R",
        project / "tests" / "smoke_parse.R",
        project / "tests" / "smoke_config.R",
        project / "tools" / "static_check.py",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    report: dict[str, Any] = {
        "project_dir": str(project),
        "static_ok": not missing,
        "missing_files": missing,
        "rscript": shutil.which("Rscript"),
        "checks": [],
    }
    if not missing:
        report["checks"].append(run_command([sys.executable, "tools/static_check.py"], project))
    if not missing and report["rscript"]:
        report["checks"].append(run_command([report["rscript"], "tests/smoke_parse.R"], project))
        report["checks"].append(run_command([report["rscript"], "tests/smoke_config.R"], project))
        if args.config:
            config = Path(args.config).expanduser().resolve()
            expr = (
                "source('config/default_config.R'); "
                "for(f in sort(list.files('R', pattern='\\\\.R$', full.names=TRUE))) sys.source(f, envir=.GlobalEnv); "
                f"e<-new.env(parent=.GlobalEnv); sys.source({json.dumps(str(config))}, envir=e); "
                "stopifnot(exists('CFG', envir=e, inherits=FALSE)); "
                "cfg<-normalize_config(deep_merge(default_config(), e$CFG)); validate_config(cfg); cat('CONFIG_OK\\n')"
            )
            report["checks"].append(run_command([report["rscript"], "-e", expr], project))

    report["runtime_validated"] = bool(report["rscript"])
    report["checks_ok"] = all(check["returncode"] == 0 for check in report["checks"])
    report["ok"] = report["static_ok"] and report["checks_ok"]
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
import json
import shutil
import sys
from pathlib import Path

try:
    input_data = json.load(sys.stdin)
    transcript_path = Path(input_data["transcript_path"]).expanduser()

    last_message = ""
    # 最後の編集内容を探す
    with transcript_path.open() as f:
        for line in f:
            obj = json.loads(line)
            if obj.get("event") == "tool_use" and obj.get("name") in ["Write", "Edit", "MultiEdit"]:
                tool_input = obj.get("input", {})
                if "file_path" in tool_input:
                    last_message = f"Update: {tool_input['file_path']}"
except Exception:
    pass

import subprocess
import sys

try:
    # gitコマンドの完全パスを取得
    git_path = shutil.which("git")
    if not git_path:
        sys.exit(1)
    
    # 変更があるか確認
    status = subprocess.run(
        [git_path, "status", "--porcelain"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True
    )

    if status.stdout.strip():  # 変更があれば
        subprocess.run(
            [git_path, "add", "."],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        subprocess.run(
            [git_path, "commit", "-m", "Auto commit"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    subprocess.run(
        [git_path, "push"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True
    )

except subprocess.CalledProcessError:
    sys.exit(1)
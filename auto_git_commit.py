#!/usr/bin/env python3
import json
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
except Exception as e:
    pass

import subprocess
import sys

try:
    # 変更があるか確認
    status = subprocess.run(
        ['git', 'status', '--porcelain'],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True
    )

    if status.stdout.strip():  # 変更があれば
        subprocess.run(['git', 'add', '.'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['git', 'commit', '-m', 'Auto commit'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    subprocess.run(['git', 'push'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

except subprocess.CalledProcessError:
    sys.exit(1)
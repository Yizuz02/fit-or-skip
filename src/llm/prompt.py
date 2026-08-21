from pathlib import Path
import re
from typing import Tuple


PROMPT_VERSION_REGEX = re.compile(r"evaluate-job-v(\d+)\.md$")

def get_latest_prompt_info(prompts_dir: str = "prompts") -> Tuple[str, str, int]:
    """
    Scans the prompts directory for 'evaluate-job-v*.md' files, finds the one
    with the highest version number.
    """
    dir_path = Path(prompts_dir)
    
    if not dir_path.exists() or not dir_path.is_dir():
        raise FileNotFoundError(f"Prompts directory not found: {prompts_dir}")

    prompt_files = []

    for file_path in dir_path.glob("evaluate-job-v*.md"):
        match = PROMPT_VERSION_REGEX.search(file_path.name)
        if match:
            version_int = int(match.group(1))
            prompt_files.append((version_int, file_path))

    if not prompt_files:
        raise FileNotFoundError(f"No valid versioned prompt files found in {prompts_dir}")

    # Sort by version integer descending to pick the absolute highest
    prompt_files.sort(key=lambda item: item[0], reverse=True)
    latest_version_num, latest_path = prompt_files[0]

    return str(latest_path), latest_path.stem, latest_version_num
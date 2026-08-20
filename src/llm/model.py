import json
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    base_url=os.environ["LLM_BASE_URL"],
    api_key=os.environ["LLM_API_KEY"],
)

def load_prompt_file(file_path: str) -> str:
    base_dir = Path(__file__).resolve().parent.parent.parent
    full_path = base_dir / file_path
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()

def evaluate_job(job):
    system_content = load_prompt_file("prompts/evaluate-job-v1.md")

    user_content = f"""
        Field: {job.field}
        Job Title: {job.job_title}
        Place: {job.place}
        Company: {job.company_name}
        Description:
        {job.job_description}
    """

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content}
    ]

    res = client.chat.completions.create(
        model=os.environ["LLM_MODEL"],
        messages=messages,
        temperature=0.2
    )

    clean_res = res.choices[0].message.content.replace("```json", "").replace("```", "").strip()

    return json.loads(clean_res)
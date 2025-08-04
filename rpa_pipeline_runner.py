# rpa_pipeline_runner.py
import json
from pathlib import Path
import re

# gemini_api.py
import os
import requests
import dotenv

dotenv.load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = "models/gemini-2.5-flash"
URL = f"https://generativelanguage.googleapis.com/v1beta/{MODEL}:generateContent?key={API_KEY}"
HEADERS = {
    "Content-Type": "application/json"
}

def call_gemini(prompt: str):
    body = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    response = requests.post(URL, headers=HEADERS, json=body)
    try:
        content = response.json()
        raw_text = content["candidates"][0]["content"]["parts"][0]["text"]
        # Gỡ bỏ markdown wrapper ```json ... ``` nếu có
        if raw_text.strip().startswith("```json"):
            raw_text = raw_text.strip().removeprefix("```json").removesuffix("```").strip()
        print(raw_text)
        return raw_text
    except Exception as e:
        print("❌ Gemini error:", response.text)
        return ""

def load_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def extract_json_from_text(text: str) -> str:
    text = text.strip()
    # Remove markdown code blocks and any leading ```python or ```
    text = re.sub(r"^```(?:python)?\\n", "", text)
    text = re.sub(r"```$", "", text)
    return text.strip()

def step1_analyze_task(input_file):
    task_text = load_text(input_file)
    prompt = f"""You are a professional UI test case generator.
Your job is to convert the following natural language test description into a list of clear, atomic UI actions.
Follow these strict rules:
- Output must be a JSON array.
- Each array item is a single, simple UI action.
- Do NOT include explanations, markdown, comments, or anything else — only the JSON array.
Example 1:
If the requirement is "Open http://webtest.ranorex.org/wp-login.php, then Fill "abc" into Username field, then Fill "ranorex" into Password field. After that Click "Login" button.", the response should be:
["Open 'http://webtest.ranorex.org/wp-login.php'", "Fill 'abc' into Username field", "Fill 'ranorex' into Password field", "Click 'Login' button"]
Example 2:
If the requirement is "Open http://127.0.0.1:5500/public/index.html and check if 'Find Food' button is orange.", the response should be:
["Open 'http://127.0.0.1:5500/public/index.html'", "Check the background color of the 'Find Food' button is orange"]

Requirement: "{task_text}"

Return only a JSON list like this:
["Atomic Task 1", "Atomic Task 2", "Atomic Task 3"]
"""
    response = call_gemini(prompt)
    clean_json = extract_json_from_text(response)
    return json.loads(clean_json), task_text

def step2_generate_steps(subtask_list):
    all_steps = []
    step_trace = []
    for sub in subtask_list:
        prompt = f"""You are a professional UI test step generator.
Your task is to convert the following atomic test instruction into a list of executable UI test steps in JSON format.

Instruction: "{sub}"

Each step must follow this JSON structure:
{{
  "action": "interact | assert | locate | verify",
  "selector": "CSS selector or a natural description (e.g. 'button with text Login', 'Sign In' button), or empty string if not applicable",
  "value": "string value to type or expect, or empty string if not applicable",
  "expected": {{
    "property": "e.g. 'color', 'width', 'text', 'position' (or empty string if not applicable)",
    "value": "expected value (or empty string if not applicable)",
    "relation": "e.g. 'above', 'near', 'left of', 'equal' (or empty string if not applicable)"
  }}
}}

Important:
- All fields (`action`, `selector`, `value`, `expected`) **must always be present**.
- If a field has no value, use:
  - `""` for empty strings
  - `{{}}` for empty object (when `expected` is not needed)
- Do not omit any field from the JSON step.

Example 1:
{{
  "action": "interact",
  "selector": "button with text 'Login'",
  "value": "",
  "expected": {{}}
}}

Example 2:
{{
  "action": "verify",
  "selector": "header",
  "value": "",
  "expected": {{
    "property": "color",
    "value": "orange",
    "relation": ""
  }}
}}

Explanation of the actions:
- **interact**: clicking, typing, hovering, selecting, or submitting forms.
- **assert**: checking that something exists, is visible, absent, or meets a layout/appearance requirement.
- **locate**: identifying UI elements based on text, position (e.g. near/above), or attributes (class, ID, etc.).
- **verify**: validating properties like color, alignment, text, count, image presence, OCR output, size, position, etc.

Notes:
- The selector can be a CSS selector or a natural-language reference to the element.
- UI may be implemented using any frontend framework (e.g., TailwindCSS, Bootstrap, raw HTML).
- Return only a JSON array. No explanation. No markdown.

Now generate the JSON array of steps for the instruction above.
"""

        response = call_gemini(prompt)
        clean = extract_json_from_text(response)
        steps = json.loads(clean)
        all_steps.extend(steps)
        step_trace.append((sub, steps))
    return all_steps, step_trace


def main(case_id):
    # folders
    INPUT_DIR = Path("Input")
    TASK_DIR = Path("JSONtask")
    STEP_DIR = Path("JSONwStep")

    for d in [TASK_DIR, STEP_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    # Step 1: text → task JSON
    task_file = INPUT_DIR / f"{case_id}.txt"
    task_json_file = TASK_DIR / f"{case_id}.task.json"
    task_list, task_text = step1_analyze_task(task_file)
    save_json(task_json_file, task_list)

    # Step 2: task JSON → step JSON
    step_json_file = STEP_DIR / f"{case_id}.step.json"
    steps, step_trace = step2_generate_steps(task_list)
    save_json(step_json_file, steps)

if __name__ == "__main__":
    import sys
    case_id = sys.argv[1] if len(sys.argv) > 1 else "text001"
    main(case_id)

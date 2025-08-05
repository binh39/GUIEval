import json
from pathlib import Path
import re
import pandas as pd
import requests
from key import KEY_LIST

MODEL = "models/gemini-2.5-flash-lite"
HEADERS = {"Content-Type": "application/json"}

current_key_index = 0
used_keys = set()

def rotate_api_key():
    global current_key_index
    used_keys.add(current_key_index)
    print(f"🔁 Gemini key index {current_key_index} failed. Switching...")
    if len(used_keys) == len(KEY_LIST):
        print("❌ All Gemini API keys exhausted. Exiting.")
        exit(1)
    current_key_index = (current_key_index + 1) % len(KEY_LIST)

def get_url():
    return f"https://generativelanguage.googleapis.com/v1beta/{MODEL}:generateContent?key={KEY_LIST[current_key_index]}"

def call_gemini(prompt: str):
    global current_key_index

    while True:
        body = {"contents": [{"parts": [{"text": prompt}]}]}
        response = requests.post(get_url(), headers=HEADERS, json=body)

        try:
            content = response.json()
            if 'candidates' in content:
                # Reset used_keys on success
                used_keys.clear()
                raw_text = content["candidates"][0]["content"]["parts"][0]["text"]
                if raw_text.strip().startswith("```json"):
                    raw_text = raw_text.strip().removeprefix("```json").removesuffix("```").strip()
                print(raw_text)
                return raw_text
            elif content.get("error", {}).get("code") == 429:
                rotate_api_key()
            else:
                print("❌ Gemini error:", json.dumps(content, indent=2))
                rotate_api_key()
        except Exception as e:
            print("❌ Unexpected error:", e)
            rotate_api_key()


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
    full_text = load_text(input_file)
    main_tasks = re.findall(r'"(.*?)"', full_text, re.DOTALL)
    print(len(main_tasks))
    task_list = []
    task_trace = []

    for task_text in main_tasks:
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
        subtasks = json.loads(clean_json)
        task_list.append(subtasks)
        task_trace.append((task_text, subtasks))

    print(task_list)
    return task_list, task_trace

def step2_generate_steps(subtask_groups):
    all_step_groups = []
    step_trace = []
    for subtask_list in subtask_groups:
        step_group = []
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
            step_group.extend(steps)
            step_trace.append((sub, steps))
        all_step_groups.append(step_group)
    return all_step_groups, step_trace

def save_excel_summary(filename, task_trace, step_groups):
    rows = []
    for idx, (main_task, subtasks) in enumerate(task_trace):
        step_group = step_groups[idx] if idx < len(step_groups) else []
        subtask_json = json.dumps(subtasks, ensure_ascii=False)
        step_json = json.dumps(step_group, ensure_ascii=False)
        rows.append({
            "Main Task": main_task,
            "Sub Tasks": subtask_json,
            "Steps": step_json
        })
    df = pd.DataFrame(rows)
    filename.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(filename, index=False)


def main(case_id):
    INPUT_DIR = Path("Input")
    TASK_DIR = Path("JSONtask")
    STEP_DIR = Path("JSONwStep")
    REPORT_DIR = Path("Report")

    for d in [TASK_DIR, STEP_DIR, REPORT_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    task_file = INPUT_DIR / f"{case_id}.txt"
    task_json_file = TASK_DIR / f"{case_id}.task.json"
    task_list, task_trace = step1_analyze_task(task_file)
    save_json(task_json_file, task_list)
    print("\n Step 1 success \n")

    step_json_file = STEP_DIR / f"{case_id}.step.json"
    step_groups, step_trace = step2_generate_steps(task_list)
    save_json(step_json_file, step_groups)
    print("\n Step 2 success \n")

    report_file = REPORT_DIR / f"{case_id}.summary.xlsx"
    save_excel_summary(report_file, task_trace, step_groups)
    print(f"✅ Excel saved to: {report_file}")


if __name__ == "__main__":
    import sys
    case_id = sys.argv[1] if len(sys.argv) > 1 else "text001"
    main(case_id)

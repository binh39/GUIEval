import json
from pathlib import Path
import re
import pandas as pd
import requests
from key import KEY_LIST

MODEL = "models/gemini-2.5-flash"
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
            print(content['usageMetadata']['candidatesTokenCount'])
            if 'candidates' in content:
                # Reset used_keys on success
                used_keys.clear()
                raw_text = content["candidates"][0]["content"]["parts"][0]["text"]
                if raw_text.strip().startswith("```json"):
                    raw_text = raw_text.strip().removeprefix("```json").removesuffix("```").strip()
                print(raw_text)
                return raw_text
            elif content.get("error", {}).get("code") == 429:
                print("❌ Gemini error:", content)
                rotate_api_key()
            else:
                print("❌ Gemini error:", content)
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

def step0_create_task(filename: str):
    # Chuẩn bị thư mục & file đích
    INPUT_DIR = Path("Input")
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = INPUT_DIR / (filename if filename.endswith(".txt") else f"{filename}.txt")
    prompt = """
You are a professional UI tester. Generate 20 different, single-sentence UI test descriptions in English.
Each sentence should be explicit and testable (include concrete values like pixel sizes, colors, counts, timing, URLs).
Always return a JSON array of exactly 20 strings. Do not include markdown. Do not number the items.

Example style (for inspiration, not to copy):
"Open 'https://www.netflix.com', click on the 'Sign In' button located at the top-right corner (within 50px from top and 30px from right), enter the email 'testuser@example.com' and password 'Test@1234', submit the login form, verify that after submission the user is redirected to 'https://www.netflix.com/browse' within 3 seconds and the page displays at least 5 personalized movie thumbnails, and ensure that all input fields have font 'Roboto 16px', padding '12px', margin-bottom '16px'; the 'Sign In' button has background color '#e50914', text color '#ffffff', border radius '4px', is responsive down to 360px screen width, and all elements meet WCAG contrast ratio of at least 4.5:1'."
"""

    all_sentences = []
    for _ in range(5):  # 5 batch -> ~100 câu
        raw = call_gemini(prompt)
        text = extract_json_from_text(raw) if raw else ""
        sentences = []
        # 1) cố parse như JSON array
        try:
            data = json.loads(text)
            if isinstance(data, list):
                sentences = [str(s) for s in data]
        except Exception as e:
            print(f"❌ Error parsing JSON: {e}")
            pass
        # 2) nếu không phải JSON array, tách theo dòng (đơn giản, không kiểm lỗi/chính tả)
        if not sentences:
            sentences = [ln.strip().strip(",") for ln in text.splitlines() if ln.strip()]
        # Chuẩn hoá: thay tất cả dấu " bên trong câu thành ' ; bọc toàn bộ câu trong dấu "
        for s in sentences:
            s = s.replace('"', "'").strip()
            if not (s.startswith('"') and s.endswith('"')):
                s = f'"{s}"'
            all_sentences.append(s)

    # Ghi file: các câu cách nhau bởi dấu phẩy, vẫn giữ mỗi câu trong dấu "
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(",\n".join(all_sentences))
    print(f"✅ Generated {len(all_sentences)} sentences -> {out_path}")

def step1_analyze_task(input_file):
    full_text = load_text(input_file)
    main_tasks = re.findall(r'"(.*?)"', full_text, re.DOTALL)
    print(len(main_tasks))
    task_list = []
    task_trace = []

    for task_text in main_tasks:
        retries = 3
        for attempt in range(retries):
            prompt = f"""You are a professional UI test case generator.
Your job is to convert the following natural language test description into a list of clear, atomic UI actions.
Follow these strict rules:
- Output must be a JSON array.
- Group related properties of the **same UI element in the same state** into one atomic task.
  - This includes all visual, layout, formatting, style, alignment, and content properties (e.g. font size, color, background, border radius, timestamp format, position, alignment).
  - Do not separate things like color, format, alignment, font, padding, size, position if they belong to the same element in the same context.
  - Only separate tasks if:
    - The properties relate to **different states** (e.g., hover vs normal).
    - The properties relate to **different elements**.
    - The instruction involves a **user action** followed by a **verification** (e.g., click then check).
    - The behavior differs between **device types** (e.g., mobile vs desktop).
  - (Example: the 'Add to Cart' button has color '#ff9900', rounded corners of '4px', and hover background color changes to '#e68a00')
- Each array item is a single atomic test action string.
  - Do NOT include explanations, markdown, comments, or anything else — only the JSON array.

Example:
- Requirement: "Open 'https://www.netflix.com', click on the 'Sign In' button located at the top-right corner (within 50px from top and 30px from right), enter the email 'testuser@example.com' and password 'Test@1234', submit the login form, verify that after submission the user is redirected to 'https://www.netflix.com/browse' within 3 seconds and the page displays at least 5 personalized movie thumbnails, and ensure that all input fields have font 'Roboto 16px', padding '12px', margin-bottom '16px'; the 'Sign In' button has background color '#e50914', text color '#ffffff', border radius '4px', is responsive down to 360px screen width, and all elements meet WCAG contrast ratio of at least 4.5:1."  
- Response:
[
  "Open 'https://www.netflix.com'",
  "Click on the 'Sign In' button located at the top-right corner (within 50px from top and 30px from right)",
  "Fill 'testuser@example.com' into the email input field",
  "Fill 'Test@1234' into the password input field",
  "Submit the login form",
  "Verify that after submission the user is redirected to 'https://www.netflix.com/browse' within 3 seconds",
  "Check that the page displays at least 5 personalized movie thumbnails",
  "Verify that all input fields have font 'Roboto 16px', padding '12px', and margin-bottom '16px'",
  "Verify that the 'Sign In' button has background color '#e50914', text color '#ffffff', and border radius '4px'",
  "Verify that the 'Sign In' button is responsive down to 360px screen width",
  "Verify that all visible elements meet WCAG contrast ratio of at least 4.5:1"
]

Now generate the JSON from this requirement:
- Requirement: "{task_text}"

Return only a JSON list like this:
["Atomic Task 1", "Atomic Task 2", "Atomic Task 3"]
"""
            try:
                print("Call gemini step 1")
                response = call_gemini(prompt)
                clean_json = extract_json_from_text(response)
                subtasks = json.loads(clean_json)
                task_list.append(subtasks)
                task_trace.append((task_text, subtasks))
                break
            except Exception as e:
                print(f"❌ Error (attempt {attempt + 1}/3): {e}")
                print(f"⚠️ Raw response: {response}")
                if attempt == retries - 1:
                    print(f"⚠️ Error max 3/3")

    print(task_list)
    return task_list, task_trace

def step2_generate_steps(subtask_groups):
    all_step_groups = []
    step_trace = []
    for subtask_list in subtask_groups:
        step_group = []
        for sub in subtask_list:
            retries = 3
            for attempt in range(retries):
                prompt = f"""You are a professional UI test step generator.
Your task is to convert the following atomic test instruction into a list of executable UI test steps in JSON format.

Instruction: "{sub}"

Each step must follow this JSON structure:
{{
  "action": "interact | assert | locate | verify",
  "selector": "CSS selector or a natural description (e.g. 'button with text Login', 'Sign In' button), or empty string if not applicable",
  "value": "string value to type or expect, or empty string if not applicable",
  "expected": {{
    // This object may contain multiple properties,
    // based only on what the instruction requires.
    // Each key is the name of a UI property (e.g. color, font, position).
    // Each value is the expected value or structured object.
  }}
}}

Important:
- All fields (`action`, `selector`, `value`, `expected`) **must always be present**.
- If a field has no value, use:
  - `""` for empty strings
  - `{{}}` for empty object (when `expected` is not needed)
- Do not omit any field from the JSON step.
- Do not include any property in `expected` if it is not clearly mentioned in the instruction.
- `expected` must be a valid object (`{{}}`), and can contain:
  - 'text':
  - 'language': e.g., `"French"`, `"Chinese"`
  - 'position': object with `x`, `y`, `width`, `height`, etc..
  - 'styles':
    - 'textAlign':
    - `color`: e.g., `"#ffffff"` or `"rgb(255, 255, 255)" or "white"
    - `backgroundColor`
    - `font`: an object with `family`, `size`, `weight`, `style` if mentioned 
    - 'border': width, style, color, radius
    - 'padding': top, right, bottom, left
    - 'margin': top, right, bottom, left
    - `opacity`: `"0.5"`, `"1"`, etc.
    - Or any property related to 'styles', as long as it follows the correct format and rules stated (only declare if present in the input description).
  - 'state':
    - `visibility`: `"visible"` or `"hidden"`
    - `enabled`: boolean (`true` or `false`)
    - 'focused': boolean
    - 'hovered': boolean     
    - 'active': boolean
    - Or any property related to 'state', as long as it follows the correct format and rules stated (only declare if present in the input description).   
  - dynamics:
    - `movement`: `"static"` or `"moves"` after an action
    - `scroll`: "sticky" | "fixed" | "static" | "none" or something,
    - `transition`: boolean (CSS transition)
    - 'animate': boolean (motion effect)
    - `focus`: boolean, (`true` if element should be focused, via Tab or click)
    - `navigation`: destination URL if checking page redirection
    - `loading`: `"present"`, `"loading"`, `"none"` for spinners, indicators
    - 'progressValue': string, (% value if it is progress bar, pie chart, etc)
    - Or any property related to 'dynamics', as long as it follows the correct format and rules stated (only declare if present in the input description).
  - `relation`: if element is expected to be `above`, `below`, or `near` another
  - Or any property related to expected , as long as it follows the correct format and rules stated (only declare if present in the input description).

Example 1:
- Task: "Verify the 'Subscribe' button is visible, located at position (x=100, y=200) with width 300px and height 50px, has white text on a blue background, uses bold italic 'Roboto' font size 18px, remains fixed when scrolling, and has smooth transition effects."
- Response:
{{
  "action": "verify",
  "selector": "'Subscribe' button",
  "value": "",
  "expected": {{
    "text": "Subscribe",
    "position": {{
      "x": 100,
      "y": 200,
      "width": 300,
      "height": 50
    }},
    "styles": {{
      "color": "white",
      "backgroundColor": "blue",
      "font": {{
        "size": "18px",
        "weight": "bold",
        "style": "italic",
        "family": "Roboto"
      }}
    }},
    "state": {{
      "visibility": "visible"
    }},
    "dynamics": {{
      "scrollEffect": "fixed",
      "transition": true
    }}
  }}
}}

Explanation of the actions:
- **interact**: clicking, typing, hovering, selecting, or submitting forms.
- **assert**: checking that something exists, is visible, absent, or meets a layout/appearance requirement.
- **locate**: identifying UI elements based on text, position (e.g. near/above), or attributes (class, ID, etc.).
- **verify**: validating properties like color, alignment, text, count, image presence, OCR output, size, position, etc.

Notes:
- Each atomic test instruction return only ONE test steps, NO splitting the instruction into multiple substeps.
- The selector can be a CSS selector or a natural-language reference to the element.
- UI may be implemented using any frontend framework (e.g., TailwindCSS, Bootstrap, raw HTML).
- Return only a JSON array. No explanation. No markdown.

Now generate the JSON array of steps for the instruction above.
"""                
                try:
                    response = call_gemini(prompt)
                    clean = extract_json_from_text(response)
                    steps = json.loads(clean)
                    step_group.extend(steps)
                    step_trace.append((sub, steps))
                    break
                except Exception as e:
                    print(f"❌ Error (attempt {attempt + 1}/3): {e}")
                    print(f"⚠️ Raw response: {response}")
                    if attempt == retries - 1:
                        print(f"⚠️ Error max 3/3")
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


def main():
    #"""
    INPUT_DIR = Path("Input")
    TASK_DIR = Path("JSONtask")
    STEP_DIR = Path("JSONwStep")
    REPORT_DIR = Path("Report")

    for i in range(100):
        filename = f"maintask_{i}.txt"
        if not (INPUT_DIR / filename).exists():
            print(f"Creating example file: {filename}")
            step0_create_task(filename)
        else:
            print(f"File already exists: {filename}")

    for d in [TASK_DIR, STEP_DIR, REPORT_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    for txt_file in INPUT_DIR.glob("*.txt"):
        case_id = txt_file.stem
        try:
            print(f"\n▶️ Running pipeline for: {case_id}")

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
        except Exception as e:
            print(f"❌ Error in {case_id}: {e}")
#"""
    

if __name__ == "__main__":
    main()

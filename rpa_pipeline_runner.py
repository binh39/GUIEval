import json
from pathlib import Path
import re
import pandas as pd
import requests
from key import KEY_LIST
import random

#KEY_LIST = []
MODEL = "models/gemini-2.5-flash"
HEADERS = {"Content-Type": "application/json"}

current_key_index = random.randint(0, len(KEY_LIST) - 1)
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
    while True:
        body = {"contents": [{"parts": [{"text": prompt}]}]}
        response = requests.post(get_url(), headers=HEADERS, json=body)

        try:
            content = response.json()
            print(content['usageMetadata'])
            if 'candidates' in content:
                # Reset used_keys on success
                used_keys.clear()
                raw_text = content["candidates"][0]["content"]["parts"][0]["text"]
                if raw_text.strip().startswith("```json"):
                    raw_text = raw_text.strip().removeprefix("```json").removesuffix("```").strip()
                print(raw_text)
                return raw_text
            elif content.get("error", {}).get("code") == 429:
                print("❌ Gemini error:")
                print(json.dumps(content, indent=2, ensure_ascii=False))
                rotate_api_key()
            else:
                print("❌ Gemini error:")
                print(json.dumps(content, indent=2, ensure_ascii=False))
                rotate_api_key()
        except Exception as e:
            print("❌ Unexpected error:", e)
            try:
                # Nếu đã có content JSON, in đầy đủ
                print("📄 Full JSON content:")
                print(json.dumps(content, indent=2, ensure_ascii=False))
            except NameError:
                # Nếu chưa parse được content thì in raw text
                print("📄 Raw response text:")
                print(response.text[:2000])  # Giới hạn 2000 ký tự tránh log quá dài
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
You are a professional UI tester.
Generate exactly 20 different UI test descriptions in English.

Strong constraints (must follow all):
- Each description is a single JSON string item, but may contain multiple sentences (10-15 sentences).
- Absolutely forbid vague words (example: 'correctly', 'appropriately', 'fast', 'quickly', 'smooth', 'enough', ...). Always give explicit, measurable values.
- The steps should be sequential and complete.
- Each sentence must:
  * Describe multiple attributes of the same element (e.g., font size, color, border,...), or
  * Specify at least one explicit spatial or relational constraint between elements (e.g., 'Element A below the Element B with a gap of 10px', 'Element E placed to the right of Element F with a gap of 20px'), or both.
- Each action must specify multiple attributes together (style, layout, state,...).
- Always provide concrete, measurable expected values with units or counts where applicable: exact pixel sizes (e.g., 16px), RGB/HEX colors (e.g., rgb(34,139,34) or #228B22 or 'green'), timing (e.g., 800ms, 2s, 1 second), percentages (e.g., 75%), URLs (full), screen widths (e.g., 360px), coordinates (x,y), gaps/tolerance (e.g., 24px ±2px).
- Do not combine two different actions into the same sentence if they are unrelated. If the same action applies to two unrelated elements, split them into separate sentences for clarity.
- Inside each description string, use only single quotes (') for UI labels or literals; do not use any double quotes (") inside the string content.

Coverage (ensure variety across the 20 items):
- You are only allowed to use the following 22 attributes, and no others:
  * Styles: color, font size, border radius
  * States & Interactivity: visible/hidden, hovered
  * Position & Layout: width, height, alignment (absolute/relative), zIndex
  * Content: exact text
  * Media: playing
  * Dynamics: transition, scroll
  * Text: altText
  * Data: count
  * Image: source, renderedDimensions
  * Accessibility: aria-label, contrastRatio
  * Repetitive/Hierarchical: nested elements check
  * Complex Visual: shape
  * More: multiple attribute comparison
- Each of the 20 descriptions must cover one or more of the above attributes. Do not generate any attributes outside this list.

Output format (must be followed exactly):
- Return ONLY a valid JSON array of exactly 20 strings.
- Use JSON double quotes for the array items (JSON requirement).
- Inside each string, do not include any double quotes; use only single quotes for quoted labels or literals.
- Do not include numbering, markdown, code fences, or any extra text outside the JSON array.

Example style (for inspiration, not to copy):
"Open 'https://www.shopdemo.com/product/123', verify that the product image has source equal to 'hero_image.jpg' and renderedDimensions of 400x300px ±2px, ensure the image has altText containing 'Premium Shoes', check that exactly count 6 thumbnails are displayed below with alignment centered and each thumbnail width 120px and height 80px, confirm the main title shows exact text 'Product Details' with font font size 18px and color '#000000', verify that the 'Buy Now' button is visible and changes to hovered state with background color '#ff0000', confirm the button has border radius of 6px and zIndex higher than 10, ensure a transition animation duration of 300ms applies when hovered, scroll the page and verify the header remains fixed (using 'scroll' behavior), check the language label has aria-label set to English and contrastRatio at least 4.5:1, validate that the comparison between the 'Price' label and the 'Discount' label shows multiple attribute comparison for font size equal at 16px."
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

def step1_analyze_task(input_file, batch_size=20):
    full_text = load_text(input_file)
    main_tasks = re.findall(r'"(.*?)"', full_text, re.DOTALL)
    print(len(main_tasks))
    task_list = []
    task_trace = []

    for start in range(0, len(main_tasks), batch_size):
        batch = main_tasks[start:start + batch_size]
        prompt = f"""You are a professional UI test case generator.
Your job is to convert the following natural language test description into a list of clear, atomic UI actions.
Follow these strict rules:
- Output must be a JSON array of arrays.
- Group related properties of the **same UI element in the same state** into one atomic task.
  - This includes all visual, layout, formatting, style, alignment, and content properties (e.g. font size, color, background, border radius, alignment).
  - Do not split alt text, watermark, natural vs rendered size, sharpness/compression, etc — if all refer to the same image in its normal state.
  - Do not separate things like color, format, alignment, font, padding, size, position, compair with another element if they belong to the same element in the same context.
  - Only separate tasks if:
    - The properties relate to **different states** (e.g., hover vs normal).
    - The properties relate to **different elements**.
    - The instruction involves a **user action** followed by a **verification** (e.g., click then check, locate then check, locate then type), or an explicit user action in between is required.
    - The instruction involves many actions (example: "Locate the 'Email' input field and enter 'invalid-email'" must be separated into 2 tasks: Locate the 'Email' input field, Enter 'invalid-email' into the 'Email' input field).
    - The behavior differs between **device types** (e.g., mobile vs desktop).
    - Action requires many steps to complete (example: Log in with the account 'patient001' and password 'Health@2023' must be separated into 2 tasks: Enter 'patient001' into the account field, Enter 'Health@2023' into the password field).
  - (Example: The 'Add to Cart' button has a color of '#ff9900', a border radius of '4px', and the background color changes to '#e68a00' on hover)
- Each array item is a single atomic test action string.
- Do not generate steps that are not described in the main task.
- Do NOT include explanations, markdown, comments, or anything else — only the JSON array.

Example:
- Requirement:
"Open 'https://www.netflix.com', click the 'Sign In' button located at the top-right corner (50px from the top edge and 30px from the right edge), enter the email 'testuser@example.com' and password 'Test@1234', submit the login form, verify that after submission, the user is redirected to 'https://www.netflix.com/browse' within 3 seconds and the page displays at least 5 personalized movie thumbnails, and ensure that all input fields have the font 'Roboto 16px', padding '12px', bottom margin '16px'; the 'Sign In' button has a background color '#e50914', text color '#ffffff', border radius '4px', is responsive down to a 360px screen width, and all elements meet a WCAG contrast ratio of at least 4.5:1.",
"Open 'https://www.amazon.com', search for 'Dàn loa Bluetooth', verify that the search completes in under 2 seconds, displays at least 10 products with titles containing 'Loa Bluetooth', confirm each product card has an image width of exactly '150px', product price has a font size of '18px', and ensure the 'Add to Cart' button has a color '#ff9900', rounded corners '4px', and hover background color changes to '#e68a00'.",
"Open 'https://shop.example.com/item/P123', verify that the main product image '#main-product-image' loads successfully within 800ms, has alt text containing 'Ví da Premium', no watermark, natural dimensions 1600x1200, displayed at 400x300 with a tolerance of ±4px, sharpness ≥ 0.85, compression artifacts ≤ 0.1, and ensure the image is positioned to the left of the price block '.price' with a minimum spacing of 24px (±2px)."
- Response:
[
  "Open 'https://www.netflix.com'",
  "Locate the 'Sign In' button at the top-right corner (50px from the top edge and 30px from the right edge)",
  "Click the 'Sign In' button",
  "Enter 'testuser@example.com' into the email input field",
  "Enter 'Test@1234' into the password input field",
  "Submit the login form",
  "Verify that after submission, the user is redirected to 'https://www.netflix.com/browse' within 3 seconds",
  "Verify that the page displays at least 5 personalized movie thumbnails",
  "Verify that all input fields have the font 'Roboto 16px', padding '12px', bottom margin '16px'",
  "Verify that the 'Sign In' button has a background color '#e50914', text color '#ffffff', border radius '4px'",
  "Verify that the 'Sign In' button is responsive down to a 360px screen width",
  "Verify that all elements meet a WCAG contrast ratio of at least 4.5:1"
],
[
  "Open 'https://www.amazon.com'",
  "Search for 'Dàn loa Bluetooth'",
  "Verify that the search completes in under 2 seconds",
  "Verify that the search results display at least 10 products with titles containing 'Loa Bluetooth'",
  "Verify that each product card has an image width of exactly '150px'",
  "Verify that the product price has a font size of '18px'",
  "Verify that the 'Add to Cart' button has a color '#ff9900' and rounded corners '4px'",
  "Verify that the 'Add to Cart' button's background color changes to '#e68a00' on hover"
],
[
  "Open 'https://shop.example.com/item/P123'",
  "Verify that the main product image '#main-product-image' loads successfully within 800ms, has alt text containing 'Ví da Premium', no watermark, natural dimensions 1600x1200, displayed at 400x300 with a tolerance of ±4px, sharpness ≥ 0.85, compression artifacts ≤ 0.1, and ensure the image is positioned to the left of the price block '.price' with a minimum spacing of 24px (±2px)"
]

Now generate the JSON from this requirement:
- Requirement:
{chr(10).join([f'{i+1}. "{t}"' for i, t in enumerate(batch)])}

Now return only the JSON array of arrays, in the same order.
"""
        retries = 3
        for attempt in range(retries):
            try:
                print("Call gemini step 1")
                response = call_gemini(prompt)
                clean_json = extract_json_from_text(response)
                result = json.loads(clean_json)
                if len(batch) == 1 and isinstance(result, list) and all(isinstance(x, str) for x in result):
                    result = [result]
                # If still not a list-of-lists with matching length → error
                if not isinstance(result, list) or len(result) != len(batch) or any(not isinstance(x, list) for x in result):
                    raise ValueError("Model did not return a valid array of arrays with matching length.")
                # Thêm từng requirement và list subtasks tương ứng
                for req_text, subtasks in zip(batch, result):
                    task_list.append(subtasks)
                    task_trace.append((req_text, subtasks))
                break
            except Exception as e:
                print(f"❌ Error (attempt {attempt + 1}/3): {e}")
                print(f"⚠️ Raw response: {response}")
                if attempt == retries - 1:
                    # Fallback: vẫn giữ chỗ bằng mảng rỗng cho đúng số lượng
                    for req_text in batch:
                        task_list.append([])
                        task_trace.append((req_text, []))
                    print("⚠️ Continued with empty results for this batch.")

    return task_list, task_trace

def step2_generate_steps(subtask_groups):
    all_step_groups = []
    step_trace = []
    for subtask_list in subtask_groups:    
        prompt = f"""You are a professional UI test step generator.
Your task is to convert the following atomic test instruction into a list of executable UI test steps in JSON format (must in English).

Instruction: "{subtask_list}"

Each step must follow this JSON structure:
{{
  "action": "action to perform (e.g. click, type, hover, locate, verify, etc.)",
  "selector": "CSS selector or a natural description (keep Vietnamese text/labels if present in the instruction, e.g. 'Login' button), or empty string if not applicable",
  "value": "string value to type or expect, or empty string if not applicable, keep Vietnamese text if provided",
  "expected": {{
    // This object may contain multiple properties,
    // based only on what the instruction requires.
    // Each key is the name of a UI property (e.g. color, font, position).
    // Each value is the expected value or structured object.
  }}
}}

Explanation of the actions:
- click, type, hover, select, submit forms, search, goto etc. (must always return 'status')
- locate: find, identifying UI elements based on text, position (e.g. near/above), or attributes (class, ID, etc.).
- verify: validating properties like color, alignment, text, count, image presence, OCR output, size, position, etc. Checking that something exists, is visible, absent, or meets a layout/appearance requirement.

Important:
- Always return output in JSON with English keys.
- All fields (`action`, `selector`, `value`, `expected`) **must always be present**.
- If a field has no value, use:
  - `""` for empty strings
  - `{{}}` for empty object (when `expected` is not needed)
- Do not omit any field from the JSON step.
- Do not include any property in `expected` if it is not clearly mentioned in the instruction.
- `expected` must be a valid object (`{{}}`), and can contain:
  - 'status': boolean (true if the action succeeds, false if it fails)
  - 'text':
  - 'placeholder':
  - 'language': e.g., `"French"`, `"Chinese"`
  - 'position': object with `x`, `y`, `width`, `height`, etc.. (e.g., 'position: {{"x": 100, "y": 200, "width": "300px", "height": "150px"}}')
  - 'overflow': boolean (true if content overflows, false if not)
  - 'occluded': boolean (true if element is occluded by another, false if not)
  - 'styles':
    - 'textAlign':
    - `color`: e.g., "#ffffff" or "rgb(255, 255, 255)" or "white"
    - `backgroundColor`
    - `font`: an object with `family`, `size`, `weight`, `style` if mentioned 
    - 'border': width, style, color, radius
    - 'padding': top, right, bottom, left
    - 'margin': top, right, bottom, left
    - 'alignment': "left", "center", "right", "justify", or horizontal/vertical alignment in pixels
    - gapPx: e.g., "10px"
    - 'opacity': "0.5", "1", etc.
    - Or any property related to 'styles', as long as it follows the correct format and rules stated (only declare if present in the input description).
  - 'state':
    - `visibility`: "visible" or "hidden"
    - `enabled`: boolean (true or false)
    - 'focused': boolean
    - 'hovered': boolean     
    - 'active': boolean
    - Or any property related to 'state', as long as it follows the correct format and rules stated (only declare if present in the input description).   
  - dynamics:
    - `movement`: "static" or "moves" after an action
    - `scroll`: "sticky" | "fixed" | "static" | "none" or something
    - 'parallax': number (e.g., `0.5` for parallax effect)
    - `transition`: boolean (CSS transition)
    - 'animate': boolean (motion effect)
    - `focus`: boolean, ('true' if element should be focused, via Tab or click)
    - `navigation`: destination URL if checking page redirection
    - `loading`: `"present", "loading", "none"` for spinners, indicators
    - 'progressValue': string, (% value if it is progress bar, pie chart, etc)
    - Or any property related to 'dynamics', as long as it follows the correct format and rules stated (only declare if present in the input description).
  - If the element is image (img), its may contain:
    - `source`: URL of the image
    - 'altText': string (e.g., "Hình ảnh sản phẩm", "Logo")
    - 'isLoaded': boolean (true if image is loaded, false if not)
    - 'loadTime': number (in milliseconds, e.g., 500 for 0.5 seconds)
    - 'shapnessScoreGTE': number (0 to 1, e.g., 0.8 for sharpness)
    - 'compressionArtifactsLTE': number (0 to 1, e.g., 0.2 for compression artifacts)
    - 'renderedDimensions': object with `width`, `height`, 'tolerancePx' (in pixels, e.g., 300x200)
    - 'naturalDimensions': object with `width`, `height` (natural size of the image)
    - 'viewportDimensions': object with `width`, `height` (size of the image in the viewport)
    - 'watermark': boolean (true if image has a watermark, false if not)
  - 'compair': if comparing with another element, it may contain:
    - 'element': object describing the element to compare with (must always have when `compare` is used). (if there are multiple elements to compare, use 'element1', 'element2', etc.)
      - This object may contain `selector` (required), and may also include `action`, `value`, 'expected' only if explicitly described in the task.  
      - `expected` follows the same structure and rules as the `expected` field for the main element.
    - Properties to compare (e.g., `color`, `fontSize`, `position`, etc.)
  - Or any property related to expected , as long as it follows the correct format and rules stated (only declare if present in the input description).

Example 1:
- Task list:
[
  "Open 'https://www.amazon.com'",
  "Search for 'Dàn loa Bluetooth'",
  "Verify that the search completes in under 2 seconds",
  "Verify that the search results display at least 10 products with titles containing the word 'Loa Bluetooth'",
  "Verify that each product card has a main image width exactly '150px'",
  "Verify that the 'Add to Cart' button has color '#ff9900' and border radius '4px', positioned at x=120px and y=300px, with width '200px' and height '50px'",
  "Verify that the 'Add to Cart' button background color changes to '#e68a00' when hovered"
]
- Response:
[
  {{
    "action": "goto",
    "selector": "",
    "value": "https://www.amazon.com",
    "expected": {{
      "status": true,
      "navigation": "https://www.amazon.com"
    }}
  }},
  {{
    "action": "search",
    "selector": "'Search' input field",
    "value": "Dàn loa Bluetooth",
    "expected": {{
      "status": true
    }}
  }},
  {{
    "action": "verify",
    "selector": "search results",
    "value": "",
    "expected": {{
      "state": {{
        "visibility": "visible"
      }},
      "dynamics": {{
        "duration": 2000
      }}
    }}
  }},
  {{
    "action": "verify",
    "selector": ".search-results .product-title",
    "value": "",
    "expected": {{
      "count": {{
        "min": 10
      }},
      "text": {{
        "contains": "Loa Bluetooth"
      }}
    }}
  }},
  {{
    "action": "verify",
    "selector": "'product card'",
    "value": "",
    "expected": {{
      "img": {{
        "styles": {{
          "width": "150px"
        }}
      }}
    }}
  }},
  {{
    "action": "verify",
    "selector": "'Add to Cart' button",
    "value": "",
    "expected": {{
      "text": "Add to Cart",
      "styles": {{
        "color": "#ff9900",
        "border": {{
          "radius": "4px"
        }}
      }},
      "position": {{
        "x": "120px",
        "y": "300px",
        "width": "200px",
        "height": "50px"
      }}
    }}
  }},
  {{
    "action": "verify",
    "selector": "'Add to Cart' button",
    "value": "",
    "expected": {{
      "text": "Add to Cart",
      "state": {{
        "hovered": true
      }},
      "styles": {{
        "backgroundColor": "#e68a00"
      }}
    }}
  }}
]

Example 2:
- Task list:
[
  "Locate the 'Login' button at the top right corner (50px from the top and 30px from the right)",
  "Click the 'Login' button",
  "Type 'testuser@example.com' into the email input field",
  "Type 'Test@1234' into the password input field",
  "Submit the login form",
  "Verify that after submission, the user is redirected to 'https://www.netflix.com/browse' within 3 seconds",
  "Verify that the page displays at least 5 personalized movie thumbnails",
  "Verify that all input fields have font 'Roboto 16px', padding '12px', and margin-bottom '16px'",
  "Verify that the 'Sign In' button has background color '#e50914', text color '#ffffff', and border radius '4px'",
  "Verify that the 'Sign In' button is responsive down to screen width 360px",
  "Verify that all visible elements meet a WCAG contrast ratio of at least 4.5:1"
]
- Response:
[
  {{
    "action": "locate",
    "selector": "'Login' button",
    "value": "",
    "expected": {{
      "status": true,
      "text": "Login",
      "position": {{
        "top": "50px",
        "right": "30px"
      }}
    }}
  }},
  {{
    "action": "click",
    "selector": "'Login' button",
    "value": "",
    "expected": {{
      "status": true,
    }}
  }}
  {{
    "action": "type",
    "selector": "email input field",
    "value": "testuser@example.com",
    "expected": {{
      "status": true
    }}
  }},
  {{
    "action": "type",
    "selector": "password input field",
    "value": "Test@1234",
    "expected": {{
      "status": true
    }}
  }},
  {{
    "action": "submit",
    "selector": "login form",
    "value": "",
    "expected": {{
      "status": true,
      "dynamics": {{
        "submit": true
      }}
    }}
  }},
  {{
    "action": "verify",
    "selector": "",
    "value": "",
    "expected": {{
      "dynamics": {{
        "navigation": "https://www.netflix.com/browse",
        "timeout": 3000
      }}
    }}
  }},
  {{
    "action": "verify",
    "selector": "personalized movie thumbnails",
    "value": "",
    "expected": {{
      "count": {{
        "min": 5
      }}
    }}
  }},
  {{
    "action": "verify",
    "selector": "input",
    "value": "",
    "expected": {{
      "styles": {{
        "font": {{
          "family": "Roboto",
          "size": "16px"
        }},
        "padding": {{
          "top": "12px",
          "right": "12px",
          "bottom": "12px",
          "left": "12px"
        }},
        "margin": {{
          "bottom": "16px"
        }}
      }}
    }}
  }},
  {{
    "action": "verify",
    "selector": "'Login' button",
    "value": "",
    "expected": {{
      "text": "Login",
      "styles": {{
        "backgroundColor": "#e50914",
        "color": "#ffffff",
        "border": {{
          "radius": "4px"
        }}
      }}
    }}
  }},
  {{
    "action": "verify",
    "selector": "'Login' button",
    "value": "",
    "expected": {{
      "text": "Login",
      "screenWidth": "360px",
      "state": {{
        "visibility": "visible",
        "enabled": true
      }}
    }}
  }},
  {{
    "action": "verify",
    "selector": "all visible elements",
    "value": "",
    "expected": {{
      "accessibility": {{
        "contrastRatio": "at least 4.5:1"
      }}
    }}
  }}
]

Example 3:
- Task list:
[
  "Open 'https://shop.example.com/item/P123'",
  "Verify that the main product image '#main-product-image' loads successfully within 800ms, has alt text containing 'Premium Leather Wallet', has no watermark, natural size 1600x1200, renders at 400x300 with tolerance ±4px, sharpness ≥ 0.85 and compression artifacts ≤ 0.1, and ensure the image is positioned to the left of the price block '.price' with a minimum gap of 24px (±2px)"
]
- Response:
[
  {{
    "action": "goto",
    "selector": "",
    "value": "https://shop.example.com/item/P123",
    "expected": {{
      "status": true,
      "navigation": "https://shop.example.com/item/P123"
    }}
  }},
  {{
    "action": "verify",
    "selector": "#main-product-image",
    "value": "",
    "expected": {{
      "isLoaded": true,
      "loadTime": {{
        "max": 800
      }},
      "altText": {{
        "contains": "Premium Leather Wallet"
      }},
      "watermark": false,
      "naturalDimensions": {{
        "width": 1600,
        "height": 1200
      }},
      "renderedDimensions": {{
        "width": 400,
        "height": 300,
        "tolerancePx": 4
      }},
      "shapnessScoreGTE": {{
        "min": 0.85
      }},
      "compressionArtifactsLTE": {{
        "max": 0.1
      }},
      "compair": {{
        "element": {{
          "selector": ".price"
        }},
        "position": "left",
        "gapPx": {{
          "min": 24,
          "tolerancePx": 2
        }}
      }}
    }}
  }}
]

Example 4:
- Task list:
[
  "Click on contact 'Nguyen Van An'",
  "Type 'Hello' into the message input field with height '40px' and font size '14px'",
  "Send the message",
  "Verify that the sent message appears in the chat window within 1 second, with background color '#dcf8c6', right-aligned, and the message timestamp formatted in '12-hour' style, aligned to the bottom-right corner inside the chat window"
]

- Response:
[
  {{
    "action": "click",
    "selector": "'Nguyen Van An' contact",
    "value": "",
    "expected": {{
      "status": true
    }}
  }},
  {{
    "action": "type",
    "selector": "'message' input",
    "value": "Hello",
    "expected": {{
      "status": true,
      "styles": {{
        "height": "40px",
        "fontSize": "14px"
      }},
    }}
  }},
  {{
    "action": "submit",
    "selector": "'send message' button",
    "value": "",
    "expected": {{
      "status": true
    }}
  }},
  {{
    "action": "verify",
    "selector": "'sent message bubble'",
    "value": "",
    "expected": {{
      "state": {{
        "visibility": true,
        "alignment": {{
          'horizontal': 'right',
          'vertical': 'bottom'
        }}
      }},
      'styles': {{
        'backgroundColor': '#dcf8c6',
      }},
      'dynamics': {{
        'timeout': 1000
      }},
      'timestamp': {{
        'format': '12-hour',
        'alignment': 'bottom-right'
      }}
    }}
  }}
]

Example 5:
- Task list:
[
  "Verify that the error message text 'Invalid account.' is displayed",
  "Verify that the font size and color of the error message are exactly the same as the font size and color of the 'Account' label and the 'Password' label, and ensure that both are exactly 20px and '#ff0000'"
]
- Response:
[
  {{
    "action": "verify",
    "selector": "error message",
    "value": "",
    "expected": {{
      "text": "Invalid account.",
      "state": {{
        "visibility": "visible"
      }}
    }}
  }},
  {{
    "action": "verify",
    "selector": "error message",
    "value": "",
    "expected": {{
      "style": {{
        "font": {{
          "size": "20px"
        }},
        "color": "#ff0000"
      }},
      "compair": {{
        "element1": {{
          "selector": "'Account' label",
          "expected": {{
            "style": {{
              "font": {{
                "size": "20px"
              }},
              "color": "#ff0000"
            }}
          }}
        }},
        "element2": {{
          "selector": "'Password' label",
          "expected": {{
            "style": {{
              "font": {{
                "size": "20px"
              }},
              "color": "#ff0000"
            }}
          }}
        }}
      }}
    }}
  }}
]

Notes:
- Each atomic test instruction return only ONE test steps, NO splitting the instruction into multiple substeps.
- The selector can be a CSS selector or a natural-language reference to the element.
- UI may be implemented using any frontend framework (e.g., TailwindCSS, Bootstrap, raw HTML).
- Return only a JSON array. No explanation. No markdown.

Now generate the JSON array of steps for the instruction above.
"""
        retries = 3
        for attempt in range(retries): 
            try:
                print("Call gemini step 2")
                response = call_gemini(prompt)
                clean = extract_json_from_text(response)
                steps = json.loads(clean)
                # Kiểm tra cơ bản: mảng và cùng độ dài với subtask_list
                if not isinstance(steps, list) or len(steps) != len(subtask_list):
                    raise ValueError("Model did not return a JSON array with the same length as input.")
                # Bảo đảm mỗi phần tử có đủ 4 khóa, điền mặc định nếu thiếu
                normalized = []
                for idx, st in enumerate(steps):
                    if not isinstance(st, dict):
                        raise ValueError(f"Step at index {idx} is not an object.")
                    action = st.get("action", "")
                    selector = st.get("selector", "")
                    value = st.get("value", "")
                    expected = st.get("expected", {})
                    if expected is None or not isinstance(expected, dict):
                        expected = {}
                    step_obj = {
                        "action": action if isinstance(action, str) else "",
                        "selector": selector if isinstance(selector, str) else "",
                        "value": value if isinstance(value, str) else "",
                        "expected": expected
                    }
                    normalized.append(step_obj)

                    # Lưu trace (mỗi subtask -> đúng 1 step)
                    step_trace.append((subtask_list[idx], [step_obj]))
                step_group = normalized
                break
            except Exception as e:
                print(f"❌ Error (attempt {attempt + 1}/3): {e}")
                print(f"⚠️ Raw response: {response}")
                if attempt == retries - 1:
                    # Fallback: tạo step rỗng giữ chỗ (để pipeline không gãy)
                    step_group = [{
                        "action": "",
                        "selector": "",
                        "value": "",
                        "expected": {}
                    } for _ in subtask_list]
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
    #global KEY_LIST
    inputName = input("Enter the base name for input files: ")
    #key1 = input("Enter the Gemini API key1: ")
    #key2 = input("Enter the Gemini API key2: ")
    #key3 = input("Enter the Gemini API key3: ")
    #key4 = input("Enter the Gemini API key4: ")
    #key5 = input("Enter the Gemini API key5: ")
    #key6 = input("Enter the Gemini API key6: ")
    #key7 = input("Enter the Gemini API key7: ")
    #key8 = input("Enter the Gemini API key8: ")
    #KEY_LIST = [key1, key2, key3, key4, key5, key6, key7, key8]

    INPUT_DIR = Path("Input")
    TASK_DIR = Path("JSONtask")
    STEP_DIR = Path("JSONwStep")
    REPORT_DIR = Path("Report")
    for d in [TASK_DIR, STEP_DIR, REPORT_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    numFile = 20
    print(f"Generate {numFile} files")
    for i in range(numFile):
        filename = f"{inputName}_{i}.txt"
        if not (INPUT_DIR / filename).exists():
            print(f"Creating example file: {filename}")
            step0_create_task(filename)
        else:
            print(f"File already exists: {filename}")
        case_id = Path(filename).stem
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

if __name__ == "__main__":
    main()

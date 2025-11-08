# app.py (fixed version)
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import requests
import re
import io
import pdfplumber
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
import os
import base64
import matplotlib.pyplot as plt
import random
import time
import traceback

load_dotenv()

# LLM client -- configured for aiPipe (keep if that's your provider)
client = OpenAI(
    api_key=os.getenv("AIPIPE_TOKEN"),
    base_url="https://aipipe.org/openai/v1"
)

def decide_task(question_text):
    """
    Uses LLM to analyze the question text and decide what type of task this is.
    Returns a single category string (lowercase).
    """
    prompt = f"""
You are an AI agent helping to categorize quiz questions into task types.
Question:
{question_text}

Choose the most likely category (respond with exactly one of the following words):
pdf_sum, csv_sum, api_fetch, visualization, text_analysis
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=16
        )
        category = response.choices[0].message.content.strip().lower()
        return category
    except Exception:
        # fallback heuristic
        txt = question_text.lower()
        if "pdf" in txt or "page" in txt:
            return "pdf_sum"
        if "csv" in txt or "excel" in txt or ".csv" in txt:
            return "csv_sum"
        if "chart" in txt or "plot" in txt or "visualize" in txt:
            return "visualization"
        return "text_analysis"

def solve_quiz(page_text: str):
    """
    Finds a downloadable file link in the page_text and tries to parse it.
    Returns (answer, reason) where reason is None on success, otherwise a string.
    """
    link_match = re.search(r'https?://[^\s"<>]+?\.(pdf|csv|xlsx|xls)', page_text, flags=re.IGNORECASE)
    if not link_match:
        return None, "No file link found."

    file_url = link_match.group(0)
    file_type = file_url.split(".")[-1].lower()

    try:
        resp = requests.get(file_url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        return None, f"Failed to download file: {e}"

    try:
        if file_type == "pdf":
            with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                if len(pdf.pages) < 2:
                    return None, "PDF does not have page 2."
                tables = pdf.pages[1].extract_tables()
                if not tables or not tables[0]:
                    return None, "No table found on page 2."
                header = tables[0][0]
                rows = tables[0][1:]
                df = pd.DataFrame(rows, columns=header)
        elif file_type == "csv":
            # allow pandas to read from bytes
            df = pd.read_csv(io.BytesIO(resp.content))
        elif file_type in ("xlsx", "xls"):
            df = pd.read_excel(io.BytesIO(resp.content))
        else:
            return None, "Unsupported file type."

        # normalize columns
        df.columns = [str(c).strip().lower() for c in df.columns]

        if "value" not in df.columns:
            return None, f"'value' column not found. Columns: {list(df.columns)}"

        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        total = df["value"].sum(skipna=True)
        # if float but integral, cast to int
        if pd.isna(total):
            return None, "Sum resulted in NaN."
        if abs(total - int(total)) < 1e-9:
            answer = int(total)
        else:
            answer = float(total)

        return answer, None
    except Exception as e:
        return None, f"Error parsing data: {e}"

def generate_chart_base64(chart_type="bar", width=600, height=360, dpi=80):
    """
    Generates a chart (default bar) and returns a base64 data URI.
    The function attempts to ensure the final base64 payload is < 1MB; if not,
    it will downscale the image once before returning.
    """
    # Dummy data for demo (replace with quiz data in real solver)
    categories = ["A", "B", "C", "D"]
    values = [random.randint(10, 80) for _ in categories]

    def _create_image(w, h, d):
        fig, ax = plt.subplots(figsize=(w / d, h / d), dpi=d)
        if chart_type == "bar":
            ax.bar(categories, values)
        elif chart_type == "line":
            ax.plot(categories, values, marker='o')
        elif chart_type == "pie":
            ax.pie(values, labels=categories, autopct='%1.1f%%')
        else:
            ax.bar(categories, values)
        ax.set_title(f"{chart_type.title()} Chart")
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    # Create image and check size
    img_bytes = _create_image(width, height, dpi)
    image_b64 = base64.b64encode(img_bytes).decode("utf-8")
    # If > 1MB (about 1,000,000 chars), downscale once
    if len(image_b64) > 950_000:
        # downscale
        img_bytes = _create_image(int(width * 0.6), int(height * 0.6), dpi)
        image_b64 = base64.b64encode(img_bytes).decode("utf-8")

    # final check
    if len(image_b64) > 1_000_000:
        return None  # too large to include
    return f"data:image/png;base64,{image_b64}"

def solve_and_submit_quiz(email, secret, start_url, overall_timeout=180):
    """
    Solves quizzes in a chain; enforces an overall timeout (seconds).
    Returns a list of result dicts (chain_log).
    """
    start_time = time.time()
    deadline = start_time + overall_timeout

    current_url = start_url
    chain_log = []

    while current_url:
        # enforce overall timeout
        if time.time() > deadline:
            chain_log.append({"quiz_url": current_url, "error": "Overall timeout exceeded (3 minutes)."})
            break

        try:
            # load page with Playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(current_url, timeout=60000)
                try:
                    page.wait_for_selector("#result", timeout=8000)
                except Exception:
                    # even if #result doesn't appear, continue
                    pass
                page.wait_for_timeout(3000)
                page_text = page.content()
                browser.close()

            # detect task
            category = decide_task(page_text)
            print(f"Solving {current_url} | category: {category}")

            if "pdf" in category or "csv" in category:
                answer, reason = solve_quiz(page_text)
                if answer is None:
                    # failed to solve; record reason and stop or attempt re-submit fallback
                    chain_log.append({"quiz_url": current_url, "correct": False, "reason": reason})
                else:
                    pass  # answer ready
            elif "visualization" in category:
                answer = generate_chart_base64("bar")
                if answer is None:
                    chain_log.append({"quiz_url": current_url, "correct": False, "reason": "Visualization too large to submit."})
            else:
                # fallback: simple text parsing or fail-safe
                answer = "test"
                reason = "fallback"

            # find submit URL on page (do not hardcode)
            submit_url_match = re.search(r'https?://[^\s"<>]+/submit', page_text, flags=re.IGNORECASE)
            if not submit_url_match:
                chain_log.append({"quiz_url": current_url, "error": "Submit URL not found on page."})
                break
            submit_url = submit_url_match.group(0)

            # ensure answer size under 1MB (encoded)
            payload = {
                "email": email,
                "secret": secret,
                "url": current_url,
                "answer": answer
            }

            # quick size check (approx)
            import json
            payload_text = json.dumps(payload)
            if len(payload_text.encode("utf-8")) > 1_000_000:
                chain_log.append({"quiz_url": current_url, "error": "Payload too large (>1MB)."})
                break

            # submit
            response = requests.post(submit_url, json=payload, timeout=30)
            result = response.json()

            chain_log.append({
                "quiz_url": current_url,
                "submit_url": submit_url,
                "correct": result.get("correct"),
                "reason": result.get("reason"),
                "next_url": result.get("url")
            })

            # follow next_url if present and still within time
            next_url = result.get("url")
            if not next_url:
                break
            current_url = next_url

        except Exception as exc:
            # catch any error and include traceback for easier debug (not exposing secrets)
            tb = traceback.format_exc()
            chain_log.append({"quiz_url": current_url, "error": str(exc), "trace": tb})
            break

    return chain_log

# Flask app
app = Flask(__name__)
SECRET = os.getenv("SECRET")

@app.route("/api", methods=["POST"])
def handle_request():
    # parse JSON safely
    try:
        data = request.get_json(force=True)
    except Exception as e:
        return jsonify({"error": "Invalid JSON", "details": str(e)}), 400

    if not all(k in data for k in ["email", "secret", "url"]):
        return jsonify({"error": "Missing required fields"}), 400

    if data["secret"] != SECRET:
        return jsonify({"error": "Invalid secret"}), 403

    # run solver & chain (enforce 3 minute deadline here as well)
    chain_log = solve_and_submit_quiz(email=data["email"], secret=data["secret"], start_url=data["url"], overall_timeout=180)

    return jsonify({"message": "Quiz chain executed", "chain_log": chain_log}), 200

if __name__ == "__main__":
    # production friendly binding (Railway / Docker / etc.)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

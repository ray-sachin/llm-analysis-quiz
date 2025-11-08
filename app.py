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
import io
import random

load_dotenv()
client = OpenAI(
    api_key=os.getenv("AIPIPE_TOKEN"),
    base_url="https://aipipe.org/openai/v1"  # This is critical for aiPipe!
)

def decide_task(question_text):
    """
    Uses LLM to analyze the question text and decide what type of task this is.
    Returns one of: 'pdf_sum', 'csv_sum', 'api_fetch', 'visualization', 'text_analysis', etc.
    """
    prompt = f"""
    You are an AI agent helping to categorize quiz questions into task types.
    Question:
    {question_text}

    Choose the most likely category:
    1. pdf_sum → involves summing or extracting data from a PDF file
    2. csv_sum → involves summing or filtering data from a CSV or Excel file
    3. api_fetch → involves calling an API or extracting from JSON
    4. visualization → involves generating a chart or base64 image
    5. text_analysis → involves extracting or counting from plain text

    Respond ONLY with one category name.
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    category = response.choices[0].message.content.strip().lower()
    return category

def solve_quiz(page_text: str):
    """
    Looks through the quiz text for a downloadable file,
    downloads it, tries to find a table, and sums the 'value' column.
    Returns either (answer, reason).
    """
    # find a downloadable link
    import re
    link_match = re.search(r'https?://[^\s"]+\.(pdf|csv|xlsx?)', page_text)
    if not link_match:
        return None, "No file link found."

    file_url = link_match.group(0)
    file_type = file_url.split(".")[-1].lower()

    # download the file
    try:
        resp = requests.get(file_url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        return None, f"Failed to download file: {e}"

    try:
        if file_type == "pdf":
            with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                # crude: assume page 2 exists
                tables = pdf.pages[1].extract_tables()
                df = pd.DataFrame(tables[0][1:], columns=tables[0][0])
        elif file_type in ("csv", "xlsx", "xls"):
            if file_type == "csv":
                df = pd.read_csv(io.BytesIO(resp.content))
            else:
                df = pd.read_excel(io.BytesIO(resp.content))
        else:
            return None, "Unsupported file type."

        # clean column names
        df.columns = [c.strip().lower() for c in df.columns]

        if "value" not in df.columns:
            return None, f"'value' column not found. Columns: {df.columns}"

        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        answer = int(df["value"].sum())

        return answer, None
    except Exception as e:
        return None, f"Error parsing data: {e}"


app = Flask(__name__)

SECRET = os.getenv("SECRET")

@app.route("/api", methods=["POST"])

def generate_chart_base64(chart_type="bar"):
    """
    Generates a sample chart (bar/line/pie) and returns its Base64 string.
    Replace the dummy data with real quiz data later.
    """
    # Dummy data for demo
    categories = ["A", "B", "C", "D"]
    values = [random.randint(10, 80) for _ in categories]

    # Create chart
    fig, ax = plt.subplots(figsize=(5, 3))
    if chart_type == "bar":
        ax.bar(categories, values)
    elif chart_type == "line":
        ax.plot(categories, values, marker='o')
    elif chart_type == "pie":
        ax.pie(values, labels=categories, autopct='%1.1f%%')
    else:
        ax.bar(categories, values)

    ax.set_title(f"{chart_type.title()} Chart Example")
    plt.tight_layout()

    # Save to memory
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)

    # Convert to Base64 string
    image_b64 = base64.b64encode(buf.read()).decode("utf-8")
    return f"data:image/png;base64,{image_b64}"

def solve_and_submit_quiz(email, secret, start_url):
    """
    Solves a quiz, submits the answer, and continues automatically
    if the response includes a 'url' for the next quiz.
    """
    current_url = start_url
    chain_log = []  # to store results of each quiz

    while current_url:
        try:
            # --- Load quiz page ---
            with sync_playwright() as p:
                browser = p.firefox.launch(headless=True)
                page = browser.new_page()
                page.goto(current_url, timeout=60000)
                page.wait_for_timeout(2000)
                page_text = page.inner_text("body")
                browser.close()

            # --- Decide type of task ---
            category = decide_task(page_text)
            print(f"🤖 Solving quiz at {current_url} | Category: {category}")

            # --- Choose solver ---
            if "pdf" in category or "csv" in category:
                answer, reason = solve_quiz(page_text)
            elif "visualization" in category:
                answer, reason = generate_chart_base64("bar"), None
            else:
                answer, reason = "test", "default fallback"

            # --- Find submit URL ---
            submit_url_match = re.search(r'https://[^\s"]+/submit', page_text)
            if not submit_url_match:
                chain_log.append({"url": current_url, "status": "No submit URL found"})
                break

            submit_url = submit_url_match.group(0)

            # --- Submit answer ---
            answer_payload = {
                "email": email,
                "secret": secret,
                "url": current_url,
                "answer": answer
            }

            response = requests.post(submit_url, json=answer_payload, timeout=30)
            result = response.json()

            # --- Record result ---
            chain_log.append({
                "quiz_url": current_url,
                "correct": result.get("correct"),
                "reason": result.get("reason"),
                "next_url": result.get("url")
            })

            # --- Continue or stop ---
            next_url = result.get("url")
            if not next_url:
                print("✅ No more quizzes left — chain completed.")
                break
            else:
                print(f"➡️ Moving to next quiz: {next_url}")
                current_url = next_url

        except Exception as e:
            chain_log.append({"url": current_url, "error": str(e)})
            break

    return chain_log

def handle_request():
    try:
        data = request.get_json(force=True)
    except Exception as e:
        return jsonify({"error": "Invalid JSON", "details": str(e)}), 400

    # Basic validation
    if not all(k in data for k in ["email", "secret", "url"]):
        return jsonify({"error": "Missing required fields"}), 400

    if data["secret"] != SECRET:
        return jsonify({"error": "Invalid secret"}), 403

    # Start solving (and auto-chain)
    chain_log = solve_and_submit_quiz(
        email=data["email"],
        secret=data["secret"],
        start_url=data["url"]
    )

    return jsonify({
        "message": "Quiz chain executed successfully!",
        "chain_log": chain_log
    }), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

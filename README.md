# LLM Analysis Quiz – Autonomous Data Reasoning Agent

An AI-powered Flask application that autonomously solves data-related quizzes using LLMs (Large Language Models).  
It analyzes natural-language quiz pages (including JavaScript-rendered pages), downloads and processes data (PDF/CSV/Excel), generates visualizations as base64 PNGs when required, and automatically follows chained quiz URLs until the chain ends.

---

Project structure:
```
project/
├── app.py               # Main Flask application
├── requirements.txt     # Python dependencies
├── .env                 # Secret environment variables
├── README.md            # Project documentation
└── (optional) solver.py # Helper modules
```

---

## Features

- Flask API endpoint to receive evaluator POST requests  
- Secret validation for request authentication  
- Playwright integration for JS-rendered pages  
- LLM-based task classification (via aiPipe/OpenAI)  
- PDF / CSV / Excel parsing and numeric analysis  
- Visualization generation (matplotlib) and base64 encoding  
- Automatic quiz chaining: follows `url` returned by server until completion  
- Clear JSON responses and error handling

---

## Setup

1. Clone the repo
```bash
git clone https://github.com/<your-username>/llm-analysis-quiz.git
cd llm-analysis-quiz
```

2. Create and activate a virtual environment
```bash
python -m venv venv
# macOS / Linux
source venv/bin/activate
# Windows (PowerShell)
venv\Scripts\Activate.ps1
```

3. Create `.env` in project root with:
```
SECRET=sachin
AIPIPE_TOKEN=your_aiPipe_api_key_here
```

4. Install dependencies
```bash
pip install -r requirements.txt
playwright install
```

---

## How It Works (high-level)

1. Evaluator sends POST to `/api` with JSON:
```json
{
  "email": "your_email",
  "secret": "your_secret",
  "url": "https://tds-llm-analysis.s-anand.net/demo"
}
```
2. App validates secret.  
3. App opens the provided `url` with Playwright (to execute JS and get rendered content).  
4. App sends the page text to an LLM to determine the task category (pdf_sum, csv_sum, visualization, api_fetch, text_analysis, etc.).  
5. App runs the appropriate solver:
   - For PDFs/CSVs: download, parse, compute (e.g., sum a column)  
   - For visualizations: build a chart and return as base64 PNG (`data:image/png;base64,...`)  
   - For API/text tasks: extract/compute as required  
6. App finds the submit URL on the page and POSTs the answer JSON:
```json
{
  "email": "your_email",
  "secret": "your_secret",
  "url": "current_quiz_url",
  "answer": <computed value or base64 image or JSON>
}
```
7. If server response includes `"url"`, the app repeats the process for the new URL until no `url` is returned.

---

## API

**Endpoint**
```
POST /api
```

**Request**
```json
{
  "email": "string",
  "secret": "string",
  "url": "string"
}
```

**Successful Response**
```json
{
  "message": "Quiz chain executed successfully!",
  "chain_log": [
    {
      "quiz_url": "https://.../demo",
      "correct": true,
      "reason": "",
      "next_url": "https://.../next"
    },
    {
      "quiz_url": "https://.../next",
      "correct": true,
      "reason": "",
      "next_url": null
    }
  ]
}
```

**HTTP status codes**
- `200` — OK (valid request, processed)
- `400` — Bad Request (invalid JSON / missing fields)
- `403` — Forbidden (invalid secret)
- `500` — Server error (page load, parsing, or submission failures)

---

## Supported Task Types

- **pdf_sum** — Extract tables from PDF (using pdfplumber) and compute numeric aggregates (e.g., sum of a named column). Output: integer or float.  
- **csv_sum** — Read CSV/Excel with pandas and compute aggregates. Output: integer or float.  
- **visualization** — Generate chart (bar/line/pie) with matplotlib, return base64-encoded PNG. Output: `data:image/png;base64,...`.  
- **api_fetch** — Call downstream APIs or parse JSON payloads as needed. Output: JSON/string.  
- **text_analysis** — Extract or summarize text content; count occurrences, etc. Output: string or number.

---

## Implementation Notes

- Playwright is required to render JS-driven quiz pages; do not rely on `requests` alone.  
- Keep `.env` private (do not commit to GitHub). Use Render / environment variables in production.  
- The LLM reasoning step helps choose which solver to run; you can add more solvers for niche tasks.  
- Responses must be returned/submitted within the evaluator’s time constraint (3 minutes per initial POST).  
- Ensure submitted JSON payload is under 1 MB (the quiz spec limit).

---

## Deployment (Render quick guide)

1. Push to GitHub:
```bash
git add .
git commit -m "Initial"
git push origin main
```
2. On Render:
- New → Web Service → connect repo  
- Build command:
```
pip install -r requirements.txt && playwright install
```
- Start command:
```
python app.py
```
- Add environment variables:
  - `SECRET` = your secret
  - `AIPIPE_TOKEN` = your aiPipe/OpenAI token

3. After deployment, the endpoint will be:
```
https://<your-service>.onrender.com/api
```
Test with curl the same sample payload used locally.

---

## Troubleshooting

- If Playwright fails on the host, ensure `playwright install` ran successfully and the host supports the browser binaries.  
- If `os` / built-in import errors appear in pip, ignore them — `os` is part of Python standard library.  
- If LLM calls fail, confirm API key and base URL are set in `.env`.  
- Use Render logs to debug runtime issues (browser timeouts, network access).

---

## Example: visualization output format

When the quiz expects an image/chart as the answer, the app returns:
```
data:image/png;base64,iVBORw0KGgoAAAANSUhEUg...
```
This string can be directly embedded in HTML `<img src="...">` or posted as the `"answer"` field in JSON.

---

## Security and Ethics

- Keep your API keys and `SECRET` private.  
- Don’t hardcode evaluator URLs — always read them from the quiz page.  
- Respect rate limits for downstream APIs and the LLM provider.

---

## Author

Sachin Kumar Ray
---
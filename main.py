from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import sys
from io import StringIO
import traceback
import os

from google import genai
from google.genai import types

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def health():
    return {"status": "ok"}

class CodeRequest(BaseModel):
    code: str

class ResponseModel(BaseModel):
    error: List[int]
    result: str


def execute_python_code(code: str):
    old_stdout = sys.stdout
    sys.stdout = StringIO()

    try:
        exec(code)
        output = sys.stdout.getvalue()
        return {"success": True, "output": output}

    except Exception:
        output = traceback.format_exc()
        return {"success": False, "output": output}

    finally:
        sys.stdout = old_stdout


def analyze_error_with_ai(code: str, tb: str):
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    prompt = f"""
Analyze this Python code and traceback.
Return the exact line numbers where errors occur.

CODE:
{code}

TRACEBACK:
{tb}
"""

    response = client.models.generate_content(
        model="gemini-2.0-flash-exp",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema={
                "type": "object",
                "properties": {
                    "error_lines": {
                        "type": "array",
                        "items": {"type": "integer"}
                    }
                },
                "required": ["error_lines"]
            }
        )
    )

    import json
    data = json.loads(response.text)
    return data["error_lines"]


@app.post("/code-interpreter", response_model=ResponseModel)
def code_interpreter(req: CodeRequest):

    result = execute_python_code(req.code)

    if result["success"]:
        return {"error": [], "result": result["output"]}

    error_lines = analyze_error_with_ai(req.code, result["output"])

    return {"error": error_lines, "result": result["output"]}
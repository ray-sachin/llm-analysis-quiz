from google import genai
from google.genai import types
from langchain_core.tools import tool
from dotenv import load_dotenv
import os
import base64

load_dotenv()
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

@tool
def transcribe_media(filename: str, prompt: str = "Describe this audio/image in detail. If it contains speech, transcribe it verbatim.") -> str:
    """
    Analyzes or transcribes an audio or image file using Gemini's multimodal capabilities.
    Use this tool when you need to understand the content of an audio file (mp3, wav) or image (png, jpg).

    Args:
        filename (str): The name of the file to analyze (must be in LLMFiles/ directory).
        prompt (str): The instruction for the model (e.g., "Transcribe this audio", "What is in this image?").

    Returns:
        str: The transcription or description of the media.
    """
    try:
        file_path = os.path.join("LLMFiles", filename)
        if not os.path.exists(file_path):
            return f"Error: File {filename} not found in LLMFiles directory."

        # Read file bytes
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        # Determine mime type based on extension
        ext = os.path.splitext(filename)[1].lower()
        mime_type = "application/octet-stream"
        if ext in [".mp3"]: mime_type = "audio/mp3"
        elif ext in [".wav"]: mime_type = "audio/wav"
        elif ext in [".opus", ".ogg"]: mime_type = "audio/ogg"
        elif ext in [".png"]: mime_type = "image/png"
        elif ext in [".jpg", ".jpeg"]: mime_type = "image/jpeg"
        
        # Generate content with the file bytes inline (for small files) or upload
        # For simplicity and speed with small quiz files, we'll try inline data first if supported,
        # but the robust way for google-genai is often just passing the bytes with mime type.
        
        # Generate content with retry logic
        from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
        from google.api_core.exceptions import ResourceExhausted

        @retry(
            retry=retry_if_exception_type(ResourceExhausted),
            wait=wait_exponential(multiplier=2, min=4, max=60),
            stop=stop_after_attempt(10)
        )
        def generate_with_retry():
            return client.models.generate_content(
                model="gemini-2.5-flash", 
                contents=[
                    types.Content(
                        parts=[
                            types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                            types.Part.from_text(text=prompt)
                        ]
                    )
                ]
            )

        response = generate_with_retry()
        return response.text

    except Exception as e:
        return f"Error analyzing media: {str(e)}"

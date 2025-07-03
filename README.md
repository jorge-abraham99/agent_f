# NutriWise AI Agent

NutriWise is an AI-powered nutrition assistant that helps users devise, review, and iteratively refine meal plans using advanced tools for nutritional lookup, calculation, and file management.

## Requirements

- Python 3.x installed

## Setup

1. **Create and activate a virtual environment:**
    ```sh
    python3 -m venv venv
    source venv/bin/activate
    ```

2. **Install dependencies:**
    ```sh
    pip3 install -r requirements.txt
    ```

3. **Create a `.env` file in the project directory and add your Gemini API key:**
    ```
    GEMINI_API_KEY="your-api-key-here"
    ```

4. **Run the agent:**
    ```sh
    python main.py "Your prompt here"
    ```

---
This project uses the Gemini API and requires an API key set in your `.env` file.
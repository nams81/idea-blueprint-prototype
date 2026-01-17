# Idea → Business Blueprint (Prototype)

This is a minimal Streamlit prototype of an AI-guided "idea to blueprint" tool.

## What it does
- Runs an adaptive conversation (not a fixed questionnaire)
- Uses: Recognition loop → Convergence → Intent Lock → Builder Mode
- Produces an execution-ready business blueprint (Markdown export)

## Quick start
1) Create an OpenAI API key and set it as an environment variable:

   export OPENAI_API_KEY="YOUR_KEY"

2) Install dependencies:

   pip install -r requirements.txt

3) Run:

   streamlit run app.py

## Notes
- This is v0. It is designed to be tested with another person quickly.
- The AI returns structured JSON so the UI can route modes safely.

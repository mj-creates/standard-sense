# standard-sense

## Quickstart (Local Development)

Follow these 5 steps to run the StandardSense pipeline locally:

1. **Clone and Checkout Dev:**
   ```bash
   git clone <repo-url>
   cd standard-sense
   git checkout dev
   ```

2. **Set up Virtual Environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Variables:**
   Copy the example environment file and add your Groq API key:
   ```bash
   cp .env.example .env
   # Open .env and insert your GROQ_API_KEY
   ```

5. **Run the Application:**
   (Note: Backend FastAPI entry point coming soon. For now, execute individual modules via Python CLI).

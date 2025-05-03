# LearnStream ✨
### Your Personal AI Audio Learning Assistant

Turn curiosity into bite-sized audio lessons! LearnStream allows users to generate personalized, short audio snippets (~3-5 minutes) on topics they want to learn about, perfect for listening during commutes, workouts, or breaks. This project was submitted for the Global AI Hackathon.

**Demo Video:** : https://drive.google.com/file/d/1xg6AW8JxjEvmPVtysAO9KAdU_gNGR-Qm/view?usp=sharing


**Tech Video:** : https://drive.google.com/file/d/1xl20Fykf4C8pe7tBQU1KQFUR2RSRmgmh/view?usp=sharing

---

## Description

Many of us have pockets of time ideal for listening but not for reading or watching long content. LearnStream addresses this by acting as a "Spotify for Learning." Users input topics, select a narration style, and the application leverages powerful AI models (Google Gemini and ElevenLabs) to generate structured educational text and convert it into high-quality, engaging audio snippets. The result is a custom playlist ready for on-the-go learning.

## Key Features

*   **Personalized Content:** Generate audio based on specific user-provided topics.
*   **Selectable Narration Tones:** Choose between "Neutral / Informative," "Enthusiastic / Engaging," or "Calm / Relaxed" styles, influencing both the script and the voice used.
*   **AI Text Generation:** Utilizes Google Gemini (`gemini-1.5-flash-latest`) for creating structured, informative scripts.
*   **High-Quality Text-to-Speech:** Employs the ElevenLabs API for natural and realistic voice generation.
*   **In-App Playback:** Listen to generated audio snippets directly within the Streamlit application.
*   **MP3 Downloads:** Download individual snippets for offline listening.
*   **Script Visibility:** Option to view the generated text script for each snippet.
*   **Topic Suggestions:** AI-powered suggestions for related topics based on user input.
*   **Polished UI:** Clean, modern interface built with Streamlit, featuring a custom theme.

## Tech Stack

*   **Language:** Python 3.9+
*   **Web Framework:** Streamlit
*   **LLM (Text Generation):** Google Gemini API (`google-generativeai` library)
*   **Text-to-Speech (TTS):** ElevenLabs API (`elevenlabs` library)
*   **Configuration:** `python-dotenv`
*   **Core Libraries:** `os`, `re`, `time`, `logging`
*   **Environment:** Python Virtual Environment (`venv`)

## Setup and Installation

Follow these steps to set up and run LearnStream locally:

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/aaron1-z/LearnStream
    cd LearnStream
    ```

2.  **Create and Activate Virtual Environment:**
    *   It's highly recommended to use a virtual environment.
    ```bash
    # Create the environment (use python3 if python maps to python2)
    python -m venv venv

    # Activate the environment
    # Windows:
    .\venv\Scripts\activate
    # macOS / Linux:
    source venv/bin/activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure API Keys:**
    *   Copy the example environment file:
        ```bash
        # Windows:
        copy .env.example .env
        # macOS / Linux:
        cp .env.example .env
        ```
    *   **Edit the `.env` file** and add your actual API keys:
        ```dotenv
        GOOGLE_API_KEY="YOUR_GOOGLE_API_KEY_HERE"
        ELEVENLABS_API_KEY="YOUR_ELEVENLABS_API_KEY_HERE"
        ```
    *   **Get Keys:**
        *   **Google API Key:** Obtain from Google AI Studio or Google Cloud Console (ensure the Generative Language API is enabled).
        *   **ElevenLabs API Key:** Obtain from your ElevenLabs account profile page.
    *   **IMPORTANT:** The `.env` file is listed in `.gitignore` and should **never** be committed to version control.

## How to Run

1.  Make sure your virtual environment is activated.
2.  Ensure your `.env` file is correctly populated with API keys.
3.  Run the Streamlit application from the project's root directory:
    ```bash
    streamlit run app.py
    ```
4.  Open your web browser and navigate to the local URL provided by Streamlit (usually `http://localhost:8501`).

## Configuration

*   **API Keys:** Managed via the `.env` file (see Setup).
*   **UI Theme:** Controlled by `.streamlit/config.toml`.
*   **Snippet Duration:** The target length (in minutes) for generated text can be adjusted via the `SNIPPET_DURATION_MINUTES` constant near the top of `app.py`. *Note: Longer durations require more ElevenLabs credits.*
*   **Voice Mapping:** The mapping between narration tones and specific ElevenLabs voice names can be customized within the `voice_name_map` dictionary inside the `generate_audio_snippet_elevenlabs` function in `app.py`. Ensure the voice names match those available in your ElevenLabs account (check logs on first run or ElevenLabs website).


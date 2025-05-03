# ---------- IMPORTS ----------
import streamlit as st
import google.generativeai as genai
# *** REMOVED potentially problematic import ***
# from google.generativeai.types import generation_types
# from google.generativeai.types import GenerateContentResponse
from elevenlabs.client import ElevenLabs
from elevenlabs import save, Voice, VoiceSettings, Model
import os
import re
import time
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ---------- CONFIGURATION ----------
load_dotenv()
google_api_key = os.getenv("GOOGLE_API_KEY")
elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")

# --- Configure Google Gemini API ---
gemini_configured = False
gemini_model = None
gemini_init_error = None # Store potential init error
if google_api_key:
    try:
        genai.configure(api_key=google_api_key)
        gemini_model = genai.GenerativeModel('gemini-1.5-flash-latest')
        try:
            gemini_model.generate_content("test connection", request_options={'timeout': 15})
            gemini_configured = True
            logging.info("✅ Google Gemini API configured successfully with gemini-1.5-flash-latest.")
        except Exception as test_e:
            gemini_init_error = test_e # Store the error
            logging.warning(f"⚠ Initial Gemini test call failed: {test_e}. Continuing, but generation might fail later.")
            gemini_configured = True # Assume config itself worked, but test failed
    except Exception as e:
        gemini_init_error = e # Store the error
        logging.error(f"❌ Failed to configure Google Gemini API during initial setup: {e}", exc_info=True)
        gemini_configured = False # Config failed entirely
else:
    logging.warning("⚠ Google API Key not found in .env file.")
    gemini_configured = False

# --- Configure ElevenLabs Client ---
elevenlabs_configured = False
elevenlabs_client = None
elevenlabs_voices = {} # Cache voice names to IDs {name.lower(): id}
elevenlabs_init_error = None # Store potential init error
if elevenlabs_api_key:
    try:
        elevenlabs_client = ElevenLabs(api_key=elevenlabs_api_key)
        voices_response = elevenlabs_client.voices.get_all()
        if voices_response and voices_response.voices:
            for voice in voices_response.voices:
                elevenlabs_voices[voice.name.lower()] = voice.voice_id
            elevenlabs_configured = True
            logging.info(f"✅ ElevenLabs API configured. Found voices: {list(elevenlabs_voices.keys())}")
        else:
            logging.warning("⚠ Could not retrieve voices from ElevenLabs. Check API key/status.")
            elevenlabs_configured = False # Treat as failure if no voices found
    except Exception as e:
        elevenlabs_init_error = e # Store the error
        logging.error(f"❌ Failed to configure ElevenLabs API: {e}", exc_info=True)
        elevenlabs_configured = False
else:
    logging.warning("⚠ ElevenLabs API Key not found in .env file.")
    elevenlabs_configured = False

# --- App Constants ---
AUDIO_DIR = "audio_outputs"
SNIPPET_DURATION_MINUTES = 5
MIN_WORDS_PER_SNIPPET = 100
os.makedirs(AUDIO_DIR, exist_ok=True)

# Safety settings for Gemini
safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
]

# Generation config for Gemini
generation_config = genai.GenerationConfig(temperature=0.7)
suggestion_generation_config = genai.GenerationConfig(temperature=0.8)

# ---------- HELPER FUNCTIONS ----------

def generate_text_snippet_gemini(topic, tone, target_duration_minutes):
    """Generates an educational text snippet using Google Gemini, checking finish_reason.name."""
    if not gemini_configured or not gemini_model:
        st.error("Gemini API not configured or failed initialization. Cannot generate text.", icon="❌")
        return None

    word_count_estimate = target_duration_minutes * 150
    prompt = f"""
    Create an engaging educational audio script about: "{topic}".

    *Instructions:*
    1.  *Role:* You are an AI creating a script for a short, informative audio snippet (like a mini-podcast segment).
    2.  *Format:* Structure logically (e.g., Hook/Intro, 2-3 Key Points with clear explanations/examples, Concise Conclusion/Takeaway). Use paragraphs for readability.
    3.  *Length:* Target script length is approximately *{word_count_estimate} words*. This should translate to roughly **{target_duration_minutes} minutes** of speaking time at a moderate pace. Aim for at least {MIN_WORDS_PER_SNIPPET} words.
    4.  *Tone:* Write the entire script in a *{tone}* style.
        *   If "Neutral / Informative": Use clear, objective language. Focus on facts and direct explanations. Maintain a professional and knowledgeable voice.
        *   If "Enthusiastic / Engaging": Use vivid language, perhaps analogies or rhetorical questions. Convey curiosity and excitement about the subject matter. Make it sound interesting and dynamic.
        *   If "Calm / Relaxed": Use smooth, flowing sentences. Maintain a gentle, reassuring, and easygoing tone. Focus on clarity and simplicity, avoiding jargon where possible.
    5.  *Audience:* Assume a generally curious listener who may not have deep prior knowledge of the topic. Explain concepts clearly.
    6.  *Output:* Provide ONLY the raw script text suitable for text-to-speech. NO titles, NO section headers (like "Introduction:"), NO "Here is the script:", NO bullet points unless essential for clarity, and NO closing remarks like "I hope this helps!". Start directly with the first sentence. End directly with the last sentence. Ensure the content flows well for audio delivery.
    """
    try:
        logging.info(f"Generating text for topic: '{topic}' with tone: '{tone}'")
        response = gemini_model.generate_content(
            prompt,
            generation_config=generation_config,
            safety_settings=safety_settings,
            request_options={'timeout': 180}
        )

        if not response.candidates:
            feedback = response.prompt_feedback
            block_reason = feedback.block_reason if feedback else "Unknown"
            safety_ratings_str = str(feedback.safety_ratings) if feedback and feedback.safety_ratings else 'N/A'
            block_reason_str = f"Reason: {block_reason}. " if block_reason else ""
            st.warning(f"Text generation for '{topic}' blocked or no candidates returned. {block_reason_str}Safety: {safety_ratings_str}", icon="⚠")
            logging.warning(f"Gemini block/fail for '{topic}'. Reason: {block_reason}. Prompt Feedback: {feedback}")
            return None

        candidate = response.candidates[0]
        finish_reason = candidate.finish_reason # This is the enum instance

        # *** THE CORRECTED CHECK using finish_reason.name (string comparison) ***
        # Get the name of the finish reason (e.g., "STOP", "MAX_TOKENS", "SAFETY", etc.)
        finish_reason_name = finish_reason.name

        # Check if the name indicates a successful or acceptable completion
        if finish_reason_name not in ("STOP", "MAX_TOKENS"):
             safety_ratings_str = str(candidate.safety_ratings) if candidate.safety_ratings else 'N/A'
             st.warning(f"Text generation for '{topic}' finished unexpectedly or with issues. Reason: {finish_reason_name}. Safety: {safety_ratings_str}", icon="⚠")
             logging.warning(f"Gemini non-optimal finish for '{topic}'. Reason: {finish_reason_name}. Candidate: {candidate}")
             return None # Treat other reasons (SAFETY, RECITATION, OTHER, UNKNOWN, etc.) as failures

        # If finish_reason_name is "STOP" or "MAX_TOKENS", check content
        if candidate.content and candidate.content.parts:
            generated_text = candidate.content.parts[0].text.strip()
            word_count = len(generated_text.split())

            # *** CORRECTED CHECK using finish_reason.name ***
            if finish_reason_name == "MAX_TOKENS":
                 st.info(f"Output for '{topic}' might be truncated due to length limits (MAX_TOKENS).", icon="ℹ")
                 logging.info(f"Gemini MAX_TOKENS reached for '{topic}'. Word count: {word_count}")

            if not generated_text or word_count < MIN_WORDS_PER_SNIPPET:
                st.warning(f"Generated text for '{topic}' is too short ({word_count} words). May indicate an issue.", icon="⚠")
                logging.warning(f"Gemini generated short text for '{topic}': {word_count} words.")

            logging.info(f"Text generated successfully for '{topic}'. Word count: {word_count}")
            return generated_text
        else:
            # Handle case where finish reason was OK but no content returned
            st.error(f"No text content found in Gemini response for '{topic}', despite finish_reason {finish_reason_name}.", icon="❌")
            logging.error(f"Gemini no content parts for '{topic}'. Candidate: {candidate}")
            return None

    except Exception as e:
        st.error(f"Exception during Gemini text generation for '{topic}': {e}", icon="❌")
        logging.error(f"Exception in generate_text_snippet_gemini for '{topic}': {e}", exc_info=True)
        return None

def generate_audio_snippet_elevenlabs(text, topic, index, tone):
    """Generates an audio file from text using ElevenLabs, mapping tone to voice."""
    if not elevenlabs_configured or not elevenlabs_client:
        st.error("ElevenLabs API not configured or failed initialization. Cannot generate audio.", icon="❌")
        return None

    # --- Simple Tone to Voice Name Mapping (CUSTOMIZE THESE NAMES!) ---
    voice_name_map = {
        "neutral / informative": "daniel",
        "enthusiastic / engaging": "charlotte",
        "calm / relaxed": "sarah"
    }
    default_voice_name = "daniel"

    target_voice_name_lower = voice_name_map.get(tone.lower().strip(), default_voice_name).lower()
    voice_id = elevenlabs_voices.get(target_voice_name_lower)

    if not voice_id:
        st.warning(f"Voice '{target_voice_name_lower}' (for tone '{tone}') not found in available voices: {list(elevenlabs_voices.keys())}. Trying first available voice.", icon="⚠")
        logging.warning(f"Voice '{target_voice_name_lower}' not found. Available: {list(elevenlabs_voices.keys())}")
        if elevenlabs_voices:
            first_available_name = list(elevenlabs_voices.keys())[0]
            voice_id = elevenlabs_voices[first_available_name]
            target_voice_name_lower = first_available_name
            st.info(f"Using fallback voice: '{first_available_name}'", icon="ℹ")
            logging.info(f"Using fallback voice: '{first_available_name}' ({voice_id})")
        else:
            st.error("CRITICAL: No available ElevenLabs voices found in your account.", icon="❌")
            logging.error("No ElevenLabs voices available to use.")
            return None

    if not voice_id: # Final check
        st.error("Failed to select any voice ID after fallbacks.", icon="❌")
        logging.error("Failed to select any ElevenLabs voice ID.")
        return None

    safe_topic = re.sub(r'[^\w\s-]', '', topic).strip()
    safe_topic = re.sub(r'[-\s]+', '_', safe_topic).lower()
    if not safe_topic: safe_topic = f"topic_{index}"
    output_filename = f"learnstream_{index+1}_{safe_topic[:40]}.mp3"
    output_path = os.path.join(AUDIO_DIR, output_filename)

    try:
        logging.info(f"Generating audio for '{topic}' using voice ID: {voice_id} ('{target_voice_name_lower}') -> {output_path}")
        settings = VoiceSettings(stability=0.6, similarity_boost=0.7, style_exaggeration=0.1, use_speaker_boost=True)
        audio_model = "eleven_multilingual_v2"

        audio_stream = elevenlabs_client.generate(text=text, voice=Voice(voice_id=voice_id, settings=settings), model=audio_model)
        save(audio_stream, output_path)

        if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
            logging.info(f"Audio saved successfully: {output_path} ({os.path.getsize(output_path)} bytes)")
            return output_path
        else:
            error_msg = f"Failed to save audio or file is empty/too small for '{topic}'. Path: {output_path}"
            st.error(error_msg, icon="❌")
            logging.error(error_msg + f", Size: {os.path.getsize(output_path) if os.path.exists(output_path) else 'Not Found'}")
            if os.path.exists(output_path):
                try: os.remove(output_path)
                except OSError as rm_err: logging.error(f"Could not remove potentially empty file {output_path}: {rm_err}")
            return None
    except Exception as e:
        st.error(f"Exception during ElevenLabs audio generation for '{topic}': {e}", icon="❌")
        logging.error(f"Exception in generate_audio_snippet_elevenlabs for '{topic}': {e}", exc_info=True)
        if os.path.exists(output_path):
             try: os.remove(output_path)
             except OSError as rm_err: logging.error(f"Could not remove file {output_path} after error: {rm_err}")
        return None

def get_topic_suggestion_gemini(topics_list):
    """Asks Gemini to suggest ONE related topic, checking finish_reason.name."""
    if not gemini_configured or not gemini_model:
        logging.warning("Suggestion skipped - Gemini not configured or failed init.")
        return None

    valid_topics = [t for t in topics_list if t and isinstance(t, str)]
    if not valid_topics:
        logging.info("Suggestion skipped - No valid topics provided.")
        return None

    topics_str = ", ".join(valid_topics)
    prompt = f"""
    Based on a user's interest in learning about: "{topics_str}".

    Suggest exactly ONE interesting and relevant topic they might be curious about next.
    Frame the suggestion as an intriguing question or a concise statement (ideally under 15 words).
    The suggestion should feel like a natural next step or a related tangent, not just a repeat of the input.

    Examples of good suggestions:
    - What was the significance of the Enigma machine in WWII?
    - How close are we to artificial general intelligence?
    - Explore the concept of 'dark matter'.
    - Unpack the psychology behind procrastination.

    Output ONLY the single suggested topic string. No introductory phrases like "Here's a suggestion:", no lists, no explanations. Just the topic itself.
    """
    try:
        logging.info(f"Generating suggestion based on topics: {valid_topics}")
        response = gemini_model.generate_content(
            prompt,
            generation_config=suggestion_generation_config,
            safety_settings=safety_settings,
            request_options={'timeout': 60}
        )

        if not response.candidates:
             feedback = response.prompt_feedback
             block_reason = feedback.block_reason if feedback else "Unknown"
             logging.warning(f"Suggestion generation failed or blocked. Reason: {block_reason}. Response: {response}")
             return None

        candidate = response.candidates[0]
        finish_reason = candidate.finish_reason
        finish_reason_name = finish_reason.name # Get the string name

        # *** CORRECTED CHECK using finish_reason.name ***
        if finish_reason_name not in ("STOP", "MAX_TOKENS"):
            logging.warning(f"Suggestion generation finished unexpectedly. Reason: {finish_reason_name}. Candidate: {candidate}")
            return None

        if candidate.content and candidate.content.parts:
             suggestion = candidate.content.parts[0].text.strip()
             # Cleaning logic
             prefixes_to_remove = [
                "suggestion:", "topic suggestion:", "how about exploring:", "you might also like:",
                "next suggested topic:", "here's a related topic:", "related topic:",
                "topic:", "here's a suggestion:", "* ", "- ", "\n",
             ]
             original_suggestion = suggestion
             cleaned_suggestion = suggestion
             prefix_found = True
             while prefix_found:
                 prefix_found = False
                 for prefix in prefixes_to_remove:
                     if cleaned_suggestion.lower().startswith(prefix.lower()):
                         cleaned_suggestion = cleaned_suggestion[len(prefix):].strip()
                         prefix_found = True
                         break
             cleaned_suggestion = cleaned_suggestion.strip('\"\'‘’”“')

             if cleaned_suggestion:
                 logging.info(f"Suggestion generated: '{cleaned_suggestion}' (Raw: '{original_suggestion}')")
                 return cleaned_suggestion
             else:
                 logging.warning(f"Suggestion cleaning resulted in empty string. Raw: '{original_suggestion}'")
                 return None
        else:
             logging.warning(f"No content parts in suggestion response despite finish_reason {finish_reason_name}. Candidate: {candidate}")
             return None

    except Exception as e:
        logging.error(f"Exception during Gemini suggestion generation: {e}", exc_info=True)
        return None


# ---------- STREAMLIT APP UI ----------
st.set_page_config(layout="wide", page_title="LearnStream", page_icon="🎧")

st.markdown("<h1 style='text-align: center; color: #1DB954;'>✨ LearnStream ✨</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; font-size: 1.1em;'>Your Personal AI Audio Learning Assistant</p>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;'>Turn curiosity into bite-sized audio lessons for your commute, workout, or break! Powered by AI.</p>", unsafe_allow_html=True)
st.divider()

# Display API configuration status prominently
api_ok = True
# Check Google Gemini status
if not google_api_key:
     st.error("🚨 **GOOGLE_API_KEY not found in `.env` file.** Text generation is disabled.", icon="🔑")
     api_ok = False # Can't generate text, button should be disabled
elif not gemini_configured:
    st.error(f"🚨 **Google Gemini API failed to configure.** Error: {gemini_init_error}. Text generation is disabled.", icon="❌")
    api_ok = False
elif gemini_init_error: # Configured=True, but test call failed
    st.warning(f"⚠️ **Initial Gemini connection test failed:** {gemini_init_error}. Text generation might fail.", icon="⚠️")
    # Keep api_ok=True, let user try

# Check ElevenLabs status
if not elevenlabs_api_key:
     st.error("🚨 **ELEVENLABS_API_KEY not found in `.env` file.** Audio generation is disabled.", icon="🔑")
     api_ok = False # Can't generate audio, button should be disabled
elif not elevenlabs_configured:
    st.error(f"🚨 **ElevenLabs API failed to configure.** Error: {elevenlabs_init_error}. Audio generation is disabled.", icon="❌")
    api_ok = False

# --- Input Section ---
st.subheader("1. Create Your Playlist")
col1, col2 = st.columns([3, 1])
with col1:
    user_prompt = st.text_area("Enter topics (one per line):", height=175,
                               placeholder="e.g.,\n- History of the printing press\n- How neural networks learn",
                               label_visibility="collapsed", key="topic_input")
with col2:
    narration_tone = st.selectbox("Select Narration Tone:",
                                  ("Neutral / Informative", "Enthusiastic / Engaging", "Calm / Relaxed"),
                                  index=0, key="tone_select",
                                  help="Influences AI writing style and mapped voice.")
    st.caption("Customize voices in `app.py` (~line 194)") # Adjust line number if needed

# --- Generation Button & Logic ---
st.subheader("2. Generate & Listen")
process_button = st.button("🚀 Generate My Learning Playlist!", type="primary",
                           use_container_width=True, disabled=(not api_ok))

if process_button:
    if not user_prompt:
        st.warning("Please enter at least one topic.", icon="✍️")
    else:
        topics = [topic.strip() for topic in user_prompt.split('\n') if topic.strip()]
        if not topics:
            st.warning("No valid topics found. Please enter topics on separate lines.", icon="🤔")
        else:
            total_estimated_time = len(topics) * SNIPPET_DURATION_MINUTES
            st.info(f"Generating *{len(topics)} snippet(s)*... Estimated listening time: **~{total_estimated_time} minutes**. Please wait.", icon="⏳")

            all_results = [{'topic': t, 'text': None, 'audio_path': None, 'status': 'pending'} for t in topics]
            progress_area = st.empty()
            results_area = st.container()
            start_time = time.time()
            num_success_audio = 0
            num_success_text = 0

            for i, topic_data in enumerate(all_results):
                topic = topic_data['topic']
                current_progress = float(i) / len(topics)
                with progress_area.container():
                    st.progress(current_progress, text=f"Processing Topic {i+1}/{len(topics)}: \"{topic[:50]}...\"")
                    status_placeholder = st.empty()

                # 1. Generate Text
                with status_placeholder.container(): st.markdown(f"📝 Generating text for: **{topic}**...")
                generated_text = None
                try:
                    generated_text = generate_text_snippet_gemini(topic, narration_tone, SNIPPET_DURATION_MINUTES)
                except Exception as e:
                     st.error(f"Unexpected error during text generation call for '{topic}': {e}", icon="❌")
                     logging.error(f"Unexpected error calling generate_text_snippet_gemini for '{topic}': {e}", exc_info=True)

                if generated_text:
                    all_results[i]['text'] = generated_text
                    all_results[i]['status'] = 'text_complete'
                    num_success_text += 1
                    st.toast(f"Text done: '{topic[:30]}...'", icon="📄")
                else:
                    all_results[i]['status'] = 'text_failed'
                    st.toast(f"Text failed: '{topic[:30]}...'", icon="❌")
                    with progress_area.container(): st.progress(float(i + 1) / len(topics), text=f"Skipping audio for Topic {i+1} (text failed)...")
                    time.sleep(0.5); continue

                # 2. Generate Audio (only if text succeeded and ElevenLabs is configured)
                if not elevenlabs_configured:
                    all_results[i]['status'] = 'audio_skipped_config'
                    logging.warning(f"Skipping audio for '{topic}' as ElevenLabs is not configured.")
                    st.toast(f"Audio skipped (config): '{topic[:30]}...'", icon="⚙️")
                    with progress_area.container(): st.progress(float(i + 1) / len(topics), text=f"Skipping audio for Topic {i+1} (config)...")
                    time.sleep(0.5); continue

                with status_placeholder.container(): st.markdown(f"🎙️ Generating audio for: **{topic}**...")
                audio_path = None
                try:
                    audio_path = generate_audio_snippet_elevenlabs(generated_text, topic, i, narration_tone)
                except Exception as e:
                     st.error(f"Unexpected error during audio generation call for '{topic}': {e}", icon="❌")
                     logging.error(f"Unexpected error calling generate_audio_snippet_elevenlabs for '{topic}': {e}", exc_info=True)

                if audio_path:
                    all_results[i]['audio_path'] = audio_path
                    all_results[i]['status'] = 'audio_complete'; num_success_audio += 1
                    st.toast(f"Audio done: '{topic[:30]}...'", icon="🔊")
                else:
                    all_results[i]['status'] = 'audio_failed'
                    st.toast(f"Audio failed: '{topic[:30]}...'", icon="❌")

                with progress_area.container(): st.progress(float(i + 1) / len(topics), text=f"Completed Topic {i+1}/{len(topics)}...")
                time.sleep(0.1)

            # --- Finalize ---
            progress_area.empty()
            end_time = time.time()
            st.success(f"✅ Playlist generation complete in {end_time - start_time:.2f} seconds!", icon="🎉")
            if num_success_audio > 0: st.balloons()

            # --- Display Results Section ---
            with results_area:
                st.divider(); st.subheader("🎧 Your Custom Learning Playlist")
                num_total = len(all_results)
                num_failed_text = sum(1 for r in all_results if r['status'] == 'text_failed')
                num_failed_audio = sum(1 for r in all_results if r['status'] == 'audio_failed')
                num_skipped_audio_config = sum(1 for r in all_results if r['status'] == 'audio_skipped_config')

                if num_total == 0: st.info("No topics were processed.")
                elif num_success_audio == 0 and num_success_text == 0:
                    st.error("❌ Generation failed for all topics. Please check logs or try different topics/tones.", icon="🚨")
                else:
                    warnings = []
                    if num_failed_text > 0: warnings.append(f"{num_failed_text} topic(s) failed text generation")
                    if num_failed_audio > 0: warnings.append(f"{num_failed_audio} topic(s) failed audio generation")
                    if num_skipped_audio_config > 0: warnings.append(f"{num_skipped_audio_config} topic(s) skipped audio (ElevenLabs not configured)")
                    if warnings: st.warning("⚠️ Issues: " + " | ".join(warnings))

                    snippet_count = 0
                    # Display successful audio snippets
                    for i, result in enumerate(all_results):
                        if result['status'] == 'audio_complete':
                            topic = result['topic']; audio_path = result['audio_path']
                            text = result.get('text', "Text summary not available."); snippet_count += 1
                            st.markdown(f"#### ▶️ Snippet {snippet_count}: {topic}")
                            col_a, col_b = st.columns([4, 1])
                            try:
                                with open(audio_path, 'rb') as f: audio_bytes_player = f.read()
                                with col_a: st.audio(audio_bytes_player, format='audio/mp3')
                                with open(audio_path, 'rb') as f: audio_bytes_dl = f.read()
                                with col_b: st.download_button(label=f"Download MP3", data=audio_bytes_dl,
                                                               file_name=os.path.basename(audio_path), mime='audio/mp3',
                                                               key=f"download_{i}", use_container_width=True)
                                with st.expander("View Text Summary"):
                                    st.text_area("Script:", value=text, height=150, disabled=True, key=f"text_{i}")
                            except FileNotFoundError: st.error(f"Audio file not found: {audio_path}", icon="❌")
                            except Exception as display_e: st.error(f"Error displaying audio/text for '{topic}': {display_e}", icon="❌")
                            st.divider()

                    # Display text summaries where audio failed or was skipped
                    text_only_results = [r for r in all_results if r['status'] in ('audio_failed', 'audio_skipped_config')]
                    if text_only_results:
                        st.subheader("📝 Text Summaries Only (Audio Failed or Skipped)")
                        for i, result in enumerate(text_only_results):
                             topic = result['topic']; text = result.get('text', "Text summary not available.")
                             reason = "(Audio Failed)" if result['status'] == 'audio_failed' else "(Audio Skipped - Config Issue)"
                             st.markdown(f"**{topic}** {reason}")
                             st.text_area("Script:", value=text, height=150, disabled=True, key=f"text_only_{i}")
                             st.divider()

                # --- Suggestion Section ---
                st.divider(); st.subheader("🤔 Fuel Your Curiosity Further!")
                successful_text_topics = [r['topic'] for r in all_results if r['status'] in ('audio_complete', 'audio_failed', 'audio_skipped_config', 'text_complete')]
                if successful_text_topics:
                    suggestion = None
                    with st.spinner("🧠 AI is thinking of a related topic..."):
                        suggestion = get_topic_suggestion_gemini(successful_text_topics)
                    if suggestion:
                        st.success(f"**Next Suggested Topic:** 👇\n> *{suggestion}*", icon="💡")
                        st.caption("(Try adding this to your next playlist!)")
                    else: st.info("Could not generate a topic suggestion this time.", icon="🤷")
                elif num_total > 0 : st.info("No snippets generated, so no suggestion available.", icon="✨")
                else: pass

    # --- Footer / Instructions ---
    st.divider()
    with st.expander("💡 How to Use & Tips"):
        st.markdown(f"""
        1.  **Enter Topics:** Type subjects (one per line). Specificity helps!
        2.  **Select Tone:** Choose narration style (influences text & mapped voice).
        3.  **Generate:** Click the button! Processing takes **~30-90 seconds *per topic***.
        4.  **Listen & Learn:** Play or download ~{SNIPPET_DURATION_MINUTES}-minute audio snippets below. View text summary.

        *   **API Keys:** Ensure correct `GOOGLE_API_KEY` and `ELEVENLABS_API_KEY` in `.env` file. Enable Google Generative AI API in Cloud Console.
        *   **Voice Customization:** Edit `voice_name_map` in `app.py` (~line 194) using *your* ElevenLabs voice names (lowercase). Check terminal logs for available voices on startup.
        *   **Errors:** Check app warnings/errors and terminal logs for details (API issues, content filters).
        *   **Examples:** Quantum computing basics, Lifecycle of a star, History of jazz music, Impact of social media, How vaccines work.
        """)
    st.caption("LearnStream MVP v1.7 (String Enum Fix) - Built for the Global AI Hackathon")
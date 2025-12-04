"""
PBA Grader - Streamlit App
A tool for grading Plan Building Assignment submissions.
Reads submissions from Google Sheets.
"""

import streamlit as st
import pandas as pd
import io
import requests
from datetime import datetime
from anthropic import Anthropic
from grading_logic import grade_submission, determine_overall_grade
from document_generator import create_grading_document

# Page config
st.set_page_config(
    page_title="PBA Grader",
    page_icon="🐕",
    layout="wide"
)

# Get API key from secrets
api_key = st.secrets.get("ANTHROPIC_API_KEY", "")


def translate_feedback(results: dict, target_language: str) -> dict:
    """Translate all feedback in results to the target language."""
    if not api_key:
        return results

    # Build the text to translate
    feedback_texts = []
    for q_id, result in results.items():
        feedback_texts.append(f"[{q_id}]: {result.feedback}")

    combined_text = "\n".join(feedback_texts)

    if target_language == "French":
        language_instruction = """You are translating dog training assessment feedback from English to French.

FRENCH DICTIONARY - Use these specific terms:
- Behavior consultant = consultant(e) en comportement canin
- Separation anxiety = anxiété de séparation
- Dog trainer = Consultant(e) en comportement canin
- Dog training = Éducation canine
- Target duration = durée cible
- Warmup steps = étapes d'échauffement

TRANSLATION RULES:
1. Do NOT literally translate idioms - use the French equivalent instead
2. Keep these English expressions as-is: "Door is a Bore", "DIAB", "Car is a Bore", "CIAB", "Key is a Bore", "KIAB", "FOMO", "push-drop"
3. Use modern, natural French - avoid antiquated expressions
4. Maintain the warm, professional tone
5. Keep the educational context of dog training
6. Preserve the [q1], [q2], etc. markers exactly as-is

Translate each feedback line, keeping the [qX]: format:"""

    elif target_language == "Dutch":
        language_instruction = """You are translating dog training assessment feedback from English to Dutch.

DUTCH TRANSLATION RULES:
1. Keep these English expressions as-is: "Door is a Bore", "DIAB", "Car is a Bore", "CIAB", "Key is a Bore", "KIAB", "FOMO", "push-drop"
2. Use "je/jij" (informal) not "u" (formal) - keep it warm and collegial
3. Avoid literal translations of English idioms - use natural Dutch equivalents
4. Watch word order in subordinate clauses (verb goes to end)
5. Use natural Dutch compound words where appropriate
6. Avoid anglicisms where good Dutch alternatives exist
7. Keep the warm, professional tone
8. Use modern Dutch - avoid stiff or formal phrasing
9. "Separation anxiety" = "verlatingsangst" or "scheidingsangst"
10. "Target duration" = "doelduur"
11. Preserve the [q1], [q2], etc. markers exactly as-is

Translate each feedback line, keeping the [qX]: format:"""
    else:
        return results

    try:
        client = Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            messages=[
                {
                    "role": "user",
                    "content": f"{language_instruction}\n\n{combined_text}"
                }
            ]
        )

        translated_text = message.content[0].text

        # Parse the translated text back into results
        import re
        from grading_logic import GradeResult

        translated_results = {}
        for q_id, result in results.items():
            # Find the translated feedback for this question
            pattern = rf'\[{q_id}\]:\s*(.+?)(?=\n\[q|$)'
            match = re.search(pattern, translated_text, re.DOTALL)
            if match:
                translated_feedback = match.group(1).strip()
                translated_results[q_id] = GradeResult(
                    is_correct=result.is_correct,
                    feedback=translated_feedback,
                    calculation=result.calculation
                )
            else:
                translated_results[q_id] = result

        return translated_results
    except Exception as e:
        st.error(f"Translation error: {e}")
        return results


# Default Google Sheet URL
DEFAULT_SHEET_URL = "https://docs.google.com/spreadsheets/d/1HOY8Mzsv2pT9XQX8EwRri3L3EEKNU_cVR9PKRaYwWX0/edit?usp=sharing"

# Column mapping from Google Sheet to our question IDs
# These are the column indices in the spreadsheet (0-indexed)

# English form: 50 columns, has "Assessed by" in col 5, and "Correct or incorrect?" columns after Maisie questions
COLUMN_MAPPING_ENGLISH = {
    'submission_date': 0,
    'first_name': 1,
    'last_name': 2,
    'email': 3,
    'q1': 12,   # QUESTION 1: Maisie Plan 1
    'q2': 15,   # QUESTION 2: Maisie Plan 2
    'q3': 18,   # QUESTION 3: Maisie Plan 3
    'q4': 21,   # QUESTION 4: Maisie after struggle
    'q5': 23,   # Question 5: Minna Plan 1
    'q6': 25,   # Question 6: Minna Plan 2
    'q7': 27,   # QUESTION 7: Minna Plan 3
    'q8': 29,   # QUESTION 8: Minna increase
    'q9': 30,   # QUESTION 9: Oliver Plan 1
    'q10': 32,  # QUESTION 10: Oliver Plan 2
    'q11': 34,  # QUESTION 11: Oliver Plan 3
    'q12': 36,  # QUESTION 12: Oliver keys
    'q13': 37,  # QUESTION 13: Bella Plan 1
    'q13b': 38, # QUESTION 13B: Bella warmups
    'q14': 40,  # QUESTION 14: Bella Plan 2
    'q14b': 41, # QUESTION 14B: Bella warmups 2
    'q15': 43,  # QUESTION 15: Bella Plan 3
    'q15b': 44, # QUESTION 15B: Bella warmups 3
    'q16': 46,  # QUESTION 16: Bella car
    'q17': 47,  # QUESTION 17: DIAB warmups
}

# French form: 47 columns, missing "Assessed by" and "Correct or incorrect?" columns
# Has empty col 5 and "Skip to end?" in col 6 (to drop)
# French is offset by +1 for cols 5-6 extras, then -4 for missing "Correct or incorrect?" columns after Maisie
COLUMN_MAPPING_FRENCH = {
    'submission_date': 0,
    'first_name': 1,
    'last_name': 2,
    'email': 3,
    'q1': 11,   # QUESTION 1: Maisie Plan 1 (En 12 - 1 for missing "Assessed by")
    'q2': 13,   # QUESTION 2: Maisie Plan 2 (En 15 - 1 "Assessed by" - 1 "Correct?")
    'q3': 15,   # QUESTION 3: Maisie Plan 3 (En 18 - 1 - 2)
    'q4': 17,   # QUESTION 4: Maisie after struggle (En 21 - 1 - 3)
    'q5': 18,   # Question 5: Minna Plan 1 (En 23 - 1 - 4)
    'q6': 20,   # Question 6: Minna Plan 2
    'q7': 22,   # QUESTION 7: Minna Plan 3
    'q8': 24,   # QUESTION 8: Minna increase
    'q9': 25,   # QUESTION 9: Oliver Plan 1
    'q10': 27,  # QUESTION 10: Oliver Plan 2
    'q11': 29,  # QUESTION 11: Oliver Plan 3
    'q12': 31,  # QUESTION 12: Oliver keys
    'q13': 32,  # QUESTION 13: Bella Plan 1
    'q13b': 33, # QUESTION 13B: Bella warmups
    'q14': 35,  # QUESTION 14: Bella Plan 2
    'q14b': 36, # QUESTION 14B: Bella warmups 2
    'q15': 38,  # QUESTION 15: Bella Plan 3
    'q15b': 39, # QUESTION 15B: Bella warmups 3
    'q16': 41,  # QUESTION 16: Bella car
    'q17': 42,  # QUESTION 17: DIAB warmups
}

# Default to English mapping (will be auto-detected)
COLUMN_MAPPING = COLUMN_MAPPING_ENGLISH


def detect_form_language(df: pd.DataFrame) -> str:
    """
    Detect if the spreadsheet is English or French based on column structure.
    French form has empty col 5 header or "Skip to end?" in col 6.
    English form has "Assessed by" in col 5.
    """
    columns = df.columns.tolist()

    # Check number of columns
    if len(columns) <= 47:
        return "French"

    # Check for "Assessed by" in column 5 (English) or empty/Skip to end (French)
    if len(columns) > 5:
        col5_header = str(columns[4]).strip().lower() if pd.notna(columns[4]) else ""
        col6_header = str(columns[5]).strip().lower() if len(columns) > 6 and pd.notna(columns[5]) else ""

        if "assessed" in col5_header:
            return "English"
        if col5_header == "" or "skip" in col6_header:
            return "French"

    # Default to English if can't determine
    return "English"


def get_column_mapping(form_language: str) -> dict:
    """Get the appropriate column mapping for the form language."""
    if form_language == "French":
        return COLUMN_MAPPING_FRENCH
    return COLUMN_MAPPING_ENGLISH


def extract_sheet_id(url: str) -> str:
    """Extract the Google Sheet ID from various URL formats."""
    if '/d/' in url:
        start = url.find('/d/') + 3
        end = url.find('/', start)
        if end == -1:
            end = url.find('?', start)
        if end == -1:
            end = url.find('#', start)
        if end == -1:
            end = len(url)
        return url[start:end]
    return url


def extract_gid(url: str) -> str:
    """Extract the gid (sheet tab ID) from URL if present."""
    import re
    # Look for gid= in URL (can be after ? or #)
    match = re.search(r'gid=(\d+)', url)
    if match:
        return match.group(1)
    return None


def load_sheet_data(sheet_url: str) -> pd.DataFrame:
    """Load data from a Google Sheet, handling specific tabs via gid."""
    sheet_id = extract_sheet_id(sheet_url)
    gid = extract_gid(sheet_url)

    # Build export URL - include gid if present to load specific tab
    if gid:
        csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    else:
        csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"

    try:
        response = requests.get(csv_url, timeout=30)
        response.raise_for_status()
        df = pd.read_csv(io.StringIO(response.text))
        return df
    except Exception as e:
        st.error(f"Error loading sheet: {e}")
        return None


def get_student_answers(row, df, column_mapping: dict) -> dict:
    """Extract answers from a DataFrame row using column indices."""
    answers = {}
    columns = df.columns.tolist()

    for q_id, col_idx in column_mapping.items():
        if q_id in ['submission_date', 'first_name', 'last_name', 'email']:
            continue
        if col_idx < len(columns):
            value = row.iloc[col_idx]
            answers[q_id] = str(value) if pd.notna(value) else ""

    return answers


# Title
st.title("🐕 Plan Building Assignment Grader")
st.markdown("*SA Pro Trainer Certification*")
st.markdown("---")

# Sidebar for settings
with st.sidebar:
    st.header("Settings")
    reviewer_name = st.text_input("Reviewer Name", value="Amanda Dwyer")
    st.markdown("---")
    st.markdown("### Instructions")
    st.markdown("""
    1. Enter the Google Sheet URL (or use default)
    2. Click 'Load Submissions'
    3. Select a student from the dropdown
    4. Review their answers
    5. Click 'Grade Submission'
    6. Download the Word document
    """)

# Google Sheet input
st.header("📊 Load Submissions from Google Sheets")

sheet_url = st.text_input(
    "Google Sheet URL",
    value=DEFAULT_SHEET_URL,
    help="Paste the URL of your Google Sheet. It must be shared with 'Anyone with the link can view'."
)

# Load button
if st.button("📥 Load Submissions", type="primary"):
    with st.spinner("Loading submissions from Google Sheets..."):
        df = load_sheet_data(sheet_url)
        if df is not None:
            # Auto-detect form language
            form_language = detect_form_language(df)
            st.session_state['sheet_data'] = df
            st.session_state['sheet_loaded'] = True
            st.session_state['form_language'] = form_language
            st.session_state['column_mapping'] = get_column_mapping(form_language)
            st.success(f"Loaded {len(df)} submissions! (Detected: {form_language} form)")

# If data is loaded, show student selector
if st.session_state.get('sheet_loaded', False) and 'sheet_data' in st.session_state:
    df = st.session_state['sheet_data']
    column_mapping = st.session_state.get('column_mapping', COLUMN_MAPPING_ENGLISH)
    form_language = st.session_state.get('form_language', 'English')

    # Show detected form type
    st.info(f"📋 Form type: **{form_language}**")

    st.markdown("---")
    st.header("👤 Select Student")

    # Create student list with name and submission date
    columns = df.columns.tolist()
    students = []
    for idx, row in df.iterrows():
        first_name = row.iloc[column_mapping['first_name']] if column_mapping['first_name'] < len(columns) else ""
        last_name = row.iloc[column_mapping['last_name']] if column_mapping['last_name'] < len(columns) else ""
        sub_date = row.iloc[column_mapping['submission_date']] if column_mapping['submission_date'] < len(columns) else ""

        if pd.notna(first_name) and pd.notna(last_name):
            display_name = f"{first_name} {last_name}"
            if pd.notna(sub_date):
                display_name += f" ({sub_date})"
            students.append((idx, display_name))

    if students:
        student_options = [s[1] for s in students]
        selected_idx = st.selectbox(
            "Select a student to grade",
            range(len(students)),
            format_func=lambda x: student_options[x]
        )

        if selected_idx is not None:
            row_idx = students[selected_idx][0]
            selected_row = df.iloc[row_idx]

            # Get student info
            student_name = f"{selected_row.iloc[column_mapping['first_name']]} {selected_row.iloc[column_mapping['last_name']]}"
            submission_date = str(selected_row.iloc[column_mapping['submission_date']])

            # Get answers
            answers = get_student_answers(selected_row, df, column_mapping)

            # Display answers for review
            st.markdown("---")
            st.header(f"📝 {student_name}'s Answers")

            # Question labels
            question_labels = {
                'q1': "Q1: Maisie Plan 1 Target Duration",
                'q2': "Q2: Maisie Plan 2 Target Duration",
                'q3': "Q3: Maisie Plan 3 Target Duration",
                'q4': "Q4: Maisie After Struggle",
                'q5': "Q5: Minna Plan 1 Target Duration",
                'q6': "Q6: Minna Plan 2 Target Duration",
                'q7': "Q7: Minna Plan 3 Target Duration",
                'q8': "Q8: Minna Target Duration Increase",
                'q9': "Q9: Oliver Plan 1 Target Duration",
                'q10': "Q10: Oliver Plan 2 Target Duration",
                'q11': "Q11: Oliver Plan 3 Target Duration",
                'q12': "Q12: Oliver Keys Testing",
                'q13': "Q13: Bella Plan 1 Target Duration",
                'q13b': "Q13B: Bella Plan 1 Warmups",
                'q14': "Q14: Bella Plan 2 Target Duration",
                'q14b': "Q14B: Bella Plan 2 Warmups",
                'q15': "Q15: Bella Plan 3 Target Duration",
                'q15b': "Q15B: Bella Plan 3 Warmups",
                'q16': "Q16: Bella Car Protocol",
                'q17': "Q17: DIAB Warmups"
            }

            # Group by dog
            dogs = [
                ("🐕 Maisie", ['q1', 'q2', 'q3', 'q4']),
                ("🐕 Minna", ['q5', 'q6', 'q7', 'q8']),
                ("🐕 Oliver", ['q9', 'q10', 'q11', 'q12']),
                ("🐕 Bella", ['q13', 'q13b', 'q14', 'q14b', 'q15', 'q15b', 'q16']),
                ("📋 DIAB", ['q17'])
            ]

            for dog_name, q_ids in dogs:
                with st.expander(dog_name, expanded=False):
                    for q_id in q_ids:
                        answer = answers.get(q_id, "")
                        st.markdown(f"**{question_labels.get(q_id, q_id)}**")
                        st.text(answer if answer else "(no answer)")
                        st.markdown("---")

            # Grade button
            st.markdown("---")
            if st.button("📝 Grade Submission", type="primary", use_container_width=True):
                # Grade
                with st.spinner("Grading submission..."):
                    results = grade_submission(answers)
                    overall_grade, resubmit_questions = determine_overall_grade(results)

                # Store results in session state
                st.session_state['grading_results'] = results
                st.session_state['overall_grade'] = overall_grade
                st.session_state['resubmit_questions'] = resubmit_questions
                st.session_state['graded_student'] = student_name
                st.session_state['graded_date'] = submission_date
                st.session_state['graded_answers'] = answers

            # Display results if available
            if st.session_state.get('graded_student') == student_name and 'grading_results' in st.session_state:
                results = st.session_state['grading_results']
                overall_grade = st.session_state['overall_grade']
                resubmit_questions = st.session_state['resubmit_questions']

                st.markdown("---")
                st.header("📊 Results")

                # Overall grade
                if overall_grade == "Cleared":
                    st.success(f"**Overall Grade: {overall_grade}** ✅")
                else:
                    st.error(f"**Overall Grade: {overall_grade}** 🔄")

                # Count correct/incorrect
                correct_count = sum(1 for r in results.values() if r.is_correct)
                total_count = len(results)
                st.metric("Score", f"{correct_count}/{total_count}")

                # Show detailed results
                st.subheader("Detailed Feedback")

                for dog_name, q_ids in dogs:
                    with st.expander(dog_name, expanded=True):
                        for q_id in q_ids:
                            if q_id not in results:
                                continue
                            result = results[q_id]
                            answer = answers.get(q_id, "")

                            status = "✅" if result.is_correct else "❌"
                            st.markdown(f"**{question_labels.get(q_id, q_id)}** {status}")
                            st.markdown(f"*Answer:* {answer if answer else '(no answer)'}")

                            if result.calculation:
                                st.markdown(f"*Calculation:* {result.calculation}")

                            st.markdown(result.feedback)
                            st.markdown("---")

                # Translation section
                st.markdown("---")
                st.subheader("🌍 Translate Feedback")
                st.markdown("*Translate all feedback to French or Dutch:*")

                col_lang, col_btn = st.columns([1, 2])
                with col_lang:
                    target_language = st.selectbox("Language", ["French", "Dutch"], key="pba_lang", label_visibility="collapsed")
                with col_btn:
                    translate_clicked = st.button(f"🔄 Translate to {target_language}", use_container_width=True)

                if translate_clicked:
                    if not api_key:
                        st.error("API key not configured. Please add ANTHROPIC_API_KEY to secrets.")
                    else:
                        with st.spinner(f"Translating feedback to {target_language}..."):
                            translated_results = translate_feedback(results, target_language)
                            st.session_state['grading_results'] = translated_results
                            # Also update resubmit questions if needed
                            overall_grade, resubmit_questions = determine_overall_grade(translated_results)
                            st.session_state['resubmit_questions'] = resubmit_questions
                            st.success(f"Translated to {target_language}!")
                            st.rerun()

                # Generate document
                st.subheader("📄 Download Feedback Document")

                doc_buffer = create_grading_document(
                    student_name=student_name,
                    submission_date=submission_date,
                    reviewer_name=reviewer_name,
                    answers=answers,
                    results=results,
                    overall_grade=overall_grade,
                    resubmit_questions=resubmit_questions
                )

                # Download button
                st.download_button(
                    label="📥 Download Word Document",
                    data=doc_buffer,
                    file_name=f"PBA_Submission_{student_name.replace(' ', '_')}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True
                )

                # Show questions to resubmit
                if resubmit_questions:
                    st.subheader("Questions to Resubmit")
                    for q_id, q_label in resubmit_questions:
                        st.markdown(f"- **{q_id.upper()}**: {q_label}")
    else:
        st.warning("No students found in the spreadsheet.")

# Footer
st.markdown("---")
st.markdown("*PBA Grader v2.0 - SA Pro Trainer Certification - Google Sheets Integration*")

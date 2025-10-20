import streamlit as st
import pandas as pd

# --------------------------
# 1. ΦΟΡΤΩΣΗ ΔΕΔΟΜΕΝΩΝ ΑΠΟ ΤΟ ΑΡΧΕΙΟ CSV
# --------------------------

DATA_FILE = 'class_data.csv' # Το όνομα του αρχείου στο GitHub

try:
    # Διαβάζουμε το CSV αρχείο
    # Σημείωση: Το Streamlit, όταν φιλοξενείται στο Streamlit Community Cloud, 
    # διαβάζει αυτόματα τα αρχεία που βρίσκονται στο ίδιο αποθετήριο.
    df = pd.read_csv(DATA_FILE)
    
    # Μετατροπή του DataFrame σε λεξικό για γρήγορη αναζήτηση
    df['Keyword'] = df['Keyword'].str.lower().str.strip()
    data_source_dict = df.set_index('Keyword')['Response'].to_dict()
    
except FileNotFoundError:
    st.error("Δεν βρέθηκε το αρχείο δεδομένων 'class_data.csv'.")
    data_source_dict = {}

# --------------------------
# 2. ΡΥΘΜΙΣΗ UI / ΤΙΤΛΟΣ
# --------------------------
st.set_page_config(page_title="Βοηθός Τάξης (GitHub Data)", layout="centered")
st.title("🤖 Ψηφιακός Βοηθός Τάξης (Data from GitHub)")
st.markdown("---")

available_keys = ', '.join(data_source_dict.keys()).capitalize()
st.info(f"Γεια! Είμαι ο βοηθός σου. Διαθέσιμες λέξεις-κλειδιά: {available_keys}")

# --------------------------
# 3. ΕΙΣΑΓΩΓΗ ΧΡΗΣΤΗ & ΛΟΓΙΚΗ
# --------------------------
user_input = st.text_input('Τι θέλεις να μάθεις;', 
                           placeholder='Πληκτρολόγησε π.χ. Μαθηματικα, Εκδρομη...')

if user_input:
    processed_input = user_input.lower().strip()
    
    if processed_input in data_source_dict:
        bot_response = data_source_dict[processed_input]
        st.success(f"**Απάντηση:** {bot_response}")

    else:
        st.warning(
            f"Δεν βρέθηκε απάντηση για το: '{user_input}'. Δοκιμάστε μία από τις διαθέσιμες λέξεις-κλειδιά: {available_keys}."
        )

st.markdown("---")
st.caption("Τα δεδομένα φορτώνονται δυναμικά από το αρχείο class_data.csv στο GitHub.")

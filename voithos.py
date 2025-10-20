import streamlit as st
import pandas as pd
from unidecode import unidecode # Χρησιμοποιείται για να αφαιρεί τους τόνους

# --------------------------
# 1. ΦΟΡΤΩΣΗ ΔΕΔΟΜΕΝΩΝ ΑΠΟ ΤΟ ΑΡΧΕΙΟ CSV
# --------------------------

DATA_FILE = 'class_data.csv' 

# Συνάρτηση για την ομαλοποίηση των λέξεων-κλειδιών
def normalize_keyword(keyword):
    """Μετατρέπει τη λέξη-κλειδί σε πεζά και αφαιρεί τους τόνους."""
    if pd.isna(keyword):
        return ''
    # 1. Μετατροπή σε πεζά
    # 2. Αφαίρεση τόνων (π.χ. 'φυσική' -> 'φυσικη')
    return unidecode(str(keyword).lower().strip())

try:
    df = pd.read_csv(DATA_FILE)
    
    # Εφαρμογή της ομαλοποίησης στη στήλη Keyword του DataFrame
    df['Keyword'] = df['Keyword'].apply(normalize_keyword)
    
    # Μετατροπή σε λεξικό για γρήγορη αναζήτηση
    data_source_dict = df.set_index('Keyword')['Response'].to_dict()
    
except FileNotFoundError:
    st.error("Δεν βρέθηκε το αρχείο δεδομένων 'class_data.csv'. Βεβαιωθείτε ότι είναι στον ίδιο φάκελο.")
    data_source_dict = {}

# --------------------------
# 2. ΡΥΘΜΙΣΗ UI / ΤΙΤΛΟΣ
# --------------------------
st.set_page_config(page_title="Βοηθός Τάξης (Βελτιωμένος)", layout="centered")
st.title("🤖 Ψηφιακός Βοηθός Τάξης")
st.markdown("---")

available_keys = ', '.join(df['Keyword'].unique()).capitalize() if 'Keyword' in df.columns else ""
st.info(f"Γεια! Είμαι ο βοηθός σου. Διαθέσιμες λέξεις-κλειδιά: {available_keys.replace(',', ', ')}")

# --------------------------
# 3. ΕΙΣΑΓΩΓΗ ΧΡΗΣΤΗ & ΛΟΓΙΚΗ
# --------------------------

# Χρησιμοποιούμε st.session_state για να αποθηκεύσουμε την τιμή του πεδίου εισαγωγής.
if 'search_query' not in st.session_state:
    st.session_state.search_query = ""

# Δημιουργία του πεδίου εισαγωγής
user_input = st.text_input(
    'Τι θέλεις να μάθεις;', 
    placeholder='Πληκτρολόγησε π.χ. Μαθηματικα, Εκδρομη...',
    key='main_input', # Δίνουμε ένα κλειδί για το πεδίο
    value=st.session_state.search_query # Χρησιμοποιούμε την τιμή από το state
)

if st.button('Αναζήτηση'):
    # Ομαλοποίηση της εισόδου του χρήστη
    processed_input = normalize_keyword(user_input)
    
    if processed_input in data_source_dict:
        # 4.1. Εμφάνιση Απάντησης
        bot_response = data_source_dict[processed_input]
        st.success(f"**Απάντηση:** {bot_response}")
        
        # 4.2. Σβήσιμο της λέξης αναζήτησης (Ανανεώνουμε το session state)
        st.session_state.search_query = ""
        st.experimental_rerun() # Επανεκκίνηση για να καθαρίσει το πεδίο εισαγωγής
    else:
        st.warning(
            f"Δεν βρέθηκε απάντηση για το: '{user_input}'. Δοκιμάστε μία από τις διαθέσιμες λέξεις-κλειδιά: {available_keys.replace(',', ', ')}."
        )

st.markdown("---")
st.caption("Το πρωτότυπο χρησιμοποιεί Python/Streamlit και δεδομένα από GitHub.")

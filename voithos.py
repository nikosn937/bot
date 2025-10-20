import streamlit as st
import pandas as pd
from unidecode import unidecode # Χρησιμοποιείται για να αφαιρεί τους τόνους

# --------------------------------------------------------------------------------
# 1. ΒΟΗΘΗΤΙΚΕΣ ΣΥΝΑΡΤΗΣΕΙΣ (ΓΙΑ ΤΟΝΟ/ΚΕΦΑΛΑΙΑ)
# --------------------------------------------------------------------------------

def normalize_keyword(keyword):
    """
    Μετατρέπει τη λέξη-κλειδί (από χρήστη ή CSV) σε πεζά και αφαιρεί τους τόνους,
    έτοιμη για εσωτερική σύγκριση.
    """
    if pd.isna(keyword):
        return ''
    # 1. Μετατροπή σε πεζά, αφαίρεση κενών
    # 2. Αφαίρεση τόνων (π.χ. 'φυσική' -> 'φυσικη')
    return unidecode(str(keyword).lower().strip())

# --------------------------------------------------------------------------------
# 2. ΦΟΡΤΩΣΗ ΚΑΙ ΕΠΕΞΕΡΓΑΣΙΑ ΔΕΔΟΜΕΝΩΝ
# --------------------------------------------------------------------------------

DATA_FILE = 'class_data.csv' 

try:
    df = pd.read_csv(DATA_FILE)
    
    # Δημιουργούμε μια νέα στήλη για την εσωτερική σύγκριση (χωρίς τόνους/κεφαλαία)
    df['Normalized_Keyword'] = df['Keyword'].apply(normalize_keyword)
    
    # Μετατροπή σε λεξικό για γρήγορη αναζήτηση, χρησιμοποιώντας τη Normalized_Keyword
    data_source_dict = df.set_index('Normalized_Keyword')['Response'].to_dict()
    
    # Λίστα με τις λέξεις-κλειδιά στα Ελληνικά (για εμφάνιση στον χρήστη)
    available_keys_display = sorted(df['Keyword'].unique())
    
except FileNotFoundError:
    st.error("Δεν βρέθηκε το αρχείο δεδομένων 'class_data.csv'. Βεβαιωθείτε ότι είναι στον ίδιο φάκελο.")
    data_source_dict = {}
    available_keys_display = []

# --------------------------------------------------------------------------------
# 3. ΡΥΘΜΙΣΗ UI / ΤΙΤΛΟΣ
# --------------------------------------------------------------------------------

st.set_page_config(page_title="Βοηθός Τάξης (Βελτιωμένος)", layout="centered")
st.title("🤖 Ψηφιακός Βοηθός Τάξης")
st.markdown("---")

# Εμφάνιση των διαθέσιμων λέξεων-κλειδιών στα Ελληνικά (με τόνους)
info_message = f"Γεια! Είμαι ο βοηθός σου. Διαθέσιμες λέξεις-κλειδιά: **{', '.join(available_keys_display)}**"
st.info(info_message)

# --------------------------------------------------------------------------------
# 4. ΕΙΣΑΓΩΓΗ ΧΡΗΣΤΗ & ΛΟΓΙΚΗ
# --------------------------------------------------------------------------------

# Χρησιμοποιούμε st.session_state για να διαχειριστούμε τη διαγραφή του κειμένου εισαγωγής.
if 'search_query' not in st.session_state:
    st.session_state.search_query = ""

# Δημιουργία του πεδίου εισαγωγής
user_input = st.text_input(
    'Τι θέλεις να μάθεις;', 
    placeholder='Πληκτρολόγησε π.χ. Μαθηματικά, Εκδρομή...',
    key='main_input',
    value=st.session_state.search_query
)

if st.button('Αναζήτηση'):
    # Ομαλοποίηση της εισόδου του χρήστη για εσωτερική σύγκριση
    processed_input = normalize_keyword(user_input)
    
    if processed_input in data_source_dict:
        # 4.1. Εμφάνιση Απάντησης
        bot_response = data_source_dict[processed_input]
        st.success(f"**Απάντηση:** {bot_response}")
        
        # 4.2. Σβήσιμο της λέξης αναζήτησης και επανεκκίνηση (διορθωμένο)
        st.session_state.search_query = ""
        st.rerun() # Η διορθωμένη εντολή για την επανεκκίνηση
        
    else:
        # Μήνυμα σφάλματος
        st.warning(
            f"Δεν βρέθηκε απάντηση για το: '{user_input}'. Δοκιμάστε μία από τις διαθέσιμες λέξεις-κλειδιά: **{', '.join(available_keys_display)}**."
        )

st.markdown("---")
st.caption("Το πρωτότυπο χρησιμοποιεί Python/Streamlit και δεδομένα από GitHub.")

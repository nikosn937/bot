import streamlit as st
import pandas as pd

# --------------------------------------------------------------------------------
# 1. ΒΟΗΘΗΤΙΚΗ ΣΥΝΑΡΤΗΣΗ (ΑΦΑΙΡΕΣΗ ΤΟΝΩΝ ΧΩΡΙΣ unidecode)
# --------------------------------------------------------------------------------

# Χάρτης αντικατάστασης για τους τόνους
TONES_MAP = str.maketrans("άέήίόύώ", "αεηιουω")

def normalize_keyword(keyword):
    """Μετατρέπει τη λέξη-κλειδί σε πεζά, αφαιρεί τα κενά και τους τόνους."""
    if pd.isna(keyword):
        return ''
    normalized = str(keyword).lower().strip()
    return normalized.translate(TONES_MAP)


# --------------------------------------------------------------------------------
# 2. ΦΟΡΤΩΣΗ ΚΑΙ ΕΠΕΞΕΡΓΑΣΙΑ ΔΕΔΟΜΕΝΩΝ ΑΠΟ CSV
# --------------------------------------------------------------------------------

DATA_FILE = 'class_data.csv' 

try:
    # Φόρτωση με ρητή κωδικοποίηση utf-8 για τα ελληνικά
    df = pd.read_csv(DATA_FILE, encoding='utf-8')
    
    # Καθαρισμός των ονομάτων των στηλών
    df.columns = df.columns.str.strip()
    
    # Έλεγχος ύπαρξης απαραίτητων στηλών
    if 'Keyword' not in df.columns or 'Response' not in df.columns:
        raise ValueError("Σφάλμα: Το CSV πρέπει να περιέχει τις επικεφαλίδες 'Keyword' και 'Response'.")
    
    # Δημιουργούμε τη στήλη για εσωτερική σύγκριση (εδώ γίνεται η αφαίρεση τόνων)
    df['Normalized_Keyword'] = df['Keyword'].apply(normalize_keyword)
    
    # Μετατροπή σε λεξικό για γρήγορη αναζήτηση
    data_source_dict = df.set_index('Normalized_Keyword')['Response'].to_dict()
    
    # Λίστα για εμφάνιση
    available_keys_display = sorted(df['Keyword'].unique())
    
except FileNotFoundError:
    st.error("Κρίσιμο Σφάλμα: Δεν βρέθηκε το αρχείο 'class_data.csv' στο GitHub repository.")
    data_source_dict = {}
    available_keys_display = []
except Exception as e:
    st.error(f"Κρίσιμο Σφάλμα Φόρτωσης Δεδομένων: {e}")
    data_source_dict = {}
    available_keys_display = []

# --------------------------------------------------------------------------------
# 3. UI / ΛΟΓΙΚΗ
# --------------------------------------------------------------------------------

st.set_page_config(page_title="Βοηθός Τάξης (CSV Edition)", layout="centered")
st.title("🤖 Ψηφιακός Βοηθός Τάξης (Δεδομένα από CSV)")
st.markdown("---")

info_message = f"Γεια! Είμαι ο βοηθός σου. Διαθέσιμες λέξεις-κλειδιά: **{', '.join(available_keys_display)}**"
st.info(info_message)

# Το πεδίο εισαγωγής δεν χρειάζεται session_state ή κουμπί, 
# καθώς αποφεύγουμε την εντολή st.rerun() για σταθερότητα.
user_input = st.text_input(
    'Τι θέλεις να μάθεις;', 
    placeholder='Πληκτρολόγησε π.χ. Μαθηματικά, Εκδρομή...'
)

if user_input: # Η λογική εκτελείται μόλις ο χρήστης πατήσει Enter
    
    # Ομαλοποίηση της εισόδου του χρήστη
    processed_input = normalize_keyword(user_input)
    
    if processed_input in data_source_dict:
        # Επιτυχία
        bot_response = data_source_dict[processed_input]
        st.success(f"**Απάντηση:** {bot_response}")
        
    else:
        # Αποτυχία
        st.warning(
            f"Δεν βρέθηκε απάντηση για το: '{user_input}'. Δοκίμασε μία από τις διαθέσιμες λέξεις-κλειδιά: **{', '.join(available_keys_display)}**."
        )

st.markdown("---")
st.caption("Η εφαρμογή χρησιμοποιεί Python/Streamlit και δεδομένα από το αρχείο class_data.csv.")

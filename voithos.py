import streamlit as st
import pandas as pd

# --------------------------------------------------------------------------------
# 1. ΒΟΗΘΗΤΙΚΗ ΣΥΝΑΡΤΗΣΗ (ΑΦΑΙΡΕΣΗ ΤΟΝΩΝ)
# --------------------------------------------------------------------------------

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
    df = pd.read_csv(DATA_FILE, encoding='utf-8')
    df.columns = df.columns.str.strip()
    
    if 'Keyword' not in df.columns or 'Response' not in df.columns:
        raise ValueError("Σφάλμα: Το CSV πρέπει να περιέχει τις επικεφαλίδες 'Keyword' και 'Response'.")
    
    # 1. Δημιουργία ομαλοποιημένης στήλης
    df['Normalized_Keyword'] = df['Keyword'].apply(normalize_keyword)
    
    # 2. ΟΜΑΔΟΠΟΙΗΣΗ: Χρησιμοποιούμε groupby για να συλλέξουμε όλες τις απαντήσεις σε μια λίστα
    data_source_dict = df.groupby('Normalized_Keyword')['Response'].apply(list).to_dict()
    
    # Λίστα για εμφάνιση (από την αρχική στήλη Keyword)
    available_keys_display = sorted(df['Keyword'].unique())
    
except FileNotFoundError:
    st.error("Κρίσιμο Σφάλμα: Δεν βρέθηκε το αρχείο 'class_data.csv'.")
    data_source_dict = {}
    available_keys_display = []
except Exception as e:
    st.error(f"Κρίσιμο Σφάλμα Φόρτωσης Δεδομένων: {e}")
    data_source_dict = {}
    available_keys_display = []

# --------------------------------------------------------------------------------
# 3. UI / ΛΟΓΙΚΗ
# --------------------------------------------------------------------------------

st.set_page_config(page_title="Βοηθός Τάξης (Πολλαπλές Απαντήσεις)", layout="centered")
st.title("🤖 Ψηφιακός Βοηθός Τάξης")
st.markdown("---")

info_message = f"Γεια! Είμαι ο βοηθός σου. Διαθέσιμες λέξεις-κλειδιά: **{', '.join(available_keys_display)}**"
st.info(info_message)

user_input = st.text_input(
    'Τι θέλεις να μάθεις;', 
    placeholder='Πληκτρολόγησε π.χ. Μαθηματικά, Εκδρομή...'
)

if user_input:
    processed_input = normalize_keyword(user_input)
    
    if processed_input in data_source_dict:
        # Επιτυχία: Η απάντηση είναι τώρα μια ΛΙΣΤΑ (list)
        list_of_responses = data_source_dict[processed_input]
        
        st.success(f"Βρέθηκαν {len(list_of_responses)} πληροφορίες για το θέμα: **{user_input}**")
        
        # Εμφάνιση κάθε απάντησης ξεχωριστά
        for i, response in enumerate(list_of_responses, 1):
            st.markdown(f"**Απάντηση {i}:** {response}")
        
    else:
        # Αποτυχία
        st.warning(
            f"Δεν βρέθηκε απάντηση για το: '{user_input}'. Δοκίμασε μία από τις διαθέσιμες λέξεις-κλειδιά: **{', '.join(available_keys_display)}**."
        )

st.markdown("---")
st.caption("Η εφαρμογή χρησιμοποιεί Python/Streamlit και δεδομένα από το αρχείο class_data.csv.")

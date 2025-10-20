import streamlit as st
import pandas as pd

# --------------------------------------------------------------------------------
# 1. ΒΟΗΘΗΤΙΚΗ ΣΥΝΑΡΤΗΣΗ (ΑΦΑΙΡΕΣΗ ΤΟΝΩΝ)
# --------------------------------------------------------------------------------

TONES_MAP = str.maketrans("άέήίόύώ", "αεηιουώ")

def normalize_keyword(keyword):
    """Μετατρέπει τη λέξη-κλειδί σε πεζά, αφαιρεί τα κενά και τους τόνους."""
    if pd.isna(keyword):
        return ''
    normalized = str(keyword).lower().strip()
    return normalized.translate(TONES_MAP)


# --------------------------------------------------------------------------------
# 2. ΦΟΡΤΩΣΗ ΚΑΙ ΕΠΕΞΕΡΓΑΣΙΑ ΔΕΔΟΜΕΝΩΝ ΑΠΟ CSV (4 ΣΤΗΛΕΣ)
# --------------------------------------------------------------------------------

DATA_FILE = 'class_data.csv' 
# !!! ΑΛΛΑΓΗ ΕΔΩ: Ορίζουμε τη μορφή DD/MM/YYYY για ανάγνωση και εμφάνιση !!!
DATE_FORMAT = '%d/%m/%Y' 

try:
    df = pd.read_csv(DATA_FILE, encoding='utf-8')
    df.columns = df.columns.str.strip()
    
    required_cols = ['Keyword', 'Response', 'Type', 'Date']
    if not all(col in df.columns for col in required_cols):
        raise ValueError(f"Σφάλμα: Το CSV πρέπει να περιέχει τις ακριβείς επικεφαλίδες: {', '.join(required_cols)}.")
    
    # 1. Μετατροπή της στήλης Date σε datetime αντικείμενα με τη νέα μορφή
    df['Date'] = pd.to_datetime(df['Date'], format=DATE_FORMAT, errors='coerce')
    
    # 2. Ταξινόμηση: Κατά Date (φθίνουσα, δηλαδή η πιο πρόσφατη πρώτη)
    df_sorted = df.sort_values(by=['Keyword', 'Date'], ascending=[True, False])
    
    # 3. Δημιουργία ομαλοποιημένης στήλης
    df_sorted['Normalized_Keyword'] = df_sorted['Keyword'].apply(normalize_keyword)
    
    # 4. Ομαδοποίηση
    data_source_dict = df_sorted.groupby('Normalized_Keyword').apply(
        lambda x: list(zip(x['Response'], x['Type'], x['Date']))
    ).to_dict()
    
    available_keys_display = sorted(df['Keyword'].unique())
    
except Exception as e:
    st.error(f"Κρίσιμο Σφάλμα Φόρτωσης Δεδομένων: {e}")
    data_source_dict = {}
    available_keys_display = []

# --------------------------------------------------------------------------------
# 3. UI / ΛΟΓΙΚΗ
# --------------------------------------------------------------------------------

st.set_page_config(page_title="Βοηθός Τάξης & Αρχεία", layout="centered")
st.title("🤖 Ψηφιακός Βοηθός Τάξης (Ταξινόμηση ανά Ημερομηνία)")
st.markdown("---")

info_message = f"Γεια! Είμαι ο βοηθός σου. Διαθέσιμες λέξεις-κλειδιά: **{', '.join(available_keys_display)}**"
st.info(info_message)

user_input = st.text_input(
    'Τι θέλεις να μάθεις;', 
    placeholder='Πληκτρολόγησε π.χ. Μαθηματικά, Φυσική...'
)

if user_input:
    processed_input = normalize_keyword(user_input)
    
    if processed_input in data_source_dict:
        list_of_items = data_source_dict[processed_input]
        
        st.success(f"Βρέθηκαν **{len(list_of_items)}** πληροφορίες/αρχεία για το θέμα: **{user_input}** (Οι πιο πρόσφατες πρώτες)")
        
        for i, (response, item_type, date_obj) in enumerate(list_of_items, 1):
            
            # Μορφοποίηση της ημερομηνίας για εμφάνιση (χρησιμοποιεί τη νέα μορφή)
            date_str = date_obj.strftime(DATE_FORMAT) if pd.notna(date_obj) else "Άγνωστη Ημ/νία"
            
            header = f"**Καταχώρηση {i}** (Ημ/νία: {date_str})"
            
            if item_type.strip().lower() == 'file':
                st.markdown(f"{header}: 📂 [{response}](<{response}>)")
            elif item_type.strip().lower() == 'text':
                st.markdown(f"{header}: 💬 {response}")
            else:
                st.markdown(f"{header}: {response}")

    else:
        st.warning(
            f"Δεν βρέθηκε απάντηση για το: '{user_input}'. Δοκίμασε μία από τις διαθέσιμες λέξεις-κλειδιά: **{', '.join(available_keys_display)}**."
        )

st.markdown("---")
st.caption("Η εφαρμογή χρησιμοποιεί Python/Streamlit και δεδομένα από το αρχείο class_data.csv.")

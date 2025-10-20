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
# 2. ΦΟΡΤΩΣΗ ΚΑΙ ΕΠΕΞΕΡΓΑΣΙΑ ΔΕΔΟΜΕΝΩΝ ΑΠΟ CSV (5 ΣΤΗΛΕΣ)
# --------------------------------------------------------------------------------

DATA_FILE = 'class_data.csv' 
DATE_FORMAT = '%d/%m/%Y' 

try:
    df = pd.read_csv(DATA_FILE, encoding='utf-8')
    df.columns = df.columns.str.strip()
    
    # Έλεγχος ύπαρξης απαραίτητων στηλών
    required_cols = ['Keyword', 'Info', 'URL', 'Type', 'Date'] # Εδώ είναι η αλλαγή
    if not all(col in df.columns for col in required_cols):
        raise ValueError(f"Σφάλμα: Το CSV πρέπει να περιέχει τις ακριβείς επικεφαλίδες: {', '.join(required_cols)}.")
    
    # 1. Μετατροπή της στήλης Date
    df['Date'] = pd.to_datetime(df['Date'], format=DATE_FORMAT, errors='coerce')
    
    # 2. Ταξινόμηση
    df_sorted = df.sort_values(by=['Keyword', 'Date'], ascending=[True, False])
    
    # 3. Δημιουργία ομαλοποιημένης στήλης
    df_sorted['Normalized_Keyword'] = df_sorted['Keyword'].apply(normalize_keyword)
    
    # 4. Ομαδοποίηση: Συλλέγουμε τώρα 4 στοιχεία (Info, URL, Type, Date)
    data_source_dict = df_sorted.groupby('Normalized_Keyword').apply(
        lambda x: list(zip(x['Info'], x['URL'], x['Type'], x['Date']))
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
st.title("🤖 Ψηφιακός Βοηθός Τάξης")
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
        # Η απάντηση είναι μια λίστα από tuples: [(Info, URL, Type, Date), ...]
        list_of_items = data_source_dict[processed_input]
        
        st.success(f"Βρέθηκαν **{len(list_of_items)}** πληροφορίες/αρχεία για το θέμα: **{user_input}** (Οι πιο πρόσφατες πρώτες)")
        
        # Εμφάνιση κάθε απάντησης/αρχείου
        for i, (info, url, item_type, date_obj) in enumerate(list_of_items, 1):
            
            date_str = date_obj.strftime(DATE_FORMAT) if pd.notna(date_obj) else "Άγνωστη Ημ/νία"
            header = f"**Καταχώρηση {i}** (Ημ/νία: {date_str})"
            
            if item_type.strip().lower() == 'file':
                # Αν είναι αρχείο, χρησιμοποιούμε το 'info' ως περιγραφή του link και το 'url' ως σύνδεσμο
                link_description = info.strip()
                link_url = url.strip()
                
                # Εμφανίζουμε το λινκ μόνο αν υπάρχει URL
                if link_url:
                    st.markdown(f"{header}: 📂 [{link_description}](<{link_url}>)")
                else:
                    st.markdown(f"{header}: 💬 **Προσοχή:** Η καταχώρηση αρχείου δεν έχει σύνδεσμο. Περιγραφή: {link_description}")
                
            elif item_type.strip().lower() == 'text':
                # Αν είναι κείμενο, χρησιμοποιούμε μόνο το 'info'
                st.markdown(f"{header}: 💬 {info}")
            
            else:
                st.markdown(f"{header}: Άγνωστος Τύπος Καταχώρησης. {info}")

    else:
        st.warning(
            f"Δεν βρέθηκε απάντηση για το: '{user_input}'. Δοκίμασε μία από τις διαθέσιμες λέξεις-κλειδιά: **{', '.join(available_keys_display)}**."
        )

st.markdown("---")
st.caption("Η εφαρμογή χρησιμοποιεί Python/Streamlit και δεδομένα από το αρχείο class_data.csv.")

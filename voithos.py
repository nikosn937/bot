import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection

# --------------------------------------------------------------------------------
# 0. ΡΥΘΜΙΣΕΙΣ (CONNECTION & FORMATS)
# --------------------------------------------------------------------------------

# Δημιουργία σύνδεσης με το Google Sheet (χρησιμοποιεί τα secrets)
conn = st.connection("gsheets", type=GSheetsConnection)
SHEET_NAME = st.secrets["sheet_name"] # Διαβάζει το όνομα του sheet από τα secrets
DATE_FORMAT = '%d/%m/%Y'

# --------------------------------------------------------------------------------
# 1. ΒΟΗΘΗΤΙΚΕΣ ΣΥΝΑΡΤΗΣΕΙΣ
# --------------------------------------------------------------------------------

TONES_MAP = str.maketrans("άέήίόύώ", "αεηιουώ")

def normalize_text(text):
    """Μετατρέπει κείμενο σε πεζά, αφαιρεί τα κενά και τους τόνους."""
    if pd.isna(text):
        return ''
    normalized = str(text).lower().strip()
    return normalized.translate(TONES_MAP)

def get_tags_from_keyword(keyword):
    """Διαχωρίζει μια φράση-κλειδί σε μεμονωμένα, ομαλοποιημένα tags."""
    if not keyword or pd.isna(keyword):
        return []
    return [normalize_text(word) for word in str(keyword).split() if word]

@st.cache_data(ttl=600) # Κάνει cache τα δεδομένα για 10 λεπτά
def load_data():
    """Φορτώνει, καθαρίζει και ταξινομεί δεδομένα από το Google Sheet."""
    try:
        # Φόρτωση δεδομένων από το Google Sheet
        df = conn.read(spreadsheet=SHEET_NAME, ttl=5, usecols=list(range(5)))
        df.columns = df.columns.str.strip()
        
        required_cols = ['Keyword', 'Info', 'URL', 'Type', 'Date']
        if not all(col in df.columns for col in required_cols):
            st.error(f"Σφάλμα δομής: Οι επικεφαλίδες πρέπει να είναι: {', '.join(required_cols)}.")
            return {}, {}, []

        # Μετατροπή της στήλης Date
        df['Date'] = pd.to_datetime(df['Date'], format=DATE_FORMAT, errors='coerce')
        df = df.dropna(subset=['Date']) # Αφαίρεση γραμμών με λάθος ημερομηνίες
        
        # Ταξινόμηση: Πιο πρόσφατη καταχώρηση πρώτη
        df_sorted = df.sort_values(by=['Keyword', 'Date'], ascending=[True, False])
        
        # Δημιουργία χάρτη Tags προς Καταχωρήσεις
        unique_keywords = df_sorted['Keyword'].unique()
        keyword_to_data_map = df_sorted.groupby('Keyword').apply(
            lambda x: list(zip(x['Info'], x['URL'], x['Type'], x['Date']))
        ).to_dict()

        tag_to_keyword_map = {}
        for keyword in unique_keywords:
            normalized_tags = get_tags_from_keyword(keyword)
            for tag in normalized_tags:
                if tag not in tag_to_keyword_map:
                    tag_to_keyword_map[tag] = set()
                tag_to_keyword_map[tag].add(keyword)
                
        return tag_to_keyword_map, keyword_to_data_map, sorted(unique_keywords)
    
    except Exception as e:
        st.error(f"Κρίσιμο Σφάλμα Φόρτωσης από Google Sheet. Ελέγξτε τα secrets και την κοινή χρήση. Λεπτομέρειες: {e}")
        return {}, {}, []

# --------------------------------------------------------------------------------
# 2. ΦΟΡΜΑ ΚΑΤΑΧΩΡΗΣΗΣ (ΝΕΑ ΛΕΙΤΟΥΡΓΙΑ)
# --------------------------------------------------------------------------------

def submit_entry(new_entry):
    """Προσθέτει μια νέα σειρά στο Google Sheet."""
    try:
        # Προσθήκη νέας σειράς στο Sheet (προστίθεται στο τέλος)
        conn.append(data=new_entry)
        
        # Καθαρισμός cache για να διαβαστούν τα νέα δεδομένα
        st.cache_data.clear() 
        st.success("🎉 Η καταχώρηση έγινε επιτυχώς! Η εφαρμογή ανανεώνεται...")
        st.balloons()
        
        # Αναγκαστική επανεκκίνηση για εμφάνιση των νέων δεδομένων
        st.rerun() 
        
    except Exception as e:
        st.error(f"Σφάλμα κατά την καταχώρηση. Ελέγξτε τα δικαιώματα. Λεπτομέρειες: {e}")

def data_entry_form():
    """Δημιουργεί τη φόρμα εισαγωγής νέων δεδομένων."""
    
    with st.expander("➕ Νέα Καταχώρηση (Διαχειριστής)"):
        with st.form("new_entry_form", clear_on_submit=True):
            st.markdown("### Εισαγωγή Νέας Πληροφορίας")
            
            # Στήλη 1: Keyword
            new_keyword = st.text_input("Φράση-Κλειδί (Keyword, π.χ. 'εργασια μαθηματικα')", key="k1")
            
            # Στήλη 4: Type
            new_type = st.radio("Τύπος Καταχώρησης", ('Text', 'File'), key="t1")
            
            # Στήλη 2 & 3: Info & URL (εξαρτώνται από τον Type)
            if new_type == 'Text':
                new_info = st.text_area("Περιγραφή (Info)", key="i1")
                new_url = "" # Το URL παραμένει κενό για Text
            else: # File
                new_info = st.text_input("Περιγραφή Link (Info)", key="i2")
                new_url = st.text_input("Σύνδεσμος (URL)", key="u1")
                
            # Στήλη 5: Date (προεπιλογή η σημερινή)
            new_date_obj = st.date_input("Ημερομηνία Καταχώρησης (Date)", value="today", key="d1")
            
            # Μετατροπή της ημερομηνίας σε ζητούμενη μορφή DD/MM/YYYY
            new_date_str = new_date_obj.strftime(DATE_FORMAT)
            
            submitted = st.form_submit_button("Καταχώρηση 💾")
            
            if submitted:
                # Έλεγχος βασικών πεδίων
                if new_keyword and new_info:
                    new_entry = pd.DataFrame([
                        {
                            'Keyword': new_keyword.strip(),
                            'Info': new_info.strip(),
                            'URL': new_url.strip(),
                            'Type': new_type,
                            'Date': new_date_str
                        }
                    ])
                    submit_entry(new_entry)
                else:
                    st.error("Παρακαλώ συμπληρώστε τη Φράση-Κλειδί και την Περιγραφή.")

# --------------------------------------------------------------------------------
# 3. UI / ΚΥΡΙΑ ΛΟΓΙΚΗ
# --------------------------------------------------------------------------------

st.set_page_config(page_title="Βοηθός Τάξης (Google Sheets)", layout="centered")
st.title("🤖 Ψηφιακός Βοηθός Τάξης (Google Sheets)")
st.markdown("---")

# Κύριες ενέργειες
tag_to_keyword_map, keyword_to_data_map, available_keys_display = load_data()

# Εμφάνιση Φόρμας Καταχώρησης
data_entry_form() 

st.markdown("---")
st.header("🔍 Αναζήτηση Πληροφοριών")

info_message = f"Διαθέσιμες φράσεις-κλειδιά: **{', '.join(available_keys_display)}**"
st.info(info_message)

user_input = st.text_input(
    'Τι θέλεις να μάθεις;', 
    placeholder='Πληκτρολόγησε π.χ. εκδρομη, εργασια, βιβλια...'
)

if user_input and keyword_to_data_map:
    # Λογική αναζήτησης (ίδια με πριν)
    search_tag = normalize_text(user_input)
    matching_keywords = tag_to_keyword_map.get(search_tag, set())
    
    if matching_keywords:
        all_results = []
        for keyword in matching_keywords:
            all_results.extend(keyword_to_data_map.get(keyword, [])) 

        # Τα αποτελέσματα είναι ήδη ταξινομημένα από το load_data()
        st.success(f"Βρέθηκαν **{len(all_results)}** πληροφορίες από **{len(matching_keywords)}** φράσεις-κλειδιά.")

        for i, (info, url, item_type, date_obj) in enumerate(all_results, 1):
            date_str = date_obj.strftime(DATE_FORMAT) if pd.notna(date_obj) else "Άγνωστη Ημ/νία"
            header = f"**Καταχώρηση {i}** (Ημ/νία: {date_str})"
            
            if item_type.strip().lower() == 'file':
                link_description = info.strip()
                link_url = url.strip()
                if link_url:
                    st.markdown(f"{header}: 📂 [{link_description}](<{link_url}>)")
                else:
                    st.markdown(f"{header}: 💬 **Προσοχή:** Καταχώρηση αρχείου χωρίς σύνδεσμο. Περιγραφή: {link_description}")
            
            elif item_type.strip().lower() == 'text':
                st.markdown(f"{header}: 💬 {info}")
            
            else:
                st.markdown(f"{header}: Άγνωστος Τύπος Καταχώρησης. {info}")
                
    else:
        st.warning(f"Δεν βρέθηκε απάντηση για το: '{user_input}'.")

st.markdown("---")
st.caption("Τα δεδομένα διαβάζονται και γράφονται στο Google Sheet.")

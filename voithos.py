import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import set_with_dataframe, get_dataframe 
from datetime import datetime

# --------------------------------------------------------------------------------
# 0. ΡΥΘΜΙΣΕΙΣ (CONNECTION & FORMATS)
# --------------------------------------------------------------------------------

# Χρησιμοποιεί τα secrets για να συνδεθεί με το Google Service Account
@st.cache_resource
def get_gspread_client():
    """Δημιουργεί και επιστρέφει τον gspread client."""
    try:
        # Δημιουργία dictionary από τα secrets (όπως ρυθμίστηκαν στο toml)
        service_account_info = dict(st.secrets["gcp_service_account"])
        
        # Αντικαθιστούμε τα \n στο private_key για να το διαβάσει σωστά το gspread
        # Αυτό διορθώνει τυχόν προβλήματα μορφοποίησης από τα Streamlit secrets.
        service_account_info['private_key'] = service_account_info['private_key'].replace('\\n', '\n')
        
        # Σύνδεση με το Google Sheets API
        gc = gspread.service_account_from_dict(service_account_info)
        return gc
    except Exception as e:
        st.error(f"Σφάλμα σύνδεσης gspread. Ελέγξτε τα secrets.toml και τα δικαιώματα. Λεπτομέρειες: {e}")
        return None

gc = get_gspread_client()
SHEET_NAME = st.secrets["sheet_name"] 
DATE_FORMAT = '%d/%m/%Y'

# --------------------------------------------------------------------------------
# 1. ΒΟΗΘΗΤΙΚΕΣ ΣΥΝΑΡΤΗΣΕΙΣ
# --------------------------------------------------------------------------------

TONES_MAP = str.maketrans("άέήίόύώ", "αεηιουώ")

def normalize_text(text):
    """Μετατρέπει κείμενο σε πεζά, αφαιρεί τα κενά και τους τόνους."""
    if pd.isna(text): return ''
    normalized = str(text).lower().strip()
    return normalized.translate(TONES_MAP)

def get_tags_from_keyword(keyword):
    """Διαχωρίζει μια φράση-κλειδί σε μεμονωμένα, ομαλοποιημένα tags."""
    if not keyword or pd.isna(keyword): return []
    return [normalize_text(word) for word in str(keyword).split() if word]

@st.cache_data(ttl=600)
def load_data():
    """Φορτώνει, καθαρίζει και ταξινομεί δεδομένα από το Google Sheet."""
    if gc is None:
        return {}, {}, []

    try:
        # Άνοιγμα του Google Sheet και του πρώτου φύλλου (worksheet)
        sh = gc.open(SHEET_NAME)
        ws = sh.get_worksheet(0)
        
        # Ανάγνωση σε DataFrame
        # Χρησιμοποιεί την πρώτη γραμμή (header=1)
        df = get_dataframe(ws, header=1) 
        df.columns = df.columns.str.strip()
        
        required_cols = ['Keyword', 'Info', 'URL', 'Type', 'Date']
        if not all(col in df.columns for col in required_cols):
            st.error(f"Σφάλμα δομής Sheet: Οι επικεφαλίδες πρέπει να είναι: {', '.join(required_cols)}.")
            return {}, {}, []

        # Καθαρισμός/Επεξεργασία δεδομένων
        df = df.dropna(subset=['Keyword', 'Date'], how='any') 
        df['Date'] = pd.to_datetime(df['Date'], format=DATE_FORMAT, errors='coerce')
        df = df.dropna(subset=['Date'])
        
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
    
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"Σφάλμα: Δεν βρέθηκε το Google Sheet με όνομα: '{SHEET_NAME}'. Ελέγξτε το όνομα στα secrets.")
        return {}, {}, []
    except Exception as e:
        st.error(f"Σφάλμα φόρτωσης/επεξεργασίας δεδομένων. Ελέγξτε τις επικεφαλίδες. Λεπτομέρειες: {e}")
        return {}, {}, []

# --------------------------------------------------------------------------------
# 2. ΦΟΡΜΑ ΚΑΤΑΧΩΡΗΣΗΣ
# --------------------------------------------------------------------------------

def submit_entry(new_entry_list):
    """Προσθέτει μια νέα σειρά στο Google Sheet χρησιμοποιώντας gspread."""
    if gc is None:
        st.error("Η σύνδεση με το Google Sheets απέτυχε.")
        return

    try:
        sh = gc.open(SHEET_NAME)
        ws = sh.get_worksheet(0)
        
        # Προσθήκη νέας σειράς (χρησιμοποιούμε τη λίστα τιμών)
        ws.append_row(new_entry_list)
        
        st.cache_data.clear() 
        st.success("🎉 Η καταχώρηση έγινε επιτυχώς! Η εφαρμογή ανανεώνεται...")
        st.balloons()
        st.rerun() 
        
    except Exception as e:
        st.error(f"Σφάλμα κατά την καταχώρηση. Ελέγξτε τα δικαιώματα. Λεπτομέρειες: {e}")

def data_entry_form():
    """Δημιουργεί τη φόρμα εισαγωγής νέων δεδομένων."""
    
    with st.expander("➕ Νέα Καταχώρηση (Διαχειριστής)"):
        with st.form("new_entry_form", clear_on_submit=True):
            st.markdown("### Εισαγωγή Νέας Πληροφορίας")
            
            new_keyword = st.text_input("Φράση-Κλειδί (Keyword, π.χ. 'εργασια μαθηματικα')", key="k1")
            new_type = st.radio("Τύπος Καταχώρησης", ('Text', 'File'), key="t1")
            
            if new_type == 'Text':
                new_info = st.text_area("Περιγραφή (Info)", key="i1")
                new_url = ""
            else: 
                new_info = st.text_input("Περιγραφή Link (Info)", key="i2")
                new_url = st.text_input("Σύνδεσμος (URL)", key="u1")
                
            new_date_obj = st.date_input("Ημερομηνία Καταχώρησης (Date)", value=datetime.today().date(), key="d1")
            
            # Μετατροπή της ημερομηνίας σε ζητούμενη μορφή DD/MM/YYYY
            new_date_str = new_date_obj.strftime(DATE_FORMAT)
            
            submitted = st.form_submit_button("Καταχώρηση 💾")
            
            if submitted:
                if new_keyword and new_info:
                    # Δημιουργία λίστας τιμών με τη σωστή σειρά για το Sheet (Keyword, Info, URL, Type, Date)
                    new_entry_list = [
                        new_keyword.strip(), 
                        new_info.strip(), 
                        new_url.strip(), 
                        new_type, 
                        new_date_str
                    ]
                    submit_entry(new_entry_list)
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

info_message = f"Διαθέσιμες φράσεις-κλειδιά: **{', '.join(available_keys_display)}**" if available_keys_display else "Δεν βρέθηκαν διαθέσιμες φράσεις-κλειδιά."
st.info(info_message)

user_input = st.text_input(
    'Τι θέλεις να μάθεις;', 
    placeholder='Πληκτρολόγησε π.χ. εκδρομη, εργασια, βιβλια...'
)

if user_input and keyword_to_data_map:
    # Λογική αναζήτησης 
    search_tag = normalize_text(user_input)
    matching_keywords = tag_to_keyword_map.get(search_tag, set())
    
    if matching_keywords:
        all_results = []
        for keyword in matching_keywords:
            all_results.extend(keyword_to_data_map.get(keyword, [])) 

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
st.caption("Τα δεδομένα διαβάζονται και γράφονται στο Google Sheet μέσω gspread.")

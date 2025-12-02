import streamlit as st
import pandas as pd
import gspread
from datetime import datetime, timedelta
import re
from typing import List
from urllib.parse import quote_plus
import numpy as np 

# --------------------------------------------------------------------------------
# 0. ΡΥΘΜΙΣΕΙΣ (CONNECTION & FORMATS) & CSS
# --------------------------------------------------------------------------------

@st.cache_resource
def get_gspread_client():
    """Δημιουργεί και επιστρέφει τον gspread client."""
    try:
        service_account_info = dict(st.secrets["gcp_service_account"])
        # Αντικατάσταση των escape sequences για τη σωστή ανάγνωση του private key
        service_account_info['private_key'] = service_account_info['private_key'].replace('\\n', '\n')
        gc = gspread.service_account_from_dict(service_account_info)
        return gc
    except Exception as e:
        # st.error(f"Σφάλμα σύνδεσης gspread. Ελέγξτε τα secrets.toml και τα δικαιώματα. Λεπτομέρειες: {e}")
        return None

gc = get_gspread_client()
SHEET_NAME = st.secrets["sheet_name"]
DATE_FORMAT = '%d/%m/%Y'

def apply_custom_css():
    """Εφαρμόζει Custom CSS για βελτίωση της εμφάνισης."""
    st.markdown("""
        <style>
            /* Κεντρική ρύθμιση εμφάνισης */
            .main-header {
                color: #2E86C1; /* Μπλε χρώμα */
                font-size: 2.2em;
                border-bottom: 2px solid #D6EAF8;
                padding-bottom: 10px;
                margin-top: -20px;
            }
            /* Styling για τις κάρτες ανακοινώσεων (Light Mode Default) */
            .info-card {
                padding: 15px;
                margin-bottom: 15px;
                border-radius: 8px;
                box-shadow: 0 4px 8px 0 rgba(0,0,0,0.1);
                border-left: 5px solid #2E86C1; /* Μπλε μπάρα για έμφαση */
                background-color: #FBFCFC; /* Πολύ ανοιχτό γκρι/μπλε (Φωτεινό) */
            }
            /* Styling για τις μπάρες (παραμένει ίδιο) */
            .info-card-link {
                border-left: 5px solid #28B463; 
            }
            .info-card-text {
                border-left: 5px solid #F39C12; 
            }
            .card-date {
                font-size: 0.9em;
                color: #5D6D7E;
                float: right;
            }
            .card-keyword {
                font-style: italic;
                color: #AAB7B8;
                font-size: 0.8em;
                margin-top: 5px;
            }
            /* Εμφάνιση του st.error σε πιο ευγενικό κίτρινο για warnings */
            div.stAlert > div:nth-child(1) {
                border-left: 10px solid #F1C40F !important;
                background-color: #FEF9E7 !important;
                color: #7D6608 !important;
            }

            /* -------------------------------------------------------------------------- */
            /* DARK MODE FIX: Χρησιμοποιούμε Media Query για να αλλάξουμε το φόντο */
            /* -------------------------------------------------------------------------- */
            @media (prefers-color-scheme: dark) {
                .info-card {
                    /* Πιο σκούρο φόντο για να φαίνεται το ανοιχτόχρωμο κείμενο του Dark Mode */
                    background-color: #1a1a1a; /* Σκούρο γκρι/μαύρο */
                    box-shadow: 0 4px 8px 0 rgba(255,255,255,0.1); /* Λευκή σκιά για Dark Mode */
                }
                .card-date, .card-keyword {
                     /* Διατηρούμε το κείμενο ευανάγνωστο στο Dark Mode */
                    color: #999999; 
                }
                div.stAlert > div:nth-child(1) {
                    /* Προσαρμογή του warning στο Dark Mode */
                    background-color: #4b4204 !important; /* Πιο σκούρο κίτρινο φόντο */
                    color: #FFEB3B !important; /* Ανοιχτό κίτρινο κείμενο */
                }
                /* Διορθώνουμε το χρώμα του κειμένου μέσα στο link στην αναζήτηση */
                a {
                    color: #BBDEFB !important; /* Πολύ ανοιχτό μπλε */
                }
            }
            /* -------------------------------------------------------------------------- */

        </style>
    """, unsafe_allow_html=True)


# --------------------------------------------------------------------------------
# 1. ΒΟΗΘΗΤΙΚΕΣ ΣΥΝΑΡΤΗΣΕΙΣ - ΦΟΡΤΩΣΗ ΔΕΔΟΜΕΝΩΝ
# --------------------------------------------------------------------------------

TONES_MAP = str.maketrans("άέήίόύώ", "αεηιουώ")

def normalize_text(text):
    """Μετατρέπει κείμενο σε πεζά, αφαιρεί τα κενά και τους τόνους (για την αναζήτηση)."""
    if pd.isna(text): return ''
    normalized = str(text).lower().strip()
    return normalized.translate(TONES_MAP)

def get_tags_from_keyword(keyword):
    """Διαχωρίζει μια φράση-κλειδί σε μεμονωμένα, ομαλοποιημένα tags."""
    if not keyword or pd.isna(keyword): return []
    return [normalize_text(word) for word in str(keyword).split() if word]

@st.cache_data(ttl=600)
def load_data():
    """Φορτώνει, καθαρίζει και ταξινομεί δεδομένα από το ενιαίο Google Sheet (ClassBot)."""
    if gc is None:
        return pd.DataFrame(), []

    try:
        sh = gc.open(SHEET_NAME)
        # Χρησιμοποιούμε το πρώτο worksheet (index 0) ως το κύριο φύλλο δεδομένων (ClassBot)
        ws = sh.get_worksheet(0)
        data = ws.get_all_values()
        
        headers = data[0] if data else []
        df = pd.DataFrame(data[1:], columns=headers)
        df.columns = df.columns.str.strip()
        
        # ΠΡΟΣΟΧΗ: Ελέγχουμε τις βασικές στήλες (ΠΡΟΣΘΗΚΗ: 'ActionDate')
        required_cols = ['Keyword', 'Info', 'URL', 'Type', 'Date', 'School', 'Tmima', 'UserId', 'ActionDate']
        if not all(col in df.columns for col in required_cols):
            st.error(f"Σφάλμα δομής Sheet 'ClassBot': Οι επικεφαλίδες πρέπει να είναι: {', '.join(required_cols)}.")
            return pd.DataFrame(), []
        
        # Καθαρισμός/Επεξεργασία δεδομένων
        df = df.dropna(subset=['Keyword', 'Date', 'School', 'Tmima'], how='any')
        
        # ΝΕΟ: Εφαρμόζουμε .str.strip() σε όλες τις κρίσιμες string στήλες για ασφάλεια
        # Αυτό διορθώνει τυχόν κενά που μπορεί να έχουν προστεθεί στις νέες εγγραφές
        string_cols = ['Keyword', 'Info', 'URL', 'Type', 'School', 'Tmima', 'UserId']
        for col in string_cols:
            if col in df.columns:
                # Χρησιμοποιούμε .astype(str) για να εξασφαλίσουμε ότι είναι strings πριν το strip
                df[col] = df[col].astype(str).str.strip()

        df['Date'] = pd.to_datetime(df['Date'], format=DATE_FORMAT, errors='coerce')
        # Επεξεργασία της ActionDate
        df['ActionDate'] = pd.to_datetime(df['ActionDate'], format=DATE_FORMAT, errors='coerce')
        df = df.dropna(subset=['Date'])
        
        available_schools = sorted(df['School'].unique().tolist()) if 'School' in df.columns else []
        
        # Προσθήκη μοναδικού ID για διαγραφή/διόρθωση (Αντιστοιχεί στην index της σειράς στο sheet)
        df['Internal_ID'] = df.index + 1 
        
        return df, available_schools
        
    except Exception as e:
        st.error(f"Σφάλμα φόρτωσης/επεξεργασίας δεδομένων 'ClassBot'. Λεπτομέρειες: {e}")
        return pd.DataFrame(), []

@st.cache_data(ttl=600)
def load_users_data():
    """Φορτώνει τα δεδομένα χρηστών (UserId, School, Name, UserName, Password) από το sheet 'Χρήστες'."""
    if gc is None:
        return pd.DataFrame()

    try:
        sh = gc.open(SHEET_NAME)
        ws = sh.worksheet("Χρήστες")
        data = ws.get_all_values()

        headers = data[0] if data else []
        df_users = pd.DataFrame(data[1:], columns=headers)
        df_users.columns = df_users.columns.str.strip()

        required_cols = ['UserId', 'School', 'UserName', 'Password']
        if not all(col in df_users.columns for col in required_cols):
            st.error(f"Σφάλμα δομής Sheet 'Χρήστες': Οι επικεφαλίδες πρέπει να είναι: {', '.join(required_cols)}.")
            return pd.DataFrame()

        df_users = df_users.dropna(subset=required_cols, how='any')
        
        # Καθαρισμός των τιμών των χρηστών (UserId, School, UserName, Password)
        for col in required_cols:
             df_users[col] = df_users[col].astype(str).str.strip()

        return df_users

    except Exception as e:
        # st.error(f"Σφάλμα φόρτωσης δεδομένων χρηστών. Λεπτομέρειες: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=600)
def load_tmima_data(school_name: str) -> List[str]:
    """Φορτώνει τη λίστα των Τμημάτων για ένα συγκεκριμένο Σχολείο από το sheet 'Σχολεία'."""
    if gc is None:
        return []

    try:
        sh = gc.open(SHEET_NAME)
        ws = sh.worksheet("Σχολεία")
        data = ws.get_all_values()
        
        headers = data[0] if data else []
        df_tmima = pd.DataFrame(data[1:], columns=headers)
        df_tmima.columns = df_tmima.columns.str.strip()
        
        required_cols = ['School', 'Tmima']
        if not all(col in df_tmima.columns for col in required_cols):
            st.warning(f"⚠️ Προσοχή: Σφάλμα δομής Sheet 'Σχολεία'. Συνεχίζουμε με χειροκίνητη εισαγωγή Τμήματος.")
            return []

        # Φιλτράρισμα βάσει Σχολείου και επιστροφή μοναδικών Τμημάτων
        tmimata = df_tmima[df_tmima['School'].astype(str).str.strip() == school_name.strip()]['Tmima'].unique().tolist()
        return sorted([t.strip().upper() for t in tmimata if t.strip()])
        
    except gspread.exceptions.WorksheetNotFound:
        st.warning("⚠️ Προσοχή: Δεν βρέθηκε το worksheet 'Σχολεία'. Η καταχώρηση Τμήματος θα γίνει χειροκίνητα.")
        return []
    except Exception as e:
        # st.error(f"Σφάλμα φόρτωσης δεδομένων Τμημάτων από το sheet 'Σχολεία'. Λεπτομέρειες: {e}")
        return []

def create_search_maps(df):
    """Δημιουργεί τους χάρτες αναζήτησης μετά το φιλτράρισμα."""
    df_sorted = df.sort_values(by=['Keyword', 'Date'], ascending=[True, False])
    
    # Το zip περιλαμβάνει 9 στοιχεία: (Info, URL, Type, Date, School, Tmima, UserId, ActionDate, Internal_ID)
    keyword_to_data_map = df_sorted.groupby('Keyword').apply(
        lambda x: list(zip(x['Info'], x['URL'], x['Type'], x['Date'], x['School'], x['Tmima'], x.get('UserId', ''), x.get('ActionDate', pd.NaT), x['Internal_ID']))
    ).to_dict()

    tag_to_keyword_map = {}
    unique_keywords = df_sorted['Keyword'].unique()
    for keyword in unique_keywords:
        normalized_tags = get_tags_from_keyword(keyword)
        for tag in normalized_tags:
            if tag not in tag_to_keyword_map:
                tag_to_keyword_map[tag] = set()
            tag_to_keyword_map[tag].add(keyword)
            
    return tag_to_keyword_map, keyword_to_data_map


# --------------------------------------------------------------------------------
# 2. ΦΟΡΜΑ ΚΑΤΑΧΩΡΗΣΗΣ / AUTHENTICATION / UPDATE
# --------------------------------------------------------------------------------

def submit_entry(new_entry_list):
    """Προσθέτει μια νέα σειρά στο Google Sheet (ClassBot)."""
    if gc is None:
        st.error("Η σύνδεση με το Google Sheets απέτυχε.")
        return

    try:
        sh = gc.open(SHEET_NAME)
        ws = sh.get_worksheet(0) # Sheet ClassBot

        # Προσθήκη της νέας σειράς
        ws.append_row(new_entry_list)

        # Κλείνουμε τη φόρμα και επαναφέρουμε τον τύπο καταχώρησης
        st.session_state['entry_expander_state'] = False 
        st.session_state['entry_type'] = 'Text'
        if 'new_url_value' in st.session_state:
             st.session_state['new_url_value'] = "" # Μηδενίζουμε και το URL

        # Καθαρισμός cache και επανεκτέλεση
        st.cache_data.clear()
        st.success("🎉 Η καταχώρηση έγινε επιτυχώς! Η εφαρμογή ανανεώνεται...")
        st.balloons()
        st.rerun()
        
    except Exception as e:
        st.error(f"Σφάλμα κατά την καταχώρηση. Ελέγξτε τα δικαιώματα. Λεπτομέρειες: {e}")


def update_entry(row_index: int, updated_list: list):
    """Ενημερώνει μια υπάρχουσα σειρά στο Google Sheet (ClassBot) με βάση το Internal_ID."""
    if gc is None:
        st.error("Η σύνδεση με το Google Sheets απέτυχε.")
        return False

    try:
        sh = gc.open(SHEET_NAME)
        ws = sh.get_worksheet(0) # Sheet ClassBot

        # Η gspread row index (1-based) είναι το Internal_ID + 1 (Internal_ID = Pandas index + 1)
        gspread_row_index = row_index + 1
        
        # Ενημέρωση της σειράς με τα νέα δεδομένα (χρησιμοποιείται η ws.update(cell, value))
        # Το gspread.update(range_name, values) παίρνει μια λίστα λιστών (για μία σειρά)
        ws.update(f'A{gspread_row_index}', [updated_list], value_input_option='USER_ENTERED') 

        # Καθαρισμός cache και επανεκτέλεση
        st.cache_data.clear() 
        st.success("✅ Η διόρθωση έγινε επιτυχώς! Η εφαρμογή ανανεώθηκε.")
        st.rerun() 
        return True
        
    except Exception as e:
        st.error(f"Σφάλμα κατά την διόρθωση στο Sheet. Λεπτομέρειες: {e}")
        return False
# -----------------------------------------------------------------------------

def data_entry_form(available_schools, logged_in_school, logged_in_userid):
    """Δημιουργεί τη φόρμα εισαγωγής νέων δεδομένων. (Το σχολείο είναι προ-επιλεγμένο)"""
    
    if 'entry_expander_state' not in st.session_state:
        st.session_state['entry_expander_state'] = False
        
    tmimata_list = load_tmima_data(logged_in_school)

    # Το expander χρησιμοποιεί την αποθηκευμένη κατάσταση
    with st.expander(f"➕ Νέα Καταχώρηση για το {logged_in_school}", expanded=st.session_state.entry_expander_state):
        
        # Λειτουργία που καλείται στο on_change για να διατηρεί το expander ανοιχτό
        def keep_expander_open():
             st.session_state['entry_expander_state'] = True
        
        st.markdown("### Εισαγωγή Νέας Πληροφορίας")
        
        # 1. ΕΠΙΛΟΓΗ ΣΧΟΛΕΙΟΥ & ΤΜΗΜΑΤΟΣ (Το Σχολείο είναι προεπιλεγμένο/κλειδωμένο)
        st.code(f"Σχολείο Καταχώρησης: {logged_in_school}", language='text')
        new_school = logged_in_school
        
        if tmimata_list:
             # Επιλογή από λίστα (από το sheet 'Σχολεία')
            new_tmima = st.selectbox(
                "Τμήμα (Tmima):", 
                options=["-- Επιλέξτε Τμήμα --"] + tmimata_list,
                key="form_tmima_select",
                on_change=keep_expander_open # Callback
            )
            new_tmima_input = new_tmima if new_tmima != "-- Επιλέξτε Τμήμα --" else ""
        else:
             # Χειροκίνητη εισαγωγή αν δεν βρεθεί το sheet 'Σχολεία'
            new_tmima_input = st.text_input(
                "Τμήμα (Tmima):", 
                placeholder="Πρέπει να είναι Ελληνικοί Κεφαλαίοι (Π.χ. Α1, Γ2)",
                key="form_tmima_text",
                on_change=keep_expander_open # Callback
            )
        
        # 2. Το Radio Button ΕΞΩ από το Form (Για άμεσο rerun/UX fix)
        if 'entry_type' not in st.session_state:
            st.session_state['entry_type'] = 'Text'
            
        st.session_state.entry_type = st.radio(
            "Τύπος Καταχώρησης", 
            ('Text', 'Link'), 
            horizontal=True,
            index=0 if st.session_state['entry_type'] == 'Text' else 1,
            key="radio_type_key"
        )
        
        new_url = ""
        
        # 3. Άμεση εμφάνιση του πεδίου URL αν επιλεγεί
        if st.session_state.entry_type == 'Link':
            st.session_state['new_url_value'] = st.text_input(
                "Σύνδεσμος (URL)", 
                key="u1_link_input",
                placeholder="Προσθέστε έναν URL, σύνδεσμο Google Drive, κλπ."
            )
            new_url = st.session_state.get('new_url_value', "")
        
        # --------------------------------------------------------------------------
        # ΠΕΔΙΑ ΗΜΕΡΟΛΟΓΙΟΥ (ΕΚΤΟΣ ΤΟΥ FORM ΓΙΑ ΔΥΝΑΜΙΚΗ ΕΜΦΑΝΙΣΗ)
        # --------------------------------------------------------------------------
        st.markdown("---")
        st.subheader("Ρυθμίσεις Ημερολογίου")
        
        # 1. Checkbox - ΤΩΡΑ ΕΚΤΟΣ ΤΟΥ FORM
        show_in_calendar = st.checkbox(
            "Εμφάνιση στο Ημερολόγιο (ως επικείμενη ενέργεια)",
            key="calendar_check_d1",
        )
        
        new_action_date_str = "" # Default Value

        # 2. Date Input - ΤΩΡΑ ΕΚΤΟΣ ΤΟΥ FORM
        if show_in_calendar:
            new_action_date_obj = st.date_input(
                "Ημερομηνία Ενέργειας (Action Date):", 
                value=datetime.today().date() + timedelta(days=7), # Προεπιλογή 1 εβδομάδα μετά
                key="action_date_d1",
            )
            new_action_date_str = new_action_date_obj.strftime(DATE_FORMAT)
        
        st.markdown("---")
        # --------------------------------------------------------------------------

        # 4. ΦΟΡΜΑ ΥΠΟΒΟΛΗΣ (με τα υπόλοιπα πεδία)
        with st.form("new_entry_form", clear_on_submit=True):
            
            new_keyword = st.text_input("Φράση-Κλειδί (Keyword, π.χ. 'εργασια μαθηματικα')", key="k1_form")

            if st.session_state.entry_type == 'Text':
                new_info = st.text_area("Περιγραφή (Info)", key="i1_text_area")
            else: 
                new_info = st.text_input("Περιγραφή Συνδέσμου (Info)", key="i2_text_input")

            # Ημερομηνία Καταχώρησης (Διατηρείται)
            new_date_obj = st.date_input("Ημερομηνία Καταχώρησης (Date)", value=datetime.today().date(), key="d1_date")
            new_date_str = new_date_obj.strftime(DATE_FORMAT)
            
            submitted = st.form_submit_button("Καταχώρηση 💾")
            
            if submitted:
                final_url = new_url.strip() if st.session_state.entry_type == 'Link' else ""
                final_tmima = new_tmima_input.strip().upper().replace(" ", "")

                # Αυτόματη Προσθήκη https://
                if final_url and st.session_state.entry_type == 'Link':
                    if not final_url.lower().startswith(('http://', 'https://', 'ftp://')):
                        final_url = 'https://' + final_url
                
                # ΕΛΕΓΧΟΣ ΕΓΚΥΡΟΤΗΤΑΤΟΣ ΤΜΗΜΑΤΟΣ (αν δεν έγινε επιλογή)
                tmima_pattern = re.compile(r'^[Α-Ω0-9]+$')

                if not tmima_pattern.match(final_tmima) or final_tmima == "":
                    st.error("⚠️ Σφάλμα Τμήματος: Το πεδίο 'Τμήμα' είναι κενό ή περιέχει μη επιτρεπτούς χαρακτήρες. Χρησιμοποιήστε μόνο Ελληνικούς κεφαλαίους (Α-Ω) και αριθμούς (0-9).")
                    st.stop()
                
                # ΕΛΕΓΧΟΣ ΕΓΚΥΡΟΤΗΤΑΣ ΗΜΕΡΟΛΟΓΙΟΥ
                # Ελέγχουμε την τιμή που διαβάστηκε από το widget εκτός φόρμας
                if show_in_calendar and not new_action_date_str:
                    st.error("⚠️ Σφάλμα Ημερολογίου: Επιλέξατε εμφάνιση στο Ημερολόγιο, αλλά δεν ορίσατε 'Ημερομηνία Ενέργειας'.")
                    st.stop()
                    
                # Έλεγχος πληρότητας
                if not new_keyword or not new_info or not new_school or (st.session_state.entry_type == 'Link' and not final_url):
                    st.error("Παρακαλώ συμπληρώστε όλα τα πεδία (Φράση-Κλειδί, Περιγραφή, Σχολείο, Τμήμα και Σύνδεσμο αν είναι Link).")
                    st.stop()
                else:
                    # Σειρά στο ClassBot Sheet: Keyword, Info, URL, Type, Date, School, Tmima, UserId, ActionDate
                    new_entry_list = [
                        new_keyword.strip(), 
                        new_info.strip(), 
                        final_url, 
                        st.session_state.entry_type, 
                        new_date_str,
                        new_school, 
                        final_tmima, 
                        logged_in_userid,
                        new_action_date_str # ActionDate (Διαβάζεται από το widget εκτός φόρμας)
                    ]
                    submit_entry(new_entry_list)

def edit_entry_form(entry_data: pd.Series, logged_in_school: str):
    """
    Δημιουργεί τη φόρμα επεξεργασίας για μια συγκεκριμένη καταχώρηση.
    """
    current_keyword = entry_data['Keyword']
    current_info = entry_data['Info']
    current_url = entry_data['URL']
    current_type = entry_data['Type']
    current_date = entry_data['Date'].date()
    current_tmima = entry_data['Tmima']
    current_userid = entry_data['UserId']
    current_action_date = entry_data.get('ActionDate')
    internal_id = entry_data['Internal_ID'] 

    tmimata_list = load_tmima_data(logged_in_school)
    
    # ΠΡΟΣΔΙΟΡΙΣΜΟΣ ΑΡΧΙΚΗΣ ΤΙΜΗΣ ΓΙΑ ΤΟ ΗΜΕΡΟΛΟΓΙΟ
    is_in_calendar_initial = pd.notna(current_action_date)
    current_action_date_value = current_action_date.date() if is_in_calendar_initial else datetime.today().date() + timedelta(days=7)


    # --------------------------------------------------------------------------
    # 1. ΤΥΠΟΣ ΚΑΤΑΧΩΡΗΣΗΣ (ΕΚΤΟΣ ΦΟΡΜΑΣ ΓΙΑ ΔΥΝΑΜΙΚΟ RERUN)
    # --------------------------------------------------------------------------

    # Εξασφάλιση ότι η session state έχει αρχική τιμή
    if f'edit_entry_type_{internal_id}' not in st.session_state:
        st.session_state[f'edit_entry_type_{internal_id}'] = current_type

    # Radio Button για την επιλογή Τύπου (Text/Link)
    st.session_state[f'edit_entry_type_{internal_id}'] = st.radio(
        "Τύπος Καταχώρησης", 
        ('Text', 'Link'), 
        index=0 if current_type == 'Text' else 1,
        horizontal=True,
        key=f"edit_radio_type_{internal_id}"
    )

    # --------------------------------------------------------------------------
    # 2. ΥΠΟΛΟΙΠΑ ΠΕΔΙΑ ΠΟΥ ΕΞΑΡΤΩΝΤΑΙ ΑΠΟ ΤΟΝ ΤΥΠΟ (ΕΚΤΟΣ ΦΟΡΜΑΣ)
    # --------------------------------------------------------------------------
    
    edited_url = ""
    edited_info = ""
    
    if st.session_state[f'edit_entry_type_{internal_id}'] == 'Link':
        # Εμφάνιση URL
        st.session_state[f'edit_url_value_{internal_id}'] = st.text_input(
            "Σύνδεσμος (URL)", 
            value=current_url if current_type == 'Link' else "",
            key=f"edit_url_input_{internal_id}",
            placeholder="Προσθέστε έναν URL, σύνδεσμο Google Drive, κλπ."
        )
        edited_url = st.session_state[f'edit_url_value_{internal_id}']
        
        # Περιγραφή Συνδέσμου (Info)
        edited_info = st.text_input(
            "Περιγραφή Συνδέσμου (Info):", 
            value=current_info, 
            key=f"edit_info_link_{internal_id}"
        )
    else:
        # Περιγραφή (Info)
        edited_info = st.text_area(
            "Περιγραφή (Info):", 
            value=current_info, 
            key=f"edit_info_text_{internal_id}"
        )

    # --------------------------------------------------------------------------
    # ΠΕΔΙΑ ΗΜΕΡΟΛΟΓΙΟΥ (ΕΚΤΟΣ ΤΟΥ FORM ΓΙΑ ΔΥΝΑΜΙΚΗ ΕΜΦΑΝΙΣΗ)
    # --------------------------------------------------------------------------
    st.markdown("---")
    st.subheader("Ρυθμίσεις Ημερολογίου")
    
    # 1. Checkbox (ΕΚΤΟΣ FORM)
    if f'edit_calendar_check_{internal_id}' not in st.session_state:
        st.session_state[f'edit_calendar_check_{internal_id}'] = is_in_calendar_initial
        
    show_in_calendar_edit = st.checkbox(
        "Εμφάνιση στο Ημερολόγιο (ως επικείμενη ενέργεια)",
        value=st.session_state[f'edit_calendar_check_{internal_id}'],
        key=f"calendar_check_edit_{internal_id}",
    )
    
    edited_action_date_str = "" # Default Value

    # 2. Date Input (ΕΚΤΟΣ FORM)
    if show_in_calendar_edit:
        edited_action_date_obj = st.date_input(
            "Ημερομηνία Ενέργειας (Action Date):", 
            value=current_action_date_value, 
            key=f"action_date_edit_{internal_id}"
        )
        edited_action_date_str = edited_action_date_obj.strftime(DATE_FORMAT)
        
    st.session_state[f'edit_calendar_check_{internal_id}'] = show_in_calendar_edit # Update session state
    st.markdown("---")
    # --------------------------------------------------------------------------

    # 3. ΦΟΡΜΑ ΥΠΟΒΟΛΗΣ 
    with st.form(f"edit_form_{internal_id}"):
        
        # Σχολείο (Locked)
        st.code(f"Σχολείο: {logged_in_school}", language='text')
        
        # Τμήμα
        if tmimata_list:
            default_tmima_index = 0
            if current_tmima in tmimata_list:
                default_tmima_index = tmimata_list.index(current_tmima) + 1 
            edited_tmima = st.selectbox(
                "Τμήμα (Tmima):", 
                options=["-- Επιλέξτε Τμήμα --"] + tmimata_list,
                index=default_tmima_index,
                key=f"edit_tmima_select_{internal_id}"
            )
            final_edited_tmima = edited_tmima if edited_tmima != "-- Επιλέξτε Τμήμα --" else ""
        else:
            final_edited_tmima = st.text_input(
                "Τμήμα (Tmima):", 
                value=current_tmima, 
                placeholder="Πρέπει να είναι Ελληνικοί Κεφαλαίοι (Π.χ. Α1, Γ2)",
                key=f"edit_tmima_text_{internal_id}"
            )

        # Φράση-Κλειδί
        edited_keyword = st.text_input(
            "Φράση-Κλειδί (Keyword):", 
            value=current_keyword, 
            key=f"edit_keyword_{internal_id}"
        )
        
        # Ημερομηνία Καταχώρησης
        edited_date_obj = st.date_input(
            "Ημερομηνία Καταχώρησης (Date):", 
            value=current_date, 
            key=f"edit_date_{internal_id}"
        )
        edited_date_str = edited_date_obj.strftime(DATE_FORMAT)

        submitted_edit = st.form_submit_button("Αποθήκευση Αλλαγών ✅")

        if submitted_edit:
            final_edited_url = edited_url.strip() if st.session_state[f'edit_entry_type_{internal_id}'] == 'Link' else ""
            final_edited_tmima_cleaned = final_edited_tmima.strip().upper().replace(" ", "")

            # Αυτόματη Προσθήκη https:// αν είναι Link και δεν έχει πρωτόκολλο
            if final_edited_url and st.session_state[f'edit_entry_type_{internal_id}'] == 'Link':
                if not final_edited_url.lower().startswith(('http://', 'https://', 'ftp://')):
                    final_edited_url = 'https://' + final_edited_url

            # Έλεγχος εγκυρότητας Τμήματος
            tmima_pattern = re.compile(r'^[Α-Ω0-9]+$')
            if not tmima_pattern.match(final_edited_tmima_cleaned) or final_edited_tmima_cleaned == "":
                st.error("⚠️ Σφάλμα Τμήματος: Το πεδίο 'Τμήμα' είναι κενό ή περιέχει μη επιτρεπτούς χαρακτήρες. Χρησιμοποιήστε μόνο Ελληνικούς κεφαλαίους (Α-Ω) και αριθμούς (0-9).")
                st.stop()
            
            # Έλεγχος εγκυρότητας ActionDate
            # Χρησιμοποιούμε τις μεταβλητές που ορίστηκαν εκτός φόρμας
            if show_in_calendar_edit and not edited_action_date_str:
                st.error("⚠️ Σφάλμα Ημερολογίου: Επιλέξατε εμφάνιση στο Ημερολόγιο, αλλά δεν ορίσατε 'Ημερομηνία Ενέργειας'.")
                st.stop()

            # Έλεγχος πληρότητας
            if not edited_keyword or not edited_info or (st.session_state[f'edit_entry_type_{internal_id}'] == 'Link' and not final_edited_url):
                st.error("Παρακαλώ συμπληρώστε όλα τα πεδία (Φράση-Κλειδί, Περιγραφή και Σύνδεσμο αν είναι Link).")
                st.stop()
            else:
                # Sheet: Keyword, Info, URL, Type, Date, School, Tmima, UserId, ActionDate
                updated_entry_list = [
                    edited_keyword.strip(), 
                    edited_info.strip(), 
                    final_edited_url, 
                    st.session_state[f'edit_entry_type_{internal_id}'], 
                    edited_date_str,
                    logged_in_school, # Το σχολείο δεν αλλάζει
                    final_edited_tmima_cleaned,  
                    current_userid, # Ο UserId δεν αλλάζει
                    edited_action_date_str # ActionDate
                ]
                
                # Καλείται η συνάρτηση update_entry
                update_entry(internal_id, updated_entry_list)


def teacher_login(df_users):
    """Δημιουργεί τη φόρμα σύνδεσης και χειρίζεται την πιστοποίηση."""

    if 'authenticated' not in st.session_state:
        st.session_state['authenticated'] = False
        st.session_state['logged_in_school'] = None
        st.session_state['logged_in_userid'] = None 
        st.session_state['login_attempted'] = False

    st.sidebar.markdown("### Σύνδεση Εκπαιδευτικού 🔑")

    if st.session_state.authenticated:
        st.sidebar.success(f"Συνδεδεμένος ως: **{st.session_state.logged_in_school}**")
        if st.sidebar.button("Αποσύνδεση"):
            st.session_state.authenticated = False
            st.session_state.logged_in_school = None
            st.session_state.logged_in_userid = None
            # Κλείνουμε το expander κατά την αποσύνδεση
            st.session_state['entry_expander_state'] = False 
            st.cache_data.clear()
            st.rerun()
        return True

    with st.sidebar.form("login_form"):
        username_input = st.text_input("Όνομα Χρήστη (UserName)", key="login_username")
        password_input = st.text_input("Κωδικός (Password)", type="password", key="login_password")
        submitted = st.form_submit_button("Σύνδεση")

        if submitted:
            st.session_state.login_attempted = True

            user_found = df_users[
                (df_users['UserName'].astype(str).str.strip() == username_input.strip()) &
                (df_users['Password'].astype(str).str.strip() == password_input.strip())
            ]

            if not user_found.empty:
                st.session_state.authenticated = True
                st.session_state.logged_in_school = user_found['School'].iloc[0].strip()
                st.session_state.logged_in_userid = user_found['UserId'].iloc[0].strip() 
                st.success("Επιτυχής σύνδεση!")
                st.rerun() 
            else:
                st.error("Λάθος όνομα χρήστη ή κωδικός.")
                st.session_state.authenticated = False
                st.session_state.logged_in_school = None
                st.session_state.logged_in_userid = None

    if st.session_state.login_attempted and not st.session_state.authenticated:
        st.sidebar.error("Αποτυχία σύνδεσης.")

    return st.session_state.authenticated

def manage_user_posts(df, logged_in_userid):
    """Εμφανίζει και επιτρέπει τη διαχείριση (διόρθωση/διαγραφή) των καταχωρήσεων του χρήστη."""
    
    # Χρησιμοποιούμε τη στήλη 'UserId' για το φιλτράρισμα
    # Το df.get('UserId', '') διασφαλίζει ότι υπάρχει η στήλη.
    # Το .astype(str).str.strip() έχει γίνει πλέον στη load_data, αλλά το διατηρούμε για διπλό έλεγχο.
    user_posts = df[df.get('UserId', '').astype(str).str.strip() == logged_in_userid].copy()
    logged_in_school = st.session_state.get('logged_in_school') # Χρειαζόμαστε το σχολείο για το edit form
    
    if user_posts.empty:
        st.info(f"Δεν βρέθηκαν καταχωρήσεις για τον δικό σας χρήστη (UserId: {logged_in_userid}).")
        return

    st.header("✏️ Διαχείριση Καταχώρησης")
    st.info(f"Εμφανίζονται οι **{len(user_posts)}** καταχωρήσεις σας. Μπορείτε να τις επεξεργαστείτε ή να τις διαγράψετε.")
    
    user_posts = user_posts.sort_values(by='Date', ascending=False)
    
    # Δημιουργία λίστας για την επιλογή επεξεργασίας/διαγραφής
    post_options = ["-- Επιλέξτε Καταχώρηση --"]
    post_details_map = {} # Για να αποθηκεύσουμε τις λεπτομέρειες κάθε post (Pandas Series)
    for index, row in user_posts.iterrows():
        date_str = row['Date'].strftime(DATE_FORMAT)
        tmima = row['Tmima']
        keyword = row['Keyword']
        # Εμφάνιση ειδοποίησης αν είναι στο ημερολόγιο
        calendar_status = " [📅]" if pd.notna(row.get('ActionDate')) else ""
        
        info_preview = row['Info'][:70] + "..." if len(row['Info']) > 70 else row['Info']
        option_label = f"[{date_str} - {tmima}]{calendar_status} {keyword} - {info_preview} (ID: {row['Internal_ID']})"
        post_options.append(option_label)
        post_details_map[option_label] = row # Αποθηκεύουμε ολόκληρη τη σειρά (DataFrame row)

    # ----------------------------------------------------------------------
    # Επιλογή Καταχώρησης για Επεξεργασία/Διαγραφή
    # ----------------------------------------------------------------------
    selected_post_str = st.selectbox(
        "Επιλέξτε την καταχώρηση για επεξεργασία ή διαγραφή:",
        options=post_options,
        key="edit_delete_select"
    )

    if selected_post_str != "-- Επιλέξτε Καταχώρηση --":
        selected_post_row = post_details_map[selected_post_str]
        
        # ----------------------------------------------------------------------
        # Φόρμα Επεξεργασίας (Edit Form)
        # ----------------------------------------------------------------------
        with st.expander(f"⚙️ Επεξεργασία Καταχώρησης (ID: {selected_post_row['Internal_ID']})", expanded=True):
            st.markdown("### Επεξεργασία Υπάρχουσας Πληροφορίας")
            
            # Καλεί τη νέα συνάρτηση για τη φόρμα επεξεργασίας
            edit_entry_form(selected_post_row, logged_in_school)

        st.markdown("---") # Οπτικός διαχωρισμός
        
        # ----------------------------------------------------------------------
        # Φόρμα Διαγραφής (Delete Form)
        # ----------------------------------------------------------------------
        with st.form("delete_form_individual"):
            st.subheader(f"Διαγραφή Καταχώρησης (ID: {selected_post_row['Internal_ID']})")
            st.error(f"⚠️ Προσοχή: Είστε σίγουροι ότι θέλετε να διαγράψετε την καταχώρηση: {selected_post_row['Keyword']} - {selected_post_row['Info'][:50]}...;")
            
            delete_submitted = st.form_submit_button("Οριστική Διαγραφή 🗑️", help="Αυτή η ενέργεια δεν αναιρείται!")

            if delete_submitted:
                # gspread row index (1-based) = Internal_ID + 1
                gspread_row_index = int(selected_post_row['Internal_ID']) + 1 

                try:
                    sh = gc.open(SHEET_NAME)
                    ws = sh.get_worksheet(0)
                    ws.delete_rows(gspread_row_index)
                    
                    st.cache_data.clear()
                    st.success(f"🗑️ Η καταχώρηση (ID: {selected_post_row['Internal_ID']}) διαγράφηκε επιτυχώς.")
                    st.rerun()

                except Exception as e:
                    st.error(f"Σφάλμα κατά τη διαγραφή από το Google Sheet. Λεπτομέρειες: {e}")
                
    st.markdown("---")


# --------------------------------------------------------------------------------
# 3. UI / ΚΥΡΙΑ ΛΟΓΙΚΗ
# --------------------------------------------------------------------------------

st.set_page_config(page_title="Βοηθός Τάξης", layout="centered")

# Εφαρμογή του Custom CSS
apply_custom_css()

# ΟΡΙΣΤΕ ΤΗΝ RAW URL ΓΙΑ ΤΟ ΛΟΓΟΤΥΠΟ
RAW_IMAGE_URL = "https://raw.githubusercontent.com/nikosn937/bot/main/ClassBot.gif"

# Δημιουργία δύο στηλών: η πρώτη (1/5) για το λογότυπο, η δεύτερη (4/5) για τον τίτλο
col1, col2 = st.columns([1, 4])

with col1:
    st.image(RAW_IMAGE_URL, width=150)

with col2:
    st.markdown("<h2 class='main-header'>Ψηφιακός Βοηθός Τάξης</h2>", unsafe_allow_html=True)
    st.caption("Steam Project")

st.markdown("---") 

# Φόρτωση όλων των δεδομένων και των διαθέσιμων επιλογών
full_df, available_schools = load_data()
df_users = load_users_data() # Φόρτωση δεδομένων χρηστών

# ΕΝΣΩΜΑΤΩΣΗ ΦΟΡΜΑΣ ΣΥΝΔΕΣΗΣ ΣΤΗΝ ΠΛΕΥΡΙΚΗ ΣΤΗΛΗ
is_authenticated = teacher_login(df_users)
st.markdown("---")


# 1. ΕΠΙΛΟΓΗ ΣΧΟΛΕΙΟΥ
logged_in_school_val = st.session_state.get('logged_in_school')
default_index = 0
if logged_in_school_val and logged_in_school_val in available_schools:
    # Εύρεση της index για την αυτόματη επιλογή
    try:
        default_index = available_schools.index(logged_in_school_val) + 1
    except ValueError:
        default_index = 0

selected_school = st.selectbox(
    "Επιλέξτε Σχολείο:",
    options=["-- Επιλέξτε --"] + available_schools,
    index=default_index, # Χρησιμοποιούμε την default_index
    key="school_selector"
)

# 2. ΦΙΛΤΡΑΡΙΣΜΑ DF ανά ΣΧΟΛΕΙΟ
if selected_school and selected_school != "-- Επιλέξτε --" and not full_df.empty:

    logged_in_school = st.session_state.get('logged_in_school')
    logged_in_userid = st.session_state.get('logged_in_userid') 

    # --------------------------------------------------------------------------
    # ΕΛΕΓΧΟΣ ΠΡΟΣΒΑΣΗΣ ΦΟΡΜΑΣ ΚΑΤΑΧΩΡΗΣΗΣ / ΔΙΑΧΕΙΡΙΣΗΣ
    # --------------------------------------------------------------------------
    if is_authenticated and logged_in_school == selected_school:
        # 1. Εμφάνιση Φόρμας Καταχώρησης
        data_entry_form(available_schools, logged_in_school, logged_in_userid)
        st.markdown("---") 
        
        # 2. Εμφάνιση Φόρμας Διαχείρισης (Διόρθωσης/Διαγραφής)
        manage_user_posts(full_df, logged_in_userid)
        st.markdown("---")
        
    elif is_authenticated:
        st.warning(f"Είστε συνδεδεμένος ως εκπαιδευτικός του **{logged_in_school}** (UserId: {logged_in_userid}). Για καταχώρηση/διαχείριση, πρέπει να επιλέξετε το σχολείο σας ('{logged_in_school}').")
        st.markdown("---")
    else:
        st.info("Για να δείτε/χρησιμοποιήσετε τη φόρμα καταχώρησης/διαχείρισης, παρακαλώ συνδεθείτε ως εκπαιδευτικός από την πλαϊνή στήλη (sidebar).")
        st.markdown("---")


    # Φιλτράρισμα βάσει του επιλεγμένου σχολείου
    filtered_df_school = full_df[full_df['School'] == selected_school].copy()

    # Εύρεση διαθέσιμων τμημάτων για το επιλεγμένο σχολείο (για την αναζήτηση - από τα δεδομένα)
    current_tmimata = sorted(filtered_df_school['Tmima'].unique().tolist())

    # --------------------------------------------------------------------------
    # ΛΟΓΙΚΗ: ΥΠΟΧΡΕΩΤΙΚΗ ΕΠΙΛΟΓΗ ΤΜΗΜΑΤΟΣ ΓΙΑ ΑΝΑΖΗΤΗΣΗ
    # --------------------------------------------------------------------------

    if not current_tmimata:
        st.warning(f"Το Σχολείο '{selected_school}' δεν έχει καταχωρήσεις τμημάτων στο σύστημα για αναζήτηση.")

    else:
        # 3β. Υποχρεωτική επιλογή Τμήματος για Αναζήτηση
        selected_tmima = st.selectbox(
            "Επιλέξτε Τμήμα (Υποχρεωτικό για Αναζήτηση):",
            options=["-- Επιλέξτε Τμήμα --"] + current_tmimata,
            key="tmima_selector"
        )

        # ΕΚΚΙΝΗΣΗ ΛΟΓΙΚΗΣ ΕΜΦΑΝΙΣΗΣ ΜΟΝΟ ΑΝ ΕΧΕΙ ΕΠΙΛΕΓΕΙ ΕΓΚΥΡΟ ΤΜΗΜΑ
        if selected_tmima and selected_tmima != "-- Επιλέξτε Τμήμα --":

            # 4. ΤΕΛΙΚΟ ΦΙΛΤΡΑΡΙΣΜΑ DF ανά ΤΜΗΜΑ
            filtered_df = filtered_df_school[filtered_df_school['Tmima'] == selected_tmima]

            # ----------------------------------------------------------------------
            # ΕΜΦΑΝΙΣΗ ΤΕΛΕΥΤΑΙΩΝ 2 ΗΜΕΡΩΝ 
            # ----------------------------------------------------------------------

            two_days_ago = datetime.now() - timedelta(days=2)
            recent_posts = filtered_df[filtered_df['Date'].dt.date >= two_days_ago.date()]

            if not recent_posts.empty:
                st.markdown(f"## 📢 Πρόσφατες Ανακοινώσεις ({selected_tmima})")
                st.info("Εμφανίζονται οι καταχωρήσεις των τελευταίων 2 ημερών.")

                recent_posts = recent_posts.sort_values(by='Date', ascending=False)

                for _, row in recent_posts.iterrows():
                    date_str = row['Date'].strftime(DATE_FORMAT)
                    keyword = row['Keyword']
                    item_type = row['Type'].strip().lower()

                    # Επιλογή κλάσης CSS βάσει τύπου
                    css_class = 'info-card'
                    content = ""
                    
                    if item_type == 'link':
                        css_class += ' info-card-link'
                        link_description = row['Info'].strip()
                        link_url = row['URL'].strip()
                        # ΔΙΟΡΘΩΣΗ: Καθαρό HTML <a> tag με quote_plus
                        safe_url = quote_plus(link_url, safe=':/') 
                        content = f"🔗 **Σύνδεσμος:** <a href='{safe_url}' target='_blank' style='color: #1A5276; text-decoration: none;'>{link_description}</a>"
                    elif item_type == 'text':
                        css_class += ' info-card-text'
                        content = f"💬 **Περιγραφή:** {row['Info']}"

                    # Δόμηση της κάρτας HTML
                    card_html = f"""
                    <div class="{css_class}">
                        <span class="card-date">🗓️ {date_str}</span>
                        {content}
                        <div class="card-keyword">🔑 Keyword: {keyword}</div>
                    </div>
                    """
                    st.markdown(card_html, unsafe_allow_html=True)

                st.markdown("---") 
            else:
                st.info(f"Δεν υπάρχουν πρόσφατες ανακοινώσεις (τελευταίες 2 ημέρες) για το τμήμα {selected_tmima}.")
                st.markdown("---")

            # ----------------------------------------------------------------------
            # ΕΝΟΤΗΤΑ: ΠΡΟΣΕΧΕΙΣ ΕΝΕΡΓΕΙΕΣ (ΗΜΕΡΟΛΟΓΙΟ)
            # ----------------------------------------------------------------------
            
            # Υπολογισμός των 30 ημερών από σήμερα
            today = datetime.now().date()
            future_limit = today + timedelta(days=30)
            
            # ΦΙΛΤΡΟ:
            # 1. Πρέπει να υπάρχει ActionDate (δεν είναι NaT - Not a Time)
            # 2. Η ActionDate πρέπει να είναι στο μέλλον (από αύριο και για 30 μέρες)
            future_posts = filtered_df[
                (pd.notna(filtered_df['ActionDate'])) & 
                (filtered_df['ActionDate'].dt.date > today) & 
                (filtered_df['ActionDate'].dt.date <= future_limit)
            ].copy()


            if not future_posts.empty:
                st.markdown(f"## 📅 Προσεχείς Ενέργειες/Γεγονότα ({selected_tmima})")
                st.info(f"Εμφανίζονται οι καταχωρήσεις που πρέπει να γίνουν μέχρι την {future_limit.strftime(DATE_FORMAT)}.")

                # Ταξινόμηση βάση της ActionDate
                future_posts = future_posts.sort_values(by='ActionDate', ascending=True)

                for _, row in future_posts.iterrows():
                    # Χρησιμοποιούμε την ActionDate για την εμφάνιση
                    date_obj = row['ActionDate'].date() 
                    date_str = row['ActionDate'].strftime(DATE_FORMAT)
                    
                    keyword = row['Keyword']
                    item_type = row['Type'].strip().lower()

                    # Επιλογή κλάσης CSS: Χρησιμοποιούμε μπλε για τις επικείμενες ενέργειες
                    css_class = 'info-card'
                    content = ""
                    
                    if item_type == 'link':
                        css_class += ' info-card-link'
                        link_description = row['Info'].strip()
                        link_url = row['URL'].strip()
                        safe_url = quote_plus(link_url, safe=':/') 
                        content = f"🔗 **Σύνδεσμος:** <a href='{safe_url}' target='_blank' style='color: #1A5276; text-decoration: none;'>{link_description}</a>"
                    elif item_type == 'text':
                        css_class += ' info-card-text'
                        content = f"💬 **Περιγραφή:** {row['Info']}"

                    # Υπολογισμός ημερών που απομένουν για έμφαση
                    days_remaining = (date_obj - today).days
                    days_message = f"**Σε {days_remaining} ημέρες**" if days_remaining > 1 else "**ΑΥΡΙΟ!**" if days_remaining == 1 else "**ΣΗΜΕΡΑ!**"
                    
                    # Δόμηση της κάρτας HTML
                    card_html = f"""
                    <div class="{css_class}">
                        <span class="card-date">🗓️ {date_str} ({days_message})</span>
                        {content}
                        <div class="card-keyword">🔑 Keyword: {keyword}</div>
                    </div>
                    """
                    st.markdown(card_html, unsafe_allow_html=True)

                st.markdown("---") 
            else:
                st.info(f"Δεν υπάρχουν προγραμματισμένες ενέργειες/γεγονότα για το τμήμα {selected_tmima} τις επόμενες 30 ημέρες.")
                st.markdown("---")
            # ----------------------------------------------------------------------
            # ΤΕΛΟΣ: ΠΡΟΣΕΧΕΙΣ ΕΝΕΡΓΕΙΕΣ
            # ----------------------------------------------------------------------


            st.markdown("## 🔍 Αναζήτηση Παλαιότερων Πληροφοριών")
            st.info("Για να βρείτε κάτι συγκεκριμένο ή παλαιότερο, πληκτρολογήστε τη φράση-κλειδί (keyword) παρακάτω.")

            # ----------------------------------------------------------------------
            # ΛΟΓΙΚΗ ΑΝΑΖΗΤΗΣΗΣ (Με χρήση CSS Card Styling & Link Fix)
            # ----------------------------------------------------------------------

            tag_to_keyword_map, keyword_to_data_map = create_search_maps(filtered_df)
            current_available_keys = sorted(filtered_df['Keyword'].unique().tolist())

            info_message = f"Διαθέσιμες φράσεις-κλειδιά: **{', '.join(current_available_keys)}**" if current_available_keys else "Δεν βρέθηκαν διαθέσιμες φράσεις-κλειδιά για αυτά τα κριτήρια."
            st.info(info_message)

            user_input = st.text_input(
                'Τι θέλεις να μάθεις;',
                placeholder='Πληκτρολόγησε π.χ. εκδρομη, εργασια, βιβλια...'
            )

            if user_input and keyword_to_data_map:
                search_tag = normalize_text(user_input)
                matching_keywords = tag_to_keyword_map.get(search_tag, set())

                if matching_keywords:
                    all_results = []

                    for keyword in matching_keywords:
                        # Το zip έχει 9 στοιχεία: (Info, URL, Type, Date, School, Tmima, UserId, ActionDate, Internal_ID)
                        all_results.extend(keyword_to_data_map.get(keyword, []))

                    st.success(f"Βρέθηκαν **{len(all_results)}** πληροφορίες για το '{user_input}'.")

                    results_list = []
                    # Αγνοούμε UserId, ActionDate και Internal_ID για την εμφάνιση. Προσθέτουμε πίσω το keyword για εμφάνιση.
                    for info, url, item_type, date_obj, school, tmima, _, _, _ in all_results:
                        # Στοιχείο 7: Keyword
                        results_list.append((date_obj, info, url, item_type, school, tmima, keyword))

                    results_list.sort(key=lambda x: x[0], reverse=True)

                    for i, (date_obj, info, url, item_type, school, tmima, keyword_result) in enumerate(results_list, 1):
                        date_str = date_obj.strftime(DATE_FORMAT) if pd.notna(date_obj) else "Άγνωστη Ημ/νία"
                        
                        item_type_clean = item_type.strip().lower()
                        css_class = 'info-card'
                        content = ""

                        if item_type_clean == 'link':
                            css_class += ' info-card-link'
                            link_description = info.strip()
                            link_url = url.strip()
                            if link_url:
                                # ΔΙΟΡΘΩΣΗ: Καθαρό HTML <a> tag με quote_plus
                                safe_url = quote_plus(link_url, safe=':/')
                                content = f"🔗 **Σύνδεσμος:** <a href='{safe_url}' target='_blank' style='color: #1A5276; text-decoration: none;'>{link_description}</a>"
                            else:
                                content = f"⚠️ **Προσοχή:** Καταχώρηση συνδέσμου χωρίς URL. Περιγραφή: {link_description}"

                        elif item_type_clean == 'text':
                            css_class += ' info-card-text'
                            content = f"💬 **Περιγραφή:** {info}"
                        else:
                            content = f"Άγνωστος Τύπος Καταχώρησης. {info}"
                        
                        # Δόμηση της κάρτας HTML
                        card_html = f"""
                        <div class="{css_class}">
                            <span class="card-date">🗓️ {date_str}</span>
                            {content}
                            <div class="card-keyword">🔑 Keyword: {keyword_result}</div>
                        </div>
                        """
                        st.markdown(card_html, unsafe_allow_html=True)

                else:
                    st.warning(f"Δεν βρέθηκε απάντηση για το: '{user_input}'.")

            st.markdown("---")


elif full_df.empty:
    st.warning("Παρακαλώ συμπληρώστε το Google Sheet με τις στήλες 'School' και 'Tmima' στο φύλλο 'ClassBot', καθώς και τα φύλλα 'Χρήστες' (UserId, School, Name, UserName, Password) και 'Σχολεία'.")
else:
    st.info("Παρακαλώ επιλέξτε Σχολείο για να ξεκινήσει η αναζήτηση.")


st.caption("Ψηφιακός Βοηθός Τάξης - Steam Project.")

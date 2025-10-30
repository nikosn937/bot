import streamlit as st
import pandas as pd
import gspread
from datetime import datetime, timedelta
import re

# --------------------------------------------------------------------------------
# 0. ΡΥΘΜΙΣΕΙΣ (CONNECTION & FORMATS)
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
    """Φορτώνει, καθαρίζει και ταξινομεί δεδομένα από το ενιαίο Google Sheet (Main Data Sheet)."""
    if gc is None:
        return pd.DataFrame(), [], []

    try:
        sh = gc.open(SHEET_NAME)
        # Χρησιμοποιούμε το πρώτο worksheet (index 0) ως το κύριο φύλλο δεδομένων
        ws = sh.get_worksheet(0)
        data = ws.get_all_values()

        headers = data[0] if data else []
        df = pd.DataFrame(data[1:], columns=headers)
        df.columns = df.columns.str.strip()

        required_cols = ['Keyword', 'Info', 'URL', 'Type', 'Date', 'School', 'Tmima']
        if not all(col in df.columns for col in required_cols):
            st.error(f"Σφάλμα δομής Sheet: Οι επικεφαλίδες πρέπει να είναι: {', '.join(required_cols)}.")
            return pd.DataFrame(), [], []

        # Καθαρισμός/Επεξεργασία δεδομένων
        df = df.dropna(subset=['Keyword', 'Date', 'School', 'Tmima'], how='any')
        # Μετατροπή της στήλης Date σε τύπο datetime
        df['Date'] = pd.to_datetime(df['Date'], format=DATE_FORMAT, errors='coerce')
        df = df.dropna(subset=['Date'])

        # Εξαγωγή διαθέσιμων Σχολείων και Τμημάτων δυναμικά
        available_schools = sorted(df['School'].unique().tolist()) if 'School' in df.columns else []
        available_tmimata = sorted(df['Tmima'].unique().tolist()) if 'Tmima' in df.columns else []

        return df, available_schools, available_tmimata

    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"Σφάλμα: Δεν βρέθηκε το Google Sheet με όνομα: '{SHEET_NAME}'. Ελέγξτε το όνομα στα secrets.")
        return pd.DataFrame(), [], []
    except Exception as e:
        st.error(f"Σφάλμα φόρτωσης/επεξεργασίας δεδομένων. Λεπτομέρειες: {e}")
        return pd.DataFrame(), [], []

@st.cache_data(ttl=600)
def load_users_data():
    """Φορτώνει τα δεδομένα χρηστών (Username, Password, School) από το sheet 'Χρήστες'."""
    if gc is None:
        return pd.DataFrame()

    try:
        sh = gc.open(SHEET_NAME)
        # Αναζήτηση του worksheet με βάση το όνομα "Χρήστες"
        ws = sh.worksheet("Χρήστες")
        data = ws.get_all_values()

        headers = data[0] if data else []
        df_users = pd.DataFrame(data[1:], columns=headers)
        df_users.columns = df_users.columns.str.strip()

        required_cols = ['School', 'UserName', 'Password']
        if not all(col in df_users.columns for col in required_cols):
            st.error(f"Σφάλμα δομής Sheet 'Χρήστες': Οι επικεφαλίδες πρέπει να είναι: {', '.join(required_cols)}.")
            return pd.DataFrame()

        # Καθαρισμός/Επεξεργασία
        df_users = df_users.dropna(subset=['School', 'UserName', 'Password'], how='any')

        return df_users

    except gspread.exceptions.WorksheetNotFound:
        st.error("Σφάλμα: Δεν βρέθηκε το worksheet 'Χρήστες'. Παρακαλώ ελέγξτε το όνομα στο Google Sheet.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Σφάλμα φόρτωσης δεδομένων χρηστών. Λεπτομέρειες: {e}")
        return pd.DataFrame()

def create_search_maps(df):
    """Δημιουργεί τους χάρτες αναζήτησης μετά το φιλτράρισμα."""
    df_sorted = df.sort_values(by=['Keyword', 'Date'], ascending=[True, False])

    # Το zip περιλαμβάνει 6 στοιχεία (Info, URL, Type, Date, School, Tmima)
    keyword_to_data_map = df_sorted.groupby('Keyword').apply(
        lambda x: list(zip(x['Info'], x['URL'], x['Type'], x['Date'], x['School'], x['Tmima']))
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
# 2. ΦΟΡΜΑ ΚΑΤΑΧΩΡΗΣΗΣ / AUTHENTICATION
# --------------------------------------------------------------------------------

def submit_entry(new_entry_list):
    """Προσθέτει μια νέα σειρά στο Google Sheet."""
    if gc is None:
        st.error("Η σύνδεση με το Google Sheets απέτυχε.")
        return

    try:
        sh = gc.open(SHEET_NAME)
        ws = sh.get_worksheet(0)

        ws.append_row(new_entry_list)

        st.cache_data.clear()
        st.success("🎉 Η καταχώρηση έγινε επιτυχώς! Η εφαρμογή ανανεώνεται...")
        st.balloons()
        st.rerun()

    except Exception as e:
        st.error(f"Σφάλμα κατά την καταχώρηση. Ελέγξτε τα δικαιώματα. Λεπτομέρειες: {e}")

def data_entry_form(available_schools, available_tmimata, logged_in_school):
    """Δημιουργεί τη φόρμα εισαγωγής νέων δεδομένων. (Το σχολείο είναι προ-επιλεγμένο)"""

    with st.expander(f"➕ Νέα Καταχώρηση για το {logged_in_school}"):

        st.markdown("### Εισαγωγή Νέας Πληροφορίας (Μόνο για Εκπαιδευτικούς)")

        # 1. ΕΠΙΛΟΓΗ ΣΧΟΛΕΙΟΥ & ΤΜΗΜΑΤΟΣ (Το Σχολείο είναι προεπιλεγμένο/κλειδωμένο)
        # Εμφάνιση του σχολείου του συνδεδεμένου χρήστη
        st.code(f"Σχολείο Καταχώρησης: {logged_in_school}", language='text')
        new_school = logged_in_school # ΟΡΙΖΕΤΑΙ από τον συνδεδεμένο χρήστη

        # Χρησιμοποιούμε text_input για το Τμήμα ώστε να μπορεί να βάλει και νέα τμήματα
        new_tmima_input = st.text_input(
            "Τμήμα (Tmima):",
            placeholder="Πρέπει να είναι Ελληνικοί Κεφαλαίοι (Π.χ. Α1, Γ2)",
            key="form_tmima"
        )

        # 2. Το Radio Button ΕΞΩ από το Form (Για άμεσο rerun/UX fix)
        if 'entry_type' not in st.session_state:
            st.session_state['entry_type'] = 'Text'

        st.session_state.entry_type = st.radio(
            "Τύπος Καταχώρησης",
            ('Text', 'Link'),
            horizontal=True,
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

        # 4. ΦΟΡΜΑ ΥΠΟΒΟΛΗΣ (με τα υπόλοιπα πεδία)
        with st.form("new_entry_form", clear_on_submit=True):

            new_keyword = st.text_input("Φράση-Κλειδί (Keyword, π.χ. 'εργασια μαθηματικα')", key="k1_form")

            if st.session_state.entry_type == 'Text':
                new_info = st.text_area("Περιγραφή (Info)", key="i1_text_area")
            else:
                new_info = st.text_input("Περιγραφή Συνδέσμου (Info)", key="i2_text_input")

            new_date_obj = st.date_input("Ημερομηνία Καταχώρησης (Date)", value=datetime.today().date(), key="d1_date")
            new_date_str = new_date_obj.strftime(DATE_FORMAT)

            submitted = st.form_submit_button("Καταχώρηση 💾")

            if submitted:
                final_url = new_url.strip() if st.session_state.entry_type == 'Link' else ""

                # Αυτόματη Προσθήκη https://
                if final_url and st.session_state.entry_type == 'Link':
                    if not final_url.lower().startswith(('http://', 'https://', 'ftp://')):
                        final_url = 'https://' + final_url

                # --------------------------------------------------------
                # ΕΛΕΓΧΟΣ ΕΓΚΥΡΟΤΗΤΑΣ ΤΜΗΜΑΤΟΣ (Tmima) - Ελληνικά/Κεφαλαία
                # --------------------------------------------------------

                tmima_check = new_tmima_input.strip().upper().replace(" ", "")

                # Pattern: Μόνο Ελληνικά Κεφαλαία (Α-Ω) ή Αριθμοί (0-9)
                tmima_pattern = re.compile(r'^[Α-Ω0-9]+$')

                if not tmima_pattern.match(tmima_check):
                    st.error("⚠️ Σφάλμα Τμήματος: Το πεδίο 'Τμήμα' πρέπει να περιέχει μόνο **Ελληνικούς** κεφαλαίους χαρακτήρες (Α, Β, Γ...) και **αριθμούς** (1, 2, 3...), χωρίς κενά. Διορθώστε την εισαγωγή σας.")
                    st.stop()
                final_tmima = tmima_check
                # --------------------------------------------------------

                # Έλεγχος πληρότητας
                if not new_keyword or not new_info or not new_school or not final_tmima or (st.session_state.entry_type == 'Link' and not final_url):
                    st.error("Παρακαλώ συμπληρώστε όλα τα πεδία (Φράση-Κλειδί, Περιγραφή, Σχολείο, Τμήμα και Σύνδεσμο αν είναι Link).")
                else:
                    new_entry_list = [
                        new_keyword.strip(),
                        new_info.strip(),
                        final_url,
                        st.session_state.entry_type,
                        new_date_str,
                        new_school,  # Σχολείο (από session state)
                        final_tmima  # Τυποποιημένο
                    ]
                    submit_entry(new_entry_list)

def teacher_login(df_users):
    """Δημιουργεί τη φόρμα σύνδεσης και χειρίζεται την πιστοποίηση."""

    # Αρχικοποίηση session state για την πιστοποίηση αν δεν υπάρχει
    if 'authenticated' not in st.session_state:
        st.session_state['authenticated'] = False
        st.session_state['logged_in_school'] = None
        st.session_state['login_attempted'] = False

    st.sidebar.markdown("### Σύνδεση Εκπαιδευτικού 🔑")

    if st.session_state.authenticated:
        st.sidebar.success(f"Συνδεδεμένος ως: **{st.session_state.logged_in_school}**")
        if st.sidebar.button("Αποσύνδεση"):
            st.session_state.authenticated = False
            st.session_state.logged_in_school = None
            st.cache_data.clear() # Καθαρισμός cache για ασφάλεια
            st.rerun()
        return True

    # Εμφάνιση φόρμας σύνδεσης
    with st.sidebar.form("login_form"):
        username_input = st.text_input("Όνομα Χρήστη (UserName)", key="login_username")
        password_input = st.text_input("Κωδικός (Password)", type="password", key="login_password")
        submitted = st.form_submit_button("Σύνδεση")

        if submitted:
            st.session_state.login_attempted = True

            # Έλεγχος διαπιστευτηρίων
            user_found = df_users[
                (df_users['UserName'].astype(str).str.strip() == username_input.strip()) &
                (df_users['Password'].astype(str).str.strip() == password_input.strip())
            ]

            if not user_found.empty:
                st.session_state.authenticated = True
                # Αποθηκεύουμε το σχολείο του συνδεδεμένου χρήστη
                st.session_state.logged_in_school = user_found['School'].iloc[0].strip()
                st.success("Επιτυχής σύνδεση!")
                st.rerun() # Επανεκτέλεση για να εμφανιστούν οι επιλογές
            else:
                st.error("Λάθος όνομα χρήστη ή κωδικός.")
                st.session_state.authenticated = False
                st.session_state.logged_in_school = None

    if st.session_state.login_attempted and not st.session_state.authenticated:
        st.sidebar.error("Αποτυχία σύνδεσης.")

    return st.session_state.authenticated

# --------------------------------------------------------------------------------
# 3. UI / ΚΥΡΙΑ ΛΟΓΙΚΗ
# --------------------------------------------------------------------------------

st.set_page_config(page_title="Βοηθός Τάξης", layout="centered")

# ΟΡΙΣΤΕ ΤΗΝ RAW URL ΓΙΑ ΤΟ ΛΟΓΟΤΥΠΟ
RAW_IMAGE_URL = "https://raw.githubusercontent.com/nikosn937/bot/b0c4fd1190a186ba1bd6c322c0f23c5c2effbb24/ClassBot.png"

# Δημιουργία δύο στηλών: η πρώτη (1/5) για το λογότυπο, η δεύτερη (4/5) για τον τίτλο
col1, col2 = st.columns([1, 4])

with col1:
    # Εμφάνιση της εικόνας
    st.image(RAW_IMAGE_URL, width=100)

with col2:
    # Εμφάνιση του τίτλου
    st.markdown("## Ψηφιακός Βοηθός Τάξης")
    st.caption("Steam Project")

st.markdown("---") # Διαχωριστική γραμμή

# Φόρτωση όλων των δεδομένων και των διαθέσιμων επιλογών
full_df, available_schools, available_tmimata = load_data()
df_users = load_users_data() # Φόρτωση δεδομένων χρηστών

# ΕΝΣΩΜΑΤΩΣΗ ΦΟΡΜΑΣ ΣΥΝΔΕΣΗΣ ΣΤΗΝ ΠΛΕΥΡΙΚΗ ΣΤΗΛΗ
is_authenticated = teacher_login(df_users)
st.markdown("---")


# 1. ΕΠΙΛΟΓΗ ΣΧΟΛΕΙΟΥ
selected_school = st.selectbox(
    "Επιλέξτε Σχολείο:",
    options=["-- Επιλέξτε --"] + available_schools,
    key="school_selector"
)

# 2. ΦΙΛΤΡΑΡΙΣΜΑ DF ανά ΣΧΟΛΕΙΟ
if selected_school and selected_school != "-- Επιλέξτε --" and not full_df.empty:

    # --------------------------------------------------------------------------
    # ΕΛΕΓΧΟΣ ΠΡΟΣΒΑΣΗΣ ΦΟΡΜΑΣ ΚΑΤΑΧΩΡΗΣΗΣ
    # --------------------------------------------------------------------------
    logged_in_school = st.session_state.get('logged_in_school')

    if is_authenticated and logged_in_school == selected_school:
        # Εμφάνιση Φόρμας Καταχώρησης ΜΟΝΟ αν ο χρήστης είναι συνδεδεμένος ΚΑΙ έχει επιλέξει το σχολείο του
        data_entry_form(available_schools, available_tmimata, logged_in_school)
        st.markdown("---") # Διαχωριστής
    elif is_authenticated:
        st.warning(f"Είστε συνδεδεμένος ως εκπαιδευτικός του **{logged_in_school}**. Για καταχώρηση, πρέπει να επιλέξετε το σχολείο σας ('{logged_in_school}').")
        st.markdown("---")
    else:
        st.info("Για να δείτε/χρησιμοποιήσετε τη φόρμα καταχώρησης, παρακαλώ συνδεθείτε ως εκπαιδευτικός από την πλαϊνή στήλη (sidebar).")
        st.markdown("---")


    # Φιλτράρισμα βάσει του επιλεγμένου σχολείου
    filtered_df_school = full_df[full_df['School'] == selected_school].copy()

    # Εύρεση διαθέσιμων τμημάτων για το επιλεγμένο σχολείο
    current_tmimata = sorted(filtered_df_school['Tmima'].unique().tolist())

    # --------------------------------------------------------------------------
    # ΛΟΓΙΚΗ: ΥΠΟΧΡΕΩΤΙΚΗ ΕΠΙΛΟΓΗ ΤΜΗΜΑΤΟΣ
    # --------------------------------------------------------------------------

    if not current_tmimata:
        # 3a. Δεν υπάρχουν καταχωρήσεις τμημάτων για το σχολείο
        st.warning(f"Το Σχολείο '{selected_school}' δεν έχει καταχωρήσεις τμημάτων στο σύστημα για αναζήτηση.")

    else:
        # 3β. Υποχρεωτική επιλογή Τμήματος
        selected_tmima = st.selectbox(
            "Επιλέξτε Τμήμα (Υποχρεωτικό):",
            options=["-- Επιλέξτε Τμήμα --"] + current_tmimata,
            key="tmima_selector"
        )

        # ΕΚΚΙΝΗΣΗ ΛΟΓΙΚΗΣ ΕΜΦΑΝΙΣΗΣ ΜΟΝΟ ΑΝ ΕΧΕΙ ΕΠΙΛΕΓΕΙ ΕΓΚΥΡΟ ΤΜΗΜΑ
        if selected_tmima and selected_tmima != "-- Επιλέξτε Τμήμα --":

            # 4. ΤΕΛΙΚΟ ΦΙΛΤΡΑΡΙΣΜΑ DF ανά ΤΜΗΜΑ
            filtered_df = filtered_df_school[filtered_df_school['Tmima'] == selected_tmima]

            # ----------------------------------------------------------------------
            # ΕΜΦΑΝΙΣΗ ΤΕΛΕΥΤΑΙΩΝ 2 ΗΜΕΡΩΝ ΠΡΙΝ ΤΗΝ ΑΝΑΖΗΤΗΣΗ
            # ----------------------------------------------------------------------

            # Υπολογισμός ημερομηνίας έναρξης: Σήμερα - 2 ημέρες
            two_days_ago = datetime.now() - timedelta(days=2)

            # Φιλτράρισμα των δεδομένων του τμήματος για τις τελευταίες 2 ημέρες
            recent_posts = filtered_df[filtered_df['Date'].dt.date >= two_days_ago.date()]

            if not recent_posts.empty:
                st.header(f"📢 Πρόσφατες Ανακοινώσεις ({selected_tmima})")
                st.info("Εμφανίζονται οι καταχωρήσεις των τελευταίων 2 ημερών.")

                # Ταξινόμηση των πρόσφατων δημοσιεύσεων (πιο πρόσφατη πρώτη)
                recent_posts = recent_posts.sort_values(by='Date', ascending=False)

                # Rendering των πρόσφατων δημοσιεύσεων
                for i, row in recent_posts.iterrows():
                    date_str = row['Date'].strftime(DATE_FORMAT)
                    header = f"**Καταχώρηση (Από: {date_str})**"

                    if row['Type'].strip().lower() == 'link':
                        link_description = row['Info'].strip()
                        link_url = row['URL'].strip()
                        st.markdown(f"{header}: 🔗 [{link_description}](<{link_url}>) (Keyword: *{row['Keyword']}*)")

                    elif row['Type'].strip().lower() == 'text':
                        st.markdown(f"{header}: 💬 {row['Info']} (Keyword: *{row['Keyword']}*)")

                st.markdown("---") # Διαχωριστική γραμμή πριν την αναζήτηση
            else:
                st.info(f"Δεν υπάρχουν πρόσφατες ανακοινώσεις (τελευταίες 2 ημέρες) για το τμήμα {selected_tmima}.")
                st.markdown("---")


            st.header("🔍 Αναζήτηση Παλαιότερων Πληροφοριών")
            st.info("Για να βρείτε κάτι συγκεκριμένο ή παλαιότερο, πληκτρολογήστε τη φράση-κλειδί (keyword) παρακάτω.")

            # ----------------------------------------------------------------------
            # ΣΥΝΕΧΕΙΑ ΤΗΣ ΛΟΓΙΚΗΣ ΑΝΑΖΗΤΗΣΗΣ
            # ----------------------------------------------------------------------

            # Δημιουργία χαρτών αναζήτησης για τα φιλτραρισμένα δεδομένα
            tag_to_keyword_map, keyword_to_data_map = create_search_maps(filtered_df)
            current_available_keys = sorted(filtered_df['Keyword'].unique().tolist())

            # Εμφάνιση των διαθέσιμων Keywords
            info_message = f"Διαθέσιμες φράσεις-κλειδιά: **{', '.join(current_available_keys)}**" if current_available_keys else "Δεν βρέθηκαν διαθέσιμες φράσεις-κλειδιά για αυτά τα κριτήρια."
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
                        # Το zip έχει 6 στοιχεία: (Info, URL, Type, Date, School, Tmima)
                        all_results.extend(keyword_to_data_map.get(keyword, []))

                    st.success(f"Βρέθηκαν **{len(all_results)}** πληροφορίες για το '{user_input}'.")

                    # Ταξινόμηση των αποτελεσμάτων αναζήτησης βάσει ημερομηνίας
                    results_list = []
                    for info, url, item_type, date_obj, school, tmima in all_results:
                        results_list.append((date_obj, info, url, item_type, school, tmima))

                    results_list.sort(key=lambda x: x[0], reverse=True) # Ταξινόμηση ανά ημερομηνία (πιο πρόσφατο πρώτο)

                    for i, (date_obj, info, url, item_type, school, tmima) in enumerate(results_list, 1):
                        date_str = date_obj.strftime(DATE_FORMAT) if pd.notna(date_obj) else "Άγνωστη Ημ/νία"
                        header = f"**Αποτέλεσμα {i}** (Ημ/νία: {date_str})"

                        if item_type.strip().lower() == 'link':
                            link_description = info.strip()
                            link_url = url.strip()
                            if link_url:
                                st.markdown(f"{header}: 🔗 [{link_description}](<{link_url}>)")
                            else:
                                st.markdown(f"{header}: ⚠️ **Προσοχή:** Καταχώρηση συνδέσμου χωρίς URL. Περιγραφή: {link_description}")

                        elif item_type.strip().lower() == 'text':
                            st.markdown(f"{header}: 💬 {info}")

                        else:
                            st.markdown(f"{header}: Άγνωστος Τύπος Καταχώρησης. {info}")

                else:
                    st.warning(f"Δεν βρέθηκε απάντηση για το: '{user_input}'.")

            st.markdown("---")


elif full_df.empty:
    st.warning("Παρακαλώ συμπληρώστε το Google Sheet με τις στήλες 'School' και 'Tmima'.")
else:
    st.info("Παρακαλώ επιλέξτε Σχολείο για να ξεκινήσει η αναζήτηση.")


st.caption("Ψηφιακός Βοηθός Τάξης - Steam Project.")

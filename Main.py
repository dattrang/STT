import streamlit as st
from dataclasses import dataclass, asdict
from typing import Optional
import time
import sqlite3
from gtts import gTTS
import tempfile
import os
import base64
import pandas as pd

# Cấu hình trang Streamlit
st.set_page_config(
    page_title="Hệ thống đăng ký chờ làm thủ tục",
    page_icon="🎫",
    layout="wide"
)

# Định nghĩa lớp Customer
@dataclass
class Customer:
    name: str
    cccd: str
    ticket_number: int
    timestamp: float

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(data):
        return Customer(**data)

# Kết nối đến cơ sở dữ liệu SQLite
@st.cache_resource
def get_db_connection():
    conn = sqlite3.connect('queue_management.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# Hàm tạo âm thanh
def create_audio(text: str) -> Optional[str]:
    try:
        tts = gTTS(text=text, lang='vi')
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as fp:
            tts.save(fp.name)
            return fp.name
    except Exception as e:
        st.error(f"Lỗi tạo âm thanh: {str(e)}")
        return None

def play_audio_autoplay(file_path: str):
    with open(file_path, 'rb') as audio_file:
        audio_bytes = audio_file.read()
        audio_base64 = base64.b64encode(audio_bytes).decode()

        # Chèn đoạn mã HTML để tự động phát âm thanh
        audio_html = f"""
        <audio autoplay="true" style="display:none;">
            <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3">
        </audio>
        """
        st.markdown(audio_html, unsafe_allow_html=True)

# Khởi tạo cơ sở dữ liệu
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            cccd TEXT PRIMARY KEY,
            name TEXT,
            ticket_number INTEGER,
            timestamp REAL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS desks (
            desk_id INTEGER PRIMARY KEY,
            current_customer_cccd TEXT,
            FOREIGN KEY(current_customer_cccd) REFERENCES customers(cccd)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS queues (
            desk_id INTEGER,
            cccd TEXT,
            position INTEGER,
            FOREIGN KEY(desk_id) REFERENCES desks(desk_id),
            FOREIGN KEY(cccd) REFERENCES customers(cccd),
            PRIMARY KEY(desk_id, cccd)
        )
    ''')
    for desk_id in [1, 2]:
        cursor.execute('INSERT OR IGNORE INTO desks (desk_id) VALUES (?)', (desk_id,))
    conn.commit()

# Hàm thêm khách hàng mới
def add_customer(name: str, cccd: str) -> tuple:
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM customers WHERE cccd = ?', (cccd,))
    if cursor.fetchone():
        return -1, -1, -1

    cursor.execute('SELECT MAX(ticket_number) FROM customers')
    result = cursor.fetchone()
    next_number = result[0] + 1 if result[0] else 1

    timestamp = time.time()
    customer = Customer(name, cccd, next_number, timestamp)

    cursor.execute('''
        INSERT INTO customers (cccd, name, ticket_number, timestamp)
        VALUES (?, ?, ?, ?)
    ''', (customer.cccd, customer.name, customer.ticket_number, customer.timestamp))

    desk_id = get_least_busy_desk(cursor)
    position = enqueue_customer(cursor, desk_id, customer.cccd)

    conn.commit()
    return position, next_number, desk_id

def get_least_busy_desk(cursor) -> int:
    cursor.execute('''
        SELECT desk_id, COUNT(cccd) as queue_length
        FROM queues
        GROUP BY desk_id
    ''')
    result = cursor.fetchall()

    if not result:
        return 1 if time.time() % 2 < 1 else 2

    desk_queue_lengths = {1: 0, 2: 0}
    for row in result:
        desk_queue_lengths[row['desk_id']] = row['queue_length']

    return 1 if desk_queue_lengths[1] <= desk_queue_lengths[2] else 2

def enqueue_customer(cursor, desk_id: int, cccd: str) -> int:
    cursor.execute('SELECT MAX(position) FROM queues WHERE desk_id = ?', (desk_id,))
    result = cursor.fetchone()
    next_position = result[0] + 1 if result[0] else 1

    cursor.execute('''
        INSERT INTO queues (desk_id, cccd, position)
        VALUES (?, ?, ?)
    ''', (desk_id, cccd, next_position))

    return next_position

def process_next_customer(desk_id: int) -> Optional[Customer]:
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute('''
            SELECT customers.* FROM queues
            JOIN customers ON queues.cccd = customers.cccd
            WHERE desk_id = ?
            ORDER BY position ASC
            LIMIT 1
        ''', (desk_id,))
        result = cursor.fetchone()

        if result:
            customer = Customer.from_dict(result)
            cursor.execute('''
                UPDATE desks SET current_customer_cccd = ?
                WHERE desk_id = ?
            ''', (customer.cccd, desk_id))
            cursor.execute('''
                DELETE FROM queues WHERE desk_id = ? AND cccd = ?
            ''', (desk_id, customer.cccd))
            conn.commit()
            return customer
        else:
            cursor.execute('''
                UPDATE desks SET current_customer_cccd = NULL
                WHERE desk_id = ?
            ''', (desk_id,))
            conn.commit()
            return None

# Thêm các tính năng hiển thị, ẩn bảng và tải xuống danh sách
def get_registered_customers():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT name, cccd, ticket_number
        FROM customers
    ''')

    rows = cursor.fetchall()

    if not rows:
        st.warning("Không có dữ liệu đăng ký.")
        return pd.DataFrame()

    data = []
    for row in rows:
        data.append({
            'Họ và tên': row['name'],
            'Số CCCD': row['cccd'],
            'Số thứ tự': row['ticket_number']
        })

    df = pd.DataFrame(data)
    return df

def toggle_list_display():
    # Hiển thị/ẩn danh sách
    if 'show_list' not in st.session_state:
        st.session_state['show_list'] = False

    if not st.session_state['show_list']:
        if st.sidebar.button("Hiển thị danh sách"):
            st.session_state['show_list'] = True
            st.rerun()
    else:
        if st.sidebar.button("Ẩn danh sách"):
            st.session_state['show_list'] = False
            st.rerun()

    if st.session_state['show_list']:
        df = get_registered_customers()
        st.write(df)  # Hiển thị bảng dữ liệu

def download_customer_list():
    # Nút tải xuống danh sách
    df = get_registered_customers()
    if not df.empty:
        st.sidebar.download_button(
            "Tải xuống danh sách",
            data=df.to_csv(index=False, encoding='utf-8-sig', sep=';').encode('utf-8-sig'),
            file_name='danh_sach_dang_ky.csv',
            mime='text/csv'
        )

def registration_form():
    st.header("Đăng ký xếp hàng lấy số thứ tự")

    if 'name' not in st.session_state:
        st.session_state['name'] = ""
    if 'cccd' not in st.session_state:
        st.session_state['cccd'] = ""

    if 'success_msg' not in st.session_state:
        st.session_state['success_msg'] = ""

    with st.form("register_form"):
        name = st.text_input("Họ và tên:", value=st.session_state['name'])
        cccd = st.text_input("Số CCCD (12 số):", value=st.session_state['cccd'])
        submitted = st.form_submit_button("Đăng ký")

        if submitted:
            if not name or not cccd:
                st.error("Vui lòng điền đủ thông tin")
                return

            if not cccd.isdigit() or len(cccd) != 12:
                st.error("Số CCCD không hợp lệ")
                return

            position, ticket_number, desk_id = add_customer(name, cccd)
            if position != -1:
                st.session_state['success_msg'] = (
                    f"Đăng ký thành công! Số thứ tự của bạn là {ticket_number}. "
                    f"Bạn ở vị trí {position} trong hàng đợi tại Bàn {desk_id}."
                )

                st.session_state['name'] = ""
                st.session_state['cccd'] = ""

                st.rerun()
            else:
                st.error("Số CCCD đã được đăng ký")

    if st.session_state['success_msg']:
        st.success(st.session_state['success_msg'])
        st.session_state['success_msg'] = ""  # Xóa thông báo sau khi hiển thị

def skip_customer(desk_id: int):
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute('''
            SELECT current_customer_cccd FROM desks
            WHERE desk_id = ?
        ''', (desk_id,))
        result = cursor.fetchone()

        if result and result['current_customer_cccd']:
            cccd_to_skip = result['current_customer_cccd']

            cursor.execute('''
                SELECT MAX(position) FROM queues
                WHERE desk_id = ?
            ''', (desk_id,))
            max_position = cursor.fetchone()[0] or 0

            new_position = max_position + 1
            cursor.execute('''
                INSERT INTO queues (desk_id, cccd, position)
                VALUES (?, ?, ?)
            ''', (desk_id, cccd_to_skip, new_position))

            cursor.execute('''
                UPDATE desks SET current_customer_cccd = NULL
                WHERE desk_id = ?
            ''', (desk_id,))

            conn.commit()

            customer = process_next_customer(desk_id)
            if customer:
                announce = f"Mời công dân {customer.name}, số thứ tự {customer.ticket_number}, đến Bàn {desk_id}"
                st.session_state[f'audio_message_ban{desk_id}'] = announce
                st.rerun()
        else:
            st.warning("Không có công dân nào đang làm thủ tục tại bàn này.")

def process_customers():
    st.sidebar.header("Xử lý công dân")

    correct_password = "Tanhung@2020"

    if 'authenticated' not in st.session_state:
        st.session_state['authenticated'] = False

    if not st.session_state['authenticated']:
        password = st.sidebar.text_input("Nhập mật khẩu để xử lý", type="password")

        if password == correct_password:
            st.session_state['authenticated'] = True
            st.rerun()
        elif password:
            st.sidebar.error("Mật khẩu không đúng!")

    if st.session_state['authenticated']:
        col1, col2 = st.sidebar.columns(2)

        with col1:
            if st.button("Bỏ qua - Bàn 1"):
                skip_customer(1)
                st.rerun()
            if st.button("Gọi công dân - Bàn 1"):
                customer = process_next_customer(1)
                if customer:
                    announce = f"Mời Công dân {customer.name}, số thứ tự {customer.ticket_number}, đến Bàn 1"
                    st.session_state['audio_message_ban1'] = announce
                    st.session_state['audio_desk'] = 1
                    st.rerun()

        with col2:
            if st.button("Bỏ qua - Bàn 2"):
                skip_customer(2)
                st.rerun()
            if st.button("Gọi công dân - Bàn 2"):
                customer = process_next_customer(2)
                if customer:
                    announce = f"Mời công dân {customer.name}, số thứ tự {customer.ticket_number}, đến Bàn 2"
                    st.session_state['audio_message_ban2'] = announce
                    st.session_state['audio_desk'] = 2
                    st.rerun()

def main():
    st.title("🎫 Hệ thống xếp hàng")

    init_db()

    col1, col2 = st.columns(2)
    with col1:
        render_desk_status(1)
    with col2:
        render_desk_status(2)

    if 'audio_message_ban1' in st.session_state and st.session_state['audio_message_ban1']:
        audio_message = st.session_state['audio_message_ban1']
        st.success(audio_message)
        audio_file = create_audio(audio_message)
        if audio_file:
            play_audio_autoplay(audio_file)
            os.unlink(audio_file)
        del st.session_state['audio_message_ban1']

    if 'audio_message_ban2' in st.session_state and st.session_state['audio_message_ban2']:
        audio_message = st.session_state['audio_message_ban2']
        st.success(audio_message)
        audio_file = create_audio(audio_message)
        if audio_file:
            play_audio_autoplay(audio_file)
            os.unlink(audio_file)
        del st.session_state['audio_message_ban2']

    registration_form()

    process_customers()

    # Thêm tính năng hiển thị/ẩn danh sách và tải xuống
    toggle_list_display()
    download_customer_list()

if __name__ == "__main__":
    main()

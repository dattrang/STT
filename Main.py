import streamlit as st
from collections import deque
from dataclasses import dataclass, asdict
from typing import Optional
from gtts import gTTS
import base64
import time
import sqlite3
from io import BytesIO

# Cấu hình trang Streamlit
st.set_page_config(
    page_title="Hệ thống quản lý hàng đợi",
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
def get_db_connection():
    conn = sqlite3.connect('queue_management.db')
    conn.row_factory = sqlite3.Row
    return conn

# Khởi tạo cơ sở dữ liệu
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Tạo bảng customers
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            cccd TEXT PRIMARY KEY,
            name TEXT,
            ticket_number INTEGER,
            timestamp REAL
        )
    ''')
    # Tạo bảng desks
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS desks (
            desk_id INTEGER PRIMARY KEY,
            current_customer_cccd TEXT,
            FOREIGN KEY(current_customer_cccd) REFERENCES customers(cccd)
        )
    ''')
    # Tạo bảng queues
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
    # Khởi tạo bàn nếu chưa có
    for desk_id in [1, 2]:
        cursor.execute('INSERT OR IGNORE INTO desks (desk_id) VALUES (?)', (desk_id,))
    conn.commit()
    conn.close()

# Hàm thêm khách hàng mới
def add_customer(name: str, cccd: str) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()

    # Kiểm tra xem khách hàng đã tồn tại chưa
    cursor.execute('SELECT * FROM customers WHERE cccd = ?', (cccd,))
    if cursor.fetchone():
        conn.close()
        return -1  # Đã tồn tại

    # Lấy số thứ tự tiếp theo
    cursor.execute('SELECT MAX(ticket_number) FROM customers')
    result = cursor.fetchone()
    next_number = result[0] + 1 if result[0] else 1

    timestamp = time.time()
    customer = Customer(name, cccd, next_number, timestamp)

    # Thêm khách hàng vào bảng customers
    cursor.execute('''
        INSERT INTO customers (cccd, name, ticket_number, timestamp)
        VALUES (?, ?, ?, ?)
    ''', (customer.cccd, customer.name, customer.ticket_number, customer.timestamp))

    # Xác định bàn có hàng đợi ngắn hơn
    desk_id = get_least_busy_desk(cursor)
    position = enqueue_customer(cursor, desk_id, customer.cccd)

    conn.commit()
    conn.close()

    # Sau khi thêm khách hàng, làm mới giao diện
    st.rerun()
    return position

def get_least_busy_desk(cursor) -> int:
    # Lấy số lượng khách hàng trong hàng đợi của mỗi bàn
    cursor.execute('''
        SELECT desk_id, COUNT(cccd) as queue_length
        FROM queues
        GROUP BY desk_id
    ''')

    result = cursor.fetchall()

    # Nếu cả 2 hàng đợi đều trống, chọn bàn ngẫu nhiên
    if not result:
        return 1 if time.time() % 2 < 1 else 2  # Chọn ngẫu nhiên giữa bàn 1 và bàn 2 nếu cả hai trống

    # Tạo từ điển để lưu số lượng hàng đợi cho từng bàn
    desk_queue_lengths = {1: 0, 2: 0}

    # Cập nhật số lượng hàng đợi cho từng bàn từ kết quả truy vấn
    for row in result:
        desk_queue_lengths[row['desk_id']] = row['queue_length']

    # Chọn bàn có ít khách hàng chờ hơn
    return 1 if desk_queue_lengths[1] <= desk_queue_lengths[2] else 2


# Thêm khách hàng vào hàng đợi
def enqueue_customer(cursor, desk_id: int, cccd: str) -> int:
    cursor.execute('SELECT MAX(position) FROM queues WHERE desk_id = ?', (desk_id,))
    result = cursor.fetchone()
    next_position = result[0] + 1 if result[0] else 1

    cursor.execute('''
        INSERT INTO queues (desk_id, cccd, position)
        VALUES (?, ?, ?)
    ''', (desk_id, cccd, next_position))

    return next_position

# Xử lý khách hàng tiếp theo
def process_next_customer(desk_id: int) -> Optional[Customer]:
    conn = get_db_connection()
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
        conn.close()
        # Sau khi gọi khách hàng, làm mới giao diện
        st.rerun()
        return customer
    else:
        cursor.execute('''
            UPDATE desks SET current_customer_cccd = NULL
            WHERE desk_id = ?
        ''', (desk_id,))
        conn.commit()
        conn.close()
        return None

# Lấy trạng thái bàn
def get_desk_status(desk_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT customers.* FROM desks
        LEFT JOIN customers ON desks.current_customer_cccd = customers.cccd
        WHERE desk_id = ?
    ''', (desk_id,))
    current_customer = cursor.fetchone()
    current_customer = Customer.from_dict(current_customer) if current_customer and current_customer['cccd'] else None

    cursor.execute('''
        SELECT customers.* FROM queues
        JOIN customers ON queues.cccd = customers.cccd
        WHERE desk_id = ?
        ORDER BY position ASC
    ''', (desk_id,))
    queue = [Customer.from_dict(row) for row in cursor.fetchall()]

    conn.close()
    return current_customer, queue

def create_audio(_text: str) -> str:
    try:
        # Sử dụng BytesIO để lưu âm thanh vào bộ nhớ thay vì tệp tạm thời
        audio_fp = BytesIO()

        # Tạo tệp âm thanh từ văn bản
        tts = gTTS(text=_text, lang='vi')
        tts.write_to_fp(audio_fp)  # Lưu trực tiếp vào đối tượng BytesIO
        audio_fp.seek(0)  # Đặt con trỏ về đầu để đọc lại dữ liệu

        # Đọc dữ liệu âm thanh từ BytesIO và mã hóa thành base64
        audio_bytes = audio_fp.read()
        audio_base64 = base64.b64encode(audio_bytes).decode()

        # Trả về HTML audio element với dữ liệu base64
        return f"""
        <audio autoplay="true" controls>
            <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3">
        </audio>
        """
    except Exception as e:
        st.error(f"Lỗi tạo âm thanh: {str(e)}")
        return ""

# Giao diện người dùng
def render_desk_status(desk_id: int):
    st.subheader(f"Bàn {desk_id}")
    current_customer, queue = get_desk_status(desk_id)

    st.markdown("##### Đang phục vụ:")
    if current_customer:
        st.markdown(f"""
        <div style='background-color: #e6f3ff; padding: 10px; border-radius: 5px;'>
            <h3 style='color: #0066cc;'>{current_customer.name}</h3>
            <p>Số thứ tự: {current_customer.ticket_number}</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("<p style='color: #666;'>Chưa có khách hàng</p>", unsafe_allow_html=True)

    st.markdown("##### Danh sách chờ:")
    if queue:
        for i, customer in enumerate(queue, 1):
            st.markdown(f"{i}. {customer.name} - Số {customer.ticket_number}")
    else:
        st.markdown("<p style='color: #666;'>Không có khách hàng đang chờ</p>", unsafe_allow_html=True)

def registration_form():
    st.header("Đăng ký mới")
    with st.form("register_form"):
        name = st.text_input("Họ và tên:")
        cccd = st.text_input("Số CCCD (12 số):")
        submitted = st.form_submit_button("Đăng ký")

        if submitted:
            if not name or not cccd:
                st.error("Vui lòng điền đầy đủ thông tin")
                return

            if not cccd.isdigit() or len(cccd) != 12:
                st.error("Số CCCD không hợp lệ")
                return

            position = add_customer(name, cccd)
            if position != -1:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('SELECT ticket_number FROM customers WHERE cccd = ?', (cccd,))
                ticket_number = cursor.fetchone()['ticket_number']
                conn.close()
                st.success(f"Đăng ký thành công! Số thứ tự của bạn là {ticket_number}. Bạn ở vị trí {position} trong hàng đợi.")
            else:
                st.error("Số CCCD đã được đăng ký")

def process_customers():
    st.sidebar.header("Xử lý khách hàng")

    col1, col2 = st.sidebar.columns(2)

    with col1:
        if st.button("Gọi khách - Bàn 1"):
            customer = process_next_customer(1)
            if customer:
                audio_html = create_audio(
                    f"Mời khách hàng {customer.name}, số {customer.ticket_number}, đến Bàn 1"
                )
                # Hiển thị HTML âm thanh ngay sau khi gọi khách
                st.markdown(audio_html, unsafe_allow_html=True)

    with col2:
        if st.button("Gọi khách - Bàn 2"):
            customer = process_next_customer(2)
            if customer:
                audio_html = create_audio(
                    f"Mời khách hàng {customer.name}, số {customer.ticket_number}, đến Bàn 2"
                )
                # Hiển thị HTML âm thanh ngay sau khi gọi khách
                st.markdown(audio_html, unsafe_allow_html=True)

def reset_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Xóa tất cả dữ liệu từ các bảng
        cursor.execute('DELETE FROM customers')
        cursor.execute('DELETE FROM desks')
        cursor.execute('DELETE FROM queues')

        # Reset lại bảng desks để khởi tạo 2 bàn làm việc nếu cần
        cursor.execute('INSERT OR IGNORE INTO desks (desk_id) VALUES (1)')
        cursor.execute('INSERT OR IGNORE INTO desks (desk_id) VALUES (2)')

        conn.commit()
        st.success("Cơ sở dữ liệu đã được reset thành công!")
    except Exception as e:
        conn.rollback()
        st.error(f"Có lỗi xảy ra khi reset cơ sở dữ liệu: {str(e)}")
    finally:
        conn.close()


def check_status():
    st.sidebar.header("Kiểm tra trạng thái")
    cccd = st.sidebar.text_input("Nhập số CCCD để kiểm tra")
    if st.sidebar.button("Kiểm tra"):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM customers WHERE cccd = ?', (cccd,))
        customer = cursor.fetchone()
        if customer:
            customer = Customer.from_dict(customer)
            cursor.execute('SELECT desk_id FROM desks WHERE current_customer_cccd = ?', (cccd,))
            result = cursor.fetchone()
            if result:
                st.sidebar.success(f"Đang được phục vụ tại Bàn {result['desk_id']}")
            else:
                cursor.execute('SELECT desk_id, position FROM queues WHERE cccd = ?', (cccd,))
                result = cursor.fetchone()
                if result:
                    st.sidebar.info(f"Đang chờ tại Bàn {result['desk_id']}, vị trí thứ {result['position']}")
                else:
                    st.sidebar.warning("Bạn đã được phục vụ hoặc chưa đăng ký")
        else:
            st.sidebar.error("Không tìm thấy thông tin")
        conn.close()

def main():
    st.title("🎫 Hệ thống quản lý hàng đợi")

    # Khởi tạo cơ sở dữ liệu nếu chưa có
    init_db()

    # Hiển thị trạng thái các bàn
    col1, col2 = st.columns(2)
    with col1:
        render_desk_status(1)
    with col2:
        render_desk_status(2)
    if st.sidebar.button('Xoá dữ liệu'):
        reset_database()
    # Form đăng ký
    registration_form()

    # Xử lý khách hàng và kiểm tra trạng thái
    process_customers()
    check_status()

if __name__ == "__main__":
    main()

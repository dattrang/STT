import streamlit as st
from dataclasses import dataclass, asdict
from typing import Optional
import time
import sqlite3
from gtts import gTTS
import tempfile
import os
import base64
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


# Kết nối đến cơ sở dữ liệu SQLite
@st.cache_resource
def get_db_connection():
    conn = sqlite3.connect('queue_management.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

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
    # Sử dụng ngữ cảnh `with` để đảm bảo kết nối được mở/đóng đúng cách
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

    return current_customer, queue

def render_desk_status(desk_id: int):
    current_customer, queue = get_desk_status(desk_id)

    st.subheader(f"Bàn {desk_id}")
    st.markdown("##### Đang làm thủ tục:")
    
    if current_customer:
        st.markdown(f"""
        <div style='background-color: #e6f3ff; padding: 10px; border-radius: 5px;'>
            <h3 style='color: #0066cc;'>{current_customer.name}</h3>
            <p>Số thứ tự: {current_customer.ticket_number}</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("<p style='color: #666;'>Chưa có công dân làm thủ tục</p>", unsafe_allow_html=True)

    st.markdown("##### Danh sách chờ:")

    # Tạo vùng danh sách có cuộn khi vượt quá chiều cao 200px
    list_html = "<div style='height: 200px; overflow-y: scroll; border: 1px solid #ccc; padding: 10px; border-radius: 5px;'>"

    if queue:
        for i, customer in enumerate(queue, 1):
            list_html += f"<p>{i}. {customer.name} - Số {customer.ticket_number}</p>"
    else:
        list_html += "<p style='color: #666;'>Không có công dân đăng ký chờ</p>"

    list_html += "</div>"

    st.markdown(list_html, unsafe_allow_html=True)

def registration_form():
    st.header("Đăng ký xếp hàng lấy số thứ tự")
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

            position, ticket_number, desk_id = add_customer(name, cccd)
            if position != -1:
                success_msg = f"Đăng ký thành công! Số thứ tự của bạn là {ticket_number}. Bạn ở vị trí {position} trong hàng đợi tại Bàn {desk_id}."
                st.success(success_msg)
                st.rerun()
            else:
                st.error("Số CCCD đã được đăng ký")

def skip_customer(desk_id: int):
    # Mở kết nối với cơ sở dữ liệu
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Lấy khách hàng hiện tại đang được phục vụ tại bàn
        cursor.execute('''
            SELECT current_customer_cccd FROM desks
            WHERE desk_id = ?
        ''', (desk_id,))
        result = cursor.fetchone()

        if result and result['current_customer_cccd']:
            cccd_to_skip = result['current_customer_cccd']

            # Lấy vị trí cao nhất hiện tại trong hàng đợi
            cursor.execute('''
                SELECT MAX(position) FROM queues
                WHERE desk_id = ?
            ''', (desk_id,))
            max_position = cursor.fetchone()[0] or 0  # Nếu hàng đợi rỗng, vị trí tối đa là 0

            # Đẩy khách hàng hiện tại xuống cuối hàng đợi
            new_position = max_position + 1
            cursor.execute('''
                INSERT INTO queues (desk_id, cccd, position)
                VALUES (?, ?, ?)
            ''', (desk_id, cccd_to_skip, new_position))

            # Cập nhật bàn hiện tại không có khách hàng phục vụ
            cursor.execute('''
                UPDATE desks SET current_customer_cccd = NULL
                WHERE desk_id = ?
            ''', (desk_id,))

            conn.commit()

            # Gọi khách hàng tiếp theo (sử dụng hàm process_next_customer)
            customer = process_next_customer(desk_id)

            # Nếu có khách hàng tiếp theo, phát âm thanh thông báo
            if customer:
                announce = f"Mời công dân {customer.name}, số thứ tự {customer.ticket_number}, đến Bàn {desk_id}"
                st.session_state[f'audio_message_ban{desk_id}'] = announce  # Lưu trạng thái thông báo
                st.rerun()
        else:
            st.warning("Không có công dân nào đang làm thủ tục tại bàn này.")

def process_customers():
    st.sidebar.header("Xử lý công dân")

    # Đặt mật khẩu đúng (bạn có thể thay đổi mật khẩu này)
    correct_password = "Tanhung@2020"

    # Nếu chưa xác thực, hiển thị ô nhập mật khẩu
    if 'authenticated' not in st.session_state:
        st.session_state['authenticated'] = False

    if not st.session_state['authenticated']:
        password = st.sidebar.text_input("Nhập mật khẩu để xử lý", type="password")

        # Kiểm tra nếu mật khẩu đúng
        if password == correct_password:
            st.session_state['authenticated'] = True  # Đánh dấu đã xác thực
            st.rerun()  # Tải lại trang để ẩn ô nhập mật khẩu
        elif password:  # Nếu mật khẩu nhập không đúng
            st.sidebar.error("Mật khẩu không đúng!")
    
    # Sau khi xác thực, hiển thị các nút xử lý và nút xóa dữ liệu
    if st.session_state['authenticated']:
        col1, col2 = st.sidebar.columns(2)

        # Bàn 1
        with col1:
            if st.button("Bỏ qua - Bàn 1"):
                skip_customer(1)
                st.rerun()
            if st.button("Gọi công dân - Bàn 1"):
                customer = process_next_customer(1)
                if customer:
                    announce = f"Mời Công dân {customer.name}, số thứ tự {customer.ticket_number}, đến Bàn 1"
                    st.session_state['audio_message_ban1'] = announce  # Lưu trạng thái cho Bàn 1
                    st.session_state['audio_desk'] = 1
                    st.rerun()

        # Bàn 2
        with col2:
            if st.button("Bỏ qua - Bàn 2"):
                skip_customer(2)
                st.rerun()
            if st.button("Gọi công dân - Bàn 2"):
                customer = process_next_customer(2)
                if customer:
                    announce = f"Mời công dân {customer.name}, số thứ tự {customer.ticket_number}, đến Bàn 2"
                    st.session_state['audio_message_ban2'] = announce  # Lưu trạng thái cho Bàn 2
                    st.session_state['audio_desk'] = 2
                    st.rerun()

        # Hiển thị nút xóa dữ liệu khi mật khẩu đúng
        if st.sidebar.button('Xoá dữ liệu'):
            reset_database()


def reset_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('DELETE FROM customers')
        cursor.execute('DELETE FROM desks')
        cursor.execute('DELETE FROM queues')
        cursor.execute('INSERT OR IGNORE INTO desks (desk_id) VALUES (1)')
        cursor.execute('INSERT OR IGNORE INTO desks (desk_id) VALUES (2)')
        conn.commit()
        st.success("Cơ sở dữ liệu đã được reset thành công!")
        st.rerun()
    except Exception as e:
        st.error(f"Có lỗi xảy ra khi reset cơ sở dữ liệu: {str(e)}")

def check_status():
    st.sidebar.header("Kiểm tra số thứ tự")
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
                st.sidebar.success(f"Đang làm thủ tục tại Bàn {result['desk_id']}")
            else:
                cursor.execute('SELECT desk_id, position FROM queues WHERE cccd = ?', (cccd,))
                result = cursor.fetchone()
                if result:
                    st.sidebar.info(f"Đang chờ tại Bàn {result['desk_id']}, vị trí thứ {result['position']}")
                else:
                    st.sidebar.warning("Bạn đã làm thủ tục hoặc chưa đăng ký")
        else:
            st.sidebar.error("Không tìm thấy thông tin")

def main():
    st.title("🎫 Hệ thống xếp hàng")
    
    # Khởi tạo cơ sở dữ liệu
    init_db()
    
    # Tạo layout chính
    col1, col2 = st.columns(2)
    with col1:
        render_desk_status(1)
    with col2:
        render_desk_status(2)

    # Phát âm thanh cho Bàn 1 nếu có thông báo
    if 'audio_message_ban1' in st.session_state and st.session_state['audio_message_ban1']:
        audio_message = st.session_state['audio_message_ban1']
        st.success(audio_message)
        audio_file = create_audio(audio_message)
        if audio_file:
            play_audio_autoplay(audio_file)  # Tự động phát âm thanh
            os.unlink(audio_file)
        del st.session_state['audio_message_ban1']  # Xóa trạng thái sau khi phát xong

    # Phát âm thanh cho Bàn 2 nếu có thông báo
    if 'audio_message_ban2' in st.session_state and st.session_state['audio_message_ban2']:
        audio_message = st.session_state['audio_message_ban2']
        st.success(audio_message)
        audio_file = create_audio(audio_message)
        if audio_file:
            play_audio_autoplay(audio_file)  # Tự động phát âm thanh
            os.unlink(audio_file)
        del st.session_state['audio_message_ban2']  # Xóa trạng thái sau khi phát xong

    # Form đăng ký
    registration_form()
    
    # Xử lý khách hàng và kiểm tra trạng thái
    process_customers()
    check_status()
    

if __name__ == "__main__":
    main()

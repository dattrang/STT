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
    status: str = 'Chưa được phục vụ'  # Thêm thuộc tính status với giá trị mặc định

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(data):
        return Customer(**data)

# Kết nối đến cơ sở dữ liệu SQLite
def get_db_connection():
    db_path = 'queue_management.db'
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

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
            # Kiểm tra nếu công dân đang làm thủ tục tại bàn nào đó
            cursor.execute('SELECT desk_id FROM desks WHERE current_customer_cccd = ?', (cccd,))
            result = cursor.fetchone()
            if result:
                st.sidebar.success(f"Đang làm thủ tục tại Bàn {result['desk_id']}")
            else:
                # Kiểm tra xem công dân đang chờ ở đâu trong hàng đợi
                cursor.execute('SELECT desk_id, position FROM queues WHERE cccd = ?', (cccd,))
                result = cursor.fetchone()
                if result:
                    st.sidebar.info(f"Đang chờ tại Bàn {result['desk_id']}, vị trí thứ {result['position']}")
                else:
                    st.sidebar.warning("Bạn đã làm thủ tục hoặc chưa đăng ký")
        else:
            st.sidebar.error("Không tìm thấy thông tin")

            
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

    # Tạo bảng 'customers' nếu chưa tồn tại
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            cccd TEXT PRIMARY KEY,
            name TEXT,
            ticket_number INTEGER,
            timestamp REAL
        )
    ''')

    # Thêm cột 'status' nếu chưa có
    cursor.execute("PRAGMA table_info(customers)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'status' not in columns:
        cursor.execute('ALTER TABLE customers ADD COLUMN status TEXT DEFAULT "Chưa được phục vụ"')

    # Tạo các bảng khác
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
    conn.close()


# Hàm thêm khách hàng mới
def add_customer(name: str, cccd: str) -> tuple:
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Kiểm tra nếu khách hàng đã tồn tại
        cursor.execute('SELECT * FROM customers WHERE cccd = ?', (cccd,))
        if cursor.fetchone():
            return -1, -1, -1

        # Tính số thứ tự (ticket_number) tiếp theo
        cursor.execute('SELECT MAX(ticket_number) FROM customers')
        result = cursor.fetchone()
        next_number = result[0] + 1 if result[0] else 1

        # Lưu timestamp hiện tại
        timestamp = time.time()

        # Tạo khách hàng mới với trạng thái mặc định 'Chưa được phục vụ'
        customer = Customer(name, cccd, next_number, timestamp)

        # Thêm khách hàng vào bảng 'customers'
        cursor.execute('''
            INSERT INTO customers (cccd, name, ticket_number, timestamp, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (customer.cccd, customer.name, customer.ticket_number, customer.timestamp, customer.status))

        # Chọn bàn có ít người nhất
        desk_id = get_least_busy_desk(cursor)

        # Thêm khách hàng vào hàng đợi
        position = enqueue_customer(cursor, desk_id, customer.cccd)

        # Commit các thay đổi vào cơ sở dữ liệu
        conn.commit()

        return position, next_number, desk_id
    except sqlite3.OperationalError as e:
        st.error(f"Lỗi cơ sở dữ liệu: {e}")
        return -1, -1, -1
    finally:
        if conn:
            conn.close()  # Đóng kết nối sau khi hoàn tất mọi thao tác

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
    conn = get_db_connection()
    cursor = conn.cursor()

    # Truy vấn công dân hiện tại tại bàn
    cursor.execute('''
        SELECT current_customer_cccd FROM desks WHERE desk_id = ?
    ''', (desk_id,))
    current_customer = cursor.fetchone()

    if current_customer and current_customer['current_customer_cccd']:
        # Cập nhật trạng thái công dân hiện tại thành "Đã làm xong"
        cursor.execute('''
            UPDATE customers SET status = 'Đã làm xong' WHERE cccd = ?
        ''', (current_customer['current_customer_cccd'],))

    # Lấy công dân tiếp theo trong hàng đợi
    cursor.execute('''
        SELECT customers.* FROM queues
        JOIN customers ON queues.cccd = customers.cccd
        WHERE desk_id = ?
        ORDER BY position ASC
        LIMIT 1
    ''', (desk_id,))
    next_customer = cursor.fetchone()

    if next_customer:
        # Cập nhật trạng thái của công dân tiếp theo thành "Đang làm thủ tục"
        cursor.execute('''
            UPDATE customers SET status = 'Đang làm thủ tục' WHERE cccd = ?
        ''', (next_customer['cccd'],))

        # Cập nhật bàn hiện tại đang phục vụ công dân này
        cursor.execute('''
            UPDATE desks SET current_customer_cccd = ? WHERE desk_id = ?
        ''', (next_customer['cccd'], desk_id))

        # Xóa công dân khỏi hàng đợi
        cursor.execute('''
            DELETE FROM queues WHERE desk_id = ? AND cccd = ?
        ''', (desk_id, next_customer['cccd']))

        conn.commit()
        return Customer.from_dict(next_customer)
    else:
        # Không có công dân nào trong hàng đợi
        cursor.execute('''
            UPDATE desks SET current_customer_cccd = NULL WHERE desk_id = ?
        ''', (desk_id,))
        conn.commit()
        return None


def render_desk_status(desk_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT customers.* FROM desks
        LEFT JOIN customers ON desks.current_customer_cccd = customers.cccd
        WHERE desks.desk_id = ?
    ''', (desk_id,))
    current_customer = cursor.fetchone()

    st.subheader(f"Bàn {desk_id}")
    st.markdown("##### Đang làm thủ tục:")

    if current_customer and current_customer['cccd']:
        st.markdown(f"""
        <div style='background-color: #e6f3ff; padding: 10px; border-radius: 5px;'>
            <h3 style='color: #0066cc;'>{current_customer['name']}</h3>
            <p>Số thứ tự: {current_customer['ticket_number']}</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("<p style='color: #666;'>Chưa có công dân làm thủ tục</p>", unsafe_allow_html=True)

    st.markdown("##### Danh sách chờ:")

    cursor.execute('''
        SELECT customers.* FROM queues
        JOIN customers ON queues.cccd = customers.cccd
        WHERE queues.desk_id = ?
        ORDER BY position ASC
    ''', (desk_id,))
    queue = cursor.fetchall()

    list_html = "<div style='height: 200px; overflow-y: scroll; border: 1px solid #ccc; padding: 10px; border-radius: 5px;'>"

    if queue:
        for i, customer in enumerate(queue, 1):
            list_html += f"<p>{i}. {customer['name']} - Số {customer['ticket_number']}</p>"
    else:
        list_html += "<p style='color: #666;'>Không có công dân đăng ký chờ</p>"

    list_html += "</div>"

    st.markdown(list_html, unsafe_allow_html=True)

# Thêm các tính năng hiển thị, ẩn bảng và tải xuống danh sách
def get_registered_customers():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Truy vấn dữ liệu bao gồm cả cột 'status'
    cursor.execute('''
        SELECT name, cccd, ticket_number, status
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
            'Số thứ tự': row['ticket_number'],
            'Trạng thái': row['status']  # Hiển thị trạng thái
        })

    df = pd.DataFrame(data)
    return df

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
        st.session_state['success_msg'] = ""

def skip_customer(desk_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Lấy công dân hiện tại đang phục vụ
    cursor.execute('''
        SELECT current_customer_cccd FROM desks WHERE desk_id = ?
    ''', (desk_id,))
    current_customer = cursor.fetchone()

    if current_customer and current_customer['current_customer_cccd']:
        cccd_to_skip = current_customer['current_customer_cccd']

        # Lấy vị trí lớn nhất trong hàng đợi
        cursor.execute('''
            SELECT MAX(position) FROM queues WHERE desk_id = ?
        ''', (desk_id,))
        max_position = cursor.fetchone()[0] or 0

        # Đẩy công dân hiện tại xuống cuối hàng đợi với trạng thái "Chưa làm thủ tục"
        new_position = max_position + 1
        cursor.execute('''
            INSERT INTO queues (desk_id, cccd, position)
            VALUES (?, ?, ?)
        ''', (desk_id, cccd_to_skip, new_position))

        cursor.execute('''
            UPDATE customers SET status = 'Chưa làm thủ tục' WHERE cccd = ?
        ''', (cccd_to_skip,))

        # Xóa công dân hiện tại khỏi bàn
        cursor.execute('''
            UPDATE desks SET current_customer_cccd = NULL WHERE desk_id = ?
        ''', (desk_id,))

        conn.commit()

        # Gọi công dân tiếp theo
        next_customer = process_next_customer(desk_id)

        # Nếu có công dân tiếp theo, phát âm thanh thông báo
        if next_customer:
            announce = f"Mời công dân {next_customer.name}, số thứ tự {next_customer.ticket_number}, đến Bàn {desk_id}"
            st.session_state[f'audio_message_ban{desk_id}'] = announce  # Lưu trạng thái thông báo
            audio_file = create_audio(announce)  # Tạo file âm thanh từ thông báo
            if audio_file:
                play_audio_autoplay(audio_file)  # Phát âm thanh
                os.unlink(audio_file)  # Xóa file âm thanh sau khi phát
        else:
            st.warning("Không có công dân nào đang chờ tại bàn này.")
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

        # Nút cho bàn 1
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

        # Nút cho bàn 2
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

        # Sau khi nhập mật khẩu đúng, hiển thị nút hiển thị danh sách và tải xuống
        toggle_list_display()
        download_customer_list()

def main():
    st.title("🎫 Hệ thống xếp hàng")

    # Khởi tạo cơ sở dữ liệu
    init_db()

    # Hiển thị trạng thái của các bàn
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
            play_audio_autoplay(audio_file)
            os.unlink(audio_file)
        del st.session_state['audio_message_ban1']

    # Phát âm thanh cho Bàn 2 nếu có thông báo
    if 'audio_message_ban2' in st.session_state and st.session_state['audio_message_ban2']:
        audio_message = st.session_state['audio_message_ban2']
        st.success(audio_message)
        audio_file = create_audio(audio_message)
        if audio_file:
            play_audio_autoplay(audio_file)
            os.unlink(audio_file)
        del st.session_state['audio_message_ban2']

    # Form đăng ký
    registration_form()

    # Xử lý công dân và chỉ hiện nút sau khi nhập mật khẩu
    process_customers()

    # Tính năng kiểm tra số thứ tự (thêm vào sidebar)
    check_status()

if __name__ == "__main__":
    main()

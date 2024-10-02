import streamlit as st
from collections import deque
import json
import os
from gtts import gTTS
import base64
import time
from dataclasses import dataclass
from typing import Dict, List, Optional
import tempfile

# Cấu hình trang Streamlit
st.set_page_config(
    page_title="Hệ thống quản lý hàng đợi",
    page_icon="🎫",
    layout="wide"
)

# Định nghĩa classes
@dataclass
class Customer:
    name: str
    cccd: str
    ticket_number: int
    timestamp: float

class DeskManager:
    def __init__(self, desk_id: int):
        self.desk_id = desk_id
        self.queue = deque()
        self.current_customer = None

# Khởi tạo session state
if 'initialized' not in st.session_state:
    st.session_state.desk1 = DeskManager(1)
    st.session_state.desk2 = DeskManager(2)
    st.session_state.customers = {}
    st.session_state.next_number = 1
    st.session_state.initialized = True

# Hàm xử lý file
def save_state():
    data = {
        'desk1': {
            'queue': list(st.session_state.desk1.queue),
            'current': st.session_state.desk1.current_customer
        },
        'desk2': {
            'queue': list(st.session_state.desk2.queue),
            'current': st.session_state.desk2.current_customer
        },
        'customers': st.session_state.customers,
        'next_number': st.session_state.next_number
    }
    
    # Sử dụng biến môi trường cho tên file
    filename = os.environ.get('QUEUE_DATA_FILE', 'queue_data.json')
    
    try:
        with open(filename, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        st.error(f"Không thể lưu dữ liệu: {str(e)}")

def load_state():
    # Sử dụng biến môi trường cho tên file
    filename = os.environ.get('QUEUE_DATA_FILE', 'queue_data.json')
    
    try:
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                data = json.load(f)
                
            st.session_state.desk1.queue = deque(data['desk1']['queue'])
            st.session_state.desk1.current_customer = data['desk1']['current']
            st.session_state.desk2.queue = deque(data['desk2']['queue'])
            st.session_state.desk2.current_customer = data['desk2']['current']
            st.session_state.customers = data['customers']
            st.session_state.next_number = data['next_number']
    except Exception as e:
        st.error(f"Không thể tải dữ liệu: {str(e)}")

# Hàm xử lý âm thanh
@st.cache_data
def create_audio(_text: str) -> str:
    try:
        # Tạo file tạm thời
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as fp:
            temp_filename = fp.name
            
        # Tạo và lưu file âm thanh
        tts = gTTS(text=_text, lang='vi')
        tts.save(temp_filename)
        
        # Đọc file âm thanh và chuyển đổi sang base64
        with open(temp_filename, 'rb') as audio_file:
            audio_bytes = audio_file.read()
            audio_base64 = base64.b64encode(audio_bytes).decode()
        
        # Xóa file tạm thời
        os.remove(temp_filename)
        
        # Trả về HTML audio element
        return f"""
        <audio autoplay="true">
        <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3">
        </audio>
        """
    except Exception as e:
        st.error(f"Lỗi tạo âm thanh: {str(e)}")
        return ""

def add_customer(name: str, cccd: str) -> int:
    if cccd in st.session_state.customers:
        return -1

    customer = {
        'name': name,
        'cccd': cccd,
        'ticket_number': st.session_state.next_number,
        'timestamp': time.time()
    }

    st.session_state.customers[cccd] = customer
    st.session_state.next_number += 1

    # Chọn bàn có ít người chờ hơn
    if len(st.session_state.desk1.queue) <= len(st.session_state.desk2.queue):
        st.session_state.desk1.queue.append(customer)
        return len(st.session_state.desk1.queue)  # Trả về vị trí trong hàng đợi
    else:
        st.session_state.desk2.queue.append(customer)
        return len(st.session_state.desk2.queue)  # Trả về vị trí trong hàng đợi

def process_next_customer(desk: DeskManager) -> Optional[dict]:
    if desk.queue:
        customer = desk.queue.popleft()
        desk.current_customer = customer
        save_state()
        return customer
    return None

# UI Components
def render_desk_status(desk: DeskManager):
    st.subheader(f"Bàn {desk.desk_id}")
    
    st.markdown("##### Đang phục vụ:")
    if desk.current_customer:
        st.markdown(f"""
        <div style='background-color: #e6f3ff; padding: 10px; border-radius: 5px;'>
            <h3 style='color: #0066cc;'>{desk.current_customer['name']}</h3>
            <p>Số thứ tự: {desk.current_customer['ticket_number']}</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("<p style='color: #666;'>Chưa có khách hàng</p>", unsafe_allow_html=True)
    
    st.markdown("##### Danh sách chờ:")
    if desk.queue:
        for i, customer in enumerate(desk.queue, 1):
            st.markdown(f"{i}. {customer['name']} - Số {customer['ticket_number']}")
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
                ticket_number = st.session_state.next_number - 1
                st.success(f"Đăng ký thành công! Số thứ tự của bạn là {ticket_number}. Bạn ở vị trí {position} trong hàng đợi.")
            else:
                st.error("Số CCCD đã được đăng ký")


if 'current_desk1' not in st.session_state:
    st.session_state.current_desk1 = None
if 'current_desk2' not in st.session_state:
    st.session_state.current_desk2 = None
    
def process_customers():
    st.sidebar.header("Xử lý khách hàng")
    
    col1, col2 = st.sidebar.columns(2)
    
    with col1:
        if st.button("Gọi khách - Bàn 1", key="desk1_button"):
            customer = process_next_customer(st.session_state.desk1)
            if customer:
                st.session_state.current_desk1 = customer
    
    with col2:
        if st.button("Gọi khách - Bàn 2", key="desk2_button"):
            customer = process_next_customer(st.session_state.desk2)
            if customer:
                st.session_state.current_desk2 = customer

    # Hiển thị âm thanh nếu có khách hàng mới
    if st.session_state.current_desk1:
        audio_html = create_audio(
            f"Mời khách hàng {st.session_state.current_desk1['name']}, số {st.session_state.current_desk1['ticket_number']}, đến Bàn 1"
        )
        st.markdown(audio_html, unsafe_allow_html=True)
        st.session_state.current_desk1 = None
    
    if st.session_state.current_desk2:
        audio_html = create_audio(
            f"Mời khách hàng {st.session_state.current_desk2['name']}, số {st.session_state.current_desk2['ticket_number']}, đến Bàn 2"
        )
        st.markdown(audio_html, unsafe_allow_html=True)
        st.session_state.current_desk2 = None


# Tối ưu hóa việc rerun bằng cách sử dụng session state
if 'needs_rerun' not in st.session_state:
    st.session_state.needs_rerun = False

def check_status():
    st.sidebar.header("Kiểm tra trạng thái")
    cccd = st.sidebar.text_input("Nhập số CCCD để kiểm tra")
    if st.sidebar.button("Kiểm tra"):
        if cccd in st.session_state.customers:
            customer = st.session_state.customers[cccd]
            
            # Kiểm tra xem khách hàng đang ở đâu
            if customer == st.session_state.desk1.current_customer:
                st.sidebar.success(f"Đang được phục vụ tại Bàn 1")
            elif customer == st.session_state.desk2.current_customer:
                st.sidebar.success(f"Đang được phục vụ tại Bàn 2")
            else:
                # Kiểm tra trong hàng đợi
                for desk in [st.session_state.desk1, st.session_state.desk2]:
                    if customer in desk.queue:
                        position = list(desk.queue).index(customer) + 1
                        st.sidebar.info(f"Đang chờ tại Bàn {desk.desk_id}, vị trí thứ {position}")
                        break
        else:
            st.sidebar.error("Không tìm thấy thông tin")

def process_next_customer(desk: DeskManager) -> Optional[dict]:
    if desk.queue:
        customer = desk.queue.popleft()
        desk.current_customer = customer
        save_state()
        st.session_state.needs_rerun = True
        return customer
    return None

# Trong hàm main, thêm kiểm tra needs_rerun
def main():
    st.title("🎫 Hệ thống quản lý hàng đợi")
    
    # Load dữ liệu từ file (nếu có)
    load_state()
    
    # Hiển thị trạng thái các bàn
    col1, col2 = st.columns(2)
    with col1:
        render_desk_status(st.session_state.desk1)
    with col2:
        render_desk_status(st.session_state.desk2)
    
    # Form đăng ký
    registration_form()
    
    # Xử lý khách hàng và kiểm tra trạng thái
    process_customers()
    check_status()
    
    # Kiểm tra và reset flag needs_rerun
    if st.session_state.needs_rerun:
        st.session_state.needs_rerun = False
        st.rerun()

if __name__ == "__main__":
    main()

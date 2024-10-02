import streamlit as st
from collections import deque
import json
import os
from gtts import gTTS
import base64

# Đường dẫn file lưu trữ dữ liệu
DATA_FILE = "customer_data.json"

# Tạo các hàng chờ cho 2 bàn
queue_1 = deque()
queue_2 = deque()

# Danh sách các số CCCD đã đăng ký với thông tin Công dân
registered_customers = {}

# Biến để lưu trạng thái Công dân đang được phục vụ và số thứ tự tiếp theo
current_customer_1 = None
current_customer_2 = None
next_ticket_number = 1  # Số thứ tự tiếp theo

# Hàm để lưu dữ liệu vào file JSON
def save_data():
    data = {
        "queue_1": list(queue_1),
        "queue_2": list(queue_2),
        "registered_customers": registered_customers,
        "current_customer_1": current_customer_1,
        "current_customer_2": current_customer_2,
        "next_ticket_number": next_ticket_number  # Lưu số thứ tự tiếp theo
    }
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f)

# Hàm để tải dữ liệu từ file JSON
def load_data():
    global queue_1, queue_2, registered_customers, current_customer_1, current_customer_2, next_ticket_number
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
            queue_1 = deque(data.get("queue_1", []))
            queue_2 = deque(data.get("queue_2", []))
            registered_customers = data.get("registered_customers", {})
            current_customer_1 = data.get("current_customer_1", None)
            current_customer_2 = data.get("current_customer_2", None)
            next_ticket_number = data.get("next_ticket_number", 1)  # Lấy số thứ tự tiếp theo từ file

# Gọi hàm load dữ liệu khi ứng dụng khởi động
load_data()

# Hàm để phân Công dân vào hàng chờ bàn tiếp khách
def add_customer_to_queue(customer_name, cccd):
    global next_ticket_number
    if len(queue_1) <= len(queue_2):
        queue_1.append(f"{customer_name} - Số thứ tự {next_ticket_number}")
    else:
        queue_2.append(f"{customer_name} - Số thứ tự {next_ticket_number}")
    registered_customers[cccd] = {'name': customer_name, 'ticket_number': next_ticket_number}
    next_ticket_number += 1  # Tăng số thứ tự
    save_data()  # Lưu dữ liệu sau khi thêm Công dân

# Hàm để kiểm tra tính hợp lệ của số CCCD
def is_valid_cccd(cccd):
    return cccd.isdigit() and len(cccd) == 12 and cccd not in registered_customers

# Hàm để phát thông báo bằng giọng nói sử dụng gTTS
def speak_text(text):
    tts = gTTS(text=text, lang='vi')
    tts.save("output.mp3")

    # Đọc file âm thanh và mã hóa thành base64 để phát lại
    audio_file = open("output.mp3", "rb")
    audio_bytes = audio_file.read()
    audio_base64 = base64.b64encode(audio_bytes).decode()

    audio_html = f"""
    <audio autoplay="true">
    <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3">
    </audio>
    """

    st.markdown(audio_html, unsafe_allow_html=True)

# Hàm để xử lý Công dân tiếp theo cho mỗi bàn
def process_next_customer():
    global current_customer_1, current_customer_2

    # Xử lý khách hàng cho Bàn 1
    process_1 = st.sidebar.button("Xử lý tiếp khách Bàn 1")
    if process_1:
        if queue_1:
            current_customer_1 = queue_1.popleft()
            save_data()  # Lưu dữ liệu sau khi xử lý công dân
            st.write(f"{current_customer_1}")
            speak_text(f"Kính mời Công dân: {current_customer_1} lên làm việc tại Bàn 1")  # Phát thông báo
        else:
            st.sidebar.warning("Không có Công dân trong hàng chờ Bàn 1.")
    
    # Xử lý khách hàng cho Bàn 2
    process_2 = st.sidebar.button("Xử lý tiếp khách Bàn 2")
    if process_2:
        if queue_2:
            current_customer_2 = queue_2.popleft()
            save_data()  # Lưu dữ liệu sau khi xử lý công dân
            st.write(f"{current_customer_2}")
            speak_text(f"Kính mời Công dân: {current_customer_2} lên làm việc tại Bàn 2")  # Phát thông báo
        else:
            st.sidebar.warning("Không có Công dân trong hàng chờ Bàn 2.")
    
    # Thông báo lại cho Bàn 1
    if current_customer_1 and st.sidebar.button("Thông báo lại Bàn 1"):
        st.write(f"{current_customer_1}")
        speak_text(f"Kính mời Công dân: {current_customer_1} lên làm việc tại Bàn 1")
    
    # Thông báo lại cho Bàn 2
    if current_customer_2 and st.sidebar.button("Thông báo lại Bàn 2"):
        st.write(f"{current_customer_2}")
        speak_text(f"Kính mời Công dân: {current_customer_2} lên làm việc tại Bàn 2")
# Hàm để reset file JSON và dữ liệu
def reset_data():
    global queue_1, queue_2, registered_customers, current_customer_1, current_customer_2, next_ticket_number
    queue_1 = deque()
    queue_2 = deque()
    registered_customers = {}
    current_customer_1 = None
    current_customer_2 = None
    next_ticket_number = 1  # Đặt lại số thứ tự về 1
    save_data()  # Lưu dữ liệu trống vào file
    st.success("Dữ liệu đã được reset thành công!")

# Hàm để thêm Công dân vào hệ thống thông qua nhập trực tiếp
def add_direct_customer():
    st.header("Đăng ký trực tiếp")
    customer_name = st.text_input("Nhập tên Công dân:")
    cccd = st.text_input("Nhập CCCD (12 số):")
    
    if st.button("Đăng ký"):
        if not customer_name:
            st.error("Tên Công dân không được để trống.")
        elif not is_valid_cccd(cccd):
            st.error("Số CCCD phải là chuỗi 12 chữ số và không được trùng lặp.")
        else:
            add_customer_to_queue(customer_name, cccd)
            st.success(f"Công dân {customer_name} đã được đăng ký thành công với CCCD {cccd} và số thứ tự {next_ticket_number - 1}.")

# Hàm để xác minh CCCD khi Công dân đến
def verify_customer():
    st.sidebar.header("Kiểm tra lại số thứ tự")
    cccd = st.sidebar.text_input("Nhập CCCD đã đăng ký để kiểm tra")
    
    if st.sidebar.button("Kiểm tra"):
        if cccd in registered_customers:
            customer_info = registered_customers[cccd]
            st.sidebar.success(f"Xác minh thành công! Công dân {customer_info['name']} với số thứ tự {customer_info['ticket_number']} có thể được phục vụ.")
        else:
            st.sidebar.error("CCCD không hợp lệ hoặc không tồn tại trong hệ thống.")

# Giao diện Streamlit
st.title("Ứng dụng quản lý cấp số thứ tự cho Công dân")

# Phần nhập trực tiếp
add_direct_customer()
# Phần xử lý Công dân và xác minh CCCD ở sidebar
process_next_customer()
verify_customer()
#if st.sidebar.button('reset'):
    #reset_data()
# Hiển thị thông tin Công dân đang được phục vụ ở Bàn 1 và Bàn 2
col1, col2 = st.columns(2)

with col1:
    st.subheader("Bàn 1")
    st.markdown("<h2>Đang phục vụ:</h2>", unsafe_allow_html=True)
    if current_customer_1:
        st.markdown(f"<h1 style='color:green;'>{current_customer_1}</h1>", unsafe_allow_html=True)
    else:
        st.markdown("<h3 style='color:red;'>Không có Công dân nào đang được phục vụ.</h3>", unsafe_allow_html=True)
    
    st.write("Hàng chờ:")
    if queue_1:
        for customer in queue_1:
            st.write(f"- {customer}")
    else:
        st.write("Không có Công dân trong hàng chờ")

with col2:
    st.subheader("Bàn 2")
    st.markdown("<h2>Đang phục vụ:</h2>", unsafe_allow_html=True)
    if current_customer_2:
        st.markdown(f"<h1 style='color:green;'>{current_customer_2}</h1>", unsafe_allow_html=True)
    else:
        st.markdown("<h3 style='color:red;'>Không có Công dân nào đang được phục vụ.</h3>", unsafe_allow_html=True)
    
    st.write("Hàng chờ:")
    if queue_2:
        for customer in queue_2:
            st.write(f"- {customer}")
    else:
        st.write("Không có Công dân trong hàng chờ")

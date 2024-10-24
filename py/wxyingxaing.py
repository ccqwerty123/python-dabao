import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import socket
import threading
import soundcard as sc
import numpy as np
import queue
import audioop
import random
import string
import jwt  # 用于生成加密链接
from flask import Flask, Response, request
import requests  # 用于网络请求生成二维码
from functools import partial
from datetime import datetime, timedelta
from io import BytesIO

class AudioStreamer:
    def __init__(self):
        self.app = Flask(__name__)
        self.audio_queue = queue.Queue(maxsize=50)
        self.connected_clients = {}  # {client_id: connection_time}
        self.password = self.generate_password()
        self.secret_key = self.generate_password(16)  # JWT密钥
        self.max_clients = 1  # 默认最大连接数
        self.setup_routes()
        self.setup_gui()

    def generate_password(self, length=6):
        """生成随机密码"""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

    def generate_token(self):
        """生成加密访问令牌"""
        expiration = datetime.now() + timedelta(hours=24)
        token = jwt.encode(
            {'password': self.password, 'exp': expiration},
            self.secret_key,
            algorithm='HS256'
        )
        return token

    def get_ip(self):
        """获取本机IP地址"""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        return ip

    def setup_gui(self):
        """设置图形界面"""
        self.root = tk.Tk()
        self.root.title("音频流服务器")
        self.root.geometry("500x750")

        # 样式设置
        style = ttk.Style()
        style.configure('TLabel', font=('Arial', 10))
        style.configure('Header.TLabel', font=('Arial', 12, 'bold'))

        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 用户限制设置
        limit_frame = ttk.LabelFrame(main_frame, text="用户限制", padding="5")
        limit_frame.pack(fill=tk.X, pady=5)

        ttk.Label(limit_frame, text="最大连接数：").pack(side=tk.LEFT)
        self.max_clients_var = tk.StringVar(value="1")
        spinbox = ttk.Spinbox(
            limit_frame,
            from_=1,
            to=10,
            width=5,
            textvariable=self.max_clients_var,
            command=self.update_max_clients
        )
        spinbox.pack(side=tk.LEFT, padx=5)

        # 加密直接访问链接
        direct_frame = ttk.LabelFrame(main_frame, text="加密直接访问", padding="5")
        direct_frame.pack(fill=tk.X, pady=5)

        self.direct_url_var = tk.StringVar()
        ttk.Entry(direct_frame, textvariable=self.direct_url_var, state='readonly').pack(fill=tk.X, pady=5)
        ttk.Button(direct_frame, text="复制链接", command=lambda: self.copy_text(self.direct_url_var.get())).pack()

        # 密码访问信息
        pwd_frame = ttk.LabelFrame(main_frame, text="密码访问", padding="5")
        pwd_frame.pack(fill=tk.X, pady=5)

        self.pwd_url_var = tk.StringVar()
        ttk.Entry(pwd_frame, textvariable=self.pwd_url_var, state='readonly').pack(fill=tk.X, pady=5)

        pwd_info_frame = ttk.Frame(pwd_frame)
        pwd_info_frame.pack(fill=tk.X)
        self.pwd_var = tk.StringVar(value=self.password)
        ttk.Label(pwd_info_frame, text="访问密码：").pack(side=tk.LEFT)
        ttk.Entry(pwd_info_frame, textvariable=self.pwd_var, state='readonly', width=10).pack(side=tk.LEFT)
        ttk.Button(pwd_info_frame, text="复制密码", command=lambda: self.copy_text(self.pwd_var.get())).pack(side=tk.LEFT, padx=5)
        ttk.Button(pwd_info_frame, text="刷新密码", command=self.refresh_password).pack(side=tk.LEFT)

        # 二维码标签页
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=10)

        # 直接访问二维码页
        direct_qr_frame = ttk.Frame(notebook)
        notebook.add(direct_qr_frame, text='直接访问二维码')
        self.direct_qr_label = ttk.Label(direct_qr_frame)
        self.direct_qr_label.pack(pady=10)

        # 密码访问二维码页
        pwd_qr_frame = ttk.Frame(notebook)
        notebook.add(pwd_qr_frame, text='密码访问二维码')
        self.pwd_qr_label = ttk.Label(pwd_qr_frame)
        self.pwd_qr_label.pack(pady=10)

        # 连接信息
        info_frame = ttk.LabelFrame(main_frame, text="连接信息", padding="5")
        info_frame.pack(fill=tk.X, pady=5)

        self.conn_var = tk.StringVar(value="当前连接数：0")
        ttk.Label(info_frame, textvariable=self.conn_var).pack()

        # 连接列表
        self.conn_list = ttk.Treeview(info_frame, columns=('ip', 'time'), show='headings', height=5)
        self.conn_list.heading('ip', text='IP地址')
        self.conn_list.heading('time', text='连接时间')
        self.conn_list.pack(fill=tk.X, pady=5)

        # 断开按钮
        ttk.Button(info_frame, text="断开选中连接", command=self.disconnect_selected).pack()

        # 状态栏
        self.status_var = tk.StringVar(value="服务器状态：准备就绪")
        ttk.Label(main_frame, textvariable=self.status_var).pack(pady=5)

        # 控制按钮
        ttk.Button(main_frame, text="关闭服务器", command=self.shutdown).pack(pady=5)

        # 初始化URL和二维码
        self.update_urls()

    def update_max_clients(self):
        """更新最大连接数"""
        try:
            self.max_clients = int(self.max_clients_var.get())
            self.status_var.set(f"状态：最大连接数已更新为 {self.max_clients}")
        except ValueError:
            self.max_clients_var.set(str(self.max_clients))

    def disconnect_selected(self):
        """断开选中的连接"""
        selected = self.conn_list.selection()
        if not selected:
            messagebox.showwarning("提示", "请选择要断开的连接")
            return

        for item in selected:
            client_ip = self.conn_list.item(item)['values'][0]
            if client_ip in self.connected_clients:
                del self.connected_clients[client_ip]
                self.conn_list.delete(item)
        self.update_connected_count()

    def copy_text(self, text):
        """复制文本到剪贴板"""
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set("状态：已复制到剪贴板")

    def refresh_password(self):
        """刷新密码"""
        self.password = self.generate_password()
        self.pwd_var.set(self.password)
        self.update_urls()
        self.status_var.set("状态：密码已更新")

    def update_urls(self):
        """更新所有URL和二维码"""
        base_url = f"http://{self.get_ip()}:5000"

        # 更新加密直接访问链接
        token = self.generate_token()
        direct_url = f"{base_url}/direct/{token}"
        self.direct_url_var.set(direct_url)

        # 更新密码访问链接
        pwd_url = f"{base_url}/login"
        self.pwd_url_var.set(pwd_url)

        # 更新两个二维码
        self.update_qr_code(direct_url, self.direct_qr_label)
        self.update_qr_code(pwd_url, self.pwd_qr_label)

    def update_qr_code(self, data, label):
        """尝试通过多个在线API生成二维码"""
        qr_image = self.get_qr_from_api(data)
        if qr_image:
            photo = ImageTk.PhotoImage(qr_image)
            label.configure(image=photo)
            label.image = photo
        else:
            label.configure(image=None)
            label.image = None

    def get_qr_from_api(self, data):
        """通过多个API尝试生成二维码"""
        apis = [
            f"https://api.qrserver.com/v1/create-qr-code/?data={data}&size=200x200",
            f"https://chart.googleapis.com/chart?chs=200x200&cht=qr&chl={data}",
            f"https://api.qrdraw.com/v1/create-qr-code/?data={data}&size=200x200"
        ]
        for api in apis:
            try:
                response = requests.get(api)
                if response.status_code == 200:
                    return Image.open(BytesIO(response.content))
            except Exception:
                continue
        return None

    def setup_routes(self):
        """设置Flask路由"""
        @self.app.route('/login', methods=['GET', 'POST'])
        def login():
            if request.method == 'POST':
                input_password = request.form.get('password')
                if input_password == self.password:
                    return self.serve_audio_page()
                else:
                    return '密码错误', 403
            return '''
                <form method="post">
                    <input type="password" name="password" placeholder="输入密码" required>
                    <input type="submit" value="提交">
                </form>
            '''

        @self.app.route('/direct/<token>')
        def direct(token):
            try:
                jwt.decode(token, self.secret_key, algorithms=['HS256'])
                return self.serve_audio_page()
            except jwt.ExpiredSignatureError:
                return '链接已过期', 403
            except jwt.InvalidTokenError:
                return '无效的链接', 403

        @self.app.route('/audio')
        def audio():
            if len(self.connected_clients) >= self.max_clients:
                return '连接数已满', 503
            client_ip = request.remote_addr
            self.connected_clients[client_ip] = datetime.now()
            self.update_connected_count()
            return Response(self.stream_audio(), mimetype="audio/wav")

    def update_connected_count(self):
        """更新连接计数"""
        self.conn_var.set(f"当前连接数：{len(self.connected_clients)}")
        self.conn_list.delete(*self.conn_list.get_children())
        for ip, time in self.connected_clients.items():
            self.conn_list.insert('', 'end', values=(ip, time.strftime('%Y-%m-%d %H:%M:%S')))

    def stream_audio(self):
        """流式传输音频数据"""
        speaker = sc.default_speaker()
        with speaker.recorder(samplerate=44100, channels=2, blocksize=1024) as mic:
            while True:
                data = mic.record(numframes=1024)
                data = (data * 32767).astype(np.int16).tobytes()
                if not self.audio_queue.full():
                    self.audio_queue.put(data)
                if not self.audio_queue.empty():
                    yield self.audio_queue.get()

    def serve_audio_page(self):
        """返回音频流页面"""
        return '''
            <h1>音频流已开始</h1>
            <p>请访问 <a href="/audio">音频流</a></p>
        '''

    def run(self):
        """运行Flask服务器和音频捕获线程"""
        threading.Thread(target=self.app.run, kwargs={'host': '0.0.0.0', 'port': 5000, 'threaded': True}).start()
        self.capture_audio()

    def capture_audio(self):
        """捕获音频并放入队列"""
        speaker = sc.default_speaker()
        with speaker.recorder(samplerate=44100, channels=2, blocksize=1024) as mic:
            while True:
                data = mic.record(numframes=1024)
                data = (data * 32767).astype(np.int16).tobytes()
                if not self.audio_queue.full():
                    self.audio_queue.put(data)

    def shutdown(self):
        """关闭服务器"""
        self.root.quit()
        self.status_var.set("状态：服务器已关闭")

if __name__ == "__main__":
    streamer = AudioStreamer()
    streamer.run()
    streamer.root.mainloop()

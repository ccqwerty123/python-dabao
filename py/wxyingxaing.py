import tkinter as tk 
from tkinter import ttk, messagebox
import qrcode
from PIL import Image, ImageTk
import socket
import threading
import numpy as np
import queue
import random
import string
import jwt
from flask import Flask, Response, request
import time
from datetime import datetime, timedelta
import sounddevice as sd
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AudioStreamer:
    def __init__(self):
        """初始化音频流服务器"""
        self.app = Flask(__name__)
        self.audio_queue = queue.Queue(maxsize=50)
        self.connected_clients = {}  # {client_id: connection_time}
        self.password = self._generate_password()
        self.secret_key = self._generate_password(16)  # JWT密钥
        self.max_clients = 1  # 默认最大连接数
        self.virtual_device = None
        self.is_running = True
        
        # 音频质量设置
        self.quality_settings = {
            '低质量': {'samplerate': 22050, 'channels': 1},
            '中等质量': {'samplerate': 44100, 'channels': 2}, 
            '高质量': {'samplerate': 48000, 'channels': 2}
        }
        self.current_quality = '中等质量'

        # 初始化Flask路由和GUI
        self._setup_routes()
        self._setup_gui()
        
        logger.info("音频流服务器初始化完成")

    def _generate_password(self, length=6):
        """生成随机密码"""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

    def _generate_token(self):
        """生成JWT访问令牌"""
        expiration = datetime.now() + timedelta(hours=24)
        token = jwt.encode(
            {'password': self.password, 'exp': expiration},
            self.secret_key,
            algorithm='HS256'
        )
        return token

    def _get_ip(self):
        """获取本机IP地址"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception as e:
            logger.error(f"获取IP地址失败: {e}")
            return 'localhost'

    def _setup_gui(self):
        """设置图形界面"""
        self.root = tk.Tk()
        self.root.title("音频流服务器")
        self.root.geometry("500x850")
        
        # 设置窗口图标
        try:
            self.root.iconbitmap("icon.ico")  # 如果有图标文件的话
        except:
            pass

        # 创建主样式
        self._create_styles()
        
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 创建各个区域
        self._create_quality_frame(main_frame)
        self._create_device_frame(main_frame)
        self._create_user_limit_frame(main_frame)
        self._create_access_frames(main_frame)
        self._create_qr_notebook(main_frame)
        self._create_connection_frame(main_frame)
        self._create_status_bar(main_frame)
        
        # 更新界面显示
        self._update_urls()
        
        logger.info("GUI界面设置完成")

    def _create_styles(self):
        """创建界面样式"""
        style = ttk.Style()
        style.configure('TLabel', font=('Arial', 10))
        style.configure('Header.TLabel', font=('Arial', 12, 'bold'))
        style.configure('Status.TLabel', font=('Arial', 9))
        style.configure('TButton', padding=5)
        
    def _create_quality_frame(self, parent):
        """创建音质设置区域"""
        quality_frame = ttk.LabelFrame(parent, text="音频质量设置", padding="5")
        quality_frame.pack(fill=tk.X, pady=5)
        
        self.quality_var = tk.StringVar(value=self.current_quality)
        for quality in self.quality_settings.keys():
            ttk.Radiobutton(
                quality_frame,
                text=quality,
                variable=self.quality_var,
                value=quality,
                command=self._update_quality
            ).pack(side=tk.LEFT, padx=5)

    def _create_device_frame(self, parent):
        """创建设备控制区域"""
        device_frame = ttk.LabelFrame(parent, text="虚拟设备控制", padding="5")
        device_frame.pack(fill=tk.X, pady=5)
        
        self.device_status_var = tk.StringVar(value="未创建")
        ttk.Label(device_frame, textvariable=self.device_status_var).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            device_frame,
            text="创建虚拟设备",
            command=self._create_virtual_device
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            device_frame,
            text="移除虚拟设备",
            command=self._remove_virtual_device
        ).pack(side=tk.LEFT, padx=5)

    def _create_user_limit_frame(self, parent):
        """创建用户限制设置区域"""
        limit_frame = ttk.LabelFrame(parent, text="用户限制", padding="5")
        limit_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(limit_frame, text="最大连接数：").pack(side=tk.LEFT)
        self.max_clients_var = tk.StringVar(value="1")
        spinbox = ttk.Spinbox(
            limit_frame, 
            from_=1, 
            to=10, 
            width=5,
            textvariable=self.max_clients_var,
            command=self._update_max_clients
        )
        spinbox.pack(side=tk.LEFT, padx=5)

    def _create_access_frames(self, parent):
        """创建访问链接区域"""
        # 加密直接访问框架
        direct_frame = self._create_direct_access_frame(parent)
        direct_frame.pack(fill=tk.X, pady=5)
        
        # 密码访问框架
        pwd_frame = self._create_password_access_frame(parent)
        pwd_frame.pack(fill=tk.X, pady=5)

    def _create_direct_access_frame(self, parent):
        """创建直接访问框架"""
        frame = ttk.LabelFrame(parent, text="加密直接访问", padding="5")
        
        self.direct_url_var = tk.StringVar()
        url_entry = ttk.Entry(frame, textvariable=self.direct_url_var, state='readonly')
        url_entry.pack(fill=tk.X, pady=5)
        
        ttk.Button(
            frame, 
            text="复制链接", 
            command=lambda: self._copy_text(self.direct_url_var.get())
        ).pack()
        
        return frame

     def _create_password_access_frame(self, parent):
        """创建密码访问框架"""
        frame = ttk.LabelFrame(parent, text="密码访问", padding="5")
        
        self.pwd_url_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.pwd_url_var, state='readonly').pack(fill=tk.X, pady=5)
        
        pwd_info_frame = ttk.Frame(frame)
        pwd_info_frame.pack(fill=tk.X)
        
        self.pwd_var = tk.StringVar(value=self.password)
        ttk.Label(pwd_info_frame, text="访问密码：").pack(side=tk.LEFT)
        ttk.Entry(pwd_info_frame, textvariable=self.pwd_var, state='readonly', width=10).pack(side=tk.LEFT)
        
        ttk.Button(
            pwd_info_frame, 
            text="复制密码", 
            command=lambda: self._copy_text(self.pwd_var.get())
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            pwd_info_frame, 
            text="更新密码", 
            command=self._update_password
        ).pack(side=tk.LEFT)
        
        return frame

    def _create_qr_notebook(self, parent):
        """创建二维码标签页"""
        notebook = ttk.Notebook(parent)
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

    def _create_connection_frame(self, parent):
        """创建连接信息区域"""
        frame = ttk.LabelFrame(parent, text="连接信息", padding="5")
        frame.pack(fill=tk.X, pady=5)
        
        # 连接数显示
        self.conn_var = tk.StringVar(value="当前连接数：0")
        ttk.Label(frame, textvariable=self.conn_var).pack()
        
        # 连接列表
        self._create_connection_list(frame)
        
        # 断开按钮
        self._create_disconnect_buttons(frame)

    def _create_connection_list(self, parent):
        """创建连接列表"""
        self.conn_list = ttk.Treeview(
            parent, 
            columns=('ip', 'time', 'quality'), 
            show='headings', 
            height=5
        )
        
        self.conn_list.heading('ip', text='IP地址')
        self.conn_list.heading('time', text='连接时间')
        self.conn_list.heading('quality', text='音频质量')
        
        self.conn_list.column('ip', width=150)
        self.conn_list.column('time', width=150)
        self.conn_list.column('quality', width=100)
        
        self.conn_list.pack(fill=tk.X, pady=5)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.conn_list.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.conn_list.configure(yscrollcommand=scrollbar.set)

    def _create_disconnect_buttons(self, parent):
        """创建断开连接按钮"""
        button_frame = ttk.Frame(parent)
        button_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(
            button_frame, 
            text="断开选中连接", 
            command=self._disconnect_selected
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame, 
            text="断开所有连接", 
            command=self._disconnect_all
        ).pack(side=tk.LEFT)

    def _create_status_bar(self, parent):
        """创建状态栏"""
        status_frame = ttk.Frame(parent)
        status_frame.pack(fill=tk.X, pady=5)
        
        self.status_var = tk.StringVar(value="服务器状态：准备就绪")
        ttk.Label(
            status_frame, 
            textvariable=self.status_var, 
            style='Status.TLabel'
        ).pack(side=tk.LEFT)
        
        ttk.Button(
            status_frame,
            text="关闭服务器",
            command=self._shutdown,
            style='Danger.TButton'
        ).pack(side=tk.RIGHT)

    def _update_quality(self):
        """更新音频质量设置"""
        try:
            self.current_quality = self.quality_var.get()
            if self.virtual_device:
                self._remove_virtual_device()
                self._create_virtual_device()
            self._update_status(f"音质已更新为 {self.current_quality}")
            logger.info(f"音频质量已更新: {self.current_quality}")
        except Exception as e:
            self._show_error("更新音质失败", str(e))

    def _create_virtual_device(self):
        """创建/查找虚拟音频设备"""
        try:
            if self.virtual_device is None:
                devices = sd.query_devices()
                for i, device in enumerate(devices):
                    if 'CABLE' in device['name']:
                        self.virtual_device = {
                            'device_id': i,
                            'name': device['name'],
                            'quality': self.current_quality
                        }
                        self.device_status_var.set(f"已连接: {device['name']}")
                        self._update_status("虚拟音频设备已连接")
                        logger.info(f"已连接虚拟设备: {device['name']}")
                        return
                    
                self._show_warning(
                    "未找到虚拟设备",
                    "请安装VB-CABLE或其他虚拟音频设备"
                )
        except Exception as e:
            self._show_error("创建虚拟设备失败", str(e))

    def _remove_virtual_device(self):
        """移除虚拟音频设备"""
        try:
            if self.virtual_device:
                self.virtual_device = None
                self.device_status_var.set("未创建")
                self._update_status("虚拟音频设备已移除")
                logger.info("虚拟设备已移除")
        except Exception as e:
            self._show_error("移除虚拟设备失败", str(e))

    def _update_password(self):
        """更新访问密码"""
        if messagebox.askyesno("确认", "更新密码将断开所有当前连接，是否继续？"):
            try:
                self.password = self._generate_password()
                self.pwd_var.set(self.password)
                self._disconnect_all()
                self._update_urls()
                self._update_status("密码已更新，所有连接已断开")
                logger.info("访问密码已更新")
            except Exception as e:
                self._show_error("更新密码失败", str(e))

     def _setup_routes(self):
        """设置Flask路由"""
        @self.app.route('/direct/<token>')
        def direct_access(token):
            try:
                data = jwt.decode(token, self.secret_key, algorithms=['HS256'])
                if data['password'] != self.password:
                    return '链接已过期', 403
                return self._serve_audio_page()
            except Exception as e:
                logger.error(f"直接访问验证失败: {e}")
                return '无效的访问链接', 403

        @self.app.route('/login')
        def login_page():
            return self._serve_login_page()

        @self.app.route('/verify', methods=['POST'])
        def verify():
            if request.form.get('password') == self.password:
                return self._serve_audio_page()
            return '密码错误', 403

        @self.app.route('/audio')
        def audio():
            client_id = request.remote_addr
            
            # 检查连接数限制
            if len(self.connected_clients) >= self.max_clients and client_id not in self.connected_clients:
                logger.warning(f"连接被拒绝(达到上限): {client_id}")
                return '连接数已达到上限', 403

            # 更新或添加客户端
            self.connected_clients[client_id] = {
                'time': datetime.now(),
                'quality': self.current_quality
            }
            self._update_client_list()
            logger.info(f"新客户端连接: {client_id}")

            def generate():
                try:
                    while True:
                        if client_id not in self.connected_clients:
                            logger.info(f"客户端断开连接: {client_id}")
                            break
                        if not self.audio_queue.empty():
                            yield self.audio_queue.get()
                finally:
                    if client_id in self.connected_clients:
                        del self.connected_clients[client_id]
                        self._update_client_list()

            return Response(generate(), mimetype='audio/x-wav')

    def _serve_login_page(self):
        """返回登录页面"""
        return '''
        <!DOCTYPE html>
        <html>
            <head>
                <title>音频流服务器 - 登录</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    * {
                        margin: 0;
                        padding: 0;
                        box-sizing: border-box;
                    }
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial;
                        background: #f5f5f5;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        min-height: 100vh;
                        padding: 20px;
                    }
                    .login-container {
                        background: white;
                        padding: 30px;
                        border-radius: 10px;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                        width: 100%;
                        max-width: 400px;
                    }
                    h1 {
                        text-align: center;
                        color: #2196F3;
                        margin-bottom: 30px;
                        font-size: 24px;
                    }
                    .form-group {
                        margin-bottom: 20px;
                    }
                    input[type="password"] {
                        width: 100%;
                        padding: 12px;
                        border: 1px solid #ddd;
                        border-radius: 5px;
                        font-size: 16px;
                        transition: border-color 0.3s;
                    }
                    input[type="password"]:focus {
                        border-color: #2196F3;
                        outline: none;
                    }
                    button {
                        width: 100%;
                        padding: 12px;
                        background: #2196F3;
                        color: white;
                        border: none;
                        border-radius: 5px;
                        font-size: 16px;
                        cursor: pointer;
                        transition: background 0.3s;
                    }
                    button:hover {
                        background: #1976D2;
                    }
                </style>
            </head>
            <body>
                <div class="login-container">
                    <h1>音频流服务器</h1>
                    <form action="/verify" method="post">
                        <div class="form-group">
                            <input type="password" name="password" placeholder="请输入访问密码" required>
                        </div>
                        <button type="submit">登录</button>
                    </form>
                </div>
            </body>
        </html>
        '''

    def _serve_audio_page(self):
        """返回音频播放页面"""
        return '''
        <!DOCTYPE html>
        <html>
            <head>
                <title>音频流播放器</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    * {
                        margin: 0;
                        padding: 0;
                        box-sizing: border-box;
                    }
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial;
                        background: #f5f5f5;
                        min-height: 100vh;
                        padding: 20px;
                    }
                    .container {
                        max-width: 600px;
                        margin: 0 auto;
                        background: white;
                        padding: 30px;
                        border-radius: 10px;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    }
                    h1 {
                        font-size: 24px;
                        text-align: center;
                        margin-bottom: 30px;
                        color: #2196F3;
                    }
                    .player {
                        width: 100%;
                        margin: 20px 0;
                        background: #f8f9fa;
                        padding: 20px;
                        border-radius: 8px;
                    }
                    audio {
                        width: 100%;
                        margin: 10px 0;
                    }
                    .status {
                        text-align: center;
                        color: #666;
                        margin-top: 20px;
                        font-size: 14px;
                    }
                    .quality-info {
                        text-align: center;
                        color: #666;
                        margin-top: 10px;
                        font-size: 14px;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>音频流播放器</h1>
                    <div class="player">
                        <audio controls autoplay>
                            <source src="/audio" type="audio/wav">
                            您的浏览器不支持音频播放
                        </audio>
                        <div class="quality-info">
                            当前音质：''' + self.current_quality + '''
                        </div>
                    </div>
                    <div class="status" id="status">
                        正在播放...
                    </div>
                </div>
                <script>
                    const audio = document.querySelector('audio');
                    const status = document.getElementById('status');
                    
                    audio.addEventListener('playing', () => {
                        status.textContent = '正在播放...';
                    });
                    
                    audio.addEventListener('pause', () => {
                        status.textContent = '已暂停';
                    });
                    
                    audio.addEventListener('error', () => {
                        status.textContent = '播放出错，请刷新页面重试';
                    });
                </script>
            </body>
        </html>
        '''

   def _capture_audio(self):
        """音频捕获线程"""
        logger.info("开始音频捕获")
        while self.is_running:
            try:
                if self.virtual_device:
                    quality = self.quality_settings[self.current_quality]
                    with sd.InputStream(
                        device=self.virtual_device['device_id'],
                        samplerate=quality['samplerate'],
                        channels=quality['channels'],
                        blocksize=1024,
                        dtype=np.float32
                    ) as stream:
                        while self.is_running and self.virtual_device:
                            try:
                                data, _ = stream.read(1024)
                                # 转换音频格式
                                data = (data * 32767).astype(np.int16).tobytes()
                                
                                # 如果队列将满，移除旧数据
                                while self.audio_queue.qsize() >= 45:  # 留一些缓冲空间
                                    try:
                                        self.audio_queue.get_nowait()
                                    except queue.Empty:
                                        break
                                
                                self.audio_queue.put(data)
                            except Exception as e:
                                logger.error(f"音频读取错误: {e}")
                                break
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"音频捕获错误: {e}")
                self._update_status(f"音频捕获错误: {str(e)}")
                time.sleep(1)

    def _update_urls(self):
        """更新访问链接和二维码"""
        try:
            base_url = f"http://{self._get_ip()}:5000"
            
            # 更新直接访问链接
            token = self._generate_token()
            direct_url = f"{base_url}/direct/{token}"
            self.direct_url_var.set(direct_url)
            
            # 更新密码访问链接
            pwd_url = f"{base_url}/login"
            self.pwd_url_var.set(pwd_url)
            
            # 更新两个二维码
            self._update_qr_code(direct_url, self.direct_qr_label)
            self._update_qr_code(pwd_url, self.pwd_qr_label)
            
            logger.info("访问链接已更新")
        except Exception as e:
            self._show_error("更新链接失败", str(e))

    def _update_qr_code(self, data, label):
        """更新指定的二维码"""
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4
            )
            qr.add_data(data)
            qr.make(fit=True)
            
            qr_image = qr.make_image(fill_color="black", back_color="white")
            qr_image = qr_image.resize((200, 200), Image.LANCZOS)
            photo = ImageTk.PhotoImage(qr_image)
            
            label.configure(image=photo)
            label.image = photo  # 保持引用
        except Exception as e:
            logger.error(f"生成二维码失败: {e}")

    def _update_client_list(self):
        """更新客户端列表显示"""
        try:
            # 清空现有列表
            for item in self.conn_list.get_children():
                self.conn_list.delete(item)
            
            # 添加当前连接
            for client_ip, info in self.connected_clients.items():
                time_str = info['time'].strftime('%H:%M:%S')
                self.conn_list.insert('', 'end', values=(
                    client_ip, 
                    time_str,
                    info['quality']
                ))
            
            # 更新连接计数
            self._update_connected_count()
        except Exception as e:
            logger.error(f"更新客户端列表失败: {e}")

    def _update_connected_count(self):
        """更新连接数显示"""
        self.conn_var.set(f"当前连接数：{len(self.connected_clients)}/{self.max_clients}")

    def _update_status(self, message):
        """更新状态栏消息"""
        self.status_var.set(f"状态：{message}")

    def _show_error(self, title, message):
        """显示错误消息"""
        logger.error(f"{title}: {message}")
        messagebox.showerror(title, message)

    def _show_warning(self, title, message):
        """显示警告消息"""
        logger.warning(f"{title}: {message}")
        messagebox.showwarning(title, message)

    def _copy_text(self, text):
        """复制文本到剪贴板"""
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._update_status("已复制到剪贴板")

    def _shutdown(self):
        """关闭服务器"""
        if messagebox.askyesno("确认", "确定要关闭服务器吗？"):
            try:
                logger.info("正在关闭服务器...")
                self.is_running = False
                self._remove_virtual_device()
                self._disconnect_all()
                self.root.quit()
            except Exception as e:
                logger.error(f"关闭服务器时出错: {e}")

    def run(self):
        """运行服务器"""
        try:
            # 启动音频捕获线程
            audio_thread = threading.Thread(
                target=self._capture_audio, 
                daemon=True
            )
            audio_thread.start()

            # 启动Flask服务器线程
            server_thread = threading.Thread(
                target=lambda: self.app.run(
                    host='0.0.0.0',
                    port=5000,
                    threaded=True
                ),
                daemon=True
            )
            server_thread.start()

            # 运行GUI主循环
            self.root.mainloop()
            
        except Exception as e:
            logger.error(f"服务器运行错误: {e}")
            self._show_error("运行错误", str(e))
        finally:
            self.is_running = False
            logger.info("服务器已关闭")

if __name__ == "__main__":
    try:
        streamer = AudioStreamer()
        streamer.run()
    except Exception as e:
        logger.critical(f"程序启动失败: {e}")
        messagebox.showerror("启动失败", str(e))  

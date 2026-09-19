import sys
import os
import subprocess
import time
import re
import requests
import struct
import json
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QComboBox, QPushButton, QTextEdit,
                             QGroupBox, QSpinBox, QFormLayout, QMessageBox, QFileDialog,
                             QTabWidget, QCheckBox, QDoubleSpinBox, QInputDialog, QSplitter, QDialog, QSizePolicy, QScrollArea, QToolTip)
from PyQt5.QtCore import QProcess, Qt, QSettings, QTimer, QProcessEnvironment, QEvent, QPoint
from PyQt5.QtGui import QFont, QColor, QTextCharFormat, QDesktopServices

GGUF_MAGIC = 0x46554747

def check_gguf_has_vision(gguf_path):
    """
    检测 GGUF 文件是否支持视觉功能
    返回: (has_vision: bool, vision_info: str)
    
    注意：检测到 clip.vision 或 clip.has_ 元数据只表示模型"支持视觉"，
    不代表视觉编码器已内置。绝大多数视觉模型需要额外的 mmproj 文件。
    """
    try:
        with open(gguf_path, 'rb') as f:
            magic = struct.unpack('<I', f.read(4))[0]
            if magic != GGUF_MAGIC:
                return False, ""
            
            version = struct.unpack('<I', f.read(4))[0]
            tensor_count = struct.unpack('<Q', f.read(8))[0]
            kv_count = struct.unpack('<Q', f.read(8))[0]
            
            vision_keys_found = []
            has_vision_tensors = False
            
            for _ in range(kv_count):
                key_len = struct.unpack('<Q', f.read(8))[0]
                key = f.read(key_len).decode('utf-8', errors='ignore')
                value_type = struct.unpack('<I', f.read(4))[0]
                
                if 'clip.vision' in key or 'clip.has_' in key:
                    vision_keys_found.append(key)
                
                if value_type == 0:
                    f.read(4)
                elif value_type == 1:
                    f.read(8)
                elif value_type == 2:
                    f.read(4)
                elif value_type == 3:
                    str_len = struct.unpack('<Q', f.read(8))[0]
                    f.read(str_len)
                elif value_type == 4:
                    arr_type = struct.unpack('<I', f.read(4))[0]
                    arr_len = struct.unpack('<Q', f.read(8))[0]
                    if arr_type == 0:
                        f.read(4 * arr_len)
                    elif arr_type == 1:
                        f.read(8 * arr_len)
                    elif arr_type == 2:
                        f.read(4 * arr_len)
                    elif arr_type == 3:
                        for _ in range(arr_len):
                            s_len = struct.unpack('<Q', f.read(8))[0]
                            f.read(s_len)
                elif value_type == 5:
                    f.read(4)
                elif value_type == 6:
                    f.read(8)
                elif value_type == 7:
                    f.read(8)
                elif value_type == 8:
                    f.read(1)
            
            if vision_keys_found:
                if tensor_count > 100 and any('clip.vision' in k for k in vision_keys_found):
                    has_vision_tensors = True
                
                if has_vision_tensors:
                    return True, "内置视觉"
                else:
                    return True, "支持视觉"
            
            return False, ""
            
    except Exception as e:
        return False, ""

def disable_wheel_event(widget):
    widget.wheelEvent = lambda event: None
    return widget

class CollapsibleGroupBox(QGroupBox):
    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.content_widget = None
        self.is_collapsed = False
        self.installEventFilter(self)
        self.collapsed_height = 38
        
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 9pt;
                border: 1px solid #3498db;
                border-radius: 4px;
                margin-top: 20px;
                padding-top: 16px;
                padding-left: 6px;
                padding-right: 6px;
                padding-bottom: 6px;
                background-color: #fafcff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 8px;
                top: 6px;
                padding: 3px 10px;
                color: #1a5276;
                background-color: #ffffff;
                border: 1px solid #3498db;
                border-radius: 3px;
            }
            QGroupBox:hover {
                border-color: #2980b9;
                background-color: #f0f7ff;
            }
            QGroupBox:hover::title {
                background-color: #e8f4fc;
                border-color: #2980b9;
            }
        """)
        self.setCursor(Qt.PointingHandCursor)
    
    def setContentWidget(self, widget):
        self.content_widget = widget
    
    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress and obj == self:
            if event.pos().y() < 40:
                self.toggleCollapse()
                return True
        return super().eventFilter(obj, event)
    
    def toggleCollapse(self):
        if self.content_widget:
            self.is_collapsed = not self.is_collapsed
            self.content_widget.setVisible(not self.is_collapsed)
            
            current_title = self.title().lstrip("▶ ").lstrip("▼ ")
            if self.is_collapsed:
                self.setFixedHeight(self.collapsed_height)
                self.setTitle("▶ " + current_title)
            else:
                self.setMinimumHeight(0)
                self.setMaximumHeight(16777215)
                self.setTitle("▼ " + current_title)
            
            self.updateGeometry()

class DialogGroupBox(QGroupBox):
    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.content_widget = None
        self.dialog_title = title
        self.setFixedHeight(38)
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 9pt;
                border: 1px solid #3498db;
                border-radius: 4px;
                margin-top: 20px;
                padding-top: 16px;
                padding-left: 6px;
                padding-right: 6px;
                padding-bottom: 6px;
                background-color: #fafcff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 8px;
                top: 6px;
                padding: 3px 10px;
                color: #1a5276;
                background-color: #ffffff;
                border: 1px solid #3498db;
                border-radius: 3px;
            }
            QGroupBox:hover {
                border-color: #2980b9;
                background-color: #f0f7ff;
            }
            QGroupBox:hover::title {
                background-color: #e8f4fc;
                border-color: #2980b9;
            }
        """)
        self.setCursor(Qt.PointingHandCursor)
        self.installEventFilter(self)
    
    def setContentWidget(self, widget):
        self.content_widget = widget
        self.content_widget.setVisible(False)
    
    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress and obj == self:
            self.openDialog()
            return True
        return super().eventFilter(obj, event)
    
    def openDialog(self):
        if not self.content_widget:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(self.dialog_title)
        dialog.setMinimumSize(620, 500)
        layout = QVBoxLayout(dialog)
        self.content_widget.setVisible(True)
        self.content_widget.setParent(None)
        layout.addWidget(self.content_widget)
        close_btn = QPushButton("关闭")
        close_btn.setMinimumHeight(36)
        close_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; border: none; border-radius: 5px;")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        dialog.exec_()
        self.content_widget.setParent(None)
        self.content_widget.setVisible(False)

class PresetSaveDialog(QDialog):
    def __init__(self, existing_presets, parent=None):
        super().__init__(parent)
        self.setWindowTitle("保存预设")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        
        label = QLabel("选择已有预设进行覆盖，或输入新预设名称：")
        layout.addWidget(label)
        
        self.combo = QComboBox()
        self.combo.wheelEvent = lambda event: None
        self.combo.setEditable(True)
        for preset in existing_presets:
            self.combo.addItem(preset)
        layout.addWidget(self.combo)
        
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
    
    def get_preset_name(self):
        return self.combo.currentText().strip()

class LlamaServerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.llama_process = None
        self.turboquant_process = None
        self.webui_process = None
        self.rpc_server_process = None
        self.settings = QSettings("LlamaServer", "GUI")
        self.request_count = 0
        self.start_time = None
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.current_input_tokens = 0
        self.current_output_tokens = 0
        self.input_speed = 0
        self.output_speed = 0
        self.stderr_buffer = ""
        self.model_vision_info = {}
        self.init_ui()
        self.load_settings()
        self.load_presets()
        self.scan_mmproj()
        self.scan_models()
        
        self.restore_window_state()
        
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.monitor_system_status)
        self.status_timer.start(30000)

    def init_ui(self):
        self.setWindowTitle("Llama Server & Open WebUI 服务管理器")
        self.setGeometry(100, 100, 520, 420)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        self.tab_widget = QTabWidget()
        self.tab_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        self.llama_tab = self.create_llama_tab()
        self.webui_tab = self.create_webui_tab()
        self.distributed_tab = self.create_distributed_tab()
        self.log_tab = self.create_log_tab()
        self.status_tab = self.create_status_tab()
        self.turboquant_tab = self.create_turboquant_tab()
        
        self.tab_widget.addTab(self.llama_tab, "Llama Server")
        self.tab_widget.addTab(self.turboquant_tab, "社区加速版 (TurboQuant-MTP)")
        self.tab_widget.addTab(self.webui_tab, "Open WebUI")
        self.tab_widget.addTab(self.distributed_tab, "分布式推理")
        self.tab_widget.addTab(self.log_tab, "日志输出")
        self.tab_widget.addTab(self.status_tab, "状态监控")
        
        main_layout.addWidget(self.tab_widget)
        
        self.models_dir = r"D:\models"
    
    def create_log_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        
        self.clear_log_btn = QPushButton("清空日志")
        self.clear_log_btn.clicked.connect(self.clear_log)
        
        layout.addWidget(self.log_text)
        layout.addWidget(self.clear_log_btn)
        
        return tab

    def create_status_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)
        
        token_group = QGroupBox("Token 统计")
        token_layout = QVBoxLayout(token_group)
        token_layout.setSpacing(10)
        
        self.token_stats_display = QLabel()
        self.token_stats_display.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            padding: 10px;
        """)
        self.token_stats_display.setTextFormat(Qt.RichText)
        token_layout.addWidget(self.token_stats_display)
        
        layout.addWidget(token_group)
        
        server_group = QGroupBox("服务状态")
        server_layout = QFormLayout(server_group)
        server_layout.setSpacing(8)
        
        self.status_server_label = QLabel("未运行")
        self.status_server_label.setStyleSheet("font-size: 14px;")
        server_layout.addRow("Llama Server:", self.status_server_label)
        
        self.status_model_label = QLabel("未加载")
        self.status_model_label.setStyleSheet("font-size: 14px;")
        server_layout.addRow("当前模型:", self.status_model_label)
        
        self.status_api_label = QLabel("http://127.0.0.1:8081")
        self.status_api_label.setStyleSheet("font-size: 14px; color: blue;")
        server_layout.addRow("API地址:", self.status_api_label)
        
        self.status_webui_label = QLabel("未运行")
        self.status_webui_label.setStyleSheet("font-size: 14px;")
        server_layout.addRow("Open WebUI:", self.status_webui_label)
        
        layout.addWidget(server_group)
        
        system_group = QGroupBox("系统资源")
        system_layout = QFormLayout(system_group)
        system_layout.setSpacing(8)
        
        self.status_memory_label = QLabel("--")
        self.status_memory_label.setStyleSheet("font-size: 14px;")
        system_layout.addRow("内存:", self.status_memory_label)
        
        self.status_cpu_label = QLabel("--")
        self.status_cpu_label.setStyleSheet("font-size: 14px;")
        system_layout.addRow("CPU:", self.status_cpu_label)
        
        self.status_gpu_label = QLabel("--")
        self.status_gpu_label.setStyleSheet("font-size: 14px;")
        system_layout.addRow("GPU:", self.status_gpu_label)
        
        layout.addWidget(system_group)
        
        layout.addStretch()
        
        return tab

    def create_llama_tab(self):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        model_group = CollapsibleGroupBox("模型选择")
        model_outer_layout = QVBoxLayout(model_group)
        model_outer_layout.setSpacing(2)
        model_outer_layout.setContentsMargins(4, 4, 4, 4)
        model_content = QWidget()
        model_layout = QFormLayout(model_content)
        model_layout.setSpacing(4)
        model_layout.setContentsMargins(2, 2, 2, 2)
        model_group.setContentWidget(model_content)
        
        # 启动/停止按钮放在模型选择上方
        control_btn_layout = QHBoxLayout()
        control_btn_layout.setSpacing(8)
        
        self.start_llama_btn = QPushButton("▶ 启动")
        self.start_llama_btn.setFixedHeight(28)
        self.start_llama_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50; 
                color: white; 
                font-weight: bold; 
                border: none; 
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.start_llama_btn.clicked.connect(self.start_llama_server)
        
        self.stop_llama_btn = QPushButton("⏹ 停止")
        self.stop_llama_btn.setFixedHeight(28)
        self.stop_llama_btn.setStyleSheet("""
            QPushButton {
                background-color: #cccccc; 
                color: #666666; 
                font-weight: bold; 
                border: none; 
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #d32f2f;
                color: white;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.stop_llama_btn.clicked.connect(self.stop_llama_server)
        self.stop_llama_btn.setEnabled(False)
        
        # 状态指示器
        self.service_status_label = QLabel("● 已停止")
        self.service_status_label.setStyleSheet("color: #999999; font-size: 11px; font-weight: bold;")
        
        control_btn_layout.addStretch()
        control_btn_layout.addWidget(self.start_llama_btn)
        control_btn_layout.addWidget(self.stop_llama_btn)
        control_btn_layout.addWidget(self.service_status_label)
        control_btn_layout.addStretch()
        model_layout.addRow(control_btn_layout)
        
        self.model_combo = QComboBox()
        self.model_combo.wheelEvent = lambda event: None
        self.model_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.model_combo.currentIndexChanged.connect(self.auto_select_mmproj)
        self.model_combo.currentIndexChanged.connect(self.update_vision_status)
        
        self.refresh_btn = QPushButton("刷新模型列表")
        self.refresh_btn.clicked.connect(self.scan_models)

        self.browse_model_btn = QPushButton("📂 浏览模型路径")
        self.browse_model_btn.setToolTip("选择存放 .gguf 模型文件的文件夹\n选择后会立即扫描该目录下的所有模型")
        self.browse_model_btn.clicked.connect(self.browse_model_dir)

        # 模型操作按钮行：刷新 + 浏览 水平排列
        model_btn_layout = QHBoxLayout()
        model_btn_layout.addWidget(self.refresh_btn)
        model_btn_layout.addWidget(self.browse_model_btn)
        model_btn_layout.addStretch()

        # 当前模型目录 + 历史路径下拉（可点选切换）
        self.model_dir_combo = QComboBox()
        self.model_dir_combo.setToolTip("点击下拉可看到浏览过的历史模型路径，选择即切换")
        self.model_dir_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.model_dir_combo.currentIndexChanged.connect(self.on_model_dir_selected)
        # 关闭滚轮误触
        self.model_dir_combo.wheelEvent = lambda event: None

        self.clear_history_btn = QPushButton("❌ 清除历史")
        self.clear_history_btn.setToolTip("清空所有浏览过的历史模型路径")
        self.clear_history_btn.clicked.connect(self.clear_model_dir_history)

        model_dir_layout = QHBoxLayout()
        model_dir_layout.setSpacing(4)
        model_dir_layout.addWidget(self.model_dir_combo, 1)
        model_dir_layout.addWidget(self.clear_history_btn)

        self.enable_vision_check = QCheckBox("启用图片识别 (加载额外 mmproj)")
        self.enable_vision_check.setChecked(True)
        self.enable_vision_check.setToolTip(
            "【重要提示】\n"
            "• 如果模型名称前有 📷 图标，表示该模型已内置视觉编码器\n"
            "• 内置视觉的模型不需要加载额外的 mmproj 文件\n"
            "• 勾选此项会加载额外的 mmproj，可能导致显存重复占用\n"
            "• 对于纯文本模型，需要勾选此项并确保有对应的 mmproj 文件"
        )

        self.vision_status_label = QLabel("")
        self.vision_status_label.setStyleSheet("color: gray; font-size: 11px;")

        self.open_model_folder_btn = QPushButton("📂 打开模型所在文件夹")
        self.open_model_folder_btn.setToolTip("打开当前选中的模型文件所在的文件夹")
        self.open_model_folder_btn.clicked.connect(self.open_model_folder)

        model_layout.addRow("选择模型:", self.model_combo)
        model_layout.addRow("", model_btn_layout)
        model_layout.addRow("当前模型目录:", model_dir_layout)
        model_layout.addRow("", self.enable_vision_check)
        model_layout.addRow("", self.vision_status_label)
        model_layout.addRow("", self.open_model_folder_btn)
        
        # MTP 加速配置
        self.enable_mtp_check = QCheckBox("启用 MTP 加速 (Multi-Token Prediction)")
        self.enable_mtp_check.setChecked(False)
        self.enable_mtp_check.setToolTip(
            "MTP (Multi-Token Prediction) 是 Qwen3 模型的原生推测解码技术\n"
            "• 每次预测多个 token，可显著提升生成速度\n"
            "• 需要 MTP 版 llama-server (llama-cpp-turboquant-mtp)\n"
            "• 需要模型本身支持 MTP（如 Qwen3.6-27B-MTP）\n"
            "• 开启后生成速度可提升 30-50%"
        )
        
        mtp_draft_layout = QHBoxLayout()
        mtp_draft_layout.setSpacing(4)
        self.mtp_draft_label = QLabel("草稿数:")
        self.mtp_draft_label.setStyleSheet("color: #555; font-size: 10pt;")
        self.mtp_draft_spin = QSpinBox()
        self.mtp_draft_spin.setRange(1, 16)
        self.mtp_draft_spin.setValue(3)
        self.mtp_draft_spin.setFixedWidth(60)
        self.mtp_draft_spin.setToolTip("每次预测的草稿 token 数量，越大提速越明显但显存占用也越高")
        mtp_draft_layout.addWidget(self.mtp_draft_label)
        mtp_draft_layout.addWidget(self.mtp_draft_spin)
        mtp_draft_layout.addStretch()
        
        model_layout.addRow("", self.enable_mtp_check)
        model_layout.addRow("", mtp_draft_layout)
        
        model_outer_layout.addWidget(model_content)
        
        # ===== 功能按钮行 =====
        func_btn_layout = QHBoxLayout()
        func_btn_layout.setSpacing(4)
        
        btn_style = """
            QPushButton {
                background-color: #3498db;
                color: white;
                font-weight: bold;
                font-size: 8pt;
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
                min-width: 60px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #1a5276;
            }
        """
        
        self.param_btn = QPushButton("⚙ 参数配置")
        self.param_btn.setStyleSheet(btn_style)
        self.param_btn.clicked.connect(self.open_param_dialog)
        
        self.preset_btn = QPushButton("💾 参数预设")
        self.preset_btn.setStyleSheet(btn_style)
        self.preset_btn.clicked.connect(self.open_preset_dialog)
        
        self.optimize_btn = QPushButton("🚀 自动优化")
        self.optimize_btn.setStyleSheet(btn_style)
        self.optimize_btn.clicked.connect(self.open_optimize_dialog)
        
        self.status_btn = QPushButton("📊 状态信息")
        self.status_btn.setStyleSheet(btn_style)
        self.status_btn.clicked.connect(self.open_status_dialog)
        
        func_btn_layout.addWidget(self.param_btn)
        func_btn_layout.addWidget(self.preset_btn)
        func_btn_layout.addWidget(self.optimize_btn)
        func_btn_layout.addWidget(self.status_btn)
        func_btn_layout.addStretch()
        
        model_outer_layout.addLayout(func_btn_layout)
        model_outer_layout.addStretch()
        
        # ===== 参数配置内容（不直接显示，弹窗用） =====
        param_content = QWidget()
        param_layout = QVBoxLayout(param_content)
        
        # 创建选项卡来分组参数
        param_tabs = QTabWidget()
        
        # ---- 基础参数选项卡 ----
        basic_tab = QWidget()
        basic_layout = QFormLayout()
        
        self.context_spin = QSpinBox()
        self.context_spin.wheelEvent = lambda event: None
        self.context_spin.setRange(512, 1048576)
        self.context_spin.setValue(8192)
        self.context_spin.setSingleStep(512)
        self.context_spin.setToolTip(
            "上下文窗口大小（Context Window）\n"
            "决定模型单次能处理的最大词元数\n\n"
            "调整范围：512 - 32768\n"
            "推荐值：8192（平衡性能和质量）\n\n"
            "影响：\n"
            "• 越大：对话越连贯，记忆越强\n"
            "• 越小：显存占用越低，速度越快\n\n"
            "使用场景：\n"
            "• 简单对话：4096\n"
            "• 长对话：8192-16384\n"
            "• 代码分析：8192-16384"
        )
        
        self.batch_spin = QSpinBox()
        self.batch_spin.wheelEvent = lambda event: None
        self.batch_spin.setRange(1, 65536)
        self.batch_spin.setValue(32)
        self.batch_spin.setToolTip(
            "批处理大小（Batch Size）\n"
            "一次处理的请求数量\n\n"
            "调整范围：1 - 4096\n"
            "推荐值：32（9B模型）\n\n"
            "影响：\n"
            "• 越大：吞吐量越高，显存占用越大\n"
            "• 越小：显存占用越低，响应越快\n\n"
            "使用场景：\n"
            "• 9B模型：32\n"
            "• 0.8B模型：64\n"
            "• 70B模型：16"
        )
        
        self.ubatch_spin = QSpinBox()
        self.ubatch_spin.wheelEvent = lambda event: None
        self.ubatch_spin.setRange(1, 65536)
        self.ubatch_spin.setValue(512)
        self.ubatch_spin.setToolTip(
            "物理批处理大小（Physical Batch）\n"
            "GPU实际处理的批次大小\n\n"
            "调整范围：1 - 2048\n"
            "推荐值：512（保持默认）\n\n"
            "影响：\n"
            "• 越大：GPU利用率越高\n"
            "• 越小：显存占用越低\n\n"
            "建议：通常保持默认值"
        )
        
        self.parallel_spin = QSpinBox()
        self.parallel_spin.wheelEvent = lambda event: None
        self.parallel_spin.setRange(1, 16)
        self.parallel_spin.setValue(1)
        self.parallel_spin.setToolTip(
            "并行序列数 (-np)\n"
            "同时处理的序列数\n\n"
            "调整范围：1 - 16\n"
            "推荐值：1（标准模式）\n\n"
            "影响：\n"
            "• 1：标准模式，一次处理一个序列\n"
            "• >1：多个序列并行生成，配合推测解码使用\n"
            "  用于 MTP 时通常保持为 1\n\n"
            "注意：增加此值会线性增加显存占用"
        )
        
        self.threads_spin = QSpinBox()
        self.threads_spin.wheelEvent = lambda event: None
        self.threads_spin.setRange(1, 32)
        self.threads_spin.setValue(6)
        self.threads_spin.setToolTip(
            "CPU线程数（Threads）\n"
            "用于模型推理的CPU线程数量\n\n"
            "调整范围：1 - 32\n"
            "推荐值：6（根据CPU核心数调整）\n\n"
            "影响：\n"
            "• 越多：CPU利用率越高\n"
            "• 越少：CPU占用越低\n\n"
            "建议：\n"
            "• 4核CPU：4\n"
            "• 8核CPU：6-8\n"
            "• 16核CPU：12-16"
        )
        
        self.port_spin = QSpinBox()
        self.port_spin.wheelEvent = lambda event: None
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(8081)
        
        # 局域网访问设置
        self.lan_access_check = QCheckBox("开放局域网访问")
        self.lan_access_check.setChecked(False)
        self.lan_access_check.setToolTip("勾选后允许局域网内其他设备访问API")
        self.lan_access_check.stateChanged.connect(self.on_lan_access_changed)
        
        self.host_edit = QLineEdit("127.0.0.1")
        self.host_edit.setReadOnly(True)
        self.host_edit.setToolTip("监听地址，127.0.0.1=仅本机，0.0.0.0=所有网络接口")
        
        # 显示本机局域网IP
        self.lan_ip_label = QLabel("本机局域网IP: 未开启")
        self.lan_ip_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        self.lan_ip_label.setVisible(False)
        
        self.apikey_combo = QComboBox()
        self.apikey_combo.wheelEvent = lambda event: None
        self.apikey_combo.setEditable(True)
        self.apikey_combo.addItem("(不使用API密钥)")
        self.apikey_combo.setToolTip("API密钥，可选择历史密钥或输入新密钥")
        
        self.ngl_spin = QSpinBox()
        self.ngl_spin.wheelEvent = lambda event: None
        self.ngl_spin.setRange(0, 999)
        self.ngl_spin.setValue(999)
        self.ngl_spin.setToolTip(
            "GPU层数（NGL - Number of GPU Layers）\n"
            "卸载到GPU的模型层数\n\n"
            "调整范围：0 - 999\n"
            "推荐值：999（全部卸载）\n\n"
            "影响：\n"
            "• 999：全部层在GPU，速度最快\n"
            "• 0：全部层在CPU，速度最慢\n"
            "• 部分值：部分GPU，部分CPU\n\n"
            "建议：\n"
            "• 显存充足：999\n"
            "• 显存不足：降低到显存允许的最大值"
        )
        
        self.cache_type_combo = QComboBox()
        self.cache_type_combo.wheelEvent = lambda event: None
        self.cache_type_combo.addItems(["auto", "f32", "f16", "bf16", "q8_0", "q3_0", "q4_0", "q4_1", "iq4_nl", "q5_0", "q5_1"])
        self.cache_type_combo.setCurrentText("auto")
        self.cache_type_combo.setToolTip("K缓存类型，影响显存占用和速度\n\n推荐：\n• q8_0: 高质量，显存略高\n• q4_0: 平衡质量和显存\n• iq4_nl: 高质量量化\n\n注意：KV Rotation（谷歌压缩技术）已自动启用，无需额外设置")
        
        basic_layout.addRow("上下文大小 (-c):", self.context_spin)
        basic_layout.addRow("批处理大小 (-b):", self.batch_spin)
        basic_layout.addRow("物理批处理 (-ub):", self.ubatch_spin)
        basic_layout.addRow("并行序列数 (-np):", self.parallel_spin)
        basic_layout.addRow("CPU线程数 (-t):", self.threads_spin)
        basic_layout.addRow("端口 (--port):", self.port_spin)
        basic_layout.addRow("局域网访问:", self.lan_access_check)
        basic_layout.addRow("监听地址 (--host):", self.host_edit)
        basic_layout.addRow("", self.lan_ip_label)
        basic_layout.addRow("API密钥 (--api-key):", self.apikey_combo)
        basic_layout.addRow("GPU层数 (-ngl):", self.ngl_spin)
        basic_layout.addRow("K缓存类型 (-ctk):", self.cache_type_combo)
        
        self.cache_type_v_combo = QComboBox()
        self.cache_type_v_combo.wheelEvent = lambda event: None
        self.cache_type_v_combo.addItems(["auto", "f32", "f16", "bf16", "q8_0", "q3_0", "q4_0", "q4_1", "iq4_nl", "q5_0", "q5_1"])
        self.cache_type_v_combo.setCurrentText("auto")
        self.cache_type_v_combo.setToolTip("V缓存类型，影响显存占用和速度\n\n推荐：\n• q8_0: 高质量，显存略高\n• q4_0: 平衡质量和显存\n• iq4_nl: 高质量量化")
        basic_layout.addRow("V缓存类型 (-ctv):", self.cache_type_v_combo)
        
        basic_tab.setLayout(basic_layout)
        
        # ---- 采样参数选项卡 ----
        sampling_tab = QWidget()
        sampling_layout = QFormLayout()
        
        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.wheelEvent = lambda event: None
        self.temp_spin.setRange(0.0, 2.0)
        self.temp_spin.setValue(0.7)
        self.temp_spin.setSingleStep(0.05)
        self.temp_spin.setToolTip(
            "温度（Temperature）\n"
            "控制输出的随机性和创造性\n\n"
            "调整范围：0.0 - 2.0\n"
            "推荐值：0.7（平衡准确和创意）\n\n"
            "影响：\n"
            "• 0.2：输出确定、稳健\n"
            "• 0.7：兼顾创意与准确\n"
            "• 1.0：更随机、更有创意\n"
            "• 2.0：可能产生不合逻辑的输出\n\n"
            "使用场景：\n"
            "• 法律/医疗/金融：0.2\n"
            "• 对话助手：0.7-0.8\n"
            "• 创意写作：1.0-1.5"
        )
        
        self.top_k_spin = QSpinBox()
        self.top_k_spin.wheelEvent = lambda event: None
        self.top_k_spin.setRange(0, 100)
        self.top_k_spin.setValue(40)
        self.top_k_spin.setToolTip(
            "Top-K采样\n"
            "只考虑概率最高的K个候选词\n\n"
            "调整范围：0 - 100\n"
            "推荐值：40（平衡多样性）\n\n"
            "影响：\n"
            "• 越大：候选词越多，多样性越强\n"
            "• 越小：候选词越少，输出越确定\n"
            "• 0：禁用Top-K采样\n\n"
            "使用场景：\n"
            "• 确定性输出：20-30\n"
            "• 平衡输出：40-50\n"
            "• 创意输出：60-80"
        )
        
        self.top_p_spin = QDoubleSpinBox()
        self.top_p_spin.wheelEvent = lambda event: None
        self.top_p_spin.setRange(0.0, 1.0)
        self.top_p_spin.setValue(0.95)
        self.top_p_spin.setSingleStep(0.01)
        self.top_p_spin.setToolTip(
            "Top-P采样（核采样）\n"
            "按概率累加候选词，直到达到阈值P\n\n"
            "调整范围：0.0 - 1.0\n"
            "推荐值：0.95（平衡多样性和一致性）\n\n"
            "影响：\n"
            "• 越高：候选词越多，多样性越强\n"
            "• 越低：候选词越少，一致性越好\n\n"
            "使用场景：\n"
            "• 确定性输出：0.7-0.8\n"
            "• 平衡输出：0.9-0.95\n"
            "• 创意输出：0.98-1.0\n\n"
            "配合使用：可与温度参数配合使用"
        )
        
        self.min_p_spin = QDoubleSpinBox()
        self.min_p_spin.wheelEvent = lambda event: None
        self.min_p_spin.setRange(0.0, 1.0)
        self.min_p_spin.setValue(0.05)
        self.min_p_spin.setSingleStep(0.01)
        self.min_p_spin.setToolTip(
            "Min-P采样\n"
            "最小概率阈值，低于此值的词被忽略\n\n"
            "调整范围：0.0 - 1.0\n"
            "推荐值：0.05（过滤低概率词）\n\n"
            "影响：\n"
            "• 越高：过滤越多，输出越确定\n"
            "• 越低：过滤越少，多样性越强\n\n"
            "使用场景：\n"
            "• 确定性输出：0.1-0.2\n"
            "• 平衡输出：0.05\n"
            "• 创意输出：0.01-0.02"
        )
        
        self.repeat_penalty_spin = QDoubleSpinBox()
        self.repeat_penalty_spin.wheelEvent = lambda event: None
        self.repeat_penalty_spin.setRange(1.0, 2.0)
        self.repeat_penalty_spin.setValue(1.1)
        self.repeat_penalty_spin.setSingleStep(0.05)
        self.repeat_penalty_spin.setToolTip(
            "重复惩罚（Repetition Penalty）\n"
            "对重复内容的惩罚系数\n\n"
            "调整范围：1.0 - 2.0\n"
            "推荐值：1.1（轻微惩罚）\n\n"
            "影响：\n"
            "• 1.0：无惩罚，可能重复\n"
            "• 1.1：轻微惩罚，减少重复\n"
            "• 1.5：中等惩罚，显著减少重复\n"
            "• 2.0：强惩罚，几乎不重复\n\n"
            "使用场景：\n"
            "• 对话：1.1-1.3\n"
            "• 创意写作：1.3-1.5\n"
            "• 摘要：1.0-1.1"
        )
        
        self.presence_penalty_spin = QDoubleSpinBox()
        self.presence_penalty_spin.wheelEvent = lambda event: None
        self.presence_penalty_spin.setRange(0.0, 1.0)
        self.presence_penalty_spin.setValue(0.0)
        self.presence_penalty_spin.setSingleStep(0.1)
        self.presence_penalty_spin.setToolTip(
            "存在惩罚（Presence Penalty）\n"
            "对已出现词元的惩罚\n\n"
            "调整范围：0.0 - 1.0\n"
            "推荐值：0.0（不惩罚）\n\n"
            "影响：\n"
            "• 0.0：无惩罚\n"
            "• 0.5：中等惩罚\n"
            "• 1.0：强惩罚\n\n"
            "特点：\n"
            "• 某词元只要出现过，无论多少次都施加同等惩罚\n"
            "• 与频率惩罚配合使用效果更好\n\n"
            "使用场景：\n"
            "• 对话：0.0-0.3\n"
            "• 创意写作：0.3-0.6"
        )
        
        self.frequency_penalty_spin = QDoubleSpinBox()
        self.frequency_penalty_spin.wheelEvent = lambda event: None
        self.frequency_penalty_spin.setRange(0.0, 1.0)
        self.frequency_penalty_spin.setValue(0.0)
        self.frequency_penalty_spin.setSingleStep(0.1)
        self.frequency_penalty_spin.setToolTip(
            "频率惩罚（Frequency Penalty）\n"
            "每次某词元出现，其下次被选中的概率就线性降低\n\n"
            "调整范围：0.0 - 1.0\n"
            "推荐值：0.0（不惩罚）\n\n"
            "影响：\n"
            "• 0.0：无惩罚\n"
            "• 0.5：中等惩罚\n"
            "• 1.0：强惩罚\n\n"
            "特点：\n"
            "• 每次出现都增加惩罚\n"
            "• 迫使模型使用更丰富的词汇表达\n\n"
            "使用场景：\n"
            "• 对话：0.0-0.3\n"
            "• 创意写作：0.3-0.6"
        )
        
        self.ignore_eos_check = QCheckBox("忽略EOS标记 (--ignore-eos)")
        self.ignore_eos_check.setToolTip("忽略结束标记，继续生成")
        
        sampling_layout.addRow("温度 (--temp):", self.temp_spin)
        sampling_layout.addRow("Top-K (--top-k):", self.top_k_spin)
        sampling_layout.addRow("Top-P (--top-p):", self.top_p_spin)
        sampling_layout.addRow("Min-P (--min-p):", self.min_p_spin)
        sampling_layout.addRow("重复惩罚 (--repeat-penalty):", self.repeat_penalty_spin)
        sampling_layout.addRow("存在惩罚 (--presence-penalty):", self.presence_penalty_spin)
        sampling_layout.addRow("频率惩罚 (--frequency-penalty):", self.frequency_penalty_spin)
        sampling_layout.addRow("", self.ignore_eos_check)
        sampling_tab.setLayout(sampling_layout)
        
        # ---- 高级参数选项卡 ----
        advanced_tab = QWidget()
        advanced_layout = QFormLayout()
        
        self.flash_attn_combo = QComboBox()
        self.flash_attn_combo.wheelEvent = lambda event: None
        self.flash_attn_combo.addItems(["auto", "on", "off"])
        self.flash_attn_combo.setCurrentText("auto")
        self.flash_attn_combo.setToolTip(
            "Flash Attention加速\n"
            "优化注意力计算，提升推理速度\n\n"
            "选项：\n"
            "• auto：自动检测并启用\n"
            "• on：强制启用\n"
            "• off：禁用\n\n"
            "影响：\n"
            "• 启用：速度提升20-30%\n"
            "• 禁用：兼容性更好\n\n"
            "建议：保持auto"
        )
        
        self.mirostat_combo = QComboBox()
        self.mirostat_combo.wheelEvent = lambda event: None
        self.mirostat_combo.addItems(["0=禁用", "1=Mirostat", "2=Mirostat v2"])
        self.mirostat_combo.setCurrentText("0=禁用")
        self.mirostat_combo.setToolTip(
            "Mirostat采样模式\n"
            "动态调整采样参数，保持输出质量\n\n"
            "选项：\n"
            "• 0=禁用：不使用Mirostat\n"
            "• 1=Mirostat：第一版算法\n"
            "• 2=Mirostat v2：改进版算法\n\n"
            "影响：\n"
            "• 启用：输出质量更稳定\n"
            "• 禁用：速度更快\n\n"
            "建议：需要高质量输出时启用"
        )
        
        self.mirostat_lr_spin = QDoubleSpinBox()
        self.mirostat_lr_spin.wheelEvent = lambda event: None
        self.mirostat_lr_spin.setRange(0.01, 1.0)
        self.mirostat_lr_spin.setValue(0.1)
        self.mirostat_lr_spin.setSingleStep(0.01)
        self.mirostat_lr_spin.setToolTip(
            "Mirostat学习率\n"
            "控制Mirostat算法的调整幅度\n\n"
            "调整范围：0.01 - 1.0\n"
            "推荐值：0.1\n\n"
            "影响：\n"
            "• 越高：调整越快，可能不稳定\n"
            "• 越低：调整越慢，更稳定\n\n"
            "建议：保持默认值0.1"
        )
        
        self.mirostat_ent_spin = QDoubleSpinBox()
        self.mirostat_ent_spin.wheelEvent = lambda event: None
        self.mirostat_ent_spin.setRange(1.0, 10.0)
        self.mirostat_ent_spin.setValue(5.0)
        self.mirostat_ent_spin.setSingleStep(0.5)
        self.mirostat_ent_spin.setToolTip(
            "Mirostat目标熵\n"
            "控制输出的多样性和复杂性\n\n"
            "调整范围：1.0 - 10.0\n"
            "推荐值：5.0\n\n"
            "影响：\n"
            "• 越高：输出越多样、越复杂\n"
            "• 越低：输出越确定、越简单\n\n"
            "建议：\n"
            "• 确定性输出：2.0-3.0\n"
            "• 平衡输出：5.0\n"
            "• 创意输出：7.0-8.0"
        )
        
        self.mlock_check = QCheckBox("锁定到内存 (--mlock)")
        self.mlock_check.setToolTip(
            "锁定到内存（mlock）\n"
            "防止模型被交换到硬盘\n\n"
            "影响：\n"
            "• 启用：模型常驻内存，速度更快\n"
            "• 禁用：可能被交换到硬盘\n\n"
            "建议：\n"
            "• 内存充足：启用\n"
            "• 内存不足：禁用"
        )
        
        self.mmap_check = QCheckBox("内存映射 (--mmap)")
        self.mmap_check.setChecked(True)
        self.mmap_check.setToolTip(
            "内存映射（mmap）\n"
            "启用内存映射加载模型\n\n"
            "影响：\n"
            "• 启用：加载快，占用少\n"
            "• 禁用：加载慢，占用多\n\n"
            "建议：保持启用"
        )
        
        self.no_mmap_check = QCheckBox("禁用内存映射 (--no-mmap)")
        self.no_mmap_check.setToolTip(
            "禁用内存映射（no-mmap）\n"
            "完全加载到内存，不使用映射\n\n"
            "影响：\n"
            "• 启用：加载慢，占用多，可能更稳定\n"
            "• 禁用：加载快，占用少\n\n"
            "建议：仅在mmap不稳定时启用"
        )
        
        self.no_kv_offload_check = QCheckBox("禁用KV缓存卸载 (--no-kv-offload)")
        self.no_kv_offload_check.setToolTip(
            "禁用KV缓存卸载（no-kv-offload）\n"
            "不将KV缓存卸载到GPU\n\n"
            "影响：\n"
            "• 启用：KV缓存在CPU，GPU占用低\n"
            "• 禁用：KV缓存在GPU，速度更快\n\n"
            "建议：显存不足时启用"
        )
        
        self.cpu_moe_check = QCheckBox("MoE层放在CPU (--cpu-moe)")
        self.cpu_moe_check.setToolTip(
            "MoE层放在CPU（cpu-moe）\n"
            "专家混合层在CPU运行\n\n"
            "影响：\n"
            "• 启用：GPU占用低，速度慢\n"
            "• 禁用：GPU占用高，速度快\n\n"
            "建议：显存不足时启用"
        )
        
        self.fit_combo = QComboBox()
        self.fit_combo.wheelEvent = lambda event: None
        self.fit_combo.addItems(["on=自动适配", "off=手动设置"])
        self.fit_combo.setCurrentText("on=自动适配")
        self.fit_combo.setToolTip(
            "自动适配显存 (--fit)\n"
            "根据显卡显存自动计算最优GPU层数和上下文大小\n\n"
            "选项：\n"
            "• on=自动适配：程序自动算最优参数，不用手动调-ngl\n"
            "• off=手动设置：用你手动设的-ngl和上下文大小\n\n"
            "自动适配的好处：\n"
            "• 换模型不用重新调参数\n"
            "• 不会因显存不够崩掉\n\n"
            "什么时候关闭：\n"
            "• 自动适配算的不准时\n"
            "• 你想精确控制GPU层数时\n"
            "• 加载速度变慢时（适配需要额外时间）"
        )
        
        advanced_layout.addRow("Flash Attention (--flash-attn):", self.flash_attn_combo)
        advanced_layout.addRow("Mirostat模式:", self.mirostat_combo)
        advanced_layout.addRow("Mirostat学习率:", self.mirostat_lr_spin)
        advanced_layout.addRow("Mirostat目标熵:", self.mirostat_ent_spin)
        advanced_layout.addRow("显存自动适配 (--fit):", self.fit_combo)
        advanced_layout.addRow("", self.mlock_check)
        advanced_layout.addRow("", self.mmap_check)
        advanced_layout.addRow("", self.no_mmap_check)
        advanced_layout.addRow("", self.no_kv_offload_check)
        advanced_layout.addRow("", self.cpu_moe_check)
        advanced_tab.setLayout(advanced_layout)
        
        # ---- 思考控制选项卡 ----
        reasoning_tab = QWidget()
        reasoning_layout = QFormLayout()
        
        reasoning_layout.addRow(QLabel("【DeepSeek等模型】"))
        
        self.reasoning_format_combo = QComboBox()
        self.reasoning_format_combo.wheelEvent = lambda event: None
        self.reasoning_format_combo.addItems(["none", "deepseek", "deepseek-legacy", "auto"])
        self.reasoning_format_combo.setCurrentText("none")
        self.reasoning_format_combo.setToolTip(
            "思考格式（Reasoning Format）\n"
            "控制DeepSeek等模型的思考模式\n\n"
            "选项：\n"
            "• none：不使用思考模式\n"
            "• deepseek：DeepSeek原生格式\n"
            "• deepseek-legacy：旧版格式\n"
            "• auto：自动检测\n\n"
            "影响：\n"
            "• 启用：推理更准确，但速度慢\n"
            "• 禁用：速度快，但可能不准确\n\n"
            "建议：根据模型类型选择"
        )
        
        self.reasoning_budget_spin = QSpinBox()
        self.reasoning_budget_spin.wheelEvent = lambda event: None
        self.reasoning_budget_spin.setRange(-1, 10000)
        self.reasoning_budget_spin.setValue(0)
        self.reasoning_budget_spin.setSpecialValueText("-1=无限")
        self.reasoning_budget_spin.setToolTip(
            "思考预算（Reasoning Budget）\n"
            "限制思考过程的token数量\n\n"
            "调整范围：-1 - 10000\n"
            "推荐值：0（禁用思考）\n\n"
            "影响：\n"
            "• -1：无限思考\n"
            "• 0：禁用思考，速度快\n"
            "• >0：限制思考token数\n\n"
            "使用场景：\n"
            "• 快速响应：0\n"
            "• 平衡：1000-2000\n"
            "• 深度思考：-1或5000+"
        )
        
        reasoning_layout.addRow("思考格式 (--reasoning-format):", self.reasoning_format_combo)
        reasoning_layout.addRow("思考预算 (--reasoning-budget):", self.reasoning_budget_spin)
        
        reasoning_layout.addRow(QLabel(""))
        reasoning_layout.addRow(QLabel("【Qwen3.5系列模型】"))
        
        self.disable_qwen_thinking_check = QCheckBox("关闭Qwen3.5思考模式")
        self.disable_qwen_thinking_check.setChecked(True)
        self.disable_qwen_thinking_check.setToolTip(
            "关闭Qwen3.5思考模式\n"
            "通过chat-template-kwargs关闭思考\n\n"
            "影响：\n"
            "• 启用：速度快，响应快\n"
            "• 禁用：推理更准确，但速度慢\n\n"
            "建议：\n"
            "• 快速对话：启用\n"
            "• 深度推理：禁用"
        )
        
        reasoning_layout.addRow("", self.disable_qwen_thinking_check)
        
        reasoning_layout.addRow(QLabel(""))
        reasoning_layout.addRow(QLabel("【通用快捷开关】"))
        
        self.disable_reasoning_check = QCheckBox("关闭所有思考模式 (快捷方式)")
        self.disable_reasoning_check.setChecked(True)
        self.disable_reasoning_check.toggled.connect(self.toggle_reasoning)
        self.disable_reasoning_check.setToolTip(
            "关闭所有思考模式（快捷方式）\n"
            "同时关闭DeepSeek和Qwen3.5的思考模式\n\n"
            "影响：\n"
            "• 启用：关闭所有思考，速度快\n"
            "• 禁用：启用思考，推理更准确\n\n"
            "建议：\n"
            "• 快速对话：启用\n"
            "• 深度推理：禁用"
        )
        
        reasoning_layout.addRow("", self.disable_reasoning_check)
        reasoning_tab.setLayout(reasoning_layout)
        
        # ---- KV缓存优化选项卡 ----
        cache_tab = QWidget()
        cache_layout = QFormLayout()
        
        cache_layout.addRow(QLabel("【KV缓存复用 - 加速重复请求】"))
        
        self.cache_reuse_spin = QSpinBox()
        self.cache_reuse_spin.wheelEvent = lambda event: None
        self.cache_reuse_spin.setRange(0, 4096)
        self.cache_reuse_spin.setValue(0)
        self.cache_reuse_spin.setToolTip(
            "KV缓存复用阈值 (--cache-reuse)\n"
            "最小复用块大小，用于KV shifting\n\n"
            "调整范围：0 - 4096\n"
            "推荐值：64（启用复用）\n\n"
            "影响：\n"
            "• 0：禁用缓存复用\n"
            "• >0：相同前缀的请求可复用缓存\n\n"
            "使用场景：\n"
            "• 多轮对话：64-128\n"
            "• 单次请求：0\n\n"
            "效果：相同system prompt的请求处理速度提升50%+"
        )
        
        cache_layout.addRow("缓存复用阈值 (--cache-reuse):", self.cache_reuse_spin)
        
        cache_layout.addRow(QLabel(""))
        cache_layout.addRow(QLabel("【内存管理】"))
        
        self.cache_ram_spin = QSpinBox()
        self.cache_ram_spin.wheelEvent = lambda event: None
        self.cache_ram_spin.setRange(-1, 65536)
        self.cache_ram_spin.setValue(8192)
        self.cache_ram_spin.setSuffix(" MiB")
        self.cache_ram_spin.setToolTip(
            "最大缓存大小 (--cache-ram)\n"
            "KV缓存的最大内存限制\n\n"
            "调整范围：-1 - 65536 MiB\n"
            "推荐值：8192（8GB）\n\n"
            "选项：\n"
            "• -1：无限制\n"
            "• 0：禁用缓存\n"
            "• >0：限制大小\n\n"
            "建议：\n"
            "• 16GB内存：4096-8192\n"
            "• 32GB内存：16384\n"
            "• 64GB内存：32768"
        )
        
        cache_layout.addRow("最大缓存 (--cache-ram):", self.cache_ram_spin)
        
        self.kv_unified_check = QCheckBox("统一KV缓冲区 (--kv-unified)")
        self.kv_unified_check.setChecked(True)
        self.kv_unified_check.setToolTip(
            "统一KV缓冲区 (--kv-unified)\n"
            "多序列共享单个KV缓冲区\n\n"
            "影响：\n"
            "• 启用：节省内存，支持更多并发\n"
            "• 禁用：每个序列独立缓存\n\n"
            "建议：保持启用"
        )
        
        cache_layout.addRow("", self.kv_unified_check)
        
        self.clear_idle_check = QCheckBox("空闲插槽缓存 (--cache-idle-slots)")
        self.clear_idle_check.setChecked(True)
        self.clear_idle_check.setToolTip(
            "空闲插槽缓存 (--cache-idle-slots)\n"
            "新任务到达时保存并清除空闲插槽\n\n"
            "前提：需要启用统一KV和cache-ram\n\n"
            "影响：\n"
            "• 启用：自动管理内存，防止溢出\n"
            "• 禁用：手动管理\n\n"
            "建议：保持启用"
        )
        
        cache_layout.addRow("", self.clear_idle_check)
        
        cache_layout.addRow(QLabel(""))
        cache_layout.addRow(QLabel("【插槽持久化 - 保存会话状态】"))
        
        slot_save_layout = QHBoxLayout()
        self.slot_save_path_edit = QLineEdit()
        self.slot_save_path_edit.setPlaceholderText("留空=不启用持久化")
        self.slot_save_path_edit.setToolTip(
            "插槽持久化路径 (--slot-save-path)\n"
            "保存KV缓存到磁盘，下次启动可恢复\n\n"
            "使用场景：\n"
            "• 长期对话：保存会话状态\n"
            "• 快速恢复：重启后继续对话\n\n"
            "示例：./slots 或 C:/llama/slots"
        )
        self.slot_save_browse_btn = QPushButton("浏览...")
        self.slot_save_browse_btn.setMaximumWidth(60)
        self.slot_save_browse_btn.clicked.connect(self.browse_slot_save_path)
        slot_save_layout.addWidget(self.slot_save_path_edit)
        slot_save_layout.addWidget(self.slot_save_browse_btn)
        
        cache_layout.addRow("持久化路径 (--slot-save-path):", slot_save_layout)
        
        cache_layout.addRow(QLabel(""))
        cache_layout.addRow(QLabel("【推理思考模式 - 新版参数】"))
        
        self.reasoning_combo = QComboBox()
        self.reasoning_combo.wheelEvent = lambda event: None
        self.reasoning_combo.addItems(["auto", "on", "off"])
        self.reasoning_combo.setCurrentText("auto")
        self.reasoning_combo.setToolTip(
            "推理思考模式 (--reasoning)\n"
            "控制模型的思考过程输出\n\n"
            "选项：\n"
            "• auto：自动检测（根据模型模板）\n"
            "• on：强制启用思考\n"
            "• off：禁用思考\n\n"
            "适用模型：\n"
            "• DeepSeek R1\n"
            "• Qwen3\n"
            "• 其他支持思考的模型\n\n"
            "建议：auto"
        )
        
        cache_layout.addRow("思考模式 (--reasoning):", self.reasoning_combo)
        
        self.reasoning_budget_new_spin = QSpinBox()
        self.reasoning_budget_new_spin.wheelEvent = lambda event: None
        self.reasoning_budget_new_spin.setRange(-1, 100000)
        self.reasoning_budget_new_spin.setValue(-1)
        self.reasoning_budget_new_spin.setSpecialValueText("-1=无限")
        self.reasoning_budget_new_spin.setToolTip(
            "思考Token预算 (--reasoning-budget)\n"
            "限制思考过程的token数量\n\n"
            "调整范围：-1 - 100000\n"
            "推荐值：-1（无限）\n\n"
            "选项：\n"
            "• -1：无限思考\n"
            "• 0：立即结束思考\n"
            "• >0：限制token数\n\n"
            "使用场景：\n"
            "• 快速响应：1000-2000\n"
            "• 深度思考：-1或10000+"
        )
        
        cache_layout.addRow("思考预算 (--reasoning-budget):", self.reasoning_budget_new_spin)
        
        cache_tab.setLayout(cache_layout)
        
        # 添加选项卡
        param_tabs.addTab(basic_tab, "基础参数")
        param_tabs.addTab(sampling_tab, "采样控制")
        param_tabs.addTab(advanced_tab, "高级参数")
        param_tabs.addTab(reasoning_tab, "思考控制")
        param_tabs.addTab(cache_tab, "缓存优化")
        param_tabs.addTab(self._create_spec_decode_tab(), "推测解码")
        param_tabs.addTab(self._create_tts_tab(), "语音合成 (TTS)")
        param_tabs.addTab(self._create_custom_params_tab(), "自定义参数")
        
        param_layout.addWidget(param_tabs)
        
        # ===== 状态信息内容（不直接显示，弹窗用） =====
        status_content = QWidget()
        status_layout = QFormLayout(status_content)
        
        self.llama_status_label = QLabel("已停止")
        self.llama_status_label.setStyleSheet("color: red; font-weight: bold;")
        
        self.llama_api_url_label = QLabel("http://127.0.0.1:8081")
        self.llama_api_url_label.setStyleSheet("color: blue; text-decoration: underline;")
        self.llama_api_url_label.setCursor(Qt.PointingHandCursor)
        self.llama_api_url_label.mousePressEvent = self.copy_llama_api_url
        
        self.current_model_label = QLabel("未加载")
        
        self.token_stats_label = QLabel()
        self.token_stats_label.setStyleSheet("font-weight: bold;")
        self.token_stats_label.setTextFormat(Qt.RichText)
        self.update_token_stats()
        
        status_layout.addRow("服务状态:", self.llama_status_label)
        status_layout.addRow("API地址 (点击复制):", self.llama_api_url_label)
        status_layout.addRow("当前模型:", self.current_model_label)
        status_layout.addRow("Token统计:", self.token_stats_label)
        
        # ===== 预设管理内容（不直接显示，弹窗用） =====
        preset_content = QWidget()
        preset_layout = QVBoxLayout(preset_content)
        
        preset_btn_layout = QHBoxLayout()
        self.save_preset_btn = QPushButton("💾 保存预设")
        self.save_preset_btn.setMinimumHeight(36)
        self.save_preset_btn.setMaximumWidth(100)
        self.save_preset_btn.clicked.connect(self.save_preset)
        self.save_preset_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; border: none; border-radius: 5px;")
        self.delete_preset_btn = QPushButton("🗑 删除预设")
        self.delete_preset_btn.setMinimumHeight(36)
        self.delete_preset_btn.setMaximumWidth(100)
        self.delete_preset_btn.clicked.connect(self.delete_preset)
        self.delete_preset_btn.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold; border: none; border-radius: 5px;")
        preset_btn_layout.addWidget(self.save_preset_btn)
        preset_btn_layout.addWidget(self.delete_preset_btn)
        preset_layout.addLayout(preset_btn_layout)
        
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumHeight(36)
        self.preset_combo.wheelEvent = lambda event: None
        self.preset_combo.currentIndexChanged.connect(self.load_preset)
        preset_layout.addWidget(self.preset_combo)
        
        # ===== 自动优化内容（不直接显示，弹窗用） =====
        optimize_content = QWidget()
        optimize_layout = QVBoxLayout(optimize_content)
        
        self.enable_optimize_check = QCheckBox("启用自动优化功能")
        self.enable_optimize_check.setChecked(False)
        self.enable_optimize_check.setToolTip("启用后将自动测试不同参数组合，找到最佳性能配置")
        self.enable_optimize_check.stateChanged.connect(self.on_optimize_enabled_changed)
        optimize_layout.addWidget(self.enable_optimize_check)
        
        optimize_settings_layout = QFormLayout()
        
        self.optimize_metric_combo = QComboBox()
        self.optimize_metric_combo.wheelEvent = lambda event: None
        self.optimize_metric_combo.addItems(["token生成速度 (tg)", "提示处理速度 (pp)", "综合平均 (mean)"])
        self.optimize_metric_combo.setToolTip("选择要优化的性能指标")
        
        self.optimize_trials_spin = QSpinBox()
        self.optimize_trials_spin.wheelEvent = lambda event: None
        self.optimize_trials_spin.setRange(5, 100)
        self.optimize_trials_spin.setValue(20)
        self.optimize_trials_spin.setToolTip("优化尝试次数，次数越多结果越准确但耗时越长")
        
        self.optimize_repeat_spin = QSpinBox()
        self.optimize_repeat_spin.wheelEvent = lambda event: None
        self.optimize_repeat_spin.setRange(1, 10)
        self.optimize_repeat_spin.setValue(3)
        self.optimize_repeat_spin.setToolTip("每次测试重复次数，提高结果稳定性")
        
        optimize_settings_layout.addRow("优化目标:", self.optimize_metric_combo)
        optimize_settings_layout.addRow("尝试次数:", self.optimize_trials_spin)
        optimize_settings_layout.addRow("重复次数:", self.optimize_repeat_spin)
        optimize_layout.addLayout(optimize_settings_layout)
        
        optimize_btn_layout = QHBoxLayout()
        self.start_optimize_btn = QPushButton("🚀 开始优化")
        self.start_optimize_btn.setMinimumHeight(40)
        self.start_optimize_btn.clicked.connect(self.start_optimization)
        self.start_optimize_btn.setStyleSheet("background-color: #9C27B0; color: white; font-weight: bold; border: none; border-radius: 5px;")
        self.start_optimize_btn.setEnabled(False)
        
        self.apply_optimize_btn = QPushButton("✅ 应用最佳参数")
        self.apply_optimize_btn.setMinimumHeight(40)
        self.apply_optimize_btn.clicked.connect(self.apply_best_params)
        self.apply_optimize_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; border: none; border-radius: 5px;")
        self.apply_optimize_btn.setEnabled(False)
        
        optimize_btn_layout.addWidget(self.start_optimize_btn)
        optimize_btn_layout.addWidget(self.apply_optimize_btn)
        optimize_layout.addLayout(optimize_btn_layout)
        
        self.optimize_status_label = QLabel("状态: 未启用")
        self.optimize_status_label.setStyleSheet("color: gray;")
        optimize_layout.addWidget(self.optimize_status_label)
        
        self.best_params_label = QLabel("")
        self.best_params_label.setWordWrap(True)
        self.best_params_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        optimize_layout.addWidget(self.best_params_label)
        
        self.best_params = None
        
        # 保存内容widget引用，供弹窗使用
        self._param_content = param_content
        self._preset_content = preset_content
        self._optimize_content = optimize_content
        self._status_content = status_content
        
        layout.addWidget(model_group)
        
        scroll_area.setWidget(tab)
        return scroll_area

    def create_turboquant_tab(self):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        title_label = QLabel("🚀 社区加速版 (TurboQuant-MTP)")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #FF9800;")
        layout.addWidget(title_label)

        desc_label = QLabel(
            "基于 llama-cpp-turboquant-mtp 社区优化版，专为 MTP 模型加速优化。\n"
            "不支持图片识别，但推理速度更快，适合纯文本场景。"
        )
        desc_label.setStyleSheet("color: #666; font-size: 10pt;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # 社区网址链接
        link_label = QLabel(
            '<a href="https://github.com/lemonyins/llama-cpp-turboquant-mtp" '
            'style="color: #FF9800; font-size: 9pt; text-decoration: none;">'
            '🔗 社区项目地址: github.com/lemonyins/llama-cpp-turboquant-mtp</a>'
        )
        link_label.setOpenExternalLinks(True)
        link_label.setCursor(Qt.PointingHandCursor)
        link_label.setAlignment(Qt.AlignLeft)
        layout.addWidget(link_label)

        # 控制按钮行
        ctrl_layout = QHBoxLayout()
        self.tq_start_btn = QPushButton("▶ 启动社区版")
        self.tq_start_btn.setFixedHeight(30)
        self.tq_start_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 4px 16px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.tq_start_btn.clicked.connect(self.start_turboquant_server)

        self.tq_stop_btn = QPushButton("⏹ 停止社区版")
        self.tq_stop_btn.setFixedHeight(30)
        self.tq_stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #cccccc;
                color: #666;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 4px 16px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #d32f2f;
                color: white;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.tq_stop_btn.clicked.connect(self.stop_turboquant_server)
        self.tq_stop_btn.setEnabled(False)

        self.tq_status_label = QLabel("● 已停止")
        self.tq_status_label.setStyleSheet("color: #999999; font-size: 11px; font-weight: bold;")

        ctrl_layout.addStretch()
        ctrl_layout.addWidget(self.tq_start_btn)
        ctrl_layout.addWidget(self.tq_stop_btn)
        ctrl_layout.addWidget(self.tq_status_label)
        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)

        # 配置信息分组 - 可编辑
        info_group = QGroupBox("配置参数（可编辑，修改后按保存）")
        info_layout = QFormLayout(info_group)
        info_layout.setSpacing(4)

        # 执行文件路径 + 浏览按钮
        exe_path_layout = QHBoxLayout()
        self.tq_exe_edit = QLineEdit()
        default_tq_dir = os.path.join(os.path.dirname(__file__),
            "llama-bin", "llama-cpp-turboquant-mtp-v1.0.0-windows-x64-cuda12.4-sm-86")
        self.tq_exe_edit.setText(os.path.join(default_tq_dir, "llama-server.exe"))
        self.tq_exe_edit.setFont(QFont("Consolas", 9))
        exe_browse_btn = QPushButton("浏览...")
        exe_browse_btn.setFixedWidth(60)
        exe_browse_btn.clicked.connect(lambda: self._browse_tq_file(self.tq_exe_edit, "可执行文件 (*.exe)"))
        exe_path_layout.addWidget(self.tq_exe_edit)
        exe_path_layout.addWidget(exe_browse_btn)
        info_layout.addRow("执行文件:", exe_path_layout)

        # 模型路径 + 浏览按钮
        model_path_layout = QHBoxLayout()
        self.tq_model_edit = QLineEdit()
        default_model = (r"D:\models"
            r"\unsloth\Qwen3.6-35B-A3B-MTP-GGUF\Qwen3.6-35B-A3B-UD-IQ4_NL.gguf")
        self.tq_model_edit.setText(default_model)
        self.tq_model_edit.setFont(QFont("Consolas", 9))
        model_browse_btn = QPushButton("浏览...")
        model_browse_btn.setFixedWidth(60)
        model_browse_btn.clicked.connect(lambda: self._browse_tq_file(self.tq_model_edit, "GGUF 模型 (*.gguf)"))
        model_path_layout.addWidget(self.tq_model_edit)
        model_path_layout.addWidget(model_browse_btn)
        info_layout.addRow("模型:", model_path_layout)

        # 端口
        port_layout = QHBoxLayout()
        self.tq_port_spin = QSpinBox()
        self.tq_port_spin.setRange(1, 65535)
        self.tq_port_spin.setValue(8081)
        self.tq_port_spin.setFixedWidth(100)
        self.tq_port_spin.setToolTip("监听端口，默认 8081")
        port_layout.addWidget(self.tq_port_spin)
        port_layout.addStretch()
        info_layout.addRow("端口:", port_layout)

        # 其他参数编辑区
        self.tq_params_display = QTextEdit()
        self.tq_params_display.setFont(QFont("Consolas", 9))
        self.tq_params_display.setFixedHeight(130)
        self.tq_params_display.setPlaceholderText(
            "在此修改参数，每行一个或空格分隔。\n"
            "不需要写 -m 模型路径、--port、--host，这些在上面单独设置。"
        )
        self.tq_params_display.setPlainText(
            "-c 120800 -b 2048 -ub 1024 -t 5 -ngl 80\n"
            "--spec-type mtp --spec-draft-n-max 2 -np 1\n"
            "-ctk q4_0 -ctv q4_0\n"
            "--temp 0.4 --top-k 40 --top-p 0.95 --min-p 0.05\n"
            "--repeat-penalty 1.1 --fit off --flash-attn on\n"
            "--no-mmap --reasoning off --reasoning-budget 0\n"
            "--cache-idle-slots --kv-unified --cont-batching"
        )
        info_layout.addRow("其他参数:", self.tq_params_display)

        # 按钮行：保存 / 恢复默认 / 复制命令
        btn_row = QHBoxLayout()
        save_cfg_btn = QPushButton("💾 保存配置")
        save_cfg_btn.setFixedWidth(100)
        save_cfg_btn.clicked.connect(self._save_turboquant_config)

        reset_btn = QPushButton("↺ 恢复默认")
        reset_btn.setFixedWidth(100)
        reset_btn.clicked.connect(self._reset_turboquant_config)

        copy_btn = QPushButton("📋 复制命令")
        copy_btn.setFixedWidth(100)
        copy_btn.clicked.connect(self._copy_turboquant_cmd)

        btn_row.addStretch()
        btn_row.addWidget(save_cfg_btn)
        btn_row.addWidget(reset_btn)
        btn_row.addWidget(copy_btn)
        info_layout.addRow("", btn_row)

        layout.addWidget(info_group)

        # 日志输出
        log_group = QGroupBox("运行日志")
        log_layout = QVBoxLayout(log_group)
        self.tq_log_text = QTextEdit()
        self.tq_log_text.setReadOnly(True)
        self.tq_log_text.setFont(QFont("Consolas", 9))
        log_layout.addWidget(self.tq_log_text)

        tq_log_btn_layout = QHBoxLayout()
        tq_clear_btn = QPushButton("清空日志")
        tq_clear_btn.clicked.connect(lambda: self.tq_log_text.clear())
        tq_log_btn_layout.addStretch()
        tq_log_btn_layout.addWidget(tq_clear_btn)
        log_layout.addLayout(tq_log_btn_layout)

        layout.addWidget(log_group)

        scroll_area.setWidget(tab)
        return scroll_area

    def create_webui_tab(self):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        config_group = CollapsibleGroupBox("Open WebUI 配置")
        config_outer_layout = QVBoxLayout(config_group)
        config_content = QWidget()
        config_layout = QFormLayout(config_content)
        config_group.setContentWidget(config_content)
        
        self.hf_endpoint_edit = QLineEdit("https://hf-mirror.com")
        
        self.data_dir_edit = QLineEdit("C:\\open-webui\\data")
        self.browse_data_btn = QPushButton("浏览...")
        self.browse_data_btn.clicked.connect(self.browse_data_dir)
        data_dir_layout = QHBoxLayout()
        data_dir_layout.addWidget(self.data_dir_edit)
        data_dir_layout.addWidget(self.browse_data_btn)
        
        self.webui_port_spin = QSpinBox()
        self.webui_port_spin.wheelEvent = lambda event: None
        self.webui_port_spin.setRange(1024, 65535)
        self.webui_port_spin.setValue(3000)
        
        self.auto_start_llama_check = QCheckBox("启动前自动启动 Llama Server")
        self.auto_start_llama_check.setChecked(True)
        
        self.startup_delay_spin = QSpinBox()
        self.startup_delay_spin.wheelEvent = lambda event: None
        self.startup_delay_spin.setRange(0, 60)
        self.startup_delay_spin.setValue(10)
        self.startup_delay_spin.setSuffix(" 秒")
        
        config_layout.addRow("HF Endpoint:", self.hf_endpoint_edit)
        config_layout.addRow("数据目录:", data_dir_layout)
        config_layout.addRow("端口:", self.webui_port_spin)
        config_layout.addRow("", self.auto_start_llama_check)
        config_layout.addRow("启动延迟:", self.startup_delay_spin)
        
        config_outer_layout.addWidget(config_content)
        
        control_group = CollapsibleGroupBox("服务控制")
        control_outer_layout = QVBoxLayout(control_group)
        control_content = QWidget()
        control_layout = QHBoxLayout(control_content)
        control_group.setContentWidget(control_content)
        
        self.start_webui_btn = QPushButton("启动 Open WebUI")
        self.start_webui_btn.setMinimumHeight(40)
        self.start_webui_btn.clicked.connect(self.start_webui)
        
        self.stop_webui_btn = QPushButton("停止 Open WebUI")
        self.stop_webui_btn.setMinimumHeight(40)
        self.stop_webui_btn.clicked.connect(self.stop_webui)
        self.stop_webui_btn.setEnabled(False)
        
        control_layout.addWidget(self.start_webui_btn)
        control_layout.addWidget(self.stop_webui_btn)
        
        control_outer_layout.addWidget(control_content)
        
        status_group = CollapsibleGroupBox("状态信息")
        status_outer_layout = QVBoxLayout(status_group)
        status_content = QWidget()
        status_layout = QFormLayout(status_content)
        status_group.setContentWidget(status_content)
        
        self.webui_status_label = QLabel("已停止")
        self.webui_status_label.setStyleSheet("color: red; font-weight: bold;")
        
        self.webui_url_label = QLabel("http://127.0.0.1:3000")
        self.webui_url_label.setStyleSheet("color: blue; text-decoration: underline;")
        self.webui_url_label.setCursor(Qt.PointingHandCursor)
        self.webui_url_label.mousePressEvent = self.copy_webui_url
        
        status_layout.addRow("服务状态:", self.webui_status_label)
        status_layout.addRow("访问地址 (点击复制):", self.webui_url_label)
        
        status_outer_layout.addWidget(status_content)
        
        info_group = CollapsibleGroupBox("使用说明")
        info_outer_layout = QVBoxLayout(info_group)
        info_content = QWidget()
        info_layout = QVBoxLayout(info_content)
        info_group.setContentWidget(info_content)
        info_text = QLabel(
            "1. Open WebUI 依赖 Llama Server 提供的 API\n"
            "2. 建议先启动 Llama Server，再启动 Open WebUI\n"
            "3. 启动延迟用于等待 Llama Server 完全加载\n"
            "4. 可在浏览器中访问 Open WebUI 进行对话"
        )
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text)
        
        info_outer_layout.addWidget(info_content)
        
        layout.addWidget(config_group)
        layout.addWidget(control_group)
        layout.addWidget(status_group)
        layout.addWidget(info_group)
        
        scroll_area.setWidget(tab)
        return scroll_area

    def create_distributed_tab(self):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        mode_group = CollapsibleGroupBox("运行模式选择")
        mode_outer_layout = QVBoxLayout(mode_group)
        mode_content = QWidget()
        mode_layout = QVBoxLayout(mode_content)
        mode_group.setContentWidget(mode_content)
        
        mode_label = QLabel("选择本机的角色：")
        mode_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        
        self.mode_combo = QComboBox()
        self.mode_combo.wheelEvent = lambda event: None
        self.mode_combo.addItems([
            "主服务器 (Master) - 运行API服务，连接远程GPU",
            "从服务器 (Worker) - 提供GPU计算能力给主服务器",
            "混合模式 - 本机GPU + 远程GPU协同计算"
        ])
        self.mode_combo.currentIndexChanged.connect(self.on_distributed_mode_changed)
        
        mode_info = QLabel(
            "主服务器：运行模型API服务，可连接多台从服务器获取GPU算力\n"
            "从服务器：仅运行rpc-server，为其他机器提供GPU计算能力\n"
            "混合模式：本机GPU参与计算，同时连接远程GPU协同工作"
        )
        mode_info.setStyleSheet("color: #666; font-size: 11px;")
        mode_info.setWordWrap(True)
        
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addWidget(mode_info)
        
        mode_outer_layout.addWidget(mode_content)
        
        master_group = CollapsibleGroupBox("主服务器配置 (连接远程GPU)")
        master_outer_layout = QVBoxLayout(master_group)
        master_content = QWidget()
        master_layout = QVBoxLayout(master_content)
        master_group.setContentWidget(master_content)
        
        self.enable_rpc_check = QCheckBox("启用分布式推理 (连接远程GPU)")
        self.enable_rpc_check.setChecked(False)
        self.enable_rpc_check.stateChanged.connect(self.on_enable_rpc_changed)
        
        rpc_servers_label = QLabel("远程RPC服务器列表 (每行一个，格式: IP:端口)")
        self.rpc_servers_edit = QTextEdit()
        self.rpc_servers_edit.setPlaceholderText("例如:\n192.168.1.100:50052\n192.168.1.101:50052")
        self.rpc_servers_edit.setMaximumHeight(100)
        
        rpc_btn_layout = QHBoxLayout()
        self.test_rpc_btn = QPushButton("测试连接")
        self.test_rpc_btn.clicked.connect(self.test_rpc_connections)
        self.add_local_rpc_btn = QPushButton("添加本机RPC")
        self.add_local_rpc_btn.clicked.connect(self.add_local_rpc_server)
        rpc_btn_layout.addWidget(self.test_rpc_btn)
        rpc_btn_layout.addWidget(self.add_local_rpc_btn)
        
        self.rpc_status_label = QLabel("状态: 未配置")
        self.rpc_status_label.setStyleSheet("color: gray;")
        
        master_layout.addWidget(self.enable_rpc_check)
        master_layout.addWidget(rpc_servers_label)
        master_layout.addWidget(self.rpc_servers_edit)
        master_layout.addLayout(rpc_btn_layout)
        master_layout.addWidget(self.rpc_status_label)
        
        master_outer_layout.addWidget(master_content)
        
        worker_group = CollapsibleGroupBox("从服务器配置 (提供GPU算力)")
        worker_outer_layout = QVBoxLayout(worker_group)
        worker_content = QWidget()
        worker_layout = QVBoxLayout(worker_content)
        worker_group.setContentWidget(worker_content)
        
        self.enable_worker_check = QCheckBox("启用从服务器模式 (运行rpc-server)")
        self.enable_worker_check.setChecked(False)
        self.enable_worker_check.stateChanged.connect(self.on_enable_worker_changed)
        
        worker_form = QFormLayout()
        
        self.worker_host_edit = QLineEdit("0.0.0.0")
        self.worker_host_edit.setToolTip("监听地址，0.0.0.0表示接受所有网络连接")
        
        self.worker_port_spin = QSpinBox()
        self.worker_port_spin.wheelEvent = lambda event: None
        self.worker_port_spin.setRange(1024, 65535)
        self.worker_port_spin.setValue(50052)
        
        self.worker_gpu_spin = QSpinBox()
        self.worker_gpu_spin.wheelEvent = lambda event: None
        self.worker_gpu_spin.setRange(0, 99)
        self.worker_gpu_spin.setValue(0)
        self.worker_gpu_spin.setToolTip("使用的GPU编号，0表示第一个GPU")
        
        worker_form.addRow("监听地址:", self.worker_host_edit)
        worker_form.addRow("监听端口:", self.worker_port_spin)
        worker_form.addRow("GPU编号:", self.worker_gpu_spin)
        
        worker_btn_layout = QHBoxLayout()
        self.start_worker_btn = QPushButton("启动 RPC Server")
        self.start_worker_btn.setMinimumHeight(40)
        self.start_worker_btn.clicked.connect(self.start_rpc_server)
        
        self.stop_worker_btn = QPushButton("停止 RPC Server")
        self.stop_worker_btn.setMinimumHeight(40)
        self.stop_worker_btn.clicked.connect(self.stop_rpc_server)
        self.stop_worker_btn.setEnabled(False)
        
        worker_btn_layout.addWidget(self.start_worker_btn)
        worker_btn_layout.addWidget(self.stop_worker_btn)
        
        self.worker_status_label = QLabel("状态: 已停止")
        self.worker_status_label.setStyleSheet("color: red; font-weight: bold;")
        
        self.worker_url_label = QLabel("")
        self.worker_url_label.setStyleSheet("color: blue;")
        
        worker_layout.addWidget(self.enable_worker_check)
        worker_layout.addLayout(worker_form)
        worker_layout.addLayout(worker_btn_layout)
        worker_layout.addWidget(self.worker_status_label)
        worker_layout.addWidget(self.worker_url_label)
        
        worker_outer_layout.addWidget(worker_content)
        
        info_group = CollapsibleGroupBox("使用说明")
        info_outer_layout = QVBoxLayout(info_group)
        info_content = QWidget()
        info_layout = QVBoxLayout(info_content)
        info_group.setContentWidget(info_content)
        
        info_text = QLabel(
            "【分布式推理使用步骤】\n\n"
            "1. 从服务器设置（6G显卡机器）:\n"
            "   - 选择'从服务器'模式\n"
            "   - 设置监听端口（默认50052）\n"
            "   - 点击'启动 RPC Server'\n"
            "   - 记下显示的IP地址\n\n"
            "2. 主服务器设置（8G显卡机器）:\n"
            "   - 选择'主服务器'或'混合模式'\n"
            "   - 在远程RPC服务器列表中填入从服务器IP:端口\n"
            "   - 勾选'启用分布式推理'\n"
            "   - 启动Llama Server时会自动连接远程GPU\n\n"
            "3. 混合模式:\n"
            "   - 本机GPU和远程GPU同时参与计算\n"
            "   - 模型层会自动分配到各个GPU上\n\n"
            "【注意事项】\n"
            "- 确保防火墙允许RPC端口通信\n"
            "- 局域网延迟会影响推理速度\n"
            "- 两台机器需要相同版本的llama.cpp"
        )
        info_text.setWordWrap(True)
        info_text.setStyleSheet("font-size: 11px;")
        info_layout.addWidget(info_text)
        
        info_outer_layout.addWidget(info_content)
        
        layout.addWidget(mode_group)
        layout.addWidget(master_group)
        layout.addWidget(worker_group)
        layout.addWidget(info_group)
        layout.addStretch()
        
        self.on_distributed_mode_changed(0)
        
        scroll_area.setWidget(tab)
        return scroll_area

    def toggle_reasoning(self, checked):
        """切换思考模式"""
        if checked:
            self.reasoning_format_combo.setCurrentText("none")
            self.reasoning_budget_spin.setValue(0)
            self.reasoning_format_combo.setEnabled(False)
            self.reasoning_budget_spin.setEnabled(False)
            self.disable_qwen_thinking_check.setChecked(True)
            self.disable_qwen_thinking_check.setEnabled(False)
        else:
            self.reasoning_format_combo.setEnabled(True)
            self.reasoning_budget_spin.setEnabled(True)
            self.disable_qwen_thinking_check.setEnabled(True)
    
    def on_distributed_mode_changed(self, index):
        """分布式模式切换"""
        is_master = index in [0, 2]
        is_worker = index == 1
        is_hybrid = index == 2
        
        self.enable_rpc_check.setEnabled(is_master)
        self.rpc_servers_edit.setEnabled(is_master)
        self.test_rpc_btn.setEnabled(is_master)
        self.add_local_rpc_btn.setEnabled(is_master)
        
        self.enable_worker_check.setEnabled(is_worker or is_hybrid)
        self.worker_host_edit.setEnabled(is_worker or is_hybrid)
        self.worker_port_spin.setEnabled(is_worker or is_hybrid)
        self.worker_gpu_spin.setEnabled(is_worker or is_hybrid)
        self.start_worker_btn.setEnabled(is_worker or is_hybrid)
        
        if is_hybrid:
            self.enable_rpc_check.setChecked(True)
            self.enable_worker_check.setChecked(True)
        
        mode_names = ["主服务器", "从服务器", "混合模式"]
        self.log_message(f"已切换到 {mode_names[index]} 模式")
    
    def on_enable_rpc_changed(self, state):
        """启用分布式推理开关"""
        enabled = state == Qt.Checked
        self.rpc_servers_edit.setEnabled(enabled)
        self.test_rpc_btn.setEnabled(enabled)
        self.add_local_rpc_btn.setEnabled(enabled)
        
        if enabled:
            self.rpc_status_label.setText("状态: 已启用，请配置远程服务器")
            self.rpc_status_label.setStyleSheet("color: green;")
        else:
            self.rpc_status_label.setText("状态: 未启用")
            self.rpc_status_label.setStyleSheet("color: gray;")
    
    def on_enable_worker_changed(self, state):
        """启用从服务器模式开关"""
        enabled = state == Qt.Checked
        self.worker_host_edit.setEnabled(enabled)
        self.worker_port_spin.setEnabled(enabled)
        self.worker_gpu_spin.setEnabled(enabled)
        self.start_worker_btn.setEnabled(enabled)
    
    def add_local_rpc_server(self):
        """添加本机RPC服务器到列表"""
        local_ip = self.get_local_ip()
        port = self.worker_port_spin.value()
        rpc_address = f"{local_ip}:{port}"
        
        current_text = self.rpc_servers_edit.toPlainText()
        if rpc_address not in current_text:
            if current_text.strip():
                self.rpc_servers_edit.setText(current_text + "\n" + rpc_address)
            else:
                self.rpc_servers_edit.setText(rpc_address)
            self.log_message(f"已添加本机RPC服务器: {rpc_address}")
        else:
            self.log_message(f"本机RPC服务器已存在: {rpc_address}")
    
    def test_rpc_connections(self):
        """测试RPC服务器连接"""
        import socket
        
        servers_text = self.rpc_servers_edit.toPlainText().strip()
        if not servers_text:
            QMessageBox.warning(self, "警告", "请先配置远程RPC服务器")
            return
        
        servers = [s.strip() for s in servers_text.split('\n') if s.strip()]
        results = []
        
        for server in servers:
            try:
                if ':' in server:
                    host, port = server.split(':')
                    port = int(port)
                else:
                    host = server
                    port = 50052
                
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                result = sock.connect_ex((host, port))
                sock.close()
                
                if result == 0:
                    results.append(f"✓ {server} - 连接成功")
                else:
                    results.append(f"✗ {server} - 连接失败 (错误码: {result})")
            except Exception as e:
                results.append(f"✗ {server} - 错误: {str(e)}")
        
        result_text = "\n".join(results)
        self.log_message(f"RPC连接测试结果:\n{result_text}")
        QMessageBox.information(self, "测试结果", result_text)
    
    def start_rpc_server(self):
        """启动RPC服务器（从服务器模式）"""
        if self.rpc_server_process and self.rpc_server_process.state() == QProcess.Running:
            QMessageBox.warning(self, "警告", "RPC Server 已在运行中")
            return
        
        exe_path = os.path.join(os.path.dirname(__file__), "llama-bin", "rpc-server.exe")
        
        if not os.path.exists(exe_path):
            QMessageBox.critical(self, "错误", f"找不到 rpc-server.exe\n路径: {exe_path}")
            return
        
        host = self.worker_host_edit.text()
        port = self.worker_port_spin.value()
        gpu = self.worker_gpu_spin.value()
        
        cmd = [exe_path, "--host", host, "--port", str(port)]
        
        self.rpc_server_process = QProcess(self)
        self.rpc_server_process.readyReadStandardOutput.connect(self.read_rpc_output)
        self.rpc_server_process.readyReadStandardError.connect(self.read_rpc_error)
        self.rpc_server_process.finished.connect(self.rpc_process_finished)
        
        env = QProcessEnvironment.systemEnvironment()
        env.insert("CUDA_VISIBLE_DEVICES", str(gpu))
        self.rpc_server_process.setProcessEnvironment(env)
        
        self.rpc_server_process.start(cmd[0], cmd[1:])
        
        if self.rpc_server_process.waitForStarted(3000):
            self.start_worker_btn.setEnabled(False)
            self.stop_worker_btn.setEnabled(True)
            self.worker_status_label.setText("状态: 启动中...")
            self.worker_status_label.setStyleSheet("color: orange; font-weight: bold;")
            
            local_ip = self.get_local_ip()
            self.worker_url_label.setText(f"外部访问地址: {local_ip}:{port}")
            
            self.log_message(f"RPC Server 启动中: {' '.join(cmd)}")
            self.log_message(f"GPU {gpu} 已分配给 RPC Server")
        else:
            QMessageBox.critical(self, "错误", "RPC Server 启动失败")
            self.log_message("RPC Server 启动失败")
    
    def stop_rpc_server(self):
        """停止RPC服务器"""
        if self.rpc_server_process and self.rpc_server_process.state() == QProcess.Running:
            self.rpc_server_process.kill()
            self.rpc_server_process.waitForFinished(3000)
            self.start_worker_btn.setStyleSheet("")
            self.stop_worker_btn.setStyleSheet("")
            self.log_message("RPC Server 已停止")
    
    def rpc_process_finished(self, exit_code, exit_status):
        """RPC进程结束"""
        self.start_worker_btn.setEnabled(True)
        self.stop_worker_btn.setEnabled(False)
        self.worker_status_label.setText("状态: 已停止")
        self.worker_status_label.setStyleSheet("color: red; font-weight: bold;")
        self.worker_url_label.setText("")
        self.start_worker_btn.setStyleSheet("")
        self.stop_worker_btn.setStyleSheet("")
        self.log_message(f"RPC Server 进程结束，退出码: {exit_code}")
    
    def read_rpc_output(self):
        """读取RPC服务器输出"""
        data = self.rpc_server_process.readAllStandardOutput()
        text = bytes(data).decode('utf-8', errors='ignore')
        self.log_text.append(f"[RPC] {text.strip()}")
        
        if "listening" in text.lower() or "started" in text.lower():
            self.worker_status_label.setText("状态: 运行中")
            self.worker_status_label.setStyleSheet("color: green; font-weight: bold;")
            self.start_worker_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; border: none; border-radius: 5px;")
            self.stop_worker_btn.setStyleSheet("background-color: #f44336; color: white; font-weight: bold; border: none; border-radius: 5px;")
            self.log_message("RPC Server 已就绪，等待主服务器连接")
    
    def read_rpc_error(self):
        """读取RPC服务器错误输出"""
        data = self.rpc_server_process.readAllStandardError()
        text = bytes(data).decode('utf-8', errors='ignore')
        self.log_text.append(f"<span style='color: red;'>[RPC Error] {text.strip()}</span>")
    
    def get_local_ip(self):
        """获取本机局域网IP地址"""
        import socket
        try:
            # 创建一个UDP连接来获取本机IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "无法获取"
    
    def on_lan_access_changed(self, state):
        """局域网访问开关状态变化"""
        if state == Qt.Checked:
            self.host_edit.setText("0.0.0.0")
            local_ip = self.get_local_ip()
            port = self.port_spin.value()
            self.lan_ip_label.setText(f"本机局域网IP: http://{local_ip}:{port}")
            self.lan_ip_label.setVisible(True)
            self.log_message(f"已开启局域网访问，其他设备可通过 http://{local_ip}:{port} 访问")
        else:
            self.host_edit.setText("127.0.0.1")
            self.lan_ip_label.setVisible(False)
            self.log_message("已关闭局域网访问，仅本机可访问")

    def _open_content_dialog(self, title, content_widget, min_width=640, min_height=500):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setMinimumSize(min_width, min_height)
        layout = QVBoxLayout(dialog)
        content_widget.setParent(dialog)
        content_widget.setVisible(True)
        layout.addWidget(content_widget)
        close_btn = QPushButton("关闭")
        close_btn.setFixedHeight(32)
        close_btn.setStyleSheet("background-color: #3498db; color: white; font-weight: bold; border: none; border-radius: 4px;")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        dialog.exec_()
        content_widget.setParent(None)
        content_widget.setVisible(False)

    def open_param_dialog(self):
        self._open_content_dialog("参数配置", self._param_content, 700, 550)

    def open_preset_dialog(self):
        self._open_content_dialog("参数预设", self._preset_content, 450, 300)

    def open_optimize_dialog(self):
        self._open_content_dialog("参数自动优化", self._optimize_content, 500, 450)

    def open_status_dialog(self):
        self._open_content_dialog("状态信息", self._status_content, 450, 300)

    # ---------- 模型目录历史管理 ----------
    MAX_MODEL_DIR_HISTORY = 10  # 最多保留多少条历史路径

    def _load_model_dir_history(self):
        """从 QSettings 读取历史模型路径列表。"""
        history = self.settings.value("llama_models_dir_history", [], type=list)
        # 过滤掉不存在的路径，去重保序
        seen = set()
        valid = []
        for p in history:
            if not isinstance(p, str):
                continue
            if p in seen:
                continue
            if not os.path.exists(p):
                continue
            seen.add(p)
            valid.append(p)
        return valid

    def _save_model_dir_history(self, history_list):
        """保存历史模型路径列表到 QSettings。"""
        self.settings.setValue("llama_models_dir_history", list(history_list))

    def _add_to_model_dir_history(self, path):
        """把一条路径加入历史（去重、置顶、限长）。返回新的历史列表。"""
        history = self._load_model_dir_history()
        if path in history:
            history.remove(path)
        history.insert(0, path)
        history = history[: self.MAX_MODEL_DIR_HISTORY]
        self._save_model_dir_history(history)
        return history

    def _refresh_model_dir_combo(self):
        """根据当前历史重新填充下拉，并选中 self.models_dir。"""
        if not hasattr(self, "model_dir_combo"):
            return
        # 临时断开信号，避免重置时触发 on_model_dir_selected
        blocked = self.model_dir_combo.blockSignals(True)
        try:
            self.model_dir_combo.clear()
            history = self._load_model_dir_history()
            for p in history:
                self.model_dir_combo.addItem(p, p)
            # 如果当前 models_dir 不在历史里，也加进去显示
            if self.models_dir and self.models_dir not in history:
                self.model_dir_combo.insertItem(0, self.models_dir, self.models_dir)
            # 选中当前
            idx = self.model_dir_combo.findData(self.models_dir)
            if idx >= 0:
                self.model_dir_combo.setCurrentIndex(idx)
        finally:
            self.model_dir_combo.blockSignals(blocked)

    def on_model_dir_selected(self, index):
        """下拉切换历史路径的回调：切换目录并重新扫描。"""
        if index < 0:
            return
        path = self.model_dir_combo.itemData(index)
        if not path or path == self.models_dir:
            return
        if not os.path.exists(path):
            QMessageBox.warning(self, "警告", f"路径不存在:\n{path}")
            # 恢复显示
            self._refresh_model_dir_combo()
            return
        self.models_dir = path
        self.settings.setValue("llama_models_dir", path)
        # 切换路径也属于主动操作，置顶到历史
        self._add_to_model_dir_history(path)
        self._refresh_model_dir_combo()
        self.log_message(f"📁 已切换模型目录: {path}")
        self.scan_models()

    def clear_model_dir_history(self):
        """清空所有历史路径，但保留当前正在使用的路径。"""
        history = self._load_model_dir_history()
        if not history:
            QMessageBox.information(self, "提示", "没有历史记录可清除")
            return
        reply = QMessageBox.question(
            self,
            "确认清除",
            f"将清空 {len(history)} 条历史路径记录。\n当前正在使用的目录不会被删除，但会从历史列表中移除。\n\n是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._save_model_dir_history([])
        # 保留当前路径到历史
        if self.models_dir and os.path.exists(self.models_dir):
            self._add_to_model_dir_history(self.models_dir)
        self._refresh_model_dir_combo()
        self.log_message("🧹 已清除模型路径历史记录（保留当前路径）")

    # ---------- 浏览 / 切换模型目录 ----------
    def browse_model_dir(self):
        """浏览选择模型文件夹，选择后更新 self.models_dir 并重新扫描模型。"""
        start_dir = self.models_dir if os.path.exists(self.models_dir) else ""
        chosen = QFileDialog.getExistingDirectory(
            self,
            "选择模型文件夹（将扫描该目录下所有 .gguf 文件）",
            start_dir,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if not chosen:
            return  # 用户取消
        # 更新模型目录并持久化
        self.models_dir = chosen
        self.settings.setValue("llama_models_dir", chosen)
        # 加入历史
        self._add_to_model_dir_history(chosen)
        self._refresh_model_dir_combo()
        self.log_message(f"📁 已切换模型目录: {chosen}")
        # 按现有逻辑重新扫描
        self.scan_models()

    def _update_model_dir_label(self):
        """同步刷新"当前模型目录"显示（向下兼容旧调用）。"""
        # 现在由下拉框呈现，直接刷新下拉即可
        self._refresh_model_dir_combo()

    def scan_models(self):
        self._update_model_dir_label()
        self.model_combo.clear()
        self.model_vision_info = {}
        self.mmproj_available = {}  # 记录哪些模型目录有mmproj文件
        models = []
        
        # 先扫描 mmproj 文件
        mmproj_dirs = set()
        if os.path.exists(self.models_dir):
            for root, dirs, files in os.walk(self.models_dir):
                for file in files:
                    if 'mmproj' in file.lower() and file.endswith('.gguf'):
                        mmproj_dirs.add(root)
                        self.log_message(f"找到 mmproj: {file}")
        
        if os.path.exists(self.models_dir):
            for root, dirs, files in os.walk(self.models_dir):
                for file in files:
                    if file.endswith('.gguf') and 'mmproj' not in file.lower():
                        model_path = os.path.join(root, file)
                        file_size = os.path.getsize(model_path)
                        size_str = self.format_size(file_size)
                        has_vision, vision_info = check_gguf_has_vision(model_path)
                        has_mmproj = root in mmproj_dirs
                        models.append((file, model_path, size_str, has_vision, has_mmproj, vision_info))
        
        if models:
            vision_count = 0
            self.log_message(f"找到 {len(models)} 个模型:")
            for name, path, size, has_vision, has_mmproj, vision_info in sorted(models):
                self.model_vision_info[path] = has_vision
                self.mmproj_available[path] = has_mmproj
                
                if has_vision or has_mmproj:
                    vision_count += 1
                    display_text = f"📷 {name} ({size})"
                    if vision_info == "内置视觉":
                        self.log_message(f"  - {name} ({size}) [📷 内置视觉编码器]")
                    elif has_mmproj:
                        self.log_message(f"  - {name} ({size}) [📷 支持视觉，有 mmproj 文件]")
                    else:
                        self.log_message(f"  - {name} ({size}) [📷 支持视觉，未找到 mmproj]")
                else:
                    display_text = f"{name} ({size})"
                    self.log_message(f"  - {display_text}")
                self.model_combo.addItem(display_text, path)
            
            self.log_message(f"其中 {vision_count} 个模型支持图片识别")
            
            last_model = self.settings.value("llama_last_model", "", type=str)
            if last_model:
                for i in range(self.model_combo.count()):
                    if self.model_combo.itemData(i) == last_model:
                        self.model_combo.setCurrentIndex(i)
                        self.log_message(f"✅ 已加载上次选择的模型")
                        break
        else:
            self.log_message("未找到模型文件，请检查模型目录")
            QMessageBox.warning(self, "警告", f"未在 {self.models_dir} 找到模型文件")
    
    def scan_mmproj(self):
        self.mmproj_files = {}  # 存储模型路径到mmproj路径的映射（同目录）
        
        if os.path.exists(self.models_dir):
            for root, dirs, files in os.walk(self.models_dir):
                for file in files:
                    if 'mmproj' in file.lower() and file.endswith('.gguf'):
                        mmproj_path = os.path.join(root, file)
                        
                        # 存储目录到mmproj的映射（用于同目录匹配）
                        dir_path = os.path.dirname(mmproj_path)
                        if dir_path not in self.mmproj_files:
                            self.mmproj_files[dir_path] = []
                        self.mmproj_files[dir_path].append(mmproj_path)
                        self.log_message(f"找到 mmproj: {file}")
    
    def open_model_folder(self):
        """打开当前选中的模型文件所在的文件夹"""
        model_path = self.model_combo.currentData()
        if not model_path:
            QMessageBox.information(self, "提示", "请先选择一个模型")
            return
        folder_path = os.path.dirname(model_path)
        if os.path.exists(folder_path):
            subprocess.Popen(['explorer', '/select,', model_path])
            self.log_message(f"📂 打开文件夹: {folder_path}")
        else:
            QMessageBox.warning(self, "错误", f"文件夹不存在:\n{folder_path}")

    def update_vision_status(self):
        """更新视觉状态标签，告知用户当前模型是否需要额外 mmproj"""
        model_path = self.model_combo.currentData()
        if not model_path:
            self.vision_status_label.setText("")
            return
        
        has_vision = self.model_vision_info.get(model_path, False)
        has_mmproj = self.mmproj_available.get(model_path, False)
        
        if has_vision and has_mmproj:
            self.vision_status_label.setText("📷 支持视觉 + 有 mmproj，勾选即可加载图片识别")
            self.vision_status_label.setStyleSheet("color: #4CAF50; font-size: 11px; font-weight: bold;")
            self.enable_vision_check.setEnabled(True)
        elif has_vision and not has_mmproj:
            self.vision_status_label.setText("📷 支持视觉但未找到 mmproj 文件，图片识别可能不可用")
            self.vision_status_label.setStyleSheet("color: #FF9800; font-size: 11px;")
            self.enable_vision_check.setEnabled(True)
        elif not has_vision and has_mmproj:
            self.vision_status_label.setText("✓ 有 mmproj 文件，勾选可加载图片识别")
            self.vision_status_label.setStyleSheet("color: #4CAF50; font-size: 11px;")
            self.enable_vision_check.setEnabled(True)
        else:
            self.vision_status_label.setText("纯文本模型，无图片识别功能")
            self.vision_status_label.setStyleSheet("color: #999; font-size: 11px;")
            self.enable_vision_check.setChecked(False)
            self.enable_vision_check.setEnabled(False)
      
    def auto_select_mmproj(self):
        """根据当前选择的模型自动选择对应的mmproj（同目录匹配）"""
        model_path = self.model_combo.currentData()
        if not model_path:
            self.log_message("auto_select_mmproj: 未选择模型")
            return None
        if not hasattr(self, 'mmproj_files'):
            self.log_message("auto_select_mmproj: mmproj_files 未初始化")
            return None
        
        model_dir = os.path.dirname(model_path)
        
        if model_dir in self.mmproj_files:
            mmproj_list = self.mmproj_files[model_dir]
            
            if len(mmproj_list) == 1:
                self.log_message(f"找到 mmproj: {os.path.basename(mmproj_list[0])}")
                return mmproj_list[0]
            else:
                best_match = None
                best_match_score = 0
                model_name = os.path.basename(model_path).replace('.gguf', '').lower()
                
                for mmproj_path in mmproj_list:
                    mmproj_name = os.path.basename(mmproj_path).replace('.gguf', '').lower()
                    mmproj_name_clean = mmproj_name.replace('mmproj', '').replace('-', '').replace('_', '').replace('.', '')
                    model_name_clean = model_name.replace('-', '').replace('_', '').replace('.', '')
                    
                    common_chars = set(model_name_clean) & set(mmproj_name_clean)
                    score = len(common_chars)
                    
                    if score > best_match_score:
                        best_match_score = score
                        best_match = mmproj_path
                
                if best_match:
                    self.log_message(f"匹配 mmproj: {os.path.basename(best_match)} (得分:{best_match_score})")
                return best_match
        else:
            self.log_message(f"模型目录中未找到 mmproj 文件: {model_dir}")
        
        return None

    def format_size(self, size_bytes):
        if size_bytes >= 1024**3:
            return f"{size_bytes / 1024**3:.2f} GB"
        elif size_bytes >= 1024**2:
            return f"{size_bytes / 1024**2:.2f} MB"
        elif size_bytes >= 1024:
            return f"{size_bytes / 1024:.2f} KB"
        else:
            return f"{size_bytes} B"

    def check_port_llama_server(self, host, port):
        """
        探测目标端口是否有 llama-server 在运行
        返回: (is_running: bool, model_info: str)
              is_running=True 且 model_info 非空 → llama-server 正在运行，model_info 为模型名
              is_running=True 且 model_info 为空 → 端口被其他程序占用
              is_running=False → 端口无服务
        """
        url = f"http://{host}:{port}"
        try:
            resp = requests.get(f"{url}/v1/models", timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("data", [])
                if models:
                    model_id = models[0].get("id", "")
                    return True, model_id
                return True, ""
        except requests.exceptions.ConnectionError:
            pass
        except Exception:
            pass
        return False, ""

    def kill_llama_server_on_port(self, host, port):
        """
        杀掉占用指定端口的 llama-server 进程（外部启动的也能杀）
        返回: (success: bool, message: str)
        """
        killed_pids = []
        try:
            # 用 netstat 找到占用端口的 PID
            result = subprocess.run(
                ["netstat", "-ano", "-p", "TCP"],
                capture_output=True, text=True, timeout=5
            )
            target_port_str = f":{port}"
            for line in result.stdout.split('\n'):
                if target_port_str in line and "LISTENING" in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        if pid.isdigit() and pid != '0':
                            # 验证该 PID 是否是 llama-server 进程
                            try:
                                task_result = subprocess.run(
                                    ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                                    capture_output=True, text=True, timeout=3
                                )
                                if "llama-server" in task_result.stdout.lower():
                                    killed_pids.append(pid)
                            except Exception:
                                pass
        except Exception as e:
            self.log_message(f"查找端口进程时出错: {e}")

        if not killed_pids:
            # 如果 netstat 没找到精确匹配，尝试直接杀所有 llama-server.exe 进程
            try:
                result = subprocess.run(
                    ["tasklist", "/FI", "IMAGENAME eq llama-server.exe", "/FO", "CSV", "/NH"],
                    capture_output=True, text=True, timeout=3
                )
                for line in result.stdout.strip().split('\n'):
                    if line and "llama-server" in line.lower():
                        parts = line.replace('"', '').split(',')
                        if len(parts) >= 2:
                            killed_pids.append(parts[1].strip())
            except Exception:
                pass

        if not killed_pids:
            return False, "未找到 llama-server 进程"

        for pid in killed_pids:
            try:
                subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, timeout=5)
                self.log_message(f"已强制终止 llama-server 进程 (PID: {pid})")
            except Exception as e:
                self.log_message(f"终止进程 PID:{pid} 失败: {e}")

        # 等待端口释放
        import socket
        for _ in range(15):
            time.sleep(0.5)
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex((host, port))
                sock.close()
                if result != 0:
                    return True, f"已终止 {len(killed_pids)} 个 llama-server 进程，端口已释放"
            except Exception:
                return True, f"已终止 {len(killed_pids)} 个 llama-server 进程"

        return True, f"已终止 {len(killed_pids)} 个 llama-server 进程，但端口可能尚未完全释放"

    def start_llama_server(self):
        if self.model_combo.count() == 0:
            QMessageBox.warning(self, "警告", "请先选择模型")
            return

        host = self.host_edit.text()
        port = self.port_spin.value()

        # ======== 第一级检测：探测端口是否有 llama-server 在运行 ========
        is_running, running_model = self.check_port_llama_server(host, port)

        if is_running:
            selected_model = os.path.basename(self.model_combo.currentData() or "")

            # 判断是否是同一个模型
            if running_model and (running_model == selected_model or running_model in selected_model or selected_model in running_model):
                # 同模型已在运行 → 恢复UI状态为"运行中"
                self.llama_status_label.setText("运行中")
                self.llama_status_label.setStyleSheet("color: green; font-weight: bold;")
                self.start_llama_btn.setEnabled(False)
                self.stop_llama_btn.setEnabled(True)
                self.start_llama_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #cccccc; 
                        color: #666666; 
                        font-weight: bold; 
                        border: none; 
                        border-radius: 4px;
                        padding: 4px 12px;
                    }
                """)
                self.stop_llama_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #f44336; 
                        color: white; 
                        font-weight: bold; 
                        border: none; 
                        border-radius: 4px;
                        padding: 4px 12px;
                    }
                    QPushButton:hover {
                        background-color: #d32f2f;
                    }
                """)
                self.service_status_label.setText("● 运行中")
                self.service_status_label.setStyleSheet("color: #4CAF50; font-size: 11px; font-weight: bold;")
                self.llama_api_url_label.setText(f"http://{host}:{port}")
                self.current_model_label.setText(running_model)
                self.log_message(f"检测到相同模型已在运行: {running_model}，已恢复运行状态")
                self.start_metrics_timer()
                return
            else:
                # 不同模型在运行 → 提示用户是否替换
                old_model_info = running_model if running_model else "未知模型"
                reply = QMessageBox.warning(
                    self, "检测到其他模型正在运行",
                    f"端口 {port} 上已有模型在运行:\n\n"
                    f"  运行中的模型: {old_model_info}\n"
                    f"  要加载的模型: {selected_model}\n\n"
                    f"继续加载将替换当前模型，显存会被释放后重新分配。\n"
                    f"是否替换？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply == QMessageBox.No:
                    self.log_message("用户取消替换，保持当前模型运行")
                    # 恢复UI状态为"运行中"
                    self.llama_status_label.setText("运行中")
                    self.llama_status_label.setStyleSheet("color: green; font-weight: bold;")
                    self.start_llama_btn.setEnabled(False)
                    self.stop_llama_btn.setEnabled(True)
                    self.start_llama_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #cccccc; 
                            color: #666666; 
                            font-weight: bold; 
                            border: none; 
                            border-radius: 4px;
                            padding: 4px 12px;
                        }
                    """)
                    self.stop_llama_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #f44336; 
                            color: white; 
                            font-weight: bold; 
                            border: none; 
                            border-radius: 4px;
                            padding: 4px 12px;
                        }
                        QPushButton:hover {
                            background-color: #d32f2f;
                        }
                    """)
                    self.service_status_label.setText("● 运行中")
                    self.service_status_label.setStyleSheet("color: #4CAF50; font-size: 11px; font-weight: bold;")
                    self.llama_api_url_label.setText(f"http://{host}:{port}")
                    self.current_model_label.setText(old_model_info)
                    self.start_metrics_timer()
                    return

                # 用户选择替换 → 先杀掉旧进程
                self.log_message(f"正在替换模型: {old_model_info} → {selected_model}")
                success, msg = self.kill_llama_server_on_port(host, port)
                self.log_message(msg)
                if not success:
                    QMessageBox.critical(self, "错误", f"无法终止旧模型进程:\n{msg}")
                    return

                # 同时清理自己的进程引用
                if self.llama_process and self.llama_process.state() == QProcess.Running:
                    self.llama_process = None

        # ======== 第二级检测：自己启动的进程是否还在运行 ========
        if self.llama_process and self.llama_process.state() == QProcess.Running:
            # 自己的进程还在，但端口探测没发现（可能刚启动还没监听）
            reply = QMessageBox.question(
                self, "确认",
                "检测到本程序启动的 Llama Server 进程仍在运行中，是否先停止再重新启动？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                self.llama_process.terminate()
                if not self.llama_process.waitForFinished(5000):
                    self.llama_process.kill()
                    self.llama_process.waitForFinished(3000)
            else:
                return

        model_path = self.model_combo.currentData()
        
        exe_path = os.path.join(os.path.dirname(__file__), "llama-bin", "llama-server.exe")
        
        if not os.path.exists(exe_path):
            QMessageBox.critical(self, "错误", f"找不到 llama-server.exe\n路径: {exe_path}")
            return
        
        # 构建命令
        cmd = [exe_path, "-m", model_path]
        
        # 基础参数
        cmd.extend(["-c", str(self.context_spin.value())])
        cmd.extend(["-b", str(self.batch_spin.value())])
        cmd.extend(["-ub", str(self.ubatch_spin.value())])
        cmd.extend(["-t", str(self.threads_spin.value())])
        cmd.extend(["-ngl", str(self.ngl_spin.value())])
        cmd.extend(["--port", str(self.port_spin.value())])
        cmd.extend(["--host", self.host_edit.text()])
        cmd.append("--metrics")
        if not self.enable_mtp_check.isChecked():
            cmd.append("--slots")
        
        apikey = self.apikey_combo.currentText()
        if apikey and apikey != "(不使用API密钥)":
            cmd.extend(["--api-key", apikey])
        
        if self.enable_vision_check.isChecked():
            mmproj_path = self.auto_select_mmproj()
            if mmproj_path:
                cmd.extend(["--mmproj", mmproj_path])
                self.log_message(f"📷 启用图片识别，加载 mmproj: {os.path.basename(mmproj_path)}")
            else:
                cmd.append("--no-mmproj-auto")
                self.log_message("⚠ 勾选了图片识别但未找到 mmproj 文件，仅加载文本模型")
        else:
            cmd.append("--no-mmproj-auto")
            self.log_message("图片识别未启用，仅加载文本模型")
        
        # MTP 加速参数
        mtp_enabled = self.enable_mtp_check.isChecked()
        self.log_message(f"[调试] MTP 复选框状态: {mtp_enabled}")
        if mtp_enabled:
            cmd.extend(["--spec-type", "draft-mtp"])
            cmd.extend(["--spec-draft-n-max", str(self.mtp_draft_spin.value())])
            cmd.extend(["-np", "1"])
            if self.parallel_spin.value() != 1:
                self.log_message("⚠ MTP 模式下强制使用 -np 1（并行序列数已自动调整为 1，避免上下文被均分）")
            self.log_message(f"⚡ 启用 MTP 加速，草稿数: {self.mtp_draft_spin.value()}")
        else:
            cmd.extend(["-np", str(self.parallel_spin.value())])
        
        if self.cache_type_combo.currentText() != "auto":
            cmd.extend(["-ctk", self.cache_type_combo.currentText()])
        
        if self.cache_type_v_combo.currentText() != "auto":
            cmd.extend(["-ctv", self.cache_type_v_combo.currentText()])
        
        if hasattr(self, 'enable_rpc_check') and self.enable_rpc_check.isChecked():
            rpc_servers = self.rpc_servers_edit.toPlainText().strip()
            if rpc_servers:
                servers_list = [s.strip() for s in rpc_servers.split('\n') if s.strip()]
                servers_str = ','.join(servers_list)
                cmd.extend(["--rpc", servers_str])
                self.log_message(f"启用分布式推理，连接远程GPU: {servers_str}")
        
        # 采样参数
        cmd.extend(["--temp", str(self.temp_spin.value())])
        cmd.extend(["--top-k", str(self.top_k_spin.value())])
        cmd.extend(["--top-p", str(self.top_p_spin.value())])
        cmd.extend(["--min-p", str(self.min_p_spin.value())])
        cmd.extend(["--repeat-penalty", str(self.repeat_penalty_spin.value())])
        
        if self.presence_penalty_spin.value() > 0:
            cmd.extend(["--presence-penalty", str(self.presence_penalty_spin.value())])
        
        if self.frequency_penalty_spin.value() > 0:
            cmd.extend(["--frequency-penalty", str(self.frequency_penalty_spin.value())])
        
        if self.ignore_eos_check.isChecked():
            cmd.append("--ignore-eos")
        
        # 高级参数
        fit_value = self.fit_combo.currentText().split("=")[0]
        cmd.extend(["--fit", fit_value])
        if fit_value == "on":
            self.log_message("启用显存自动适配，程序将自动计算最优GPU层数")
        
        if self.flash_attn_combo.currentText() != "auto":
            cmd.extend(["--flash-attn", self.flash_attn_combo.currentText()])
        
        mirostat_value = self.mirostat_combo.currentText()[0]
        if mirostat_value != "0":
            cmd.extend(["--mirostat", mirostat_value])
            cmd.extend(["--mirostat-lr", str(self.mirostat_lr_spin.value())])
            cmd.extend(["--mirostat-ent", str(self.mirostat_ent_spin.value())])
        
        if self.mlock_check.isChecked():
            cmd.append("--mlock")
        
        if not self.mmap_check.isChecked() or self.no_mmap_check.isChecked():
            cmd.append("--no-mmap")
        
        if self.no_kv_offload_check.isChecked():
            cmd.append("--no-kv-offload")
        
        if self.cpu_moe_check.isChecked():
            cmd.append("--cpu-moe")
        
        # 思考控制参数
        reasoning_budget_set = False
        if self.disable_qwen_thinking_check.isChecked():
            cmd.extend(["--reasoning", "off"])
            cmd.extend(["--reasoning-budget", "0"])
            reasoning_budget_set = True
        else:
            if self.reasoning_format_combo.currentText() != "auto":
                cmd.extend(["--reasoning-format", self.reasoning_format_combo.currentText()])
            cmd.extend(["--reasoning-budget", str(self.reasoning_budget_spin.value())])
            reasoning_budget_set = True
        
        # KV缓存优化参数
        if self.cache_reuse_spin.value() > 0:
            cmd.extend(["--cache-reuse", str(self.cache_reuse_spin.value())])
            self.log_message(f"启用KV缓存复用，阈值: {self.cache_reuse_spin.value()}")
        
        if self.cache_ram_spin.value() != 8192:
            cmd.extend(["--cache-ram", str(self.cache_ram_spin.value())])
        
        if not self.kv_unified_check.isChecked():
            cmd.append("--no-kv-unified")
        
        if self.clear_idle_check.isChecked():
            cmd.append("--cache-idle-slots")
        else:
            cmd.append("--no-cache-idle-slots")
        
        slot_save_path = self.slot_save_path_edit.text().strip()
        if slot_save_path:
            cmd.extend(["--slot-save-path", slot_save_path])
            self.log_message(f"启用插槽持久化: {slot_save_path}")
        
        # 新版思考模式参数
        if self.reasoning_combo.currentText() != "auto":
            cmd.extend(["--reasoning", self.reasoning_combo.currentText()])
        
        if not reasoning_budget_set and self.reasoning_budget_new_spin.value() != -1:
            cmd.extend(["--reasoning-budget", str(self.reasoning_budget_new_spin.value())])
        
        # 推测解码参数
        draft_model = self.draft_model_edit.text().strip()
        if draft_model:
            cmd.extend(["--spec-draft-model", draft_model])
            self.log_message(f"启用推测解码，草稿模型: {draft_model}")
            
            if self.spec_draft_ngl_spin.value() != 999:
                cmd.extend(["--spec-draft-ngl", str(self.spec_draft_ngl_spin.value())])
            
            if self.spec_draft_n_max_spin.value() != 16:
                cmd.extend(["--spec-draft-n-max", str(self.spec_draft_n_max_spin.value())])
            
            if self.spec_draft_n_min_spin.value() != 1:
                cmd.extend(["--spec-draft-n-min", str(self.spec_draft_n_min_spin.value())])
            
            if self.spec_draft_ctx_spin.value() != 0:
                cmd.extend(["--spec-draft-ctx-size", str(self.spec_draft_ctx_spin.value())])
        else:
            if self.spec_type_combo.currentText() != "none":
                cmd.extend(["--spec-type", self.spec_type_combo.currentText()])
                self.log_message(f"启用推测解码类型: {self.spec_type_combo.currentText()}")
        
        # TTS 语音合成参数
        vocoder_model = self.vocoder_model_edit.text().strip()
        if vocoder_model:
            # 检查文件是否存在
            if os.path.exists(vocoder_model):
                file_size = os.path.getsize(vocoder_model)
                self.log_message(f"[TTS调试] 声码器模型文件存在: {vocoder_model} ({file_size/1024/1024:.1f} MB)")
            else:
                self.log_message(f"[TTS调试] ⚠️ 声码器模型文件不存在: {vocoder_model}")
            
            cmd.extend(["--model-vocoder", vocoder_model])
            self.log_message(f"[TTS调试] 添加参数: --model-vocoder {vocoder_model}")
            
            if self.tts_guide_tokens_check.isChecked():
                cmd.append("--tts-use-guide-tokens")
                self.log_message("[TTS调试] 添加参数: --tts-use-guide-tokens")
            else:
                self.log_message("[TTS调试] 未启用 TTS 引导 Token")
        else:
            self.log_message("[TTS调试] 未设置声码器模型路径，TTS 未启用")
            hf_repo_v = self.vocoder_hf_repo_edit.text().strip()
            if hf_repo_v:
                cmd.extend(["--hf-repo-v", hf_repo_v])
                hf_file_v = self.vocoder_hf_file_edit.text().strip()
                if hf_file_v:
                    cmd.extend(["--hf-file-v", hf_file_v])
                self.log_message(f"[TTS调试] 将从 Hugging Face 下载声码器模型: {hf_repo_v}")
        
        # 合并自定义参数
        custom_text = self.custom_params_edit.toPlainText().strip()
        if custom_text:
            custom_args = self._parse_tq_params(custom_text)
            if custom_args:
                cmd.extend(custom_args)
                self.log_message(f"已添加 {len(custom_args)} 个自定义参数")
        
        self.llama_process = QProcess(self)
        self.llama_process.readyReadStandardOutput.connect(self.read_llama_output)
        self.llama_process.readyReadStandardError.connect(self.read_llama_error)
        self.llama_process.finished.connect(self.llama_process_finished)
        
        self.llama_process.start(cmd[0], cmd[1:])
        
        if self.llama_process.waitForStarted(3000):
            self.start_llama_btn.setEnabled(False)
            self.stop_llama_btn.setEnabled(True)
            self.llama_status_label.setText("启动中...")
            self.llama_status_label.setStyleSheet("color: orange; font-weight: bold;")
            self.start_llama_btn.setStyleSheet("""
                QPushButton {
                    background-color: #cccccc; 
                    color: #666666; 
                    font-weight: bold; 
                    border: none; 
                    border-radius: 4px;
                    padding: 4px 12px;
                }
            """)
            self.stop_llama_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f44336; 
                    color: white; 
                    font-weight: bold; 
                    border: none; 
                    border-radius: 4px;
                    padding: 4px 12px;
                }
                QPushButton:hover {
                    background-color: #d32f2f;
                }
            """)
            self.service_status_label.setText("● 启动中...")
            self.service_status_label.setStyleSheet("color: #FF9800; font-size: 11px; font-weight: bold;")
            self.llama_api_url_label.setText(f"http://{self.host_edit.text()}:{self.port_spin.value()}")
            self.current_model_label.setText(self.model_combo.currentText())
            self.log_message(f"Llama Server 启动中: {' '.join(cmd)}")
        else:
            QMessageBox.critical(self, "错误", "Llama Server 启动失败")
            self.log_message("Llama Server 启动失败")

    def stop_llama_server(self):
        """停止 llama-server：能停掉自己启动的进程和外部启动的进程"""
        host = self.host_edit.text()
        port = self.port_spin.value()
        stopped_own = False

        # 先尝试优雅停止自己启动的进程
        if self.llama_process and self.llama_process.state() == QProcess.Running:
            self.llama_process.terminate()
            if not self.llama_process.waitForFinished(5000):
                self.log_message("进程未能在5秒内退出，强制终止...")
                self.llama_process.kill()
                self.llama_process.waitForFinished(3000)
            stopped_own = True
            self.log_message("已停止本程序启动的 Llama Server 进程")

        # 检查端口上是否还有残留的 llama-server 进程（外部启动的）
        is_running, running_model = self.check_port_llama_server(host, port)
        if is_running:
            self.log_message(f"检测到端口 {port} 上仍有 llama-server 进程在运行，正在终止...")
            success, msg = self.kill_llama_server_on_port(host, port)
            self.log_message(msg)
        elif not stopped_own:
            # 自己没启动进程，端口也没检测到，但可能进程正在关闭中
            # 尝试直接检查是否有 llama-server.exe 进程
            try:
                result = subprocess.run(
                    ["tasklist", "/FI", "IMAGENAME eq llama-server.exe", "/NH"],
                    capture_output=True, text=True, timeout=3
                )
                if "llama-server" in result.stdout.lower():
                    self.log_message("检测到系统中存在 llama-server 进程，正在终止...")
                    success, msg = self.kill_llama_server_on_port(host, port)
                    self.log_message(msg)
                else:
                    self.log_message("未检测到运行中的 llama-server 进程")
            except Exception:
                self.log_message("未检测到运行中的 llama-server 进程")

        # 清理UI状态
        self._reset_llama_ui_stopped()
        self.log_message("Llama Server 已停止")
        self.stop_metrics_timer()

    def _reset_llama_ui_stopped(self):
        """重置 llama server 相关UI到"已停止"状态"""
        self.start_llama_btn.setEnabled(True)
        self.stop_llama_btn.setEnabled(False)
        self.llama_status_label.setText("已停止")
        self.llama_status_label.setStyleSheet("color: red; font-weight: bold;")
        self.start_llama_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50; 
                color: white; 
                font-weight: bold; 
                border: none; 
                border-radius: 4px;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.stop_llama_btn.setStyleSheet("""
            QPushButton {
                background-color: #cccccc; 
                color: #666666; 
                font-weight: bold; 
                border: none; 
                border-radius: 4px;
                padding: 4px 12px;
            }
        """)
        self.service_status_label.setText("● 已停止")
        self.service_status_label.setStyleSheet("color: #999999; font-size: 11px; font-weight: bold;")
        self.current_model_label.setText("未加载")

    def llama_process_finished(self, exit_code, exit_status):
        self._reset_llama_ui_stopped()
        self.log_message(f"Llama Server 进程结束，退出码: {exit_code}")
        self.stop_metrics_timer()

    # ========== TurboQuant-MTP 社区版控制 ==========

    def tq_log(self, message):
        if hasattr(self, 'tq_log_text') and self.tq_log_text is not None:
            from datetime import datetime
            ts = datetime.now().strftime("%H:%M:%S")
            self.tq_log_text.append(f"[{ts}] {message}")

    def _browse_tq_file(self, line_edit, file_filter):
        path, _ = QFileDialog.getOpenFileName(self, "选择文件", os.path.dirname(line_edit.text()), file_filter)
        if path:
            line_edit.setText(path)

    def _get_tq_default_params(self):
        return (
            "-c 120800 -b 2048 -ub 1024 -t 5 -ngl 80\n"
            "--spec-type mtp --spec-draft-n-max 2 -np 1\n"
            "-ctk q4_0 -ctv q4_0\n"
            "--temp 0.4 --top-k 40 --top-p 0.95 --min-p 0.05\n"
            "--repeat-penalty 1.1 --fit off --flash-attn on\n"
            "--no-mmap --reasoning off --reasoning-budget 0\n"
            "--cache-idle-slots --kv-unified --cont-batching"
        )

    def _get_tq_default_exe(self):
        d = os.path.join(os.path.dirname(__file__),
            "llama-bin", "llama-cpp-turboquant-mtp-v1.0.0-windows-x64-cuda12.4-sm-86")
        return os.path.join(d, "llama-server.exe")

    def _get_tq_default_model(self):
        return (r"D:\models"
            r"\unsloth\Qwen3.6-35B-A3B-MTP-GGUF\Qwen3.6-35B-A3B-UD-IQ4_NL.gguf")

    def _parse_tq_params(self, text):
        args = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            i = 0
            while i < len(parts):
                p = parts[i]
                if p.startswith("-"):
                    args.append(p)
                    if i + 1 < len(parts) and not parts[i + 1].startswith("-"):
                        args.append(parts[i + 1])
                        i += 2
                    else:
                        i += 1
                else:
                    i += 1
        return args

    def _copy_turboquant_cmd(self):
        exe_path = self.tq_exe_edit.text()
        model_path = self.tq_model_edit.text()
        port = self.tq_port_spin.value()
        params_text = self.tq_params_display.toPlainText()
        cmd = f'"{exe_path}" -m "{model_path}" --port {port} --host 127.0.0.1 --metrics\n'
        cmd += params_text
        clipboard = QApplication.clipboard()
        clipboard.setText(cmd)
        self.tq_log("完整命令已复制到剪贴板")

    def _save_turboquant_config(self):
        self.settings.setValue("turboquant_exe", self.tq_exe_edit.text())
        self.settings.setValue("turboquant_model", self.tq_model_edit.text())
        self.settings.setValue("turboquant_port", self.tq_port_spin.value())
        self.settings.setValue("turboquant_params", self.tq_params_display.toPlainText())
        self.tq_log("配置已保存")

    def _reset_turboquant_config(self):
        self.tq_exe_edit.setText(self._get_tq_default_exe())
        self.tq_model_edit.setText(self._get_tq_default_model())
        self.tq_port_spin.setValue(8081)
        self.tq_params_display.setPlainText(self._get_tq_default_params())
        self.tq_log("已恢复默认配置")

    def _load_turboquant_config(self):
        saved_exe = self.settings.value("turboquant_exe", "", type=str)
        saved_model = self.settings.value("turboquant_model", "", type=str)
        saved_port = self.settings.value("turboquant_port", -1, type=int)
        saved_params = self.settings.value("turboquant_params", "", type=str)

        self.tq_exe_edit.setText(saved_exe if saved_exe else self._get_tq_default_exe())
        self.tq_model_edit.setText(saved_model if saved_model else self._get_tq_default_model())
        self.tq_port_spin.setValue(saved_port if saved_port > 0 else 8081)
        self.tq_params_display.setPlainText(saved_params if saved_params else self._get_tq_default_params())

    def start_turboquant_server(self):
        exe_path = self.tq_exe_edit.text()
        model_path = self.tq_model_edit.text()
        port = self.tq_port_spin.value()
        host = "127.0.0.1"
        params_text = self.tq_params_display.toPlainText()

        if not os.path.exists(exe_path):
            QMessageBox.critical(self, "错误",
                f"找不到社区版执行文件:\n{exe_path}\n\n"
                f"请确认已下载并解压到正确位置。")
            return

        if not os.path.exists(model_path):
            QMessageBox.critical(self, "错误", f"找不到模型文件:\n{model_path}")
            return

        is_running, running_model = self.check_port_llama_server(host, port)
        if is_running:
            reply = QMessageBox.warning(
                self, "端口被占用",
                f"端口 {port} 上已有 Llama Server 在运行。\n"
                f"如需启动社区版，请先停止该服务。\n\n"
                f"是否先停止该服务？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                success, msg = self.kill_llama_server_on_port(host, port)
                self.tq_log(msg)
                if self.llama_process and self.llama_process.state() == QProcess.Running:
                    self.llama_process = None
                self._reset_llama_ui_stopped()
                if not success:
                    return
            else:
                return

        if self.turboquant_process and self.turboquant_process.state() == QProcess.Running:
            reply = QMessageBox.question(
                self, "确认",
                "社区版进程仍在运行中，是否先停止再重新启动？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                self.stop_turboquant_server()
            else:
                return

        cmd = [exe_path, "-m", model_path]
        extra_args = self._parse_tq_params(params_text)
        cmd.extend(extra_args)
        cmd.extend(["--port", str(port)])
        cmd.extend(["--host", host])
        cmd.append("--metrics")

        self.turboquant_process = QProcess(self)
        self.turboquant_process.readyReadStandardOutput.connect(self.read_turboquant_output)
        self.turboquant_process.readyReadStandardError.connect(self.read_turboquant_error)
        self.turboquant_process.finished.connect(self.turboquant_process_finished)

        env = QProcessEnvironment.systemEnvironment()
        self.turboquant_process.setProcessEnvironment(env)
        self.turboquant_process.start(cmd[0], cmd[1:])

        if self.turboquant_process.waitForStarted(3000):
            self.tq_start_btn.setEnabled(False)
            self.tq_stop_btn.setEnabled(True)
            self.tq_status_label.setText("● 启动中...")
            self.tq_status_label.setStyleSheet("color: #FF9800; font-size: 11px; font-weight: bold;")
            self.tq_start_btn.setStyleSheet("""
                QPushButton {
                    background-color: #cccccc;
                    color: #666666;
                    font-weight: bold;
                    border: none;
                    border-radius: 4px;
                    padding: 4px 16px;
                    font-size: 10pt;
                }
            """)
            self.tq_stop_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f44336;
                    color: white;
                    font-weight: bold;
                    border: none;
                    border-radius: 4px;
                    padding: 4px 16px;
                    font-size: 10pt;
                }
                QPushButton:hover {
                    background-color: #d32f2f;
                }
            """)
            self.tq_log("社区版 TurboQuant-MTP 启动中...")
            self.tq_log(f"命令: {' '.join(cmd)}")
        else:
            QMessageBox.critical(self, "错误", "社区版启动失败")
            self.tq_log("错误: 社区版启动失败")
            self.turboquant_process = None

    def stop_turboquant_server(self):
        if self.turboquant_process and self.turboquant_process.state() == QProcess.Running:
            self.turboquant_process.terminate()
            if not self.turboquant_process.waitForFinished(5000):
                self.tq_log("进程未能在5秒内退出，强制终止...")
                self.turboquant_process.kill()
                self.turboquant_process.waitForFinished(3000)
            self.tq_log("社区版已停止")
        else:
            host = "127.0.0.1"
            port = self.tq_port_spin.value()
            is_running, running_model = self.check_port_llama_server(host, port)
            if is_running:
                success, msg = self.kill_llama_server_on_port(host, port)
                self.tq_log(msg)
            else:
                self.tq_log("未检测到运行中的社区版进程")

        self._reset_turboquant_ui_stopped()

    def _reset_turboquant_ui_stopped(self):
        self.tq_start_btn.setEnabled(True)
        self.tq_stop_btn.setEnabled(False)
        self.tq_status_label.setText("● 已停止")
        self.tq_status_label.setStyleSheet("color: #999999; font-size: 11px; font-weight: bold;")
        self.tq_start_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 4px 16px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.tq_stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #cccccc;
                color: #666666;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 4px 16px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #d32f2f;
                color: white;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)

    def turboquant_process_finished(self, exit_code, exit_status):
        self._reset_turboquant_ui_stopped()
        self.tq_log(f"社区版进程结束，退出码: {exit_code}")

    def read_turboquant_output(self):
        if not self.turboquant_process:
            return
        data = self.turboquant_process.readAllStandardOutput()
        text = bytes(data).decode('utf-8', errors='ignore').strip()
        if not text:
            return
        self.tq_log(text)

        if "server listening" in text.lower() or "build info" in text.lower():
            self.tq_status_label.setText("● 运行中")
            self.tq_status_label.setStyleSheet("color: #4CAF50; font-size: 11px; font-weight: bold;")
            self.tq_stop_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f44336;
                    color: white;
                    font-weight: bold;
                    border: none;
                    border-radius: 4px;
                    padding: 4px 16px;
                    font-size: 10pt;
                }
                QPushButton:hover {
                    background-color: #d32f2f;
                }
            """)
            model_name = os.path.basename(self.tq_model_edit.text())
            self.tq_log("✅ 社区版 TurboQuant-MTP 启动成功！")
            self.tq_log(f"🌐 API地址: http://127.0.0.1:{self.tq_port_spin.value()}")
            self.tq_log(f"📦 模型: {model_name}")

    def read_turboquant_error(self):
        if not self.turboquant_process:
            return
        data = self.turboquant_process.readAllStandardError()
        text = bytes(data).decode('utf-8', errors='ignore').strip()
        if not text:
            return
        self.tq_log(text)

        if "server listening" in text.lower() or "build info" in text.lower():
            self.tq_status_label.setText("● 运行中")
            self.tq_status_label.setStyleSheet("color: #4CAF50; font-size: 11px; font-weight: bold;")
            self.tq_stop_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f44336;
                    color: white;
                    font-weight: bold;
                    border: none;
                    border-radius: 4px;
                    padding: 4px 16px;
                    font-size: 10pt;
                }
                QPushButton:hover {
                    background-color: #d32f2f;
                }
            """)
            model_name = os.path.basename(self.tq_model_edit.text())
            self.tq_log("✅ 社区版 TurboQuant-MTP 启动成功！")
            self.tq_log(f"🌐 API地址: http://127.0.0.1:{self.tq_port_spin.value()}")
            self.tq_log(f"📦 模型: {model_name}")

    # ========== 启动时自动检测端口同步状态 ==========

    def _check_turboquant_running_on_startup(self):
        QTimer.singleShot(2000, self._do_turboquant_startup_check)

    def _do_turboquant_startup_check(self):
        host = "127.0.0.1"
        port = int(self.settings.value("turboquant_port", 8081, type=int))
        is_running, running_model = self.check_port_llama_server(host, port)
        if is_running:
            self.tq_start_btn.setEnabled(False)
            self.tq_stop_btn.setEnabled(True)
            self.tq_status_label.setText("● 运行中")
            self.tq_status_label.setStyleSheet("color: #4CAF50; font-size: 11px; font-weight: bold;")
            self.tq_stop_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f44336;
                    color: white;
                    font-weight: bold;
                    border: none;
                    border-radius: 4px;
                    padding: 4px 16px;
                    font-size: 10pt;
                }
                QPushButton:hover {
                    background-color: #d32f2f;
                }
            """)
            self.tq_log(f"🔍 检测到端口 {port} 已有服务运行")
            if running_model:
                self.tq_log(f"📦 已加载模型: {running_model}")
            self.tq_log("💡 可通过「停止社区版」按钮终止该服务")

    def read_llama_output(self):
        data = self.llama_process.readAllStandardOutput()
        text = bytes(data).decode('utf-8', errors='ignore')
        self.log_text.append(f"[Llama] {text.strip()}")

        if "HTTP server listening" in text or "server listening" in text.lower():
            self.llama_status_label.setText("运行中")
            self.llama_status_label.setStyleSheet("color: green; font-weight: bold;")
            self.start_llama_btn.setStyleSheet("""
                QPushButton {
                    background-color: #cccccc; 
                    color: #666666; 
                    font-weight: bold; 
                    border: none; 
                    border-radius: 4px;
                    padding: 4px 12px;
                }
            """)
            self.stop_llama_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f44336; 
                    color: white; 
                    font-weight: bold; 
                    border: none; 
                    border-radius: 4px;
                    padding: 4px 12px;
                }
                QPushButton:hover {
                    background-color: #d32f2f;
                }
            """)
            self.service_status_label.setText("● 运行中")
            self.service_status_label.setStyleSheet("color: #4CAF50; font-size: 11px; font-weight: bold;")
            self.print_startup_summary()
        
        if "prompt eval time" in text:
            match = re.search(r'prompt eval time = [\d.]+ ms / (\d+) tokens', text)
            if match:
                input_tokens = int(match.group(1))
                self.total_input_tokens += input_tokens
                self.current_input_tokens = input_tokens
                self.log_message(f"[Token] 解析到输入token: {input_tokens}")
                self.update_token_stats()
        
        if re.search(r'eval time = [\d.]+ ms / \d+ tokens', text) and "prompt eval time" not in text:
            match = re.search(r'eval time = [\d.]+ ms / (\d+) tokens', text)
            if match:
                output_tokens = int(match.group(1))
                self.total_output_tokens += output_tokens
                self.current_output_tokens = output_tokens
                self.log_message(f"[Token] 解析到输出token: {output_tokens}")
                self.update_token_stats()
        
        # TTS 相关输出过滤
        tts_keywords = ["vocoder", "model-vocoder", "tts", "audio", "wave", "speech", "声码器", "语音"]
        if any(kw in text.lower() for kw in tts_keywords):
            self.log_text.append(f"<span style='color: #FF9800; font-weight: bold;'>[TTS] {text.strip()}</span>")

    def print_startup_summary(self):
        summary = []
        summary.append("✅ Llama Server 启动成功！")
        summary.append("─" * 40)
        summary.append(f"📦 模型: {self.model_combo.currentText()}")
        summary.append(f"🌐 API地址: http://{self.host_edit.text()}:{self.port_spin.value()}")
        summary.append(f"📝 上下文长度: {self.context_spin.value()}")
        summary.append(f"⚡ 批处理大小: {self.batch_spin.value()}")
        summary.append(f"🖥️ CPU线程: {self.threads_spin.value()}")
        summary.append(f"🎮 GPU层数: {self.ngl_spin.value()}")
        
        apikey = self.apikey_combo.currentText()
        if apikey and apikey != "(不使用API密钥)":
            summary.append(f"🔑 API密钥: {apikey[:4]}***")
        else:
            summary.append(f"🔑 API密钥: 未设置")
        
        if hasattr(self, 'enable_rpc_check') and self.enable_rpc_check.isChecked():
            rpc_servers = self.rpc_servers_edit.toPlainText().strip()
            if rpc_servers:
                summary.append(f"🔗 分布式推理: 已启用")
                summary.append(f"   远程GPU: {rpc_servers.replace(chr(10), ', ')}")
        
        # TTS 状态
        vocoder_model = self.vocoder_model_edit.text().strip()
        if vocoder_model:
            if os.path.exists(vocoder_model):
                file_size = os.path.getsize(vocoder_model)
                summary.append(f"🔊 语音合成 (TTS): 已启用 ({file_size/1024/1024:.0f} MB)")
                if self.tts_guide_tokens_check.isChecked():
                    summary.append(f"   引导 Token: 已开启")
            else:
                summary.append(f"⚠️ 语音合成 (TTS): 模型文件不存在")
        else:
            summary.append(f"🔇 语音合成 (TTS): 未启用")
        
        summary.append("─" * 40)
        summary.append("💡 提示: 可在 Open WebUI 中访问此 API")
        
        self.log_text.append(f"<span style='color: #4CAF50; font-weight: bold;'>{chr(10).join(summary)}</span>")
        self.start_time = time.time()
    
    def update_token_stats(self):
        html = (
            f"<span style='color: #2196F3; font-size: 18px;'>输入: {self.current_input_tokens}</span> "
            f"<span style='color: #888;'>({self.input_speed:.0f} t/s)</span>　　"
            f"<span style='color: #4CAF50; font-size: 18px;'>输出: {self.current_output_tokens}</span> "
            f"<span style='color: #888;'>({self.output_speed:.0f} t/s)</span><br><br>"
            f"<span style='color: #666;'>累计输入:</span> <span style='color: #2196F3;'>{self.total_input_tokens}</span>　　"
            f"<span style='color: #666;'>累计输出:</span> <span style='color: #4CAF50;'>{self.total_output_tokens}</span>"
        )
        self.token_stats_label.setText(html)
        if hasattr(self, 'token_stats_display'):
            self.token_stats_display.setText(html)
    
    def start_metrics_timer(self):
        self.stop_metrics_timer()
        self.metrics_timer = QTimer()
        self.metrics_timer.timeout.connect(self.fetch_llama_metrics)
        self.metrics_timer.start(2000)
    
    def stop_metrics_timer(self):
        if hasattr(self, 'metrics_timer') and self.metrics_timer:
            self.metrics_timer.stop()
            self.metrics_timer.deleteLater()
            self.metrics_timer = None
    
    def fetch_llama_metrics(self):
        pass
    
    def parse_metrics(self, metrics_text):
        prompt_tokens = 0
        completion_tokens = 0
        for line in metrics_text.split('\n'):
            if line.startswith('llm_prompt_tokens_total'):
                match = re.search(r'(\d+)', line.split()[-1])
                if match:
                    prompt_tokens = int(match.group(1))
            elif line.startswith('llm_completion_tokens_total'):
                match = re.search(r'(\d+)', line.split()[-1])
                if match:
                    completion_tokens = int(match.group(1))
        self.log_message(f"[Metrics] 解析结果: 输入={prompt_tokens}, 输出={completion_tokens}")
        if prompt_tokens > 0 or completion_tokens > 0:
            self.total_input_tokens = prompt_tokens
            self.total_output_tokens = completion_tokens
            self.update_token_stats()

    def read_llama_error(self):
        data = self.llama_process.readAllStandardError()
        text = bytes(data).decode('utf-8', errors='ignore')
        self.log_text.append(f"<span style='color: #666;'>[Llama] {text.strip()}</span>")
        
        # 检测启动成功（llama.cpp 的启动信息可能在 stderr 中）
        if "HTTP server listening" in text or "server listening" in text.lower():
            self.llama_status_label.setText("运行中")
            self.llama_status_label.setStyleSheet("color: green; font-weight: bold;")
            self.start_llama_btn.setStyleSheet("""
                QPushButton {
                    background-color: #cccccc; 
                    color: #666666; 
                    font-weight: bold; 
                    border: none; 
                    border-radius: 4px;
                    padding: 4px 12px;
                }
            """)
            self.stop_llama_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f44336; 
                    color: white; 
                    font-weight: bold; 
                    border: none; 
                    border-radius: 4px;
                    padding: 4px 12px;
                }
                QPushButton:hover {
                    background-color: #d32f2f;
                }
            """)
            self.service_status_label.setText("● 运行中")
            self.service_status_label.setStyleSheet("color: #4CAF50; font-size: 11px; font-weight: bold;")
            self.print_startup_summary()
        
        self.stderr_buffer += text.replace('\r\n', '\n').replace('\r', '\n')
        
        while '\n' in self.stderr_buffer:
            line, self.stderr_buffer = self.stderr_buffer.split('\n', 1)
            line = line.strip()
            if not line:
                continue
            
            if "prompt eval time" in line:
                match = re.search(r'prompt eval time\s*=\s*[\d.]+\s*ms\s*/\s*(\d+)\s*tokens.*?([\d.]+)\s*tokens per second', line)
                if match:
                    input_tokens = int(match.group(1))
                    self.input_speed = float(match.group(2))
                    self.total_input_tokens += input_tokens
                    self.current_input_tokens = input_tokens
                    self.update_token_stats()
            
            if "eval time" in line and "prompt eval time" not in line:
                match = re.search(r'eval time\s*=\s*[\d.]+\s*ms\s*/\s*(\d+)\s*tokens.*?([\d.]+)\s*tokens per second', line)
                if match:
                    output_tokens = int(match.group(1))
                    self.output_speed = float(match.group(2))
                    self.total_output_tokens += output_tokens
                    self.current_output_tokens = output_tokens
                    self.update_token_stats()
            
            # TTS 相关错误/信息过滤
            tts_keywords = ["vocoder", "model-vocoder", "tts", "audio", "wave", "speech", "声码器", "语音"]
            if any(kw in line.lower() for kw in tts_keywords):
                self.log_text.append(f"<span style='color: #FF9800; font-weight: bold;'>[TTS] {line}</span>")

    def start_webui(self):
        if self.webui_process and self.webui_process.state() == QProcess.Running:
            QMessageBox.warning(self, "警告", "Open WebUI 已在运行中")
            return
        
        if self.auto_start_llama_check.isChecked():
            if not self.llama_process or self.llama_process.state() != QProcess.Running:
                self.log_message("正在启动 Llama Server...")
                self.start_llama_server()
                
                delay = self.startup_delay_spin.value()
                self.log_message(f"等待 {delay} 秒后启动 Open WebUI...")
                
                QTimer.singleShot(delay * 1000, self._do_start_webui)
            else:
                self.log_message("Llama Server 已在运行，直接启动 Open WebUI")
                QTimer.singleShot(1000, self._do_start_webui)
        else:
            self._do_start_webui()

    def _do_start_webui(self):
        hf_endpoint = self.hf_endpoint_edit.text()
        data_dir = self.data_dir_edit.text()
        port = self.webui_port_spin.value()
        
        if not os.path.exists(data_dir):
            try:
                os.makedirs(data_dir, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法创建数据目录: {e}")
                return
        
        self.webui_process = QProcess(self)
        
        env = QProcessEnvironment.systemEnvironment()
        env.insert("HF_ENDPOINT", hf_endpoint)
        env.insert("DATA_DIR", data_dir)
        env.insert("PORT", str(port))
        env.insert("CONTENT_LENGTH_MAX", "104857600")
        env.insert("DATA_UPLOAD_MAX_MEMORY_SIZE", "104857600")
        env.insert("MAX_BODY_SIZE", "104857600")
        # 配置 Open WebUI 使用 Llama Server 作为后端
        # 禁用 Ollama，使用 OpenAI 兼容 API
        env.insert("OLLAMA_BASE_URL", "")
        env.insert("OPENAI_API_BASE_URLS", f"http://127.0.0.1:{self.port_spin.value()}/v1")
        # 获取 API 密钥（从 combo 中获取，处理 "(不使用API密钥)" 的情况）
        apikey = self.apikey_combo.currentText()
        if apikey and apikey != "(不使用API密钥)":
            env.insert("OPENAI_API_KEYS", apikey)
        self.webui_process.setProcessEnvironment(env)
        
        self.webui_process.readyReadStandardOutput.connect(self.read_webui_output)
        self.webui_process.readyReadStandardError.connect(self.read_webui_error)
        self.webui_process.finished.connect(self.webui_process_finished)
        
        self.webui_process.start("open-webui", ["serve"])
        
        if self.webui_process.waitForStarted(5000):
            self.start_webui_btn.setEnabled(False)
            self.stop_webui_btn.setEnabled(True)
            self.webui_status_label.setText("启动中...")
            self.webui_status_label.setStyleSheet("color: orange; font-weight: bold;")
            self.webui_url_label.setText(f"http://127.0.0.1:{port}")
            self.log_message(f"Open WebUI 启动中 (端口: {port})")
        else:
            QMessageBox.critical(self, "错误", "Open WebUI 启动失败，请确保已安装 open-webui")
            self.log_message("Open WebUI 启动失败")

    def stop_webui(self):
        if self.webui_process and self.webui_process.state() == QProcess.Running:
            self.webui_process.kill()
            self.webui_process.waitForFinished(3000)
            self.start_webui_btn.setStyleSheet("")
            self.stop_webui_btn.setStyleSheet("")
            self.log_message("Open WebUI 已停止")

    def webui_process_finished(self, exit_code, exit_status):
        self.start_webui_btn.setEnabled(True)
        self.stop_webui_btn.setEnabled(False)
        self.webui_status_label.setText("已停止")
        self.webui_status_label.setStyleSheet("color: red; font-weight: bold;")
        self.start_webui_btn.setStyleSheet("")
        self.stop_webui_btn.setStyleSheet("")
        self.log_message(f"Open WebUI 进程结束，退出码: {exit_code}")

    def read_webui_output(self):
        data = self.webui_process.readAllStandardOutput()
        text = bytes(data).decode('utf-8', errors='ignore')
        self.log_text.append(f"[WebUI] {text.strip()}")
        
        if "Application startup complete" in text or "Running on" in text:
            self.webui_status_label.setText("运行中")
            self.webui_status_label.setStyleSheet("color: green; font-weight: bold;")
            self.start_webui_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; border: none; border-radius: 5px;")
            self.stop_webui_btn.setStyleSheet("background-color: #f44336; color: white; font-weight: bold; border: none; border-radius: 5px;")
            self.print_webui_summary()

    def print_webui_summary(self):
        summary = []
        summary.append("✅ Open WebUI 启动成功！")
        summary.append("─" * 40)
        summary.append(f"🌐 访问地址: http://127.0.0.1:{self.webui_port_spin.value()}")
        summary.append(f"🔗 后端API: http://127.0.0.1:{self.port_spin.value()}/v1")
        summary.append("─" * 40)
        summary.append("💡 提示: 在浏览器中打开上述地址即可使用")
        
        self.log_text.append(f"<span style='color: #4CAF50; font-weight: bold;'>{chr(10).join(summary)}</span>")

    def read_webui_error(self):
        data = self.webui_process.readAllStandardError()
        text = bytes(data).decode('utf-8', errors='ignore')
        
        if "INFO" in text:
            if "POST /api/chat" in text and "200" in text:
                self.request_count += 1
                self.log_text.append(f"<span style='color: #4CAF50;'>[WebUI] 💬 聊天请求成功 (累计: {self.request_count})</span>")
            elif "GET /api/notifications" in text:
                pass
            elif "200" in text or "201" in text:
                self.log_text.append(f"<span style='color: #666;'>[WebUI] {text.strip()}</span>")
            else:
                self.log_text.append(f"<span style='color: #FF9800;'>[WebUI] {text.strip()}</span>")
        elif "error" in text.lower() or "failed" in text.lower():
            self.log_text.append(f"<span style='color: red;'>[WebUI 错误] {text.strip()}</span>")
        else:
            self.log_text.append(f"<span style='color: #666;'>[WebUI] {text.strip()}</span>")

    def browse_data_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择数据目录", self.data_dir_edit.text())
        if dir_path:
            self.data_dir_edit.setText(dir_path)

    def browse_slot_save_path(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择插槽持久化目录", self.slot_save_path_edit.text())
        if dir_path:
            self.slot_save_path_edit.setText(dir_path)

    def _create_spec_decode_tab(self):
        spec_tab = QWidget()
        spec_layout = QFormLayout()

        spec_layout.addRow(QLabel("【草稿模型 - 推测解码加速】"))
        spec_layout.addRow(QLabel(
            "用小模型给大模型打草稿，大幅提升生成速度\n"
            "Gemma 4 系列官方草稿模型仅 ~1GB，可提速 1.5~3 倍"
        ))

        draft_model_layout = QHBoxLayout()
        self.draft_model_edit = QLineEdit()
        self.draft_model_edit.setPlaceholderText("选择草稿模型文件 (.gguf)")
        self.draft_model_edit.setToolTip(
            "草稿模型路径 (--spec-draft-model)\n"
            "用于推测解码的小模型\n\n"
            "推荐：\n"
            "• gemma-4-26B-it-assistant (~1GB)\n"
            "• gemma-4-31B-it-assistant (939MB)\n\n"
            "提示：留空=不使用推测解码"
        )
        self.draft_model_browse_btn = QPushButton("浏览...")
        self.draft_model_browse_btn.setMaximumWidth(60)
        self.draft_model_browse_btn.clicked.connect(self.browse_draft_model)
        draft_model_layout.addWidget(self.draft_model_edit)
        draft_model_layout.addWidget(self.draft_model_browse_btn)
        spec_layout.addRow("草稿模型 (--spec-draft-model):", draft_model_layout)

        self.spec_draft_ngl_spin = QSpinBox()
        self.spec_draft_ngl_spin.wheelEvent = lambda event: None
        self.spec_draft_ngl_spin.setRange(0, 999)
        self.spec_draft_ngl_spin.setValue(999)
        self.spec_draft_ngl_spin.setToolTip(
            "草稿模型 GPU 层数 (--spec-draft-ngl)\n"
            "将草稿模型多少层加载到显存\n\n"
            "推荐值：\n"
            "• 999：全部加载到 GPU（最快）\n"
            "• 0：全部在 CPU 运行\n\n"
            "提示：草稿模型很小，建议全放 GPU"
        )
        spec_layout.addRow("草稿 GPU 层数 (--spec-draft-ngl):", self.spec_draft_ngl_spin)

        self.spec_draft_n_max_spin = QSpinBox()
        self.spec_draft_n_max_spin.wheelEvent = lambda event: None
        self.spec_draft_n_max_spin.setRange(1, 128)
        self.spec_draft_n_max_spin.setValue(16)
        self.spec_draft_n_max_spin.setToolTip(
            "最大草稿 Token 数 (--spec-draft-n-max)\n"
            "草稿模型每次生成的最大 token 数量\n\n"
            "调整范围：1 - 128\n"
            "推荐值：16\n\n"
            "说明：\n"
            "• 越大：单次生成更多草稿，但验证开销也大\n"
            "• 越小：更保守，接受率可能更高\n\n"
            "建议：保持默认 16"
        )
        spec_layout.addRow("最大草稿 Token (--spec-draft-n-max):", self.spec_draft_n_max_spin)

        self.spec_draft_n_min_spin = QSpinBox()
        self.spec_draft_n_min_spin.wheelEvent = lambda event: None
        self.spec_draft_n_min_spin.setRange(1, 64)
        self.spec_draft_n_min_spin.setValue(1)
        self.spec_draft_n_min_spin.setToolTip(
            "最小草稿 Token 数 (--spec-draft-n-min)\n"
            "草稿模型每次生成的最小 token 数量\n\n"
            "调整范围：1 - 64\n"
            "推荐值：1\n\n"
            "说明：\n"
            "• 值越大：草稿越稳定，但灵活性降低\n\n"
            "建议：保持默认 1"
        )
        spec_layout.addRow("最小草稿 Token (--spec-draft-n-min):", self.spec_draft_n_min_spin)

        self.spec_draft_ctx_spin = QSpinBox()
        self.spec_draft_ctx_spin.wheelEvent = lambda event: None
        self.spec_draft_ctx_spin.setRange(0, 65536)
        self.spec_draft_ctx_spin.setValue(0)
        self.spec_draft_ctx_spin.setSpecialValueText("0=与主模型相同")
        self.spec_draft_ctx_spin.setToolTip(
            "草稿模型上下文 (--spec-draft-ctx-size)\n"
            "草稿模型的上下文大小\n\n"
            "调整范围：0 - 65536\n"
            "推荐值：0（与主模型相同）\n\n"
            "说明：\n"
            "• 0：与主模型上下文一致\n"
            "• >0：独立设置草稿模型上下文\n\n"
            "建议：保持默认 0"
        )
        spec_layout.addRow("草稿上下文 (--spec-draft-ctx-size):", self.spec_draft_ctx_spin)

        spec_layout.addRow(QLabel(""))
        spec_layout.addRow(QLabel("【无草稿模型时的推测解码】"))

        self.spec_type_combo = QComboBox()
        self.spec_type_combo.wheelEvent = lambda event: None
        self.spec_type_combo.addItems(["none", "ngram-cache", "ngram-simple", "ngram-map-k", "ngram-map-k4v", "ngram-mod"])
        self.spec_type_combo.setCurrentText("none")
        self.spec_type_combo.setToolTip(
            "推测解码类型 (--spec-type)\n"
            "不指定草稿模型时使用的推测解码方式\n\n"
            "选项：\n"
            "• none：禁用（默认）\n"
            "• ngram-cache：基于 n-gram 缓存\n"
            "• ngram-simple：简单 n-gram\n"
            "• ngram-map-k：K 映射 n-gram\n"
            "• ngram-map-k4v：K4V 映射 n-gram\n"
            "• ngram-mod：模块化 n-gram\n\n"
            "建议：有草稿模型时用草稿模型，否则保持 none"
        )
        spec_layout.addRow("推测解码类型 (--spec-type):", self.spec_type_combo)

        spec_tab.setLayout(spec_layout)
        return spec_tab

    def _create_tts_tab(self):
        tts_tab = QWidget()
        tts_layout = QFormLayout()

        tts_layout.addRow(QLabel("【文字转语音 (TTS) - 让模型开口说话】"))
        tts_layout.addRow(QLabel(
            "加载声码器模型后，模型回答的文字会自动转为语音输出\n"
            "支持 MOSS-TTS、MioTTS 等 GGUF 格式的 TTS 模型"
        ))

        vocoder_layout = QHBoxLayout()
        self.vocoder_model_edit = QLineEdit()
        self.vocoder_model_edit.setPlaceholderText("选择声码器模型文件 (.gguf)")
        self.vocoder_model_edit.setToolTip(
            "声码器模型路径 (--model-vocoder)\n"
            "用于将文字转为语音的模型\n\n"
            "推荐模型：\n"
            "• MOSS-TTS-GGUF (OpenMOSS 出品)\n"
            "• MioTTS (轻量快速)\n\n"
            "提示：留空=不使用 TTS"
        )
        self.vocoder_browse_btn = QPushButton("浏览...")
        self.vocoder_browse_btn.setMaximumWidth(60)
        self.vocoder_browse_btn.clicked.connect(self.browse_vocoder_model)
        vocoder_layout.addWidget(self.vocoder_model_edit)
        vocoder_layout.addWidget(self.vocoder_browse_btn)
        tts_layout.addRow("声码器模型 (--model-vocoder):", vocoder_layout)

        self.tts_guide_tokens_check = QCheckBox("使用引导 Token 改善 TTS 单词召回率 (--tts-use-guide-tokens)")
        self.tts_guide_tokens_check.setToolTip(
            "使用引导 Token 改善 TTS 单词召回率\n"
            "启用后，模型会生成引导 token 帮助声码器更准确地发音\n\n"
            "影响：\n"
            "• 启用：发音更准确，单词召回率更高\n"
            "• 禁用：速度略快\n\n"
            "建议：启用"
        )
        tts_layout.addRow("", self.tts_guide_tokens_check)

        tts_layout.addRow(QLabel(""))
        tts_layout.addRow(QLabel("【从 Hugging Face 下载声码器模型】"))

        hf_repo_layout = QHBoxLayout()
        self.vocoder_hf_repo_edit = QLineEdit()
        self.vocoder_hf_repo_edit.setPlaceholderText("例如: OpenMOSS-Team/MOSS-TTS-GGUF")
        self.vocoder_hf_repo_edit.setToolTip(
            "Hugging Face 仓库 (--hf-repo-v)\n"
            "自动从 Hugging Face 下载声码器模型\n\n"
            "格式：<用户>/<仓库>[:量化类型]\n"
            "示例：OpenMOSS-Team/MOSS-TTS-GGUF:Q4_K_M"
        )
        hf_repo_layout.addWidget(self.vocoder_hf_repo_edit)
        tts_layout.addRow("HF 仓库 (--hf-repo-v):", hf_repo_layout)

        hf_file_layout = QHBoxLayout()
        self.vocoder_hf_file_edit = QLineEdit()
        self.vocoder_hf_file_edit.setPlaceholderText("例如: moss-tts-8b-q4_k_m.gguf")
        self.vocoder_hf_file_edit.setToolTip(
            "Hugging Face 文件名 (--hf-file-v)\n"
            "指定要下载的具体文件名"
        )
        hf_file_layout.addWidget(self.vocoder_hf_file_edit)
        tts_layout.addRow("HF 文件名 (--hf-file-v):", hf_file_layout)

        tts_tab.setLayout(tts_layout)
        return tts_tab

    def _create_custom_params_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)

        hint = QLabel(
            "在此输入额外的命令行参数，每行一个或空格分隔。\n"
            "这些参数会追加到启动命令的末尾。\n"
            "提示：如果与上方已有控件参数冲突，后面的会覆盖前面的。"
        )
        hint.setStyleSheet("color: #666; font-size: 9pt;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.custom_params_edit = QTextEdit()
        self.custom_params_edit.setPlaceholderText(
            "示例：\n"
            "--sampling-seq ykdm\n"
            "--draft-max-n 5\n"
            "--draft-p-min 0.9\n"
            "--no-warmup\n"
            "--no-warmup-slots\n"
            "--slots 1"
        )
        self.custom_params_edit.setFont(QFont("Consolas", 9))
        layout.addWidget(self.custom_params_edit, 1)

        tab.setLayout(layout)
        return tab

    def browse_vocoder_model(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择声码器模型文件", "", "GGUF 模型 (*.gguf);;所有文件 (*)"
        )
        if file_path:
            self.vocoder_model_edit.setText(file_path)

    def browse_draft_model(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择草稿模型文件", "", "GGUF 模型 (*.gguf);;所有文件 (*)"
        )
        if file_path:
            self.draft_model_edit.setText(file_path)

    def copy_llama_api_url(self, event):
        url = self.llama_api_url_label.text()
        clipboard = QApplication.clipboard()
        clipboard.setText(url)
        self.log_message(f"已复制 Llama API 地址: {url}")

    def copy_webui_url(self, event):
        url = self.webui_url_label.text()
        clipboard = QApplication.clipboard()
        clipboard.setText(url)
        self.log_message(f"已复制 WebUI 访问地址: {url}")

    def clear_log(self):
        self.log_text.clear()

    def log_message(self, message):
        if not hasattr(self, 'log_text') or self.log_text is None:
            return
        self.log_text.append(f"<span style='color: blue;'>[{self.get_timestamp()}] {message}</span>")

    def get_timestamp(self):
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")

    def on_optimize_enabled_changed(self, state):
        """优化功能开关状态变化"""
        enabled = state == Qt.Checked
        self.start_optimize_btn.setEnabled(enabled)
        self.optimize_metric_combo.setEnabled(enabled)
        self.optimize_trials_spin.setEnabled(enabled)
        self.optimize_repeat_spin.setEnabled(enabled)
        
        if enabled:
            self.optimize_status_label.setText("状态: 已启用，点击开始优化")
            self.optimize_status_label.setStyleSheet("color: green;")
            self.log_message("自动优化功能已启用")
        else:
            self.optimize_status_label.setText("状态: 未启用")
            self.optimize_status_label.setStyleSheet("color: gray;")

    def start_optimization(self):
        """开始参数优化"""
        if self.model_combo.count() == 0:
            QMessageBox.warning(self, "警告", "请先选择模型")
            return
        
        llama_running = self.llama_process and self.llama_process.state() == QProcess.Running
        if llama_running:
            reply = QMessageBox.question(
                self, "确认",
                "Llama Server 正在运行！\n\n优化过程会加载模型到显存，可能导致显存不足。\n\n建议先停止 Llama Server 再运行优化。\n\n是否继续？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
        
        model_path = self.model_combo.currentData()
        if not model_path or not os.path.exists(model_path):
            QMessageBox.warning(self, "警告", "模型路径无效")
            return
        
        exe_path = os.path.join(os.path.dirname(__file__), "llama-bin", "llama-bench.exe")
        if not os.path.exists(exe_path):
            QMessageBox.critical(self, "错误", f"找不到 llama-bench.exe\n路径: {exe_path}")
            return
        
        self.start_optimize_btn.setEnabled(False)
        self.optimize_status_label.setText("状态: 优化中...")
        self.optimize_status_label.setStyleSheet("color: orange; font-weight: bold;")
        self.best_params = None
        self.best_params_label.setText("")
        
        self.log_message("=" * 50)
        self.log_message("🚀 开始参数自动优化...")
        self.log_message(f"📦 模型: {self.model_combo.currentText()}")
        self.log_message(f"📁 路径: {model_path}")
        self.log_message(f"🎯 目标: {self.optimize_metric_combo.currentText()}")
        self.log_message(f"🔄 尝试次数: {self.optimize_trials_spin.value()}")
        self.log_message("=" * 50)
        
        trials = self.optimize_trials_spin.value()
        repeat = self.optimize_repeat_spin.value()
        metric = self.optimize_metric_combo.currentIndex()
        
        batch_sizes = [32, 64, 128, 256, 512, 1024]
        ubatch_sizes = [32, 64, 128, 256, 512]
        threads_options = [4, 6, 8, 10, 12]
        
        best_score = 0
        best_config = None
        total_tests = min(trials, len(batch_sizes) * len(ubatch_sizes) * len(threads_options))
        test_count = 0
        
        for batch in batch_sizes:
            for ubatch in ubatch_sizes:
                for threads in threads_options:
                    if test_count >= trials:
                        break
                    
                    test_count += 1
                    
                    cmd = [
                        exe_path, "-m", model_path,
                        "-t", str(threads),
                        "-b", str(batch),
                        "-ub", str(ubatch),
                        "-ngl", str(self.ngl_spin.value()),
                        "-n", "64", "-p", "64",
                        "-r", str(repeat)
                    ]
                    
                    self.log_message(f"[{test_count}/{total_tests}] 测试: batch={batch}, ubatch={ubatch}, threads={threads}")
                    
                    try:
                        result = subprocess.run(
                            cmd,
                            capture_output=True,
                            text=True,
                            timeout=120,
                            cwd=os.path.dirname(__file__),
                            encoding='utf-8',
                            errors='replace'
                        )
                        
                        output = result.stdout + result.stderr
                        
                        if test_count == 1:
                            self.log_message(f"   [调试] 完整输出长度: {len(output)}")
                        
                        tg_score = 0
                        pp_score = 0
                        
                        for line in output.split('\n'):
                            line = line.strip()
                            if '|' in line and ('pp' in line or 'tg' in line):
                                parts = [p.strip() for p in line.split('|')]
                                for j, p in enumerate(parts):
                                    if 'pp' in p.lower() and j + 1 < len(parts):
                                        next_val = parts[j + 1]
                                        if '±' in next_val or any(c.isdigit() for c in next_val):
                                            try:
                                                speed_str = next_val.split('±')[0].strip()
                                                if not speed_str:
                                                    speed_str = next_val.split()[0] if next_val.split() else '0'
                                                pp_score = float(speed_str)
                                            except:
                                                pass
                                    elif 'tg' in p.lower() and j + 1 < len(parts):
                                        next_val = parts[j + 1]
                                        if '±' in next_val or any(c.isdigit() for c in next_val):
                                            try:
                                                speed_str = next_val.split('±')[0].strip()
                                                if not speed_str:
                                                    speed_str = next_val.split()[0] if next_val.split() else '0'
                                                tg_score = float(speed_str)
                                            except:
                                                pass
                        
                        if metric == 0:
                            score = tg_score
                        elif metric == 1:
                            score = pp_score
                        else:
                            if tg_score > 0 and pp_score > 0:
                                score = (tg_score + pp_score) / 2
                            else:
                                score = max(tg_score, pp_score)
                        
                        self.log_message(f"   结果: tg={tg_score:.2f}, pp={pp_score:.2f}, 综合得分={score:.2f}")
                        
                        if score > best_score:
                            best_score = score
                            best_config = {
                                'batch': batch,
                                'ubatch': ubatch,
                                'threads': threads,
                                'tg': tg_score,
                                'pp': pp_score,
                                'score': score
                            }
                            self.log_message(f"   ✅ 新最佳配置！")
                    
                    except subprocess.TimeoutExpired:
                        self.log_message(f"   ⚠️ 超时，跳过此配置")
                    except Exception as e:
                        self.log_message(f"   ❌ 错误: {str(e)}")
                
                if test_count >= trials:
                    break
            if test_count >= trials:
                break
        
        if best_config:
            self.best_params = best_config
            self.apply_optimize_btn.setEnabled(True)
            
            result_text = f"🏆 最佳配置:\n"
            result_text += f"batch={best_config['batch']}, ubatch={best_config['ubatch']}, threads={best_config['threads']}\n"
            result_text += f"tg={best_config['tg']:.2f} t/s, pp={best_config['pp']:.2f} t/s"
            
            self.best_params_label.setText(result_text)
            
            self.log_message("=" * 50)
            self.log_message("🎉 优化完成！")
            self.log_message(f"🏆 最佳配置: batch={best_config['batch']}, ubatch={best_config['ubatch']}, threads={best_config['threads']}")
            self.log_message(f"📊 性能: tg={best_config['tg']:.2f} t/s, pp={best_config['pp']:.2f} t/s")
            self.log_message("💡 点击'应用最佳参数'按钮应用此配置")
            self.log_message("=" * 50)
            
            self.optimize_status_label.setText("状态: 优化完成")
            self.optimize_status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.log_message("❌ 优化失败，未找到有效配置")
            self.optimize_status_label.setText("状态: 优化失败")
            self.optimize_status_label.setStyleSheet("color: red;")
        
        self.start_optimize_btn.setEnabled(True)

    def apply_best_params(self):
        """应用最佳参数到界面"""
        if not self.best_params:
            QMessageBox.warning(self, "警告", "没有可用的优化结果")
            return
        
        self.batch_spin.setValue(self.best_params['batch'])
        self.ubatch_spin.setValue(self.best_params['ubatch'])
        self.threads_spin.setValue(self.best_params['threads'])
        
        self.log_message("✅ 已应用最佳参数到界面")
        QMessageBox.information(self, "成功", f"已应用最佳参数:\n\nbatch={self.best_params['batch']}\nubatch={self.best_params['ubatch']}\nthreads={self.best_params['threads']}")

    def monitor_system_status(self):
        if not hasattr(self, 'log_text') or self.log_text is None:
            return
        
        status_parts = []
        
        llama_running = self.llama_process and self.llama_process.state() == QProcess.Running
        webui_running = self.webui_process and self.webui_process.state() == QProcess.Running
        rpc_running = self.rpc_server_process and self.rpc_server_process.state() == QProcess.Running
        
        if not (llama_running or webui_running or rpc_running):
            return
        
        status_parts.append("📊 系统状态监控")
        status_parts.append("─" * 40)
        
        if llama_running:
            model_name = self.model_combo.currentText() if self.model_combo.currentText() else "未知"
            status_parts.append(f"🟢 Llama Server: 运行中")
            status_parts.append(f"   模型: {model_name}")
            status_parts.append(f"   地址: http://{self.host_edit.text()}:{self.port_spin.value()}")
            if hasattr(self, 'status_server_label'):
                self.status_server_label.setText("🟢 运行中")
                self.status_server_label.setStyleSheet("font-size: 14px; color: green;")
            if hasattr(self, 'status_model_label'):
                self.status_model_label.setText(model_name)
            if hasattr(self, 'status_api_label'):
                self.status_api_label.setText(f"http://{self.host_edit.text()}:{self.port_spin.value()}")
        else:
            status_parts.append("⚫ Llama Server: 未运行")
            if hasattr(self, 'status_server_label'):
                self.status_server_label.setText("⚫ 未运行")
                self.status_server_label.setStyleSheet("font-size: 14px; color: red;")
        
        if webui_running:
            status_parts.append(f"🟢 Open WebUI: 运行中")
            status_parts.append(f"   地址: http://127.0.0.1:{self.webui_port_spin.value()}")
            if hasattr(self, 'status_webui_label'):
                self.status_webui_label.setText("🟢 运行中")
                self.status_webui_label.setStyleSheet("font-size: 14px; color: green;")
        else:
            status_parts.append("⚫ Open WebUI: 未运行")
            if hasattr(self, 'status_webui_label'):
                self.status_webui_label.setText("⚫ 未运行")
                self.status_webui_label.setStyleSheet("font-size: 14px; color: red;")
        
        if rpc_running:
            status_parts.append(f"🟢 RPC Server: 运行中")
            status_parts.append(f"   地址: {self.worker_host_edit.text()}:{self.worker_port_spin.value()}")
        
        try:
            import psutil
            mem = psutil.virtual_memory()
            mem_used = mem.used / (1024**3)
            mem_total = mem.total / (1024**3)
            mem_percent = mem.percent
            status_parts.append(f"💾 内存: {mem_used:.1f}/{mem_total:.1f} GB ({mem_percent}%)")
            if hasattr(self, 'status_memory_label'):
                self.status_memory_label.setText(f"{mem_used:.1f}/{mem_total:.1f} GB ({mem_percent}%)")
            
            cpu_percent = psutil.cpu_percent(interval=0.1)
            status_parts.append(f"🖥️ CPU: {cpu_percent}%")
            if hasattr(self, 'status_cpu_label'):
                self.status_cpu_label.setText(f"{cpu_percent}%")
        except ImportError:
            pass
        
        try:
            import subprocess
            import sys
            
            nvidia_cmd = ['nvidia-smi', '--query-gpu=memory.used,memory.total,utilization.gpu', 
                          '--format=csv,noheader,nounits']
            
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                result = subprocess.run(nvidia_cmd, capture_output=True, text=True, timeout=5, startupinfo=startupinfo)
            else:
                result = subprocess.run(nvidia_cmd, capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                gpu_info = []
                for i, line in enumerate(lines):
                    parts = [p.strip() for p in line.split(',')]
                    if len(parts) >= 3:
                        gpu_mem_used = float(parts[0])
                        gpu_mem_total = float(parts[1])
                        gpu_util = float(parts[2])
                        status_parts.append(f"🎮 GPU {i}: {gpu_mem_used:.0f}/{gpu_mem_total:.0f} MB ({gpu_util}% 利用率)")
                        gpu_info.append(f"GPU {i}: {gpu_mem_used:.0f}/{gpu_mem_total:.0f} MB ({gpu_util}%)")
                if hasattr(self, 'status_gpu_label') and gpu_info:
                    self.status_gpu_label.setText(" | ".join(gpu_info))
        except Exception:
            pass
        
        status_parts.append("─" * 40)
        
        self.log_text.append(f"<span style='color: #2196F3; font-weight: bold;'>{chr(10).join(status_parts)}</span>")

    def load_settings(self):
        # 模型目录（可由用户在界面浏览切换，持久化保存）
        saved_dir = self.settings.value("llama_models_dir", "", type=str)
        if saved_dir and os.path.exists(saved_dir):
            self.models_dir = saved_dir
        # 确保当前路径在历史记录里（首次启动或老版本升级时兼容）
        if self.models_dir and os.path.exists(self.models_dir):
            self._add_to_model_dir_history(self.models_dir)
        self._update_model_dir_label()

        # 基础参数
        self.context_spin.setValue(self.settings.value("llama_context", 8192, type=int))
        self.batch_spin.setValue(self.settings.value("llama_batch", 32, type=int))
        self.ubatch_spin.setValue(self.settings.value("llama_ubatch", 512, type=int))
        self.threads_spin.setValue(self.settings.value("llama_threads", 6, type=int))
        self.parallel_spin.setValue(self.settings.value("llama_parallel", 1, type=int))
        self.port_spin.setValue(self.settings.value("llama_port", 8081, type=int))
        self.host_edit.setText(self.settings.value("llama_host", "127.0.0.1"))
        
        # 加载API密钥列表
        apikeys = self.settings.value("llama_apikeys", [], type=list)
        last_apikey = self.settings.value("llama_last_apikey", "", type=str)
        self.apikey_combo.clear()
        self.apikey_combo.addItem("(不使用API密钥)")
        for key in apikeys[:10]:
            if key and key not in [self.apikey_combo.itemText(i) for i in range(self.apikey_combo.count())]:
                self.apikey_combo.addItem(key)
        if last_apikey and last_apikey in apikeys:
            self.apikey_combo.setCurrentText(last_apikey)
        else:
            self.apikey_combo.setCurrentIndex(0)
        
        self.ngl_spin.setValue(self.settings.value("llama_ngl", 999, type=int))
        self.cache_type_combo.setCurrentText(self.settings.value("llama_cache_type", "auto"))
        self.cache_type_v_combo.setCurrentText(self.settings.value("llama_cache_type_v", "auto"))
        self.enable_vision_check.setChecked(self.settings.value("llama_enable_vision", True, type=bool))
        
        # 采样参数
        self.temp_spin.setValue(self.settings.value("llama_temp", 0.7, type=float))
        self.top_k_spin.setValue(self.settings.value("llama_top_k", 40, type=int))
        self.top_p_spin.setValue(self.settings.value("llama_top_p", 0.95, type=float))
        self.min_p_spin.setValue(self.settings.value("llama_min_p", 0.05, type=float))
        self.repeat_penalty_spin.setValue(self.settings.value("llama_repeat_penalty", 1.1, type=float))
        self.presence_penalty_spin.setValue(self.settings.value("llama_presence_penalty", 0.0, type=float))
        self.frequency_penalty_spin.setValue(self.settings.value("llama_frequency_penalty", 0.0, type=float))
        self.ignore_eos_check.setChecked(self.settings.value("llama_ignore_eos", False, type=bool))
        
        # 高级参数
        self.flash_attn_combo.setCurrentText(self.settings.value("llama_flash_attn", "auto"))
        self.mirostat_combo.setCurrentText(self.settings.value("llama_mirostat", "0=禁用"))
        self.mirostat_lr_spin.setValue(self.settings.value("llama_mirostat_lr", 0.1, type=float))
        self.mirostat_ent_spin.setValue(self.settings.value("llama_mirostat_ent", 5.0, type=float))
        self.mlock_check.setChecked(self.settings.value("llama_mlock", False, type=bool))
        self.mmap_check.setChecked(self.settings.value("llama_mmap", True, type=bool))
        self.no_mmap_check.setChecked(self.settings.value("llama_no_mmap", False, type=bool))
        self.no_kv_offload_check.setChecked(self.settings.value("llama_no_kv_offload", False, type=bool))
        self.cpu_moe_check.setChecked(self.settings.value("llama_cpu_moe", False, type=bool))
        self.fit_combo.setCurrentText(self.settings.value("llama_fit", "on=自动适配"))
        
        # 缓存优化参数
        self.cache_reuse_spin.setValue(self.settings.value("llama_cache_reuse", 0, type=int))
        self.cache_ram_spin.setValue(self.settings.value("llama_cache_ram", 8192, type=int))
        self.kv_unified_check.setChecked(self.settings.value("llama_kv_unified", True, type=bool))
        self.clear_idle_check.setChecked(self.settings.value("llama_clear_idle", True, type=bool))
        self.slot_save_path_edit.setText(self.settings.value("llama_slot_save_path", ""))
        
        # 新版思考模式参数
        self.reasoning_combo.setCurrentText(self.settings.value("llama_reasoning_mode", "auto"))
        self.reasoning_budget_new_spin.setValue(self.settings.value("llama_reasoning_budget_new", -1, type=int))
        
        # 推测解码参数
        self.draft_model_edit.setText(self.settings.value("spec_draft_model", ""))
        self.spec_draft_ngl_spin.setValue(self.settings.value("spec_draft_ngl", 999, type=int))
        self.spec_draft_n_max_spin.setValue(self.settings.value("spec_draft_n_max", 16, type=int))
        self.spec_draft_n_min_spin.setValue(self.settings.value("spec_draft_n_min", 1, type=int))
        self.spec_draft_ctx_spin.setValue(self.settings.value("spec_draft_ctx", 0, type=int))
        self.spec_type_combo.setCurrentText(self.settings.value("spec_type", "none"))
        
        # MTP 加速参数
        self.enable_mtp_check.setChecked(self.settings.value("llama_enable_mtp", False, type=bool))
        self.mtp_draft_spin.setValue(self.settings.value("llama_mtp_draft", 3, type=int))
        
        # TTS 语音合成参数
        self.vocoder_model_edit.setText(self.settings.value("tts_vocoder_model", ""))
        self.tts_guide_tokens_check.setChecked(self.settings.value("tts_guide_tokens", False, type=bool))
        self.vocoder_hf_repo_edit.setText(self.settings.value("tts_hf_repo_v", ""))
        self.vocoder_hf_file_edit.setText(self.settings.value("tts_hf_file_v", ""))
        
        # 自动优化参数
        self.enable_optimize_check.setChecked(self.settings.value("llama_enable_optimize", False, type=bool))
        self.optimize_metric_combo.setCurrentIndex(self.settings.value("llama_optimize_metric", 0, type=int))
        self.optimize_trials_spin.setValue(self.settings.value("llama_optimize_trials", 20, type=int))
        self.optimize_repeat_spin.setValue(self.settings.value("llama_optimize_repeat", 3, type=int))
        self.on_optimize_enabled_changed(self.enable_optimize_check.checkState())
        
        # 思考控制
        self.reasoning_format_combo.setCurrentText(self.settings.value("llama_reasoning_format", "none"))
        self.reasoning_budget_spin.setValue(self.settings.value("llama_reasoning_budget", 0, type=int))
        self.disable_reasoning_check.setChecked(self.settings.value("llama_disable_reasoning", True, type=bool))
        self.disable_qwen_thinking_check.setChecked(self.settings.value("llama_disable_qwen_thinking", True, type=bool))
        
        # 自定义参数加载
        custom_params = self.settings.value("llama_custom_params", "", type=str)
        if custom_params:
            self.custom_params_edit.setPlainText(custom_params)
        
        # 应用思考模式状态
        self.toggle_reasoning(self.disable_reasoning_check.isChecked())
        
        # 局域网访问设置
        lan_access = self.settings.value("llama_lan_access", False, type=bool)
        self.lan_access_check.setChecked(lan_access)
        if lan_access:
            self.on_lan_access_changed(Qt.Checked)
        
        # Open WebUI 参数
        self.hf_endpoint_edit.setText(self.settings.value("webui_hf_endpoint", "https://hf-mirror.com"))
        self.data_dir_edit.setText(self.settings.value("webui_data_dir", "C:\\open-webui\\data"))
        self.webui_port_spin.setValue(self.settings.value("webui_port", 3000, type=int))
        self.auto_start_llama_check.setChecked(self.settings.value("webui_auto_start_llama", True, type=bool))
        self.startup_delay_spin.setValue(self.settings.value("webui_startup_delay", 10, type=int))
        
        # 分布式推理参数
        if hasattr(self, 'mode_combo'):
            self.mode_combo.setCurrentIndex(self.settings.value("distributed_mode", 0, type=int))
            self.enable_rpc_check.setChecked(self.settings.value("distributed_enable_rpc", False, type=bool))
            self.rpc_servers_edit.setPlainText(self.settings.value("distributed_rpc_servers", ""))
            self.enable_worker_check.setChecked(self.settings.value("distributed_enable_worker", False, type=bool))
            self.worker_host_edit.setText(self.settings.value("distributed_worker_host", "0.0.0.0"))
            self.worker_port_spin.setValue(self.settings.value("distributed_worker_port", 50052, type=int))
            self.worker_gpu_spin.setValue(self.settings.value("distributed_worker_gpu", 0, type=int))

        # 社区版 TurboQuant-MTP 配置加载
        self._load_turboquant_config()
        self._check_turboquant_running_on_startup()

    def save_settings(self):
        # 保存当前选择的模型
        current_model = self.model_combo.currentData()
        if current_model:
            self.settings.setValue("llama_last_model", current_model)
        
        # 基础参数
        self.settings.setValue("llama_context", self.context_spin.value())
        self.settings.setValue("llama_batch", self.batch_spin.value())
        self.settings.setValue("llama_ubatch", self.ubatch_spin.value())
        self.settings.setValue("llama_threads", self.threads_spin.value())
        self.settings.setValue("llama_parallel", self.parallel_spin.value())
        self.settings.setValue("llama_port", self.port_spin.value())
        self.settings.setValue("llama_host", self.host_edit.text())
        
        # 保存API密钥列表
        current_apikey = self.apikey_combo.currentText()
        if current_apikey and current_apikey != "(不使用API密钥)":
            apikeys = self.settings.value("llama_apikeys", [], type=list)
            if current_apikey in apikeys:
                apikeys.remove(current_apikey)
            apikeys.insert(0, current_apikey)
            apikeys = apikeys[:10]
            self.settings.setValue("llama_apikeys", apikeys)
            self.settings.setValue("llama_last_apikey", current_apikey)
        else:
            self.settings.setValue("llama_last_apikey", "")
        
        self.settings.setValue("llama_ngl", self.ngl_spin.value())
        
        # 采样参数
        self.settings.setValue("llama_temp", self.temp_spin.value())
        self.settings.setValue("llama_top_k", self.top_k_spin.value())
        self.settings.setValue("llama_top_p", self.top_p_spin.value())
        self.settings.setValue("llama_min_p", self.min_p_spin.value())
        self.settings.setValue("llama_repeat_penalty", self.repeat_penalty_spin.value())
        self.settings.setValue("llama_presence_penalty", self.presence_penalty_spin.value())
        self.settings.setValue("llama_frequency_penalty", self.frequency_penalty_spin.value())
        self.settings.setValue("llama_ignore_eos", self.ignore_eos_check.isChecked())
        
        # 高级参数
        self.settings.setValue("llama_flash_attn", self.flash_attn_combo.currentText())
        self.settings.setValue("llama_mirostat", self.mirostat_combo.currentText())
        self.settings.setValue("llama_mirostat_lr", self.mirostat_lr_spin.value())
        self.settings.setValue("llama_mirostat_ent", self.mirostat_ent_spin.value())
        self.settings.setValue("llama_mlock", self.mlock_check.isChecked())
        self.settings.setValue("llama_mmap", self.mmap_check.isChecked())
        self.settings.setValue("llama_no_mmap", self.no_mmap_check.isChecked())
        self.settings.setValue("llama_no_kv_offload", self.no_kv_offload_check.isChecked())
        self.settings.setValue("llama_cpu_moe", self.cpu_moe_check.isChecked())
        self.settings.setValue("llama_cache_type", self.cache_type_combo.currentText())
        self.settings.setValue("llama_cache_type_v", self.cache_type_v_combo.currentText())
        self.settings.setValue("llama_enable_vision", self.enable_vision_check.isChecked())
        self.settings.setValue("llama_fit", self.fit_combo.currentText())
        
        # 缓存优化参数
        self.settings.setValue("llama_cache_reuse", self.cache_reuse_spin.value())
        self.settings.setValue("llama_cache_ram", self.cache_ram_spin.value())
        self.settings.setValue("llama_kv_unified", self.kv_unified_check.isChecked())
        self.settings.setValue("llama_clear_idle", self.clear_idle_check.isChecked())
        self.settings.setValue("llama_slot_save_path", self.slot_save_path_edit.text())
        
        # 新版思考模式参数
        self.settings.setValue("llama_reasoning_mode", self.reasoning_combo.currentText())
        self.settings.setValue("llama_reasoning_budget_new", self.reasoning_budget_new_spin.value())
        
        # 推测解码参数
        self.settings.setValue("spec_draft_model", self.draft_model_edit.text())
        self.settings.setValue("spec_draft_ngl", self.spec_draft_ngl_spin.value())
        self.settings.setValue("spec_draft_n_max", self.spec_draft_n_max_spin.value())
        self.settings.setValue("spec_draft_n_min", self.spec_draft_n_min_spin.value())
        self.settings.setValue("spec_draft_ctx", self.spec_draft_ctx_spin.value())
        self.settings.setValue("spec_type", self.spec_type_combo.currentText())
        
        # MTP 加速参数
        self.settings.setValue("llama_enable_mtp", self.enable_mtp_check.isChecked())
        self.settings.setValue("llama_mtp_draft", self.mtp_draft_spin.value())
        
        # TTS 语音合成参数
        self.settings.setValue("tts_vocoder_model", self.vocoder_model_edit.text())
        self.settings.setValue("tts_guide_tokens", self.tts_guide_tokens_check.isChecked())
        self.settings.setValue("tts_hf_repo_v", self.vocoder_hf_repo_edit.text())
        self.settings.setValue("tts_hf_file_v", self.vocoder_hf_file_edit.text())
        
        # 自动优化参数
        self.settings.setValue("llama_enable_optimize", self.enable_optimize_check.isChecked())
        self.settings.setValue("llama_optimize_metric", self.optimize_metric_combo.currentIndex())
        self.settings.setValue("llama_optimize_trials", self.optimize_trials_spin.value())
        self.settings.setValue("llama_optimize_repeat", self.optimize_repeat_spin.value())
        
        # 思考控制
        self.settings.setValue("llama_reasoning_format", self.reasoning_format_combo.currentText())
        self.settings.setValue("llama_reasoning_budget", self.reasoning_budget_spin.value())
        self.settings.setValue("llama_disable_reasoning", self.disable_reasoning_check.isChecked())
        self.settings.setValue("llama_disable_qwen_thinking", self.disable_qwen_thinking_check.isChecked())
        self.settings.setValue("llama_lan_access", self.lan_access_check.isChecked())
        
        # Open WebUI 参数
        self.settings.setValue("webui_hf_endpoint", self.hf_endpoint_edit.text())
        self.settings.setValue("webui_data_dir", self.data_dir_edit.text())
        self.settings.setValue("webui_port", self.webui_port_spin.value())
        self.settings.setValue("webui_auto_start_llama", self.auto_start_llama_check.isChecked())
        self.settings.setValue("webui_startup_delay", self.startup_delay_spin.value())
        
        # 分布式推理参数
        if hasattr(self, 'mode_combo'):
            self.settings.setValue("distributed_mode", self.mode_combo.currentIndex())
            self.settings.setValue("distributed_enable_rpc", self.enable_rpc_check.isChecked())
            self.settings.setValue("distributed_rpc_servers", self.rpc_servers_edit.toPlainText())
            self.settings.setValue("distributed_enable_worker", self.enable_worker_check.isChecked())
            self.settings.setValue("distributed_worker_host", self.worker_host_edit.text())
            self.settings.setValue("distributed_worker_port", self.worker_port_spin.value())
            self.settings.setValue("distributed_worker_gpu", self.worker_gpu_spin.value())
        
        # 自定义参数保存
        self.settings.setValue("llama_custom_params", self.custom_params_edit.toPlainText())
        
        # 社区版 TurboQuant-MTP 配置保存
        self.settings.setValue("turboquant_exe", self.tq_exe_edit.text())
        self.settings.setValue("turboquant_model", self.tq_model_edit.text())
        self.settings.setValue("turboquant_port", self.tq_port_spin.value())
        self.settings.setValue("turboquant_params", self.tq_params_display.toPlainText())
        
        self.load_presets()
    
    def load_presets(self):
        """加载预设列表"""
        self.preset_combo.clear()
        self.preset_combo.addItem("(选择预设...)", "")
        presets = self.settings.value("presets", {}, type=dict)
        if presets:
            for name in sorted(presets.keys()):
                self.preset_combo.addItem(name, name)
    
    def save_preset(self):
        """保存当前参数为预设"""
        try:
            presets = self.settings.value("presets", {}, type=dict)
            existing_presets = list(presets.keys())
            
            dialog = PresetSaveDialog(existing_presets, self)
            if dialog.exec_() == QDialog.Accepted:
                preset_name = dialog.get_preset_name()
                
                if not preset_name:
                    QMessageBox.warning(self, "警告", "预设名称不能为空")
                    return
                
                if preset_name == "(选择预设...)":
                    QMessageBox.warning(self, "警告", "预设名称不能使用此名称")
                    return
                
                model_text = self.model_combo.currentText() if self.model_combo.count() > 0 else ""
                
                presets[preset_name] = {
                    "model": model_text,
                    "context": self.context_spin.value(),
                    "batch": self.batch_spin.value(),
                    "ubatch": self.ubatch_spin.value(),
                    "threads": self.threads_spin.value(),
                    "port": self.port_spin.value(),
                    "host": self.host_edit.text(),
                    "apikey": self.apikey_combo.currentText(),
                    "ngl": self.ngl_spin.value(),
                    "cache_type": self.cache_type_combo.currentText(),
                    "cache_type_v": self.cache_type_v_combo.currentText(),
                    "temp": self.temp_spin.value(),
                    "top_k": self.top_k_spin.value(),
                    "top_p": self.top_p_spin.value(),
                    "min_p": self.min_p_spin.value(),
                    "repeat_penalty": self.repeat_penalty_spin.value(),
                    "presence_penalty": self.presence_penalty_spin.value(),
                    "frequency_penalty": self.frequency_penalty_spin.value(),
                    "ignore_eos": self.ignore_eos_check.isChecked(),
                    "flash_attn": self.flash_attn_combo.currentText(),
                    "mirostat": self.mirostat_combo.currentText(),
                    "mirostat_lr": self.mirostat_lr_spin.value(),
                    "mirostat_ent": self.mirostat_ent_spin.value(),
                    "mlock": self.mlock_check.isChecked(),
                    "mmap": self.mmap_check.isChecked(),
                    "no_mmap": self.no_mmap_check.isChecked(),
                    "no_kv_offload": self.no_kv_offload_check.isChecked(),
                    "cpu_moe": self.cpu_moe_check.isChecked(),
                    "fit": self.fit_combo.currentText(),
                    "reasoning_format": self.reasoning_format_combo.currentText(),
                    "reasoning_budget": self.reasoning_budget_spin.value(),
                    "disable_reasoning": self.disable_reasoning_check.isChecked(),
                    "disable_qwen_thinking": self.disable_qwen_thinking_check.isChecked(),
                    "enable_vision": self.enable_vision_check.isChecked(),
                    "cache_reuse": self.cache_reuse_spin.value(),
                    "cache_ram": self.cache_ram_spin.value(),
                    "kv_unified": self.kv_unified_check.isChecked(),
                    "clear_idle": self.clear_idle_check.isChecked(),
                    "slot_save_path": self.slot_save_path_edit.text(),
                    "reasoning_mode": self.reasoning_combo.currentText(),
                    "reasoning_budget_new": self.reasoning_budget_new_spin.value(),
                    "spec_draft_model": self.draft_model_edit.text(),
                    "spec_draft_ngl": self.spec_draft_ngl_spin.value(),
                    "spec_draft_n_max": self.spec_draft_n_max_spin.value(),
                    "spec_draft_n_min": self.spec_draft_n_min_spin.value(),
                    "spec_draft_ctx": self.spec_draft_ctx_spin.value(),
                    "spec_type": self.spec_type_combo.currentText(),
                    "enable_mtp": self.enable_mtp_check.isChecked(),
                    "mtp_draft": self.mtp_draft_spin.value(),
                    "tts_vocoder_model": self.vocoder_model_edit.text(),
                    "tts_guide_tokens": self.tts_guide_tokens_check.isChecked(),
                    "tts_hf_repo_v": self.vocoder_hf_repo_edit.text(),
                    "tts_hf_file_v": self.vocoder_hf_file_edit.text()
                }
                
                self.settings.setValue("presets", presets)
                self.load_presets()
                QMessageBox.information(self, "成功", f"预设 '{preset_name}' 已保存")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存预设失败: {str(e)}")
    
    def load_preset(self, index):
        """加载选中的预设"""
        if index <= 0:
            return
        
        preset_name = self.preset_combo.itemData(index)
        presets = self.settings.value("presets", {}, type=dict)
        
        if preset_name and preset_name in presets:
            preset = presets[preset_name]
            
            self.model_combo.setCurrentText(preset.get("model", ""))
            self.context_spin.setValue(preset.get("context", 8192))
            self.batch_spin.setValue(preset.get("batch", 32))
            self.ubatch_spin.setValue(preset.get("ubatch", 512))
            self.threads_spin.setValue(preset.get("threads", 6))
            self.port_spin.setValue(preset.get("port", 8081))
            self.host_edit.setText(preset.get("host", "127.0.0.1"))
            apikey = preset.get("apikey", "")
            if apikey:
                self.apikey_combo.setCurrentText(apikey)
            else:
                self.apikey_combo.setCurrentIndex(0)
            self.ngl_spin.setValue(preset.get("ngl", 999))
            self.cache_type_combo.setCurrentText(preset.get("cache_type", "auto"))
            self.cache_type_v_combo.setCurrentText(preset.get("cache_type_v", "auto"))
            self.temp_spin.setValue(preset.get("temp", 0.7))
            self.top_k_spin.setValue(preset.get("top_k", 40))
            self.top_p_spin.setValue(preset.get("top_p", 0.95))
            self.min_p_spin.setValue(preset.get("min_p", 0.05))
            self.repeat_penalty_spin.setValue(preset.get("repeat_penalty", 1.1))
            self.presence_penalty_spin.setValue(preset.get("presence_penalty", 0.0))
            self.frequency_penalty_spin.setValue(preset.get("frequency_penalty", 0.0))
            self.ignore_eos_check.setChecked(preset.get("ignore_eos", False))
            self.flash_attn_combo.setCurrentText(preset.get("flash_attn", "auto"))
            self.mirostat_combo.setCurrentText(preset.get("mirostat", "0=禁用"))
            self.mirostat_lr_spin.setValue(preset.get("mirostat_lr", 0.1))
            self.mirostat_ent_spin.setValue(preset.get("mirostat_ent", 5.0))
            self.mlock_check.setChecked(preset.get("mlock", False))
            self.mmap_check.setChecked(preset.get("mmap", True))
            self.no_mmap_check.setChecked(preset.get("no_mmap", False))
            self.no_kv_offload_check.setChecked(preset.get("no_kv_offload", False))
            self.cpu_moe_check.setChecked(preset.get("cpu_moe", False))
            self.fit_combo.setCurrentText(preset.get("fit", "on=自动适配"))
            self.reasoning_format_combo.setCurrentText(preset.get("reasoning_format", "none"))
            self.reasoning_budget_spin.setValue(preset.get("reasoning_budget", 0))
            self.disable_reasoning_check.setChecked(preset.get("disable_reasoning", True))
            self.disable_qwen_thinking_check.setChecked(preset.get("disable_qwen_thinking", True))
            self.enable_vision_check.setChecked(preset.get("enable_vision", True))
            self.cache_reuse_spin.setValue(preset.get("cache_reuse", 0))
            self.cache_ram_spin.setValue(preset.get("cache_ram", 8192))
            self.kv_unified_check.setChecked(preset.get("kv_unified", True))
            self.clear_idle_check.setChecked(preset.get("clear_idle", True))
            self.slot_save_path_edit.setText(preset.get("slot_save_path", ""))
            self.reasoning_combo.setCurrentText(preset.get("reasoning_mode", "auto"))
            self.reasoning_budget_new_spin.setValue(preset.get("reasoning_budget_new", -1))
            self.draft_model_edit.setText(preset.get("spec_draft_model", ""))
            self.spec_draft_ngl_spin.setValue(preset.get("spec_draft_ngl", 999))
            self.spec_draft_n_max_spin.setValue(preset.get("spec_draft_n_max", 16))
            self.spec_draft_n_min_spin.setValue(preset.get("spec_draft_n_min", 1))
            self.spec_draft_ctx_spin.setValue(preset.get("spec_draft_ctx", 0))
            self.spec_type_combo.setCurrentText(preset.get("spec_type", "none"))
            self.enable_mtp_check.setChecked(preset.get("enable_mtp", False))
            self.mtp_draft_spin.setValue(preset.get("mtp_draft", 3))
            self.vocoder_model_edit.setText(preset.get("tts_vocoder_model", ""))
            self.tts_guide_tokens_check.setChecked(preset.get("tts_guide_tokens", False))
            self.vocoder_hf_repo_edit.setText(preset.get("tts_hf_repo_v", ""))
            self.vocoder_hf_file_edit.setText(preset.get("tts_hf_file_v", ""))
            
            QMessageBox.information(self, "成功", f"预设 '{preset_name}' 已加载")
    
    def delete_preset(self):
        """删除选中的预设"""
        index = self.preset_combo.currentIndex()
        if index <= 0:
            return
        
        preset_name = self.preset_combo.itemData(index)
        reply = QMessageBox.question(self, "确认删除", 
                f"确定要删除预设 '{preset_name}' 吗？",
                QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            presets = self.settings.value("presets", {}, type=dict)
            if preset_name in presets:
                del presets[preset_name]
                self.settings.setValue("presets", presets)
                self.load_presets()
                QMessageBox.information(self, "成功", f"预设 '{preset_name}' 已删除")
    
    def save_window_state(self):
        """保存窗口大小和位置"""
        self.settings.setValue("window_geometry", self.saveGeometry())
        self.settings.setValue("window_state", self.saveState())
    
    def restore_window_state(self):
        """恢复窗口大小和位置"""
        geometry = self.settings.value("window_geometry")
        if geometry:
            self.restoreGeometry(geometry)
        state = self.settings.value("window_state")
        if state:
            self.restoreState(state)
    
    def closeEvent(self, event):
        self.save_window_state()
        self.save_settings()
        
        running_services = []
        if self.llama_process and self.llama_process.state() == QProcess.Running:
            running_services.append("Llama Server")
        if self.webui_process and self.webui_process.state() == QProcess.Running:
            running_services.append("Open WebUI")
        if self.rpc_server_process and self.rpc_server_process.state() == QProcess.Running:
            running_services.append("RPC Server")
        
        if running_services:
            reply = QMessageBox.question(self, "确认", 
                f"以下服务正在运行:\n{chr(10).join(running_services)}\n\n确定要退出吗？",
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                if self.llama_process and self.llama_process.state() == QProcess.Running:
                    self.stop_llama_server()
                if self.webui_process and self.webui_process.state() == QProcess.Running:
                    self.stop_webui()
                if self.rpc_server_process and self.rpc_server_process.state() == QProcess.Running:
                    self.stop_rpc_server()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

# ============================================================
# 无头控制 API — 供外部（llama_swap.py）通过 HTTP 启停 llama-server
# GUI 启动时自动开启，监听 localhost:8092
# ============================================================

class _HeadlessAPIServer:
    """极简 HTTP API，运行在独立线程中，不阻塞 GUI 事件循环。"""
    
    def __init__(self, gui_instance, port=8092):
        self.gui = gui_instance
        self.port = port
        self.server = None
        self.thread = None
    
    def _dispatch(self, action):
        if action == 'start':
            self.gui.start_llama_btn.click()
            return {"status": "ok", "message": "已发送启动请求"}
        elif action == 'stop':
            self.gui.stop_llama_btn.click()
            return {"status": "ok", "message": "已发送停止请求"}
        elif action == 'status':
            is_running = (self.gui.llama_process is not None and 
                         self.gui.llama_process.state() == QProcess.Running)
            return {"running": is_running}
        else:
            return {"error": f"unknown action: {action}"}
    
    def start(self):
        """在独立线程中启动 HTTP 服务器。"""
        from http.server import HTTPServer, BaseHTTPRequestHandler

        api_server = self

        class _RequestHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path in ('/start', '/stop', '/status'):
                    action = self.path.lstrip('/')
                    result = api_server._dispatch(action)
                    body = json.dumps(result, ensure_ascii=False).encode('utf-8')
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json; charset=utf-8')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    body = json.dumps({"error": "not found"}).encode('utf-8')
                    self.send_response(404)
                    self.send_header('Content-Type', 'application/json; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(body)

            def log_message(self, format, *args):
                pass  # 静默日志

        self.server = HTTPServer(('127.0.0.1', self.port), _RequestHandler)

        import threading
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def shutdown(self):
        if self.server:
            self.server.shutdown()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    QToolTip.setFont(QFont("Microsoft YaHei", 9))
    QToolTip.setPalette(app.palette())
    QToolTip.showText(QPoint(0, 0), "")
    
    window = LlamaServerGUI()
    window.show()
    
    # 启动无头控制 API（HTTP localhost:8092）
    api_server = _HeadlessAPIServer(window)
    api_server.start()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

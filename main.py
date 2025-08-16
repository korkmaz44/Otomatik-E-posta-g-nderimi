#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Otomatik E-posta Gönderim Sistemi
Ana Uygulama Dosyası
"""
import sys
import os
import logging
from datetime import datetime, timedelta
import threading
import time
import platform
if platform.system() == "Windows":
    import winsound
import json
import subprocess

# PyQt5 importları
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QTabWidget, QPushButton, QLabel, 
                             QLineEdit, QTextEdit, QComboBox, QSpinBox, 
                             QCheckBox, QGroupBox, QGridLayout, QTableWidget,
                             QTableWidgetItem, QMessageBox, QFileDialog,
                             QProgressBar, QFrame, QScrollArea,
                             QSizePolicy, QMenu, QInputDialog, QDialog,
                             QColorDialog, QTimeEdit, QDateEdit, QListWidget,
                             QHeaderView)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QDateTime, QTime, QDate
from PyQt5.QtGui import QFont, QIcon, QPalette, QColor

# Proje modüllerini import et
from modules.database_manager import DatabaseManager
from modules.config_manager import ConfigManager
from modules.logger import Logger

# SMTP için gerekli import'lar
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email import encoders

def plain_text_to_html_with_lists(text):
    import re
    lines = text.splitlines()
    html_parts = []
    in_list = False
    list_type = None

    def close_list():
        nonlocal in_list, list_type
        if in_list:
            html_parts.append('</ul>' if list_type == 'ul' else '</ol>')
            in_list = False
            list_type = None

    for line in lines:
        if not line.strip():
            close_list()
            continue
        stripped = line.strip()
        m_num = re.match(r'^(\d+)[\.\)]\s+(.*)', stripped)
        m_bullet = re.match(r'^[-•*–—]\s+(.*)', stripped)
        indented = (len(line) - len(line.lstrip(' '))) >= 2
        if m_num:
            if not in_list or list_type != 'ol':
                close_list()
                html_parts.append('<ol style="margin:8px 0 12px 20px; padding:0;">')
                in_list = True
                list_type = 'ol'
            html_parts.append(f'<li style="margin:4px 0; line-height:1.35;">{m_num.group(2)}</li>')
        elif m_bullet or indented:
            content = m_bullet.group(1) if m_bullet else stripped
            if not in_list or list_type != 'ul':
                close_list()
                html_parts.append('<ul style="margin:8px 0 12px 20px; padding:0; list-style:disc;">')
                in_list = True
                list_type = 'ul'
            html_parts.append(f'<li style="margin:4px 0; line-height:1.35;">{content}</li>')
        else:
            close_list()
            html_parts.append(f'<p style="margin:8px 0; line-height:1.55;">{stripped}</p>')
    close_list()
    return ''.join(html_parts)

class TurkishTextEdit(QTextEdit):
    """Türkçe sağ tık menüsü olan QTextEdit"""
    
    def contextMenuEvent(self, event):
        """Sağ tık menüsünü özelleştir"""
        menu = QMenu(self)
        
        # Geri al
        undo_action = menu.addAction("Geri Al")
        undo_action.setShortcut("Ctrl+Z")
        undo_action.triggered.connect(self.undo)
        
        # Yinele
        redo_action = menu.addAction("Yinele")
        redo_action.setShortcut("Ctrl+Y")
        redo_action.triggered.connect(self.redo)
        
        menu.addSeparator()
        
        # Kes
        cut_action = menu.addAction("Kes")
        cut_action.setShortcut("Ctrl+X")
        cut_action.triggered.connect(self.cut)
        
        # Kopyala
        copy_action = menu.addAction("Kopyala")
        copy_action.setShortcut("Ctrl+C")
        copy_action.triggered.connect(self.copy)
        
        # Yapıştır
        paste_action = menu.addAction("Yapıştır")
        paste_action.setShortcut("Ctrl+V")
        paste_action.triggered.connect(self.paste)
        
        # Sil
        delete_action = menu.addAction("Sil")
        delete_action.triggered.connect(self.delete_selected)
        
        menu.addSeparator()
        
        # Tümünü Seç
        select_all_action = menu.addAction("Tümünü Seç")
        select_all_action.setShortcut("Ctrl+A")
        select_all_action.triggered.connect(self.selectAll)
        
        # Menüyü göster
        menu.exec_(event.globalPos())
    
    def delete_selected(self):
        """Seçili metni sil"""
        cursor = self.textCursor()
        cursor.removeSelectedText()

def send_email_smtp(subject, body, to, attachments=None, smtp_settings=None, is_html=False, vcard_image_path=None):
    """
    SMTP üzerinden e-posta gönder
    smtp_settings: {
        'server': 'smtp.gmail.com',
        'port': 587,
        'username': 'your_email@gmail.com',
        'password': 'your_password'
    }
    """
    try:
        if smtp_settings is None:
            smtp_settings = {
                'server': 'smtp.gmail.com',
                'port': 587,
                'username': 'your_email@gmail.com',
                'password': 'your_password'
            }

        # Ana mesaj - related type kullan (inline görseller için)
        msg = MIMEMultipart('related')
        msg['From'] = smtp_settings['username']
        msg['To'] = to
        msg['Subject'] = subject
        msg['Disposition-Notification-To'] = smtp_settings['username']
        msg['Return-Receipt-To'] = smtp_settings['username']
        msg['X-Confirm-Reading-To'] = smtp_settings['username']
        
        # E-posta gövdesi için multipart/alternative
        alternative_part = MIMEMultipart('alternative')
        
        # Düz metin versiyonu (HTML etiketlerini temizle)
        plain_text = body
        if is_html:
            import re
            plain_text = re.sub(r'<[^>]+>', '', body)
            plain_text = plain_text.replace('&nbsp;', ' ')
            plain_text = re.sub(r'\s+', ' ', plain_text).strip()
        
        text_part = MIMEText(plain_text, 'plain', 'utf-8')
        alternative_part.attach(text_part)
        
        # HTML versiyonu (takip pikseli ile)
        if is_html:
            html_body = body
            
            html_part = MIMEText(html_body, 'html', 'utf-8')
            alternative_part.attach(html_part)
        
        # Alternative part'ı ana mesaja ekle
        msg.attach(alternative_part)
        
        # Ek dosyalardaki görsellerin ön izlemesini inline olarak ekle
        image_counter = 1
        if attachments:
            for file_path in attachments:
                if os.path.exists(file_path):
                    file_ext = os.path.splitext(file_path)[1].lower()
                    if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
                        try:
                            with open(file_path, "rb") as attachment:
                                part = MIMEImage(attachment.read())
                                content_id = f'<image{image_counter}>'
                                part.add_header('Content-ID', content_id)
                                part.add_header('Content-Disposition', 'inline', filename=os.path.basename(file_path))
                                msg.attach(part)
                                image_counter += 1
                        except Exception as e:
                            print(f"Görsel ön izleme eklenirken hata: {e}")
        
        # Kartvizit görselini en sona inline olarak ekle (eğer varsa)
        if vcard_image_path and os.path.exists(vcard_image_path):
            try:
                with open(vcard_image_path, "rb") as attachment:
                    part = MIMEImage(attachment.read())
                    part.add_header('Content-ID', '<kartvizit>')
                    part.add_header('Content-Disposition', 'inline', filename=os.path.basename(vcard_image_path))
                    msg.attach(part)
            except Exception as e:
                print(f"Kartvizit görseli eklenirken hata: {e}")
        
        # Ek dosyaları en sona ekle
        if attachments:
            for file_path in attachments:
                if os.path.exists(file_path):
                    with open(file_path, "rb") as attachment:
                        # Normal ek dosya olarak ekle
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(attachment.read())
                        encoders.encode_base64(part)
                        filename = os.path.basename(file_path)
                        part.add_header(
                            'Content-Disposition',
                            'attachment',
                            filename=('utf-8', '', filename)
                        )
                        msg.attach(part)
        
        # SSL veya TLS seçimi (daha sağlam EHLO ve timeout ile)
        port = int(smtp_settings['port'])
        host = smtp_settings['server']
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=30)
            server.ehlo()
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.ehlo()
            server.starttls()
            server.ehlo()
        # Bazı sunucularda giriş kullanıcı adı e-posta adresinden farklı olabilir
        login_username = smtp_settings.get('auth_username', smtp_settings['username'])
        try:
            server.login(login_username, smtp_settings['password'])
        except smtplib.SMTPAuthenticationError as auth_err:
            raise Exception(f"SMTP kimlik doğrulama hatası (535). Lütfen kullanıcı adı/şifreyi ve gerekirse uygulama şifresini kontrol edin. Sunucu: {host}, Port: {port}. Orijinal hata: {auth_err}")
        text = msg.as_string()
        server.sendmail(smtp_settings['username'], to, text)
        server.quit()
        
        return True
    except Exception as e:
        print(f"SMTP e-posta gönderme hatası: {e}")
        import traceback
        traceback.print_exc()
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.critical(None, "SMTP Hatası", f"SMTP e-posta gönderme hatası: {e}")
        return False

class DatabaseMappingManager:
    """Veritabanı tablo başlıklarını sabit başlıklarla eşleştirme yöneticisi"""
    
    def __init__(self):
        self.mappings_file = "database_mappings.json"
        self.fixed_fields = ["ID", "il", "Sektör", "Firma Adı", "Yetkili Adı Soyadı", "E-posta-1", "E-posta 2", "Web sitesi"]
        self.mappings = self.load_mappings()
    
    def load_mappings(self):
        """Kaydedilmiş eşleştirmeleri yükle"""
        if os.path.exists(self.mappings_file):
            try:
                with open(self.mappings_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Eşleştirme dosyası okuma hatası: {e}")
                return {}
        return {}
    
    def save_mappings(self):
        """Eşleştirmeleri kalıcı olarak kaydet"""
        try:
            with open(self.mappings_file, 'w', encoding='utf-8') as f:
                json.dump(self.mappings, f, ensure_ascii=False, indent=2)
            print(f"Eşleştirmeler kaydedildi: {self.mappings_file}")
        except Exception as e:
            print(f"Eşleştirme kaydetme hatası: {e}")
    
    def get_mapping(self, table_name):
        """Tablo için eşleştirmeyi getir"""
        return self.mappings.get(table_name, {})
    
    def save_mapping(self, table_name, mapping_dict):
        """Eşleştirmeyi kaydet ve dosyaya yaz"""
        self.mappings[table_name] = mapping_dict
        self.save_mappings()
        print(f"'{table_name}' tablosu için eşleştirme kaydedildi")
    
    def apply_mapping_to_data(self, table_name, sql_data, sql_columns):
        """SQL verilerini sabit başlıklarla eşleştir"""
        mapping = self.get_mapping(table_name)
        if not mapping:
            return sql_data, sql_columns  # Eşleştirme yoksa orijinal veriyi döndür
        
        mapped_data = []
        for row in sql_data:
            mapped_row = []
            for fixed_field in self.fixed_fields:
                sql_field = mapping.get(fixed_field, "")
                if sql_field and sql_field in sql_columns:
                    col_index = sql_columns.index(sql_field)
                    mapped_row.append(row[col_index] if col_index < len(row) else "")
                else:
                    mapped_row.append("")
            mapped_data.append(mapped_row)
        
        return mapped_data, self.fixed_fields

class MainWindow(QMainWindow):
    """Ana uygulama penceresi"""
    
    def __init__(self):
        super().__init__()
        self.config_manager = ConfigManager()
        self.logger = Logger()
        self.database_manager = DatabaseManager()
        
        # EŞLEŞTİRME YÖNETİCİSİ - YENİ
        self.mapping_manager = DatabaseMappingManager()
        
        # Gönderim sayaçları
        self.hourly_sent_count = 0
        self.daily_sent_count = 0
        self.last_hourly_reset = datetime.now()
        self.last_daily_reset = datetime.now()
        
        # Zamanlama listesi
        self.scheduled_emails = []
        self.email_timers = {}
        
        self.init_ui()
        self.load_config()
        
        # Veritabanı bağlantısını başlat
        # self.initialize_database_connection()
        
        # İstatistikleri yükle
        self.load_sending_stats()
        
        # UI oluşturulduktan sonra limit ayarlarını yükle
        QTimer.singleShot(100, self.load_limit_settings)
        
        # Periyodik olarak sonraki zamanlama etiketini güncelle (her 30 saniyede bir)
        self.next_schedule_timer = QTimer()
        self.next_schedule_timer.timeout.connect(self.update_next_schedule_label)
        self.next_schedule_timer.start(30000)  # 30 saniye
        
        # İstatistik güncelleme timer'ı (her 10 saniyede bir)
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.refresh_sending_stats)
        self.stats_timer.start(10000)  # 10 saniye
        
        self.backup_thread = None
        self.backup_stop_event = threading.Event()
        
        # Log timer'ını başlat
        QTimer.singleShot(1000, self.start_log_timer)
        
    def initialize_database_connection(self):
        """Veritabanı bağlantısını başlat"""
        try:
            # Config dosyasından veritabanı bilgilerini al
            config = self.config_manager.load_config()
            if config.get("database"):
                db_config = config["database"]
                
                # Veritabanı bağlantısını test et
                success = self.database_manager.test_connection(
                    host=db_config.get("host", "localhost"),
                    port=db_config.get("port", "5432"),
                    db_name=db_config.get("database", ""),
                    user=db_config.get("user", ""),
                    password=db_config.get("password", "")
                )
                
                if success:
                    # Bağlantı parametrelerini kaydet
                    self.database_manager.connection_params = {
                        'host': db_config.get("host", "localhost"),
                        'port': db_config.get("port", "5432"),
                        'dbname': db_config.get("database", ""),
                        'user': db_config.get("user", ""),
                        'password': db_config.get("password", "")
                    }
                    
                    # Bağlantıyı aç
                    self.database_manager.conn = self.database_manager.get_connection()
                    
                    if self.database_manager.conn:
                        self.logger.info("Veritabanı bağlantısı başarıyla kuruldu")
                        self.status_label.setText("Sistem Durumu: Veritabanı Bağlı")
                        self.status_label.setStyleSheet("color: green; font-weight: bold;")
                    else:
                        self.logger.error("Veritabanı bağlantısı kurulamadı")
                        self.status_label.setText("Sistem Durumu: Veritabanı Bağlantısı Yok")
                        self.status_label.setStyleSheet("color: red; font-weight: bold;")
                else:
                    self.logger.error("Veritabanı bağlantı testi başarısız")
                    self.status_label.setText("Sistem Durumu: Veritabanı Bağlantısı Yok")
                    self.status_label.setStyleSheet("color: red; font-weight: bold;")
            else:
                self.logger.error("Veritabanı yapılandırması bulunamadı")
                self.status_label.setText("Sistem Durumu: Yapılandırma Eksik")
                self.status_label.setStyleSheet("color: orange; font-weight: bold;")
                
        except Exception as e:
            self.logger.error(f"Veritabanı başlatma hatası: {e}")
            self.status_label.setText("Sistem Durumu: Hata")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
        
    def init_ui(self):
        """Kullanıcı arayüzünü başlat"""
        self.setWindowTitle("Otomatik E-posta Gönderim Sistemi")
        self.setGeometry(100, 100, 1400, 900)
        
        # Ana widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Ana layout
        main_layout = QHBoxLayout(central_widget)
        
        # Sol panel (Kontrol paneli)
        left_panel = self.create_control_panel()
        main_layout.addWidget(left_panel, 1)
        
        # Sağ panel (Tab widget)
        self.right_panel = self.create_tab_widget()
        main_layout.addWidget(self.right_panel, 3)
        
        # Stil uygula
        self.apply_styles()
        
        # Program açıldığında filtreleme sekmesine geç
        self.switch_to_filter_tab()
        
    def create_control_panel(self):
        """Sol kontrol panelini oluştur"""
        panel = QFrame()
        panel.setFrameStyle(QFrame.Shape.Box)
        panel.setMaximumWidth(400)
        
        layout = QVBoxLayout(panel)
        
        # Başlık
        title = QLabel("Kontrol Paneli")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Durum göstergesi
        self.status_label = QLabel("Sistem Durumu: Hazır")
        self.status_label.setStyleSheet("color: green; font-weight: bold;")
        layout.addWidget(self.status_label)
        
        # Hızlı işlem butonları
        quick_actions = QGroupBox("Hızlı İşlemler")
        quick_layout = QVBoxLayout(quick_actions)
        
        # 1. Veritabanı Bağlantısını Test Et
        self.btn_test_db = QPushButton("Veritabanı Bağlantısını Test Et")
        self.btn_test_db.clicked.connect(self.test_database_connection)
        quick_layout.addWidget(self.btn_test_db)
        
        # 2. E-posta Bağlantısını Test Et
        self.btn_test_email_conn = QPushButton("E-posta Bağlantısını Test Et")
        self.btn_test_email_conn.clicked.connect(self.test_email_connection)
        quick_layout.addWidget(self.btn_test_email_conn)
        
        # 3. Manuel Yedekle
        self.btn_manual_backup = QPushButton("Manuel Yedekle")
        self.btn_manual_backup.clicked.connect(self.manual_backup)
        quick_layout.addWidget(self.btn_manual_backup)
        
        layout.addWidget(quick_actions)
        
        # Sistem bilgileri
        system_info = QGroupBox("Sistem Bilgileri")
        system_layout = QVBoxLayout(system_info)
        
        self.db_status_label = QLabel("Veritabanı: Bağlantı yok")
        system_layout.addWidget(self.db_status_label)
        
        # E-posta bağlantı durumu
        self.email_status_label = QLabel("E-posta Bağlantısı: Başarısız")
        system_layout.addWidget(self.email_status_label)
        
        self.next_schedule_label = QLabel("Sonraki Zamanlama: Yok")
        system_layout.addWidget(self.next_schedule_label)
        
        layout.addWidget(system_info)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        layout.addStretch()
        return panel
        
    def create_tab_widget(self):
        """Sağ tab widget'ını oluştur"""
        tab_widget = QTabWidget()
        
        # Yapılandırma sekmesi
        config_tab = self.create_config_tab()
        tab_widget.addTab(config_tab, "Yapılandırma")
        
        # Veritabanı sekmesi
        database_tab = self.create_database_tab()
        tab_widget.addTab(database_tab, "Veritabanı")
        
        # Filtreleme sekmesi
        filter_tab = self.create_report_tab()
        tab_widget.addTab(filter_tab, "Filtreleme")
        
        # E-posta sekmesi
        email_tab = self.create_email_tab()
        tab_widget.addTab(email_tab, "E-posta")
        
        # Zamanlama sekmesi
        schedule_tab = self.create_schedule_tab()
        tab_widget.addTab(schedule_tab, "Zamanlama")
        
        # Log sekmesi
        log_tab = self.create_log_tab()
        tab_widget.addTab(log_tab, "Loglar")
        
        return tab_widget
    def create_config_tab(self):
        """Yapılandırma sekmesini oluştur"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Genel ayarlar
        general_group = QGroupBox("Genel Ayarlar")
        general_layout = QGridLayout(general_group)
        general_layout.setColumnStretch(0, 0)  # Label sütunu sabit genişlik
        general_layout.setColumnStretch(1, 1)  # Input sütunu esnek genişlik
        
        # Otomatik yedekleme (Tema seçimi kaldırıldı)
        general_layout.addWidget(QLabel("Otomatik Yedekleme:"), 0, 0)
        self.backup_check = QCheckBox("Belirli aralıklarla yedek al")
        self.backup_check.setStyleSheet("QCheckBox { margin: 0; padding: 0; }")
        general_layout.addWidget(self.backup_check, 0, 1)
        self.backup_check.stateChanged.connect(self.toggle_auto_backup)
        # Yedekleme dizini
        general_layout.addWidget(QLabel("Yedekleme Dizini:"), 1, 0)
        self.backup_dir_edit = QLineEdit()
        self.backup_dir_edit.setText("./backups")
        self.backup_dir_edit.setMinimumWidth(250)
        general_layout.addWidget(self.backup_dir_edit, 1, 1)
        # Bildirim sesi
        general_layout.addWidget(QLabel("Bildirim Sesi:"), 2, 0)
        self.sound_check = QCheckBox("Sesli uyarı ver")
        self.sound_check.setStyleSheet("QCheckBox { margin: 0; padding: 0; }")
        general_layout.addWidget(self.sound_check, 2, 1)
        # Pop-up uyarı aç/kapat
        general_layout.addWidget(QLabel("Pop-up Uyarıları:"), 3, 0)
        self.popup_check = QCheckBox("Bilgilendirme pencerelerini göster")
        self.popup_check.setStyleSheet("QCheckBox { margin: 0; padding: 0; }")
        general_layout.addWidget(self.popup_check, 3, 1)
        # E-posta ile hata bildirimi
        general_layout.addWidget(QLabel("E-posta ile Hata Bildirimi:"), 4, 0)
        self.email_error_check = QCheckBox("Kritik hatalarda yöneticilere e-posta gönder")
        self.email_error_check.setStyleSheet("QCheckBox { margin: 0; padding: 0; }")
        general_layout.addWidget(self.email_error_check, 4, 1)
        # Log dizini
        general_layout.addWidget(QLabel("Log Dizini:"), 5, 0)
        self.log_dir_edit = QLineEdit()
        self.log_dir_edit.setText("./logs")
        self.log_dir_edit.setMinimumWidth(250)
        general_layout.addWidget(self.log_dir_edit, 5, 1)
        
        layout.addWidget(general_group)

        # SMTP Ayarları grubu (E-posta sekmesinden taşındı)
        smtp_group = QGroupBox("SMTP Ayarları")
        smtp_layout = QGridLayout(smtp_group)
        smtp_layout.setColumnStretch(0, 0)  # Label sütunu sabit genişlik
        smtp_layout.setColumnStretch(1, 1)  # Input sütunu esnek genişlik
        
        smtp_layout.addWidget(QLabel("SMTP Sunucusu:"), 0, 0)
        self.smtp_server_edit = QLineEdit()
        self.smtp_server_edit.setText("smtp.gmail.com")
        self.smtp_server_edit.setMinimumWidth(250)
        smtp_layout.addWidget(self.smtp_server_edit, 0, 1)
        smtp_layout.addWidget(QLabel("Port:"), 1, 0)
        self.smtp_port_edit = QLineEdit()
        self.smtp_port_edit.setText("587")
        self.smtp_port_edit.setMinimumWidth(250)
        smtp_layout.addWidget(self.smtp_port_edit, 1, 1)
        smtp_layout.addWidget(QLabel("Gönderen E-posta:"), 2, 0)
        self.sender_email_edit = QLineEdit()
        self.sender_email_edit.setMinimumWidth(250)
        smtp_layout.addWidget(self.sender_email_edit, 2, 1)
        smtp_layout.addWidget(QLabel("Şifre:"), 3, 0)
        self.sender_password_edit = QLineEdit()
        self.sender_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.sender_password_edit.setMinimumWidth(250)
        smtp_layout.addWidget(self.sender_password_edit, 3, 1)
        
        # Butonları yatay hizala
        smtp_btn_layout = QHBoxLayout()
        test_email_conn_btn = QPushButton("E-posta Bağlantısını Test Et")
        test_email_conn_btn.setFixedHeight(32)
        test_email_conn_btn.setStyleSheet("background-color: #1976D2; color: white; font-size: 12px; border: none; border-radius: 4px; padding: 0 12px;")
        test_email_conn_btn.clicked.connect(self.test_email_connection)
        smtp_btn_layout.addWidget(test_email_conn_btn)
        
        test_email_btn = QPushButton("Test E-postası Gönder")
        test_email_btn.setFixedHeight(32)
        test_email_btn.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold; font-size: 12px; border: none; border-radius: 4px; padding: 0 12px;")
        test_email_btn.clicked.connect(self.send_test_email)
        smtp_btn_layout.addWidget(test_email_btn)
        smtp_btn_layout.addStretch()
        
        smtp_layout.addLayout(smtp_btn_layout, 4, 0, 1, 2)
        
        layout.addWidget(smtp_group)

        # Kartvizit Ayarları grubu
        vcard_group = QGroupBox("Kartvizit Ayarları")
        vcard_layout = QGridLayout(vcard_group)
        vcard_layout.setColumnStretch(0, 0)  # Label sütunu sabit genişlik
        vcard_layout.setColumnStretch(1, 1)  # Input sütunu esnek genişlik
        
        # Kartvizit aktif/pasif seçeneği
        vcard_layout.addWidget(QLabel("Kartvizit Ekleme:"), 0, 0)
        self.vcard_enabled_check = QCheckBox("E-postalara otomatik kartvizit ekle")
        self.vcard_enabled_check.setStyleSheet("QCheckBox { margin: 0; padding: 0; }")
        vcard_layout.addWidget(self.vcard_enabled_check, 0, 1)
        
        # Kartvizit Görseli Seçimi
        vcard_layout.addWidget(QLabel("Kartvizit Görseli:"), 1, 0)
        vcard_image_layout = QHBoxLayout()
        vcard_image_layout.setSpacing(4)
        
        self.vcard_image_combo = QComboBox()
        self.vcard_image_combo.setMinimumWidth(250)
        self.vcard_image_combo.setMaximumWidth(300)
        # Kartvizitler klasöründeki dosyaları dinamik olarak bul
        kartvizit_items = ["Kartvizit Yok", "Özel Kartvizit"]
        kartvizitler_path = "kartvizitler"
        if os.path.exists(kartvizitler_path):
            for file in os.listdir(kartvizitler_path):
                if file.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp')):
                    kartvizit_items.append(file)
        
        self.vcard_image_combo.addItems(kartvizit_items)
        self.vcard_image_combo.currentTextChanged.connect(self.on_vcard_image_changed)
        vcard_image_layout.addWidget(self.vcard_image_combo)
        
        # Görsel seç butonu
        self.vcard_browse_btn = QPushButton("Görsel Seç")
        self.vcard_browse_btn.setFixedHeight(30)
        self.vcard_browse_btn.setFixedWidth(80)
        self.vcard_browse_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 11px;
                border: none;
                border-radius: 4px;
                padding: 0 6px;
            }
            QPushButton:hover {
                background-color: #45A049;
            }
        """)
        self.vcard_browse_btn.clicked.connect(self.browse_vcard_image)
        vcard_image_layout.addWidget(self.vcard_browse_btn)
        
        vcard_image_layout.addStretch()
        vcard_layout.addLayout(vcard_image_layout, 1, 1)
        
        # Seçili görsel yolu
        vcard_layout.addWidget(QLabel("Seçili Görsel:"), 2, 0)
        self.vcard_image_path_edit = QLineEdit()
        self.vcard_image_path_edit.setReadOnly(True)
        self.vcard_image_path_edit.setPlaceholderText("Kartvizit görseli seçilmedi")
        self.vcard_image_path_edit.setMinimumWidth(250)
        vcard_layout.addWidget(self.vcard_image_path_edit, 2, 1)
        
        # Profesyonel İmza (HTML) alanları
        vcard_layout.addWidget(QLabel("Profesyonel İmza Aktif:"), 3, 0)
        self.vcard_signature_enabled = QCheckBox("HTML tabanlı imza ekle")
        self.vcard_signature_enabled.setStyleSheet("QCheckBox { margin: 0; padding: 0; }")
        vcard_layout.addWidget(self.vcard_signature_enabled, 3, 1)

        vcard_layout.addWidget(QLabel("Ad Soyad:"), 4, 0)
        self.signature_name_edit = QLineEdit()
        self.signature_name_edit.setPlaceholderText("Mustafa KORKMAZ")
        self.signature_name_edit.setMinimumWidth(250)
        vcard_layout.addWidget(self.signature_name_edit, 4, 1)

        vcard_layout.addWidget(QLabel("Telefon:"), 5, 0)
        self.signature_phone_edit = QLineEdit()
        self.signature_phone_edit.setPlaceholderText("0850 346 10 32")
        self.signature_phone_edit.setMinimumWidth(250)
        vcard_layout.addWidget(self.signature_phone_edit, 5, 1)

        vcard_layout.addWidget(QLabel("Cep:"), 6, 0)
        self.signature_mobile_edit = QLineEdit()
        self.signature_mobile_edit.setPlaceholderText("0537 594 80 72")
        self.signature_mobile_edit.setMinimumWidth(250)
        vcard_layout.addWidget(self.signature_mobile_edit, 6, 1)

        vcard_layout.addWidget(QLabel("E-posta:"), 7, 0)
        self.signature_email_edit = QLineEdit()
        self.signature_email_edit.setPlaceholderText("destek@biosoft.com.tr")
        self.signature_email_edit.setMinimumWidth(250)
        vcard_layout.addWidget(self.signature_email_edit, 7, 1)

        vcard_layout.addWidget(QLabel("Web:"), 8, 0)
        self.signature_web_edit = QLineEdit()
        self.signature_web_edit.setPlaceholderText("www.biosoft.com.tr")
        self.signature_web_edit.setMinimumWidth(250)
        vcard_layout.addWidget(self.signature_web_edit, 8, 1)

        vcard_layout.addWidget(QLabel("Adres:"), 9, 0)
        self.signature_address_edit = QLineEdit()
        self.signature_address_edit.setPlaceholderText("Fatih Mh. Dağsaray Sk. No:28 Selçuklu/KONYA")
        self.signature_address_edit.setMinimumWidth(250)
        vcard_layout.addWidget(self.signature_address_edit, 9, 1)

        vcard_layout.addWidget(QLabel("Hizmetler:"), 10, 0)
        self.signature_services_edit = QLineEdit()
        self.signature_services_edit.setPlaceholderText("Personel Devam Kontrol Sistemleri - Bekçi Tur Sistemleri")
        self.signature_services_edit.setMinimumWidth(250)
        vcard_layout.addWidget(self.signature_services_edit, 10, 1)
        layout.addWidget(vcard_group)

        # Kontrol butonları için layout
        control_layout = QHBoxLayout()
        
        # Yapılandırma Ayarlarını Kaydet butonu
        save_config_btn = QPushButton("💾 Ayarları Kaydet")
        save_config_btn.setFixedHeight(30)
        save_config_btn.setFixedWidth(140)
        save_config_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                font-size: 11px;
                border: none;
                border-radius: 4px;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background-color: #45A049;
            }
        """)
        save_config_btn.clicked.connect(self.save_config)
        control_layout.addWidget(save_config_btn)
        
        control_layout.addStretch()
        layout.addLayout(control_layout)
        
        return widget
        
    def create_database_tab(self):
        """Veritabanı sekmesini oluştur"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Veritabanı bağlantı ayarları (PostgreSQL için)
        db_group = QGroupBox("Veritabanı Bağlantı Ayarları")
        db_layout = QGridLayout(db_group)
        
        db_layout.addWidget(QLabel("Host:"), 0, 0)
        self.db_host_edit = QLineEdit()
        self.db_host_edit.setText("localhost")
        db_layout.addWidget(self.db_host_edit, 0, 1)
        
        db_layout.addWidget(QLabel("Port:"), 1, 0)
        self.db_port_edit = QLineEdit()
        self.db_port_edit.setText("5432")
        db_layout.addWidget(self.db_port_edit, 1, 1)

        db_layout.addWidget(QLabel("Veritabanı Adı:"), 2, 0)
        self.db_name_edit = QLineEdit()
        self.db_name_edit.setText("postgres")
        db_layout.addWidget(self.db_name_edit, 2, 1)
        
        db_layout.addWidget(QLabel("Kullanıcı Adı:"), 3, 0)
        self.db_user_edit = QLineEdit()
        self.db_user_edit.setText("postgres")
        db_layout.addWidget(self.db_user_edit, 3, 1)
        
        db_layout.addWidget(QLabel("Şifre:"), 4, 0)
        self.db_password_edit = QLineEdit()
        self.db_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        db_layout.addWidget(self.db_password_edit, 4, 1)
        
        layout.addWidget(db_group)

        # Kaydet butonu (daha uygun en ve konum)
        db_save_btn = QPushButton("Kaydet")
        db_save_btn.setFixedWidth(200)
        db_save_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; font-size: 14px; padding: 8px;")
        db_save_btn.clicked.connect(self.save_database_config)
        db_save_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout.addWidget(db_save_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        
        # Tablo listesi
        table_group = QGroupBox("Veritabanı Tabloları")
        table_layout = QVBoxLayout(table_group)
        
        self.table_list = QTableWidget()
        self.table_list.setColumnCount(3)
        self.table_list.setHorizontalHeaderLabels(["Tablo Adı", "Kayıt Sayısı", "Durum"])
        table_layout.addWidget(self.table_list)
        
        layout.addWidget(table_group)
        
        # EŞLEŞTİRME BÖLÜMÜ - YENİ
        mapping_group = QGroupBox("Başlık Eşleştirme")
        mapping_layout = QVBoxLayout(mapping_group)
        
        # Tablo seçimi
        table_select_layout = QHBoxLayout()
        table_select_layout.addWidget(QLabel("Tablo Seç:"))
        self.mapping_table_combo = QComboBox()
        self.mapping_table_combo.currentTextChanged.connect(self.on_mapping_table_changed)
        table_select_layout.addWidget(self.mapping_table_combo)
        mapping_layout.addLayout(table_select_layout)
        
        # Eşleştirme alanı
        mapping_area = QHBoxLayout()
        
        # SQL başlıkları
        sql_group = QGroupBox("SQL Tablo Başlıkları")
        sql_layout = QVBoxLayout(sql_group)
        self.sql_headers_list = QListWidget()
        self.sql_headers_list.setMaximumHeight(200)
        sql_layout.addWidget(self.sql_headers_list)
        mapping_area.addWidget(sql_group)
        
        # Eşleştirme okları
        arrow_layout = QVBoxLayout()
        arrow_layout.addStretch()
        arrow_label = QLabel("↔")
        arrow_label.setStyleSheet("font-size: 24px; color: #666; padding: 10px;")
        arrow_layout.addWidget(arrow_label)
        arrow_layout.addStretch()
        mapping_area.addLayout(arrow_layout)
        
        # Sabit başlıklar ve dropdown'lar
        fixed_group = QGroupBox("Sabit Tablo Başlıkları")
        fixed_layout = QVBoxLayout(fixed_group)
        
        # Her sabit başlık için dropdown oluştur
        self.mapping_dropdowns = {}
        for field in self.mapping_manager.fixed_fields:
            field_layout = QHBoxLayout()
            field_layout.addWidget(QLabel(f"{field}:"))
            
            dropdown = QComboBox()
            dropdown.addItem("-- Seçiniz --")
            dropdown.setMinimumWidth(150)
            self.mapping_dropdowns[field] = dropdown
            
            field_layout.addWidget(dropdown)
            fixed_layout.addLayout(field_layout)
        
        mapping_area.addWidget(fixed_group)
        mapping_layout.addLayout(mapping_area)
        
        # Eşleştirme butonları
        mapping_buttons = QHBoxLayout()
        
        self.load_mapping_btn = QPushButton("Mevcut Eşleştirmeyi Yükle")
        self.load_mapping_btn.clicked.connect(self.load_existing_mapping)
        self.load_mapping_btn.setEnabled(False)
        mapping_buttons.addWidget(self.load_mapping_btn)
        
        self.save_mapping_btn = QPushButton("Eşleştirmeyi Kaydet")
        self.save_mapping_btn.clicked.connect(self.save_field_mapping)
        self.save_mapping_btn.setEnabled(False)
        mapping_buttons.addWidget(self.save_mapping_btn)
        
        mapping_layout.addLayout(mapping_buttons)
        layout.addWidget(mapping_group)
        
        layout.addStretch()
        return widget
        
    def create_report_tab(self):
        """Filtreleme sekmesini oluştur"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # --- FİLTRELEME ARAYÜZÜ ---
        filter_group = QGroupBox("Filtreleme")
        filter_layout = QGridLayout(filter_group)
        
        # Tablo Adı filtresi
        filter_layout.addWidget(QLabel("Tablo Adı:"), 0, 0)
        self.filter_tablo_adi = QComboBox()
        self.filter_tablo_adi.setEditable(True)
        filter_layout.addWidget(self.filter_tablo_adi, 0, 1)
        
        # İl filtresi
        filter_layout.addWidget(QLabel("İl:"), 1, 0)
        self.filter_il = QComboBox()
        self.filter_il.setEditable(True)
        filter_layout.addWidget(self.filter_il, 1, 1)
        
        # Sektör filtresi
        filter_layout.addWidget(QLabel("Sektör:"), 2, 0)
        self.filter_sektor = QComboBox()
        self.filter_sektor.setEditable(True)
        filter_layout.addWidget(self.filter_sektor, 2, 1)

        # E-posta filtresi checkbox'ı
        self.filter_email_checkbox = QCheckBox("Sadece e-posta adresi olanları göster")
        self.filter_email_checkbox.setChecked(False)
        filter_layout.addWidget(self.filter_email_checkbox, 3, 0, 1, 2)

        # Butonlar için yatay layout
        button_layout = QHBoxLayout()
        
        self.filter_btn = QPushButton("Filtrele")
        self.filter_btn.clicked.connect(self.apply_filters)
        button_layout.addWidget(self.filter_btn)
        
        self.add_to_recipients_btn = QPushButton("Alıcı Listesine Ekle")
        self.add_to_recipients_btn.clicked.connect(self.add_filtered_results_to_recipients)
        self.add_to_recipients_btn.setEnabled(False)  # Başlangıçta devre dışı
        button_layout.addWidget(self.add_to_recipients_btn)
        
        filter_layout.addLayout(button_layout, 4, 0, 1, 2)
        
        layout.addWidget(filter_group)
        
        # --- SONUÇ TABLOSU ---
        # Tablo için ScrollArea oluştur
        table_scroll_area = QScrollArea()
        table_scroll_area.setWidgetResizable(True)
        table_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        table_scroll_area.setMinimumHeight(400)  # Minimum yükseklik ayarla
        
        # Tablo widget'ı
        self.filter_table = QTableWidget()
        self.filter_table.setColumnCount(8)
        self.filter_table.setHorizontalHeaderLabels([
            "ID", "İl", "Sektör", "Firma Adı", "Yetkili Adı Soyadı", 
            "E-posta 1", "E-posta 2", "Web Sitesi"
        ])
        
        # Tablo başlıklarını pencereye tam konumlandır
        self.filter_table.horizontalHeader().setStretchLastSection(True)
        self.filter_table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        
        # Sütun genişliklerini ayarla
        column_widths = [60, 80, 100, 200, 150, 120, 120, 150]
        for i, width in enumerate(column_widths):
            self.filter_table.setColumnWidth(i, width)
        
        # Tablo stil ayarları
        self.filter_table.setAlternatingRowColors(True)
        self.filter_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.filter_table.setSortingEnabled(True)
        
        # Tablo için minimum satır sayısı ayarla (dikey kaydırma çubuğunu tetiklemek için)
        self.filter_table.setMinimumHeight(300)
        
        # ScrollArea'ya tabloyu ekle
        table_scroll_area.setWidget(self.filter_table)
        layout.addWidget(table_scroll_area)
        layout.addStretch()

        # Dinamik combobox doldurma başlangıçta çalıştırılmıyor; bağlantı testinden sonra çağrılacak
        # self.update_filter_comboboxes()

        return widget

    def update_filter_comboboxes(self):
        """Tablo Adı, İl ve Sektör comboboxlarını veritabanındaki DISTINCT değerlerle doldurur."""
        try:
            # Önce veritabanı bağlantısını kontrol et
            if not self.database_manager.conn:
                # Bağlantı yoksa mevcut ayarlarla bağlanmayı dene
                host = self.db_host_edit.text()
                port = self.db_port_edit.text()
                db_name = self.db_name_edit.text()
                user = self.db_user_edit.text()
                password = self.db_password_edit.text()
                
                if not all([host, port, db_name, user, password]):
                    print("Veritabanı bağlantı bilgileri eksik")
                    return
                    
                # Bağlantıyı test et
                success = self.database_manager.test_connection(host, port, db_name, user, password)
                if not success:
                    print("Veritabanı bağlantısı başarısız")
                    return
            
            conn = self.database_manager.conn or self.database_manager.connect_from_ui(self)
            cur = conn.cursor()
            
            # Tablo adlarını getir
            cur.execute("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public'")
            tablolar = [row[0] for row in cur.fetchall()]
            self.filter_tablo_adi.clear()
            self.filter_tablo_adi.addItem("")
            self.filter_tablo_adi.addItems(tablolar)
            
            # İL - HAZIR LİSTE YAKLAŞIMI (Performans için)
            turkiye_illeri = [
                "Adana", "Adıyaman", "Afyonkarahisar", "Ağrı", "Aksaray", "Amasya", "Ankara", "Antalya", "Ardahan", "Artvin", "Aydın", "Balıkesir",
                "Bartın", "Batman", "Bayburt", "Bilecik", "Bingöl", "Bitlis", "Bolu", "Burdur", "Bursa", "Çanakkale", "Çankırı", "Çorum",
                "Denizli", "Diyarbakır", "Düzce", "Edirne", "Elazığ", "Erzincan", "Erzurum", "Eskişehir", "Gaziantep", "Giresun", "Gümüşhane", "Hakkari",
                "Hatay", "Iğdır", "Isparta", "İstanbul", "İzmir", "Kahramanmaraş", "Karabük", "Karaman", "Kars", "Kastamonu", "Kayseri", "Kilis",
                "Kırıkkale", "Kırklareli", "Kırşehir", "Kocaeli", "Konya", "Kütahya", "Malatya", "Manisa", "Mardin", "Mersin", "Muğla", "Muş",
                "Nevşehir", "Niğde", "Ordu", "Osmaniye", "Rize", "Sakarya", "Samsun", "Şanlıurfa", "Siirt", "Sinop", "Sivas", "Şırnak",
                "Tekirdağ", "Tokat", "Trabzon", "Tunceli", "Uşak", "Van", "Yalova", "Yozgat", "Zonguldak"
            ]
            
            # İl combobox'ını önce hazır liste ile doldur
            self.filter_il.clear()
            self.filter_il.addItem("")
            self.filter_il.addItems(turkiye_illeri)
            
            # Eğer veritabanı bağlantısı varsa, dinamik verileri de ekle
            if self.database_manager.conn:
                try:
                    # Seçili tabloya göre dinamik il verilerini al
                    selected_table = self.filter_tablo_adi.currentText()
                    if selected_table:
                        # Eşleştirme kontrol et
                        mapping = self.mapping_manager.get_mapping(selected_table)
                        
                        if mapping and "il" in mapping:
                            # Eşleştirme varsa, eşleştirilmiş sütun adını kullan
                            il_column = mapping["il"]
                            print(f"Eşleştirme ile il sütunu: {il_column}")
                        else:
                            # Eşleştirme yoksa, varsayılan "il" sütununu kullan
                            il_column = "il"
                            print("Eşleştirme yok, varsayılan il sütunu kullanılıyor")
                        
                        # Veritabanındaki ek illeri de ekle (varsa)
                        cur.execute(f"SELECT DISTINCT \"{il_column}\" FROM \"{selected_table}\" WHERE \"{il_column}\" IS NOT NULL AND \"{il_column}\" <> '' ORDER BY \"{il_column}\"")
                        db_iller = [row[0] for row in cur.fetchall()]
                        
                        # Veritabanındaki ek illeri de ekle (varsa)
                        for il in db_iller:
                            if il not in turkiye_illeri:
                                self.filter_il.addItem(il)
                                print(f"Ek il eklendi: {il}")
                except Exception as e:
                    print(f"Veritabanından il verisi alınamadı: {e}")
            
            # SEKTÖR - EŞLEŞTİRME İLE DİNAMİK SQL YAKLAŞIMI
            try:
                # Seçili tabloya göre sektör verilerini al
                selected_table = self.filter_tablo_adi.currentText()
                if selected_table:
                    # Eşleştirme kontrol et
                    mapping = self.mapping_manager.get_mapping(selected_table)
                    
                    if mapping and "Sektör" in mapping:
                        # Eşleştirme varsa, eşleştirilmiş sütun adını kullan
                        sektor_column = mapping["Sektör"]
                        print(f"Eşleştirme ile sektör sütunu: {sektor_column}")
                    else:
                        # Eşleştirme yoksa, eski yöntemle bul
                        cur.execute(f"""
                            SELECT column_name 
                            FROM information_schema.columns 
                            WHERE table_name = '{selected_table}' 
                            ORDER BY ordinal_position
                        """)
                        columns = [row[0] for row in cur.fetchall()]
                        print(f"Tablo '{selected_table}' sütunları: {columns}")
                        
                        sektor_column = None
                        for col in columns:
                            if col.lower() in ['sektör', 'sektor', 'sector']:
                                sektor_column = col
                                break
                    
                    if sektor_column:
                        cur.execute(f"SELECT DISTINCT \"{sektor_column}\" FROM \"{selected_table}\" WHERE \"{sektor_column}\" IS NOT NULL AND \"{sektor_column}\" <> '' ORDER BY \"{sektor_column}\"")
                        sektorler = [row[0] for row in cur.fetchall()]
                        self.filter_sektor.clear()
                        self.filter_sektor.addItem("")
                        self.filter_sektor.addItems(sektorler)
                        print(f"Sektör verileri yüklendi: {len(sektorler)} adet")
                    else:
                        print(f"Sektör sütunu bulunamadı.")
                        self.filter_sektor.clear()
                        self.filter_sektor.addItem("")
                else:
                    # Tablo seçilmemişse boş liste
                    self.filter_sektor.clear()
                    self.filter_sektor.addItem("")
                    
            except Exception as e:
                print(f"Sektör verisi alınamadı: {e}")
                # Hata durumunda boş liste
                self.filter_sektor.clear()
                self.filter_sektor.addItem("")
            
            cur.close()
            if not self.database_manager.conn:
                conn.close()
                
            print(f"Filtre comboboxları güncellendi: {len(tablolar)} tablo, {len(turkiye_illeri)} il (hazır liste), {len(sektorler) if 'sektorler' in locals() else 0} sektör (dinamik)")
            
        except Exception as e:
            print(f"Filtre comboboxları güncellenemedi: {e}")
    def create_email_tab(self):
        """E-posta sekmesini oluştur"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Şablon widget referanslarını saklamak için
        self.template_widgets = []
        
        # Alıcı listesi
        recipient_group = QGroupBox("Alıcı Listesi")
        recipient_layout = QVBoxLayout(recipient_group)
        
        # BCC onay kutucuğu
        bcc_layout = QHBoxLayout()
        self.bcc_checkbox = QCheckBox("BCC (Gizli Alıcı) Kullan")
        self.bcc_checkbox.setStyleSheet("font-weight: bold; color: #333; font-size: 12px;")
        self.bcc_checkbox.stateChanged.connect(self.on_bcc_checkbox_changed)
        bcc_layout.addWidget(self.bcc_checkbox)
        
        # BCC durum etiketi
        self.bcc_status_label = QLabel("BCC Kapalı")
        self.bcc_status_label.setStyleSheet("color: #666; font-size: 11px; font-style: italic;")
        bcc_layout.addWidget(self.bcc_status_label)
        bcc_layout.addStretch()
        
        recipient_layout.addLayout(bcc_layout)
        
        self.recipient_list = QTableWidget()
        self.recipient_list.setColumnCount(3)
        self.recipient_list.setHorizontalHeaderLabels(["E-posta", "Ad Soyad", "Durum"])
        recipient_layout.addWidget(self.recipient_list)
        
        # Alıcı ekleme butonları - yatay düzen
        add_recipient_buttons_layout = QHBoxLayout()
        
        # Manuel ekleme bölümü
        manual_add_layout = QHBoxLayout()
        self.new_email_edit = QLineEdit()
        self.new_email_edit.setPlaceholderText("E-posta adresi")
        manual_add_layout.addWidget(self.new_email_edit)
        
        self.new_name_edit = QLineEdit()
        self.new_name_edit.setPlaceholderText("Ad Soyad")
        manual_add_layout.addWidget(self.new_name_edit)
        
        add_btn = QPushButton("Ekle")
        add_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-size: 12px; border: none; border-radius: 4px; padding: 8px 12px; } QPushButton:hover { background-color: #388e3c; }")
        add_btn.setToolTip("Alıcı listesine ekle")
        add_btn.clicked.connect(self.add_recipient)
        manual_add_layout.addWidget(add_btn)
        
        add_recipient_buttons_layout.addLayout(manual_add_layout)
        
        # Çoklu import butonu
        import_btn = QPushButton("📥 Çoklu İçe Aktar")
        import_btn.setStyleSheet("QPushButton { background-color: #2196F3; color: white; font-size: 12px; border: none; border-radius: 4px; padding: 8px 12px; } QPushButton:hover { background-color: #1976D2; }")
        import_btn.setToolTip("Toplu e-posta adresi içe aktar")
        import_btn.clicked.connect(self.show_manual_import_dialog)
        add_recipient_buttons_layout.addWidget(import_btn)
        
        # Temizle butonu
        clear_btn = QPushButton("🗑️ Listeyi Temizle")
        clear_btn.setStyleSheet("QPushButton { background-color: #f44336; color: white; font-size: 12px; border: none; border-radius: 4px; padding: 8px 12px; } QPushButton:hover { background-color: #d32f2f; }")
        clear_btn.setToolTip("Alıcı listesini temizle")
        clear_btn.clicked.connect(self.clear_recipient_list)
        add_recipient_buttons_layout.addWidget(clear_btn)
        
        recipient_layout.addLayout(add_recipient_buttons_layout)
        layout.addWidget(recipient_group)
        
        # E-posta şablonu - Tab sistemi ile
        template_group = QGroupBox("E-posta Şablonu")
        template_layout = QVBoxLayout(template_group)

        # Tab widget oluştur
        self.email_tab_widget = QTabWidget()
        # Şablon sekme isimlerini daha vurgulu göster
        self.email_tab_widget.setStyleSheet("QTabWidget::pane { border: 1px solid #E0E0E0; top: -1px; } QTabBar::tab { color: #616161; font-weight: 600; padding: 6px 12px; margin-right: 6px; background: #F5F5F5; border: 1px solid #E0E0E0; border-bottom-color: #E0E0E0; border-top-left-radius: 6px; border-top-right-radius: 6px; } QTabBar::tab:selected { color: #FF1744; background: #FFFFFF; border-color: #FF1744; } QTabBar::tab:hover { background: #EEEEEE; }")

        # Butonlar için widget - tab bar ile tam hizalama
        btn_widget = QWidget()
        btn_layout = QHBoxLayout(btn_widget)
        btn_layout.setContentsMargins(0, 0, 0, 0)  # Kenar boşlukları sıfır
        btn_layout.setSpacing(4)  # Butonlar arası boşluk artırıldı

        btn_add_tab = QPushButton("Ekle")
        btn_add_tab.setFixedSize(50, 26)
        btn_add_tab.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-size: 12px; border: none; border-radius: 4px; padding: 0 6px; } QPushButton:hover { background-color: #388e3c; }")
        btn_add_tab.setToolTip("Yeni şablon ekle")
        btn_add_tab.clicked.connect(self.add_message_tab)
        btn_layout.addWidget(btn_add_tab)

        btn_remove_tab = QPushButton("Sil")
        btn_remove_tab.setFixedSize(50, 26)
        btn_remove_tab.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-size: 12px; border: none; border-radius: 4px; padding: 0 6px; } QPushButton:hover { background-color: #388e3c; }")
        btn_remove_tab.setToolTip("Seçili şablonu sil")
        btn_remove_tab.clicked.connect(self.remove_message_tab)
        btn_layout.addWidget(btn_remove_tab)

        btn_save_templates = QPushButton("Kaydet")
        btn_save_templates.setFixedSize(65, 26)
        btn_save_templates.setStyleSheet("QPushButton { background-color: #1976D2; color: white; font-size: 12px; border: none; border-radius: 4px; padding: 0 8px; } QPushButton:hover { background-color: #1565c0; }")
        btn_save_templates.setToolTip("Şablonları Kaydet")
        btn_save_templates.clicked.connect(self.save_templates)
        btn_layout.addWidget(btn_save_templates)

        # Butonları tab widget'ın sağ üst köşesine yerleştir
        self.email_tab_widget.setCornerWidget(btn_widget, Qt.TopRightCorner)

        # Sekme adını çift tıklayınca değiştirme
        self.email_tab_widget.tabBar().tabBarDoubleClicked.connect(self.rename_message_tab)

        # Şablonları yükle
        self.load_templates()
        if self.email_tab_widget.count() == 0:
            self.create_message_tab("Mesaj 1", "Konu", "Mesaj içeriği")

        template_layout.addWidget(self.email_tab_widget)
        layout.addWidget(template_group)

        layout.addStretch()
        return widget

    def add_message_tab(self):
        tab_count = self.email_tab_widget.count() + 1
        tab_name = f"Mesaj {tab_count}"
        self.create_message_tab(tab_name, "Konu", "Mesaj içeriği")
        self.email_tab_widget.setCurrentIndex(self.email_tab_widget.count() - 1)
        self.save_templates()

    def remove_message_tab(self):
        current_index = self.email_tab_widget.currentIndex()
        if self.email_tab_widget.count() > 1:
            self.email_tab_widget.removeTab(current_index)
            del self.template_widgets[current_index]
            self.save_templates()
        else:
            QMessageBox.warning(self, "Uyarı", "En az bir mesaj şablonu kalmalı!")

    def rename_message_tab(self, index):
        if index < 0:
            return
        current_name = self.email_tab_widget.tabText(index)
        new_name, ok = QInputDialog.getText(self, "Şablon Adı Değiştir", "Yeni şablon adı:", text=current_name)
        if ok and new_name.strip():
            self.email_tab_widget.setTabText(index, new_name.strip())
            self.save_templates()

    def create_message_tab(self, tab_name, default_subject, default_body):
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        # Konu etiketi ve alanı
        subject_label = QLabel("Konu")
        layout.addWidget(subject_label)
        subject_edit = QLineEdit()
        subject_edit.setText(default_subject)
        subject_edit.setPlaceholderText("Konu")
        layout.addWidget(subject_edit)
        
        # Gövde metni ve değişken genişlik seçenekleri
        body_options_layout = QHBoxLayout()
        
        # Gövde metni dropdown
        body_text_label = QLabel("Gövde metni:")
        body_options_layout.addWidget(body_text_label)
        
        self.body_text_combo = QComboBox()
        self.body_text_combo.addItems(["Normal", "HTML", "Rich Text", "Plain Text"])
        body_options_layout.addWidget(self.body_text_combo)
        
        # Değişken genişlik dropdown
        width_label = QLabel("Değişken genişlik:")
        body_options_layout.addWidget(width_label)
        
        self.width_combo = QComboBox()
        self.width_combo.addItems(["Otomatik", "Sabit", "Esnek", "Tam Genişlik"])
        body_options_layout.addWidget(self.width_combo)
        
        body_options_layout.addStretch()
        layout.addLayout(body_options_layout)
        
        # Mesaj gövdesi
        body_edit = TurkishTextEdit()
        body_edit.setPlainText(default_body)
        layout.addWidget(body_edit)
        
        # Kapsamlı formatlama toolbar'ı
        format_toolbar = QHBoxLayout()
        format_toolbar.setSpacing(2)
        format_toolbar.setContentsMargins(5, 5, 5, 5)  # Kenar boşlukları ekle
        
        # Format toolbar container widget for styling
        format_toolbar_widget = QWidget()
        format_toolbar_widget.setLayout(format_toolbar)
        format_toolbar_widget.setStyleSheet("QWidget { background-color: #f8f8f8; border: 1px solid #ddd; border-radius: 4px; padding: 2px; }")
        format_toolbar_widget.setMinimumHeight(35)  # Minimum yükseklik
        
        # Renk seçiciler
        fg_color_btn = QPushButton()
        fg_color_btn.setFixedSize(20, 20)
        fg_color_btn.setStyleSheet("QPushButton { background-color: white; border: 1px solid #ccc; border-radius: 2px; }")
        fg_color_btn.setToolTip("Metin rengi")
        fg_color_btn.clicked.connect(lambda: self.choose_text_color(body_edit))
        format_toolbar.addWidget(fg_color_btn)
        
        bg_color_btn = QPushButton()
        bg_color_btn.setFixedSize(20, 20)
        bg_color_btn.setStyleSheet("QPushButton { background-color: black; border: 1px solid #ccc; border-radius: 2px; }")
        bg_color_btn.setToolTip("Arka plan rengi")
        bg_color_btn.clicked.connect(lambda: self.choose_bg_color(body_edit))
        format_toolbar.addWidget(bg_color_btn)
        
        format_toolbar.addSpacing(10)
        
        # Font seçenekleri
        font_family_btn = QPushButton("T")
        font_family_btn.setFixedSize(25, 25)
        font_family_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 10px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
        font_family_btn.setToolTip("Font ailesi")
        font_family_btn.clicked.connect(lambda: self.choose_font_family(body_edit))
        format_toolbar.addWidget(font_family_btn)
        
        font_size_down_btn = QPushButton("T↓")
        font_size_down_btn.setFixedSize(25, 25)
        font_size_down_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 8px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
        font_size_down_btn.setToolTip("Font boyutunu küçült")
        font_size_down_btn.clicked.connect(lambda: self.change_font_size(body_edit, -1))
        format_toolbar.addWidget(font_size_down_btn)
        
        font_size_up_btn = QPushButton("T↑")
        font_size_up_btn.setFixedSize(25, 25)
        font_size_up_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 8px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
        font_size_up_btn.setToolTip("Font boyutunu büyült")
        font_size_up_btn.clicked.connect(lambda: self.change_font_size(body_edit, 1))
        format_toolbar.addWidget(font_size_up_btn)
        
        format_toolbar.addSpacing(10)
        
        # Metin stilleri
        btn_bold = QPushButton("B")
        btn_bold.setFixedSize(25, 25)
        btn_bold.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 10px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; } QPushButton:pressed { background-color: #4CAF50; color: white; }")
        btn_bold.setToolTip("Kalın")
        btn_bold.clicked.connect(lambda: self.format_text(body_edit, "bold"))
        format_toolbar.addWidget(btn_bold)
        
        btn_italic = QPushButton("I")
        btn_italic.setFixedSize(25, 25)
        btn_italic.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 10px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; } QPushButton:pressed { background-color: #4CAF50; color: white; }")
        btn_italic.setToolTip("İtalik")
        btn_italic.clicked.connect(lambda: self.format_text(body_edit, "italic"))
        format_toolbar.addWidget(btn_italic)
        
        btn_underline = QPushButton("U")
        btn_underline.setFixedSize(25, 25)
        btn_underline.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 10px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; } QPushButton:pressed { background-color: #4CAF50; color: white; }")
        btn_underline.setToolTip("Altı çizili")
        btn_underline.clicked.connect(lambda: self.format_text(body_edit, "underline"))
        format_toolbar.addWidget(btn_underline)
        
        format_toolbar.addSpacing(10)
        
        # Metin rengi/highlight
        text_color_btn = QPushButton("A")
        text_color_btn.setFixedSize(25, 25)
        text_color_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 10px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
        text_color_btn.setToolTip("Metin rengi")
        text_color_btn.clicked.connect(lambda: self.choose_text_color(body_edit))
        format_toolbar.addWidget(text_color_btn)
        
        format_toolbar.addSpacing(10)
        
        # Liste butonları
        bullet_list_btn = QPushButton("•")
        bullet_list_btn.setFixedSize(25, 25)
        bullet_list_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 14px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
        bullet_list_btn.setToolTip("Madde işaretli liste")
        bullet_list_btn.clicked.connect(lambda: self.format_text(body_edit, "bullet_list"))
        format_toolbar.addWidget(bullet_list_btn)
        
        number_list_btn = QPushButton("1.")
        number_list_btn.setFixedSize(25, 25)
        number_list_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 8px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
        number_list_btn.setToolTip("Numaralı liste")
        number_list_btn.clicked.connect(lambda: self.format_text(body_edit, "number_list"))
        format_toolbar.addWidget(number_list_btn)
        
        format_toolbar.addSpacing(10)
        
        # Hizalama butonları
        align_left_btn = QPushButton("◄")
        align_left_btn.setFixedSize(25, 25)
        align_left_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 10px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
        align_left_btn.setToolTip("Sola hizala")
        align_left_btn.clicked.connect(lambda: self.format_text(body_edit, "align_left"))
        format_toolbar.addWidget(align_left_btn)
        
        align_center_btn = QPushButton("◄►")
        align_center_btn.setFixedSize(25, 25)
        align_center_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 8px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
        align_center_btn.setToolTip("Ortala")
        align_center_btn.clicked.connect(lambda: self.format_text(body_edit, "align_center"))
        format_toolbar.addWidget(align_center_btn)
        
        align_right_btn = QPushButton("►")
        align_right_btn.setFixedSize(25, 25)
        align_right_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 10px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
        align_right_btn.setToolTip("Sağa hizala")
        align_right_btn.clicked.connect(lambda: self.format_text(body_edit, "align_right"))
        format_toolbar.addWidget(align_right_btn)
        
        align_justify_btn = QPushButton("◄►◄")
        align_justify_btn.setFixedSize(25, 25)
        align_justify_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 7px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
        align_justify_btn.setToolTip("İki yana hizala")
        align_justify_btn.clicked.connect(lambda: self.format_text(body_edit, "align_justify"))
        format_toolbar.addWidget(align_justify_btn)
        
        format_toolbar.addSpacing(10)
        
        # Girinti butonları
        outdent_btn = QPushButton("←")
        outdent_btn.setFixedSize(25, 25)
        outdent_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 10px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
        outdent_btn.setToolTip("Girinti azalt")
        outdent_btn.clicked.connect(lambda: self.format_text(body_edit, "outdent"))
        format_toolbar.addWidget(outdent_btn)
        
        indent_btn = QPushButton("→")
        indent_btn.setFixedSize(25, 25)
        indent_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 10px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
        indent_btn.setToolTip("Girinti artır")
        indent_btn.clicked.connect(lambda: self.format_text(body_edit, "indent"))
        format_toolbar.addWidget(indent_btn)
        
        format_toolbar.addSpacing(10)
        
        # Daha fazla seçenek dropdown
        more_options_btn = QPushButton("...")
        more_options_btn.setFixedSize(25, 25)
        more_options_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 10px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
        more_options_btn.setToolTip("Daha fazla seçenek")
        more_options_btn.clicked.connect(lambda: self.show_more_formatting_options(body_edit))
        format_toolbar.addWidget(more_options_btn)
        
        format_toolbar.addSpacing(10)
        
        # Medya ekleme butonları
        emoji_btn = QPushButton("😊")
        emoji_btn.setFixedSize(25, 25)
        emoji_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 12px; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
        emoji_btn.setToolTip("Emoji ekle")
        emoji_btn.clicked.connect(lambda: self.insert_emoji(body_edit))
        format_toolbar.addWidget(emoji_btn)
        
        format_toolbar.addStretch()
        layout.addWidget(format_toolbar_widget)
        
        # Ek dosyalar bölümü
        attachment_group = QGroupBox("Dosya ve Fotoğrafları Ekle")
        attachment_layout = QVBoxLayout(attachment_group)
        
        # Tablo
        attachment_table = QTableWidget()
        attachment_table.setColumnCount(3)
        attachment_table.setHorizontalHeaderLabels(["Dosya Adı", "Tür", "Açıklama"])
        attachment_layout.addWidget(attachment_table)
        
        # Butonlar ve menü - tüm butonlar aynı satırda
        attachment_buttons_layout = QHBoxLayout()
        
        # Menü butonu
        menu_btn = QPushButton("☰ Dosya Ekle")
        menu_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-size: 12px; border: none; border-radius: 4px; padding: 8px 12px; } QPushButton:hover { background-color: #388e3c; }")
        menu_btn.clicked.connect(lambda: self.show_attachment_menu(menu_btn, attachment_table))
        attachment_buttons_layout.addWidget(menu_btn)
        
        # Temizle butonu
        clear_btn = QPushButton("Listeyi Temizle")
        clear_btn.setStyleSheet("QPushButton { background-color: #f44336; color: white; font-size: 12px; border: none; border-radius: 4px; padding: 8px 12px; } QPushButton:hover { background-color: #d32f2f; }")
        clear_btn.clicked.connect(lambda: self.clear_attachment_list(attachment_table))
        attachment_buttons_layout.addWidget(clear_btn)
        
        # Stretch - butonları sağa yaslamak için
        attachment_buttons_layout.addStretch()
        
        # Gönderme butonları - en sağa
        btn_schedule = QPushButton("⏰ Zamanla Gönder")
        btn_schedule.setStyleSheet("QPushButton { background-color: #FF9800; color: white; font-size: 12px; border: none; border-radius: 4px; padding: 8px 16px; } QPushButton:hover { background-color: #F57C00; }")
        btn_schedule.setToolTip("E-postayı belirli bir tarih/saatte gönder - Alıcı listesi gerekli")
        btn_schedule.clicked.connect(lambda: self.schedule_email(subject_edit.text(), body_edit.toPlainText(), attachment_table))
        attachment_buttons_layout.addWidget(btn_schedule)
        
        btn_send_now = QPushButton("🚀 Şimdi Gönder")
        btn_send_now.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-size: 12px; border: none; border-radius: 4px; padding: 8px 16px; } QPushButton:hover { background-color: #388e3c; }")
        btn_send_now.setToolTip("E-postayı hemen gönder - Alıcı listesi gerekli, saatlik limitlerle otomatik devam eder")
        btn_send_now.clicked.connect(lambda: self.send_email_with_attachments(subject_edit.text(), body_edit.toPlainText(), attachment_table))
        attachment_buttons_layout.addWidget(btn_send_now)
        
        attachment_layout.addLayout(attachment_buttons_layout)
        
        layout.addWidget(attachment_group)
        # Widget referanslarını sakla
        self.template_widgets.append({
            "subject": subject_edit,
            "body": body_edit,
            "attachments": attachment_table
        })
        self.email_tab_widget.addTab(tab_widget, tab_name)
        self.save_templates()

    def save_templates(self):
        templates = []
        for i in range(self.email_tab_widget.count()):
            tab_name = self.email_tab_widget.tabText(i)
            w = self.template_widgets[i]
            subject = w["subject"].text()
            body = w["body"].toPlainText()
            attachment_table = w["attachments"]
            attachments = []
            for row in range(attachment_table.rowCount()):
                file_path = attachment_table.item(row, 0).data(Qt.UserRole)
                file_type = attachment_table.item(row, 1).text() if attachment_table.item(row, 1) else ""
                desc = attachment_table.item(row, 2).text() if attachment_table.item(row, 2) else ""
                attachments.append({"path": file_path, "type": file_type, "desc": desc})
            templates.append({
                "name": tab_name,
                "subject": subject,
                "body": body,
                "attachments": attachments
            })
        with open("email_templates.json", "w", encoding="utf-8") as f:
            json.dump(templates, f, ensure_ascii=False, indent=2)

    def load_templates(self):
        import os
        self.template_widgets = []
        self.email_tab_widget.clear()
        if not os.path.exists("email_templates.json"):
            return
        with open("email_templates.json", "r", encoding="utf-8") as f:
            templates = json.load(f)
        for tpl in templates:
            self.create_message_tab_from_data(tpl)
    def create_message_tab_from_data(self, tpl):
        """Veriden mesaj şablonu oluştur - Geliştirilmiş versiyon"""
        try:
            # 1. VERİ DOĞRULAMA
            if not isinstance(tpl, dict):
                self.logger.error("Geçersiz şablon verisi: dict değil")
                QMessageBox.warning(self, "Uyarı", "Geçersiz şablon formatı!")
                return
            
            # Zorunlu alanları kontrol et
            required_fields = ["subject", "body", "name"]
            missing_fields = [field for field in required_fields if field not in tpl]
            if missing_fields:
                self.logger.error(f"Eksik şablon alanları: {missing_fields}")
                QMessageBox.warning(self, "Uyarı", f"Şablon eksik alanlar içeriyor: {', '.join(missing_fields)}")
                return
            
            # Şablon versiyonu kontrolü
            version = tpl.get("version", 1)
            if version > 2:
                QMessageBox.information(self, "Bilgi", "Bu şablon yeni bir versiyonla oluşturulmuş!")
            
            tab_widget = QWidget()
            layout = QVBoxLayout(tab_widget)
            subject_label = QLabel("Konu")
            layout.addWidget(subject_label)
            subject_edit = QLineEdit()
            subject_edit.setText(tpl.get("subject", ""))  # Güvenli erişim
            subject_edit.setPlaceholderText("Konu")
            layout.addWidget(subject_edit)
            
            # Gövde metni ve değişken genişlik seçenekleri
            body_options_layout = QHBoxLayout()
            
            # Gövde metni dropdown
            body_text_label = QLabel("Gövde metni:")
            body_options_layout.addWidget(body_text_label)
            
            self.body_text_combo = QComboBox()
            self.body_text_combo.addItems(["Normal", "HTML", "Rich Text", "Plain Text"])
            body_options_layout.addWidget(self.body_text_combo)
            
            # Değişken genişlik dropdown
            width_label = QLabel("Değişken genişlik:")
            body_options_layout.addWidget(width_label)
            
            self.width_combo = QComboBox()
            self.width_combo.addItems(["Otomatik", "Sabit", "Esnek", "Tam Genişlik"])
            body_options_layout.addWidget(self.width_combo)
            
            body_options_layout.addStretch()
            layout.addLayout(body_options_layout)
            
            body_edit = TurkishTextEdit()
            body_edit.setPlainText(tpl.get("body", ""))  # Güvenli erişim
            layout.addWidget(body_edit)
            
            # Kapsamlı formatlama toolbar'ı
            format_toolbar = QHBoxLayout()
            format_toolbar.setSpacing(2)
            format_toolbar.setContentsMargins(5, 5, 5, 5)  # Kenar boşlukları ekle
            
            # Format toolbar container widget for styling
            format_toolbar_widget = QWidget()
            format_toolbar_widget.setLayout(format_toolbar)
            format_toolbar_widget.setStyleSheet("QWidget { background-color: #f8f8f8; border: 1px solid #ddd; border-radius: 4px; padding: 2px; }")
            format_toolbar_widget.setMinimumHeight(35)  # Minimum yükseklik
            
            # Renk seçiciler
            fg_color_btn = QPushButton()
            fg_color_btn.setFixedSize(20, 20)
            fg_color_btn.setStyleSheet("QPushButton { background-color: white; border: 1px solid #ccc; border-radius: 2px; }")
            fg_color_btn.setToolTip("Metin rengi")
            fg_color_btn.clicked.connect(lambda: self.choose_text_color(body_edit))
            format_toolbar.addWidget(fg_color_btn)
            
            bg_color_btn = QPushButton()
            bg_color_btn.setFixedSize(20, 20)
            bg_color_btn.setStyleSheet("QPushButton { background-color: black; border: 1px solid #ccc; border-radius: 2px; }")
            bg_color_btn.setToolTip("Arka plan rengi")
            bg_color_btn.clicked.connect(lambda: self.choose_bg_color(body_edit))
            format_toolbar.addWidget(bg_color_btn)
            
            format_toolbar.addSpacing(10)
            
            # Font seçenekleri
            font_family_btn = QPushButton("T")
            font_family_btn.setFixedSize(25, 25)
            font_family_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 10px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
            font_family_btn.setToolTip("Font ailesi")
            font_family_btn.clicked.connect(lambda: self.choose_font_family(body_edit))
            format_toolbar.addWidget(font_family_btn)
            
            font_size_down_btn = QPushButton("T↓")
            font_size_down_btn.setFixedSize(25, 25)
            font_size_down_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 8px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
            font_size_down_btn.setToolTip("Font boyutunu küçült")
            font_size_down_btn.clicked.connect(lambda: self.change_font_size(body_edit, -1))
            format_toolbar.addWidget(font_size_down_btn)
            
            font_size_up_btn = QPushButton("T↑")
            font_size_up_btn.setFixedSize(25, 25)
            font_size_up_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 8px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
            font_size_up_btn.setToolTip("Font boyutunu büyült")
            font_size_up_btn.clicked.connect(lambda: self.change_font_size(body_edit, 1))
            format_toolbar.addWidget(font_size_up_btn)
            
            format_toolbar.addSpacing(10)
            
            # Metin stilleri
            btn_bold = QPushButton("B")
            btn_bold.setFixedSize(25, 25)
            btn_bold.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 10px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; } QPushButton:pressed { background-color: #4CAF50; color: white; }")
            btn_bold.setToolTip("Kalın")
            btn_bold.clicked.connect(lambda: self.format_text(body_edit, "bold"))
            format_toolbar.addWidget(btn_bold)
            
            btn_italic = QPushButton("I")
            btn_italic.setFixedSize(25, 25)
            btn_italic.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 10px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; } QPushButton:pressed { background-color: #4CAF50; color: white; }")
            btn_italic.setToolTip("İtalik")
            btn_italic.clicked.connect(lambda: self.format_text(body_edit, "italic"))
            format_toolbar.addWidget(btn_italic)
            
            btn_underline = QPushButton("U")
            btn_underline.setFixedSize(25, 25)
            btn_underline.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 10px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; } QPushButton:pressed { background-color: #4CAF50; color: white; }")
            btn_underline.setToolTip("Altı çizili")
            btn_underline.clicked.connect(lambda: self.format_text(body_edit, "underline"))
            format_toolbar.addWidget(btn_underline)
            
            format_toolbar.addSpacing(10)
            
            # Metin rengi/highlight
            text_color_btn = QPushButton("A")
            text_color_btn.setFixedSize(25, 25)
            text_color_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 10px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
            text_color_btn.setToolTip("Metin rengi")
            text_color_btn.clicked.connect(lambda: self.choose_text_color(body_edit))
            format_toolbar.addWidget(text_color_btn)
            
            format_toolbar.addSpacing(10)
            
            # Liste butonları
            bullet_list_btn = QPushButton("•")
            bullet_list_btn.setFixedSize(25, 25)
            bullet_list_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 14px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
            bullet_list_btn.setToolTip("Madde işaretli liste")
            bullet_list_btn.clicked.connect(lambda: self.format_text(body_edit, "bullet_list"))
            format_toolbar.addWidget(bullet_list_btn)
            
            number_list_btn = QPushButton("1.")
            number_list_btn.setFixedSize(25, 25)
            number_list_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 8px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
            number_list_btn.setToolTip("Numaralı liste")
            number_list_btn.clicked.connect(lambda: self.format_text(body_edit, "number_list"))
            format_toolbar.addWidget(number_list_btn)
            
            format_toolbar.addSpacing(10)
            
            # Hizalama butonları
            align_left_btn = QPushButton("◄")
            align_left_btn.setFixedSize(25, 25)
            align_left_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 10px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
            align_left_btn.setToolTip("Sola hizala")
            align_left_btn.clicked.connect(lambda: self.format_text(body_edit, "align_left"))
            format_toolbar.addWidget(align_left_btn)
            
            align_center_btn = QPushButton("◄►")
            align_center_btn.setFixedSize(25, 25)
            align_center_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 8px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
            align_center_btn.setToolTip("Ortala")
            align_center_btn.clicked.connect(lambda: self.format_text(body_edit, "align_center"))
            format_toolbar.addWidget(align_center_btn)
            
            align_right_btn = QPushButton("►")
            align_right_btn.setFixedSize(25, 25)
            align_right_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 10px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
            align_right_btn.setToolTip("Sağa hizala")
            align_right_btn.clicked.connect(lambda: self.format_text(body_edit, "align_right"))
            format_toolbar.addWidget(align_right_btn)
            
            align_justify_btn = QPushButton("◄►◄")
            align_justify_btn.setFixedSize(25, 25)
            align_justify_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 7px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
            align_justify_btn.setToolTip("İki yana hizala")
            align_justify_btn.clicked.connect(lambda: self.format_text(body_edit, "align_justify"))
            format_toolbar.addWidget(align_justify_btn)
            
            format_toolbar.addSpacing(10)
            
            # Girinti butonları
            outdent_btn = QPushButton("←")
            outdent_btn.setFixedSize(25, 25)
            outdent_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 10px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
            outdent_btn.setToolTip("Girinti azalt")
            outdent_btn.clicked.connect(lambda: self.format_text(body_edit, "outdent"))
            format_toolbar.addWidget(outdent_btn)
            
            indent_btn = QPushButton("→")
            indent_btn.setFixedSize(25, 25)
            indent_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 10px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
            indent_btn.setToolTip("Girinti artır")
            indent_btn.clicked.connect(lambda: self.format_text(body_edit, "indent"))
            format_toolbar.addWidget(indent_btn)
            
            format_toolbar.addSpacing(10)
            
            # Daha fazla seçenek dropdown
            more_options_btn = QPushButton("...")
            more_options_btn.setFixedSize(25, 25)
            more_options_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 10px; font-weight: bold; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
            more_options_btn.setToolTip("Daha fazla seçenek")
            more_options_btn.clicked.connect(lambda: self.show_more_formatting_options(body_edit))
            format_toolbar.addWidget(more_options_btn)
            
            format_toolbar.addSpacing(10)
            
            # Medya ekleme butonları
            emoji_btn = QPushButton("😊")
            emoji_btn.setFixedSize(25, 25)
            emoji_btn.setStyleSheet("QPushButton { background-color: #f0f0f0; color: #333; font-size: 12px; border: 1px solid #ccc; border-radius: 3px; } QPushButton:hover { background-color: #e0e0e0; }")
            emoji_btn.setToolTip("Emoji ekle")
            emoji_btn.clicked.connect(lambda: self.insert_emoji(body_edit))
            format_toolbar.addWidget(emoji_btn)
            
            format_toolbar.addStretch()
            layout.addWidget(format_toolbar_widget)
            
            # Ek dosyalar bölümü
            attachment_group = QGroupBox("Dosya ve Fotoğrafları Ekle")
            attachment_layout = QVBoxLayout(attachment_group)
            
            # Tablo
            attachment_table = QTableWidget()
            attachment_table.setColumnCount(3)
            attachment_table.setHorizontalHeaderLabels(["Dosya Adı", "Tür", "Açıklama"])
            attachment_layout.addWidget(attachment_table)
            
            # Ekleri tabloya ekle - Güvenli erişim
            for att in tpl.get("attachments", []):
                row = attachment_table.rowCount()
                attachment_table.insertRow(row)
                file_name = os.path.basename(att.get("path", "")) if att.get("path") else ""
                file_type = att.get("type", "")
                desc = att.get("desc", "")
                attachment_table.setItem(row, 0, QTableWidgetItem(file_name))
                attachment_table.setItem(row, 1, QTableWidgetItem(file_type))
                attachment_table.setItem(row, 2, QTableWidgetItem(desc))
                attachment_table.item(row, 0).setData(Qt.UserRole, att.get("path", ""))
            
            # Butonlar ve menü - tüm butonlar aynı satırda
            attachment_buttons_layout = QHBoxLayout()
            
            # Menü butonu
            menu_btn = QPushButton("☰ Dosya Ekle")
            menu_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-size: 12px; border: none; border-radius: 4px; padding: 8px 12px; } QPushButton:hover { background-color: #388e3c; }")
            menu_btn.clicked.connect(lambda: self.show_attachment_menu(menu_btn, attachment_table))
            attachment_buttons_layout.addWidget(menu_btn)
            
            # Temizle butonu
            clear_btn = QPushButton("Listeyi Temizle")
            clear_btn.setStyleSheet("QPushButton { background-color: #f44336; color: white; font-size: 12px; border: none; border-radius: 4px; padding: 8px 12px; } QPushButton:hover { background-color: #d32f2f; }")
            clear_btn.clicked.connect(lambda: self.clear_attachment_list(attachment_table))
            attachment_buttons_layout.addWidget(clear_btn)
            
            # Stretch - butonları sağa yaslamak için
            attachment_buttons_layout.addStretch()
            
            # Gönderme butonları - en sağa
            btn_schedule = QPushButton("⏰ Zamanla Gönder")
            btn_schedule.setStyleSheet("QPushButton { background-color: #FF9800; color: white; font-size: 12px; border: none; border-radius: 4px; padding: 8px 16px; } QPushButton:hover { background-color: #F57C00; }")
            btn_schedule.setToolTip("E-postayı belirli bir tarih/saatte gönder - Alıcı listesi gerekli")
            btn_schedule.clicked.connect(lambda: self.schedule_email(subject_edit.text(), body_edit.toPlainText(), attachment_table))
            attachment_buttons_layout.addWidget(btn_schedule)
            
            btn_send_now = QPushButton("🚀 Şimdi Gönder")
            btn_send_now.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-size: 12px; border: none; border-radius: 4px; padding: 8px 16px; } QPushButton:hover { background-color: #388e3c; }")
            btn_send_now.setToolTip("E-postayı hemen gönder - Alıcı listesi gerekli, saatlik limitlerle otomatik devam eder")
            btn_send_now.clicked.connect(lambda: self.send_email_with_attachments(subject_edit.text(), body_edit.toPlainText(), attachment_table))
            attachment_buttons_layout.addWidget(btn_send_now)
            
            attachment_layout.addLayout(attachment_buttons_layout)
            
            layout.addWidget(attachment_group)
            self.template_widgets.append({
                "subject": subject_edit,
                "body": body_edit,
                "attachments": attachment_table
            })
            self.email_tab_widget.addTab(tab_widget, tpl.get("name", "Bilinmeyen Şablon"))
            
            # 3. KULLANICI BİLDİRİMİ (Sessiz mod)
            template_name = tpl.get("name", "Bilinmeyen")
            self.logger.info(f"Şablon yüklendi: {template_name}")
            # QMessageBox.information(self, "Başarılı", f"'{template_name}' şablonu başarıyla yüklendi!")
            
        except Exception as e:
            # HATA YÖNETİMİ
            self.logger.error(f"Şablon yükleme hatası: {e}")
            QMessageBox.critical(self, "Hata", f"Şablon yüklenirken hata oluştu:\n{str(e)}")
            return
        
    def create_schedule_tab(self):
        """Zamanlama sekmesini oluştur"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)  # Azaltıldı
        layout.setContentsMargins(10, 10, 10, 10)  # Azaltıldı
        
        # Gönderim Limitleri grubu - Daha kompakt
        limits_group = QGroupBox("📊 Gönderim Limitleri")
        limits_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 1px solid #E0E0E0;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }
        """)
        limits_layout = QGridLayout(limits_group)
        limits_layout.setSpacing(8)
        
        # 1. SATIR: Saatlik ve Günlük Limit
        # Saatlik Limit
        hourly_label = QLabel("⏰ Saatlik:")
        hourly_label.setStyleSheet("font-size: 11px; color: #333;")
        limits_layout.addWidget(hourly_label, 0, 0)
        
        self.hourly_limit_spin = QSpinBox()
        self.hourly_limit_spin.setRange(1, 1000)
        self.hourly_limit_spin.setValue(30)
        self.hourly_limit_spin.setSuffix(" e-posta/saat")
        self.hourly_limit_spin.setStyleSheet("""
            QSpinBox {
                font-size: 11px;
                padding: 3px;
                border: 1px solid #CCC;
                border-radius: 3px;
                min-height: 20px;
            }
        """)
        limits_layout.addWidget(self.hourly_limit_spin, 0, 1)
        
        # Günlük Limit - Yanına ekle
        daily_label = QLabel("📅 Günlük:")
        daily_label.setStyleSheet("font-size: 11px; color: #333;")
        limits_layout.addWidget(daily_label, 0, 2)
        
        self.daily_limit_spin = QSpinBox()
        self.daily_limit_spin.setRange(1, 10000)
        self.daily_limit_spin.setValue(150)
        self.daily_limit_spin.setSuffix(" e-posta/gün")
        self.daily_limit_spin.setStyleSheet("""
            QSpinBox {
                font-size: 11px;
                padding: 3px;
                border: 1px solid #CCC;
                border-radius: 3px;
                min-height: 20px;
            }
        """)
        limits_layout.addWidget(self.daily_limit_spin, 0, 3)
        
        # 2. SATIR: E-posta Arası Süre ve Limit Kontrolü
        delay_label = QLabel("⏱️ Bekleme:")
        delay_label.setStyleSheet("font-size: 11px; color: #333;")
        limits_layout.addWidget(delay_label, 1, 0)
        
        self.email_delay_spin_schedule = QSpinBox()
        self.email_delay_spin_schedule.setRange(1, 60)
        self.email_delay_spin_schedule.setValue(3)
        self.email_delay_spin_schedule.setSuffix(" saniye")
        self.email_delay_spin_schedule.setStyleSheet("""
            QSpinBox {
                font-size: 11px;
                padding: 3px;
                border: 1px solid #CCC;
                border-radius: 3px;
                min-height: 20px;
            }
        """)
        limits_layout.addWidget(self.email_delay_spin_schedule, 1, 1)
        
        # Limit Kontrolü - Yanına ekle
        self.limit_check = QCheckBox("Limitleri aktif et")
        self.limit_check.setChecked(True)
        self.limit_check.setStyleSheet("font-size: 11px;")
        limits_layout.addWidget(self.limit_check, 1, 2, 1, 2)  # 2 sütun genişliğinde
        
        # 3. SATIR: Güncel Durum
        status_layout = QHBoxLayout()
        status_layout.setSpacing(10)
        
        # Bu Saat
        hourly_status = QWidget()
        hourly_layout = QVBoxLayout(hourly_status)
        hourly_layout.setSpacing(2)
        hourly_layout.setContentsMargins(0, 0, 0, 0)
        
        hourly_title = QLabel("Bu Saat:")
        hourly_title.setStyleSheet("font-size: 10px; color: #666;")
        hourly_layout.addWidget(hourly_title)
        
        self.hourly_sent_label = QLabel("0/30 e-posta")
        self.hourly_sent_label.setStyleSheet("""
            color: #4CAF50;
            font-weight: bold;
            font-size: 11px;
            padding: 2px 5px;
            background: #E8F5E8;
            border-radius: 3px;
        """)
        hourly_layout.addWidget(self.hourly_sent_label)
        status_layout.addWidget(hourly_status)
        
        # Bu Gün
        daily_status = QWidget()
        daily_layout = QVBoxLayout(daily_status)
        daily_layout.setSpacing(2)
        daily_layout.setContentsMargins(0, 0, 0, 0)
        
        daily_title = QLabel("Bu Gün:")
        daily_title.setStyleSheet("font-size: 10px; color: #666;")
        daily_layout.addWidget(daily_title)
        
        self.daily_sent_label = QLabel("0/150 e-posta")
        self.daily_sent_label.setStyleSheet("""
            color: #2196F3;
            font-weight: bold;
            font-size: 11px;
            padding: 2px 5px;
            background: #E3F2FD;
            border-radius: 3px;
        """)
        daily_layout.addWidget(self.daily_sent_label)
        status_layout.addWidget(daily_status)
        
        # Yenile ve Limit Durumu butonları
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        
        refresh_btn = QPushButton("🔄 Yenile")
        refresh_btn.setFixedSize(90, 32)
        refresh_btn.setToolTip("İstatistikleri yenile")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background: #FF9800;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
                padding: 4px 10px;
                qproperty-iconSize: 16px;
            }
            QPushButton:hover { 
                background: #F57C00;
                border: 1px solid #FFA726;
            }
        """)
        refresh_btn.clicked.connect(self.refresh_sending_stats)
        button_layout.addWidget(refresh_btn)
        
        limit_status_btn = QPushButton("📊 Detay")
        limit_status_btn.setFixedSize(90, 32)
        limit_status_btn.setToolTip("Limit durumunu göster")
        limit_status_btn.setStyleSheet("""
            QPushButton {
                background: #2196F3;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
                padding: 4px 10px;
                qproperty-iconSize: 16px;
            }
            QPushButton:hover { 
                background: #1976D2;
                border: 1px solid #42A5F5;
            }
        """)
        limit_status_btn.clicked.connect(self.show_limit_status)
        button_layout.addWidget(limit_status_btn)
        
        # Kaydet butonu
        save_btn = QPushButton("💾 Kaydet")
        save_btn.setFixedSize(90, 32)
        save_btn.setToolTip("Limit ayarlarını kaydet")
        save_btn.setStyleSheet("""
            QPushButton {
                background: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
                padding: 4px 10px;
                qproperty-iconSize: 16px;
            }
            QPushButton:hover { 
                background: #45A049;
                border: 1px solid #66BB6A;
            }
        """)
        save_btn.clicked.connect(self.save_limit_settings)
        button_layout.addWidget(save_btn)
        
        status_layout.addLayout(button_layout)
        limits_layout.addLayout(status_layout, 2, 0, 1, 4)  # Tüm sütunları kapla
        
        layout.addWidget(limits_group)
        
        # Zamanlama listesi grubu
        schedule_list_group = QGroupBox("📅 Aktif Zamanlamalar")
        schedule_list_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 1px solid #E0E0E0;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }
        """)
        schedule_list_layout = QVBoxLayout(schedule_list_group)
        schedule_list_layout.setSpacing(8)
        
        self.schedule_list = QTableWidget()
        self.schedule_list.setColumnCount(6)
        self.schedule_list.setHorizontalHeaderLabels(["📋 Görev", "📧 Konu", "⏰ Zamanlanan Tarih", "👥 Alıcı Sayısı", "📊 Durum", "⚙️ İşlem"])
        self.schedule_list.setSelectionBehavior(QTableWidget.SelectRows)
        self.schedule_list.setAlternatingRowColors(True)
        self.schedule_list.setStyleSheet("""
            QTableWidget {
                font-size: 11px;
                gridline-color: #E0E0E0;
                border: 1px solid #CCC;
                border-radius: 4px;
            }
            QHeaderView::section {
                background-color: #F5F5F5;
                padding: 6px;
                border: 1px solid #E0E0E0;
                font-weight: bold;
                font-size: 11px;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QTableWidget::item:selected {
                background-color: #E3F2FD;
                color: black;
            }
        """)
        
        # Sütun genişliklerini ayarla
        self.schedule_list.setColumnWidth(0, 120)  # Görev
        self.schedule_list.setColumnWidth(1, 200)  # Konu
        self.schedule_list.setColumnWidth(2, 120)  # Tarih
        self.schedule_list.setColumnWidth(3, 80)   # Alıcı sayısı
        self.schedule_list.setColumnWidth(4, 120)  # Durum
        self.schedule_list.setColumnWidth(5, 80)   # İşlem
        
        schedule_list_layout.addWidget(self.schedule_list)
        
        # Sil butonu ekle
        delete_btn = QPushButton("🗑️ Seçili Zamanlamayı Sil")
        delete_btn.setFixedSize(200, 32)
        delete_btn.setToolTip("Seçili zamanlanmış e-postayı sil")
        delete_btn.setStyleSheet("""
            QPushButton {
                background: #F44336;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
                padding: 4px 10px;
                qproperty-iconSize: 16px;
            }
            QPushButton:hover { 
                background: #D32F2F;
                border: 1px solid #EF5350;
            }
            QPushButton:disabled {
                background: #BDBDBD;
                color: #757575;
            }
        """)
        delete_btn.clicked.connect(self.delete_selected_schedule)
        schedule_list_layout.addWidget(delete_btn)
        
        layout.addWidget(schedule_list_group)
        
        return widget
        
    # ==================== LOG İŞLEVLERİ ====================
    
    def start_log_timer(self):
        """Log güncelleme timer'ını başlat"""
        try:
            self.log_timer = QTimer()
            self.log_timer.timeout.connect(self.update_log_display)
            self.log_timer.start(2000)  # Her 2 saniyede güncelle
        except Exception as e:
            print(f"Log timer başlatma hatası: {e}")
    def update_log_display(self):
        """Log görüntüleyiciyi güncelle"""
        try:
            # Güncelleme sırasında seçim olaylarını geçici olarak devre dışı bırak
            self._updating_logs = True
            
            # Mevcut seçili satırı kaydet
            current_selection = self.log_table.currentRow()
            selected_timestamp = None
            if current_selection >= 0 and current_selection < self.log_table.rowCount():
                timestamp_item = self.log_table.item(current_selection, 0)
                if timestamp_item:
                    selected_timestamp = timestamp_item.text()
            
            # Detaylı e-posta loglarını al
            detailed_logs = self.logger.get_detailed_email_logs()
            
            # Tabloyu temizle
            self.log_table.setRowCount(0)
            
            # Logları tabloya ekle
            for log in detailed_logs:
                row = self.log_table.rowCount()
                self.log_table.insertRow(row)
                
                # Tarih/Saat
                self.log_table.setItem(row, 0, QTableWidgetItem(log.get('timestamp', '')))
                
                # Tip
                self.log_table.setItem(row, 1, QTableWidgetItem(log.get('type', '')))
                
                # Konu
                self.log_table.setItem(row, 2, QTableWidgetItem(log.get('subject', '')))
                
                # Alıcılar
                recipients = log.get('recipients', [])
                recipient_text = ', '.join(recipients) if recipients else ''
                self.log_table.setItem(row, 3, QTableWidgetItem(recipient_text))
                
                # Durum
                self.log_table.setItem(row, 4, QTableWidgetItem(log.get('status', '')))
                
                # Detaylar
                details = log.get('details', '')
                self.log_table.setItem(row, 5, QTableWidgetItem(details))
            
            # Önceki seçimi geri yükle
            if selected_timestamp:
                for row in range(self.log_table.rowCount()):
                    timestamp_item = self.log_table.item(row, 0)
                    if timestamp_item and timestamp_item.text() == selected_timestamp:
                        self.log_table.selectRow(row)
                        break
            
            # Güncelleme tamamlandı, seçim olaylarını tekrar etkinleştir
            self._updating_logs = False
            
            # Seçili satırın detaylarını güncelle
            if selected_timestamp:
                self.on_log_selection_changed()
            
            # Son güncelleme zamanını güncelle
            current_time = QDateTime.currentDateTime().toString("dd.MM.yyyy HH:mm:ss")
            self.last_update_label.setText(f"Son Güncelleme: {current_time}")
            
        except Exception as e:
            print(f"Log güncelleme hatası: {e}")
            self._updating_logs = False
    

    
    def on_log_selection_changed(self):
        """Log seçimi değiştiğinde detayları göster"""
        # Eğer loglar güncelleniyorsa, seçim olayını işleme
        if hasattr(self, '_updating_logs') and self._updating_logs:
            return
            
        try:
            current_row = self.log_table.currentRow()
            if current_row >= 0 and current_row < self.log_table.rowCount():
                # Seçili satırın verilerini doğrudan tablodan al
                timestamp = self.log_table.item(current_row, 0).text() if self.log_table.item(current_row, 0) else ""
                log_type = self.log_table.item(current_row, 1).text() if self.log_table.item(current_row, 1) else ""
                subject = self.log_table.item(current_row, 2).text() if self.log_table.item(current_row, 2) else ""
                recipients = self.log_table.item(current_row, 3).text() if self.log_table.item(current_row, 3) else ""
                status = self.log_table.item(current_row, 4).text() if self.log_table.item(current_row, 4) else ""
                details = self.log_table.item(current_row, 5).text() if self.log_table.item(current_row, 5) else ""
                
                # Detay metnini oluştur
                detail_text = f"Tarih/Saat: {timestamp}\n"
                detail_text += f"Tip: {log_type}\n"
                detail_text += f"Konu: {subject}\n"
                detail_text += f"Alıcılar: {recipients}\n"
                detail_text += f"Durum: {status}\n"
                detail_text += f"Detaylar: {details}\n"
                
                # E-posta içeriği varsa ekle (detaylı loglardan al)
                try:
                    detailed_logs = self.logger.get_detailed_email_logs()
                    if current_row < len(detailed_logs):
                        log = detailed_logs[current_row]
                        if log.get('email_content'):
                            detail_text += f"\nE-posta İçeriği:\n{log.get('email_content', '')}"
                except:
                    pass  # E-posta içeriği alınamazsa devam et
                
                self.log_detail_text.setPlainText(detail_text)
            else:
                self.log_detail_text.clear()
                
        except Exception as e:
            print(f"Log seçim hatası: {e}")
            self.log_detail_text.clear()
    
    def on_log_level_changed(self):
        """Log seviyesi değiştiğinde filtreleme yap"""
        self.filter_logs()
    
    def filter_logs(self):
        """Logları filtrele"""
        try:
            search_text = self.log_search_edit.text().lower()
            selected_level = self.log_level_combo.currentText()
            selected_date = self.log_date_edit.date().toString("yyyy-MM-dd")
            
            # Tüm satırları kontrol et
            for row in range(self.log_table.rowCount()):
                show_row = True
                
                # Metin araması
                if search_text:
                    row_text = ""
                    for col in range(self.log_table.columnCount()):
                        item = self.log_table.item(row, col)
                        if item:
                            row_text += item.text().lower() + " "
                    
                    if search_text not in row_text:
                        show_row = False
                
                # Log seviyesi filtresi
                if selected_level != "TÜMÜ":
                    type_item = self.log_table.item(row, 1)
                    if type_item and type_item.text() != selected_level:
                        show_row = False
                
                # Tarih filtresi
                date_item = self.log_table.item(row, 0)
                if date_item:
                    log_date = date_item.text()[:10]  # İlk 10 karakter (YYYY-MM-DD)
                    if log_date != selected_date:
                        show_row = False
                
                # Satırı göster/gizle
                self.log_table.setRowHidden(row, not show_row)
                
        except Exception as e:
            print(f"Log filtreleme hatası: {e}")
    
    def refresh_logs(self):
        """Logları yenile"""
        try:
            self.update_log_display()
            self.logger.info("Loglar manuel olarak yenilendi")
        except Exception as e:
            print(f"Log yenileme hatası: {e}")
    
    def export_logs(self):
        """Logları dışa aktar"""
        try:
            from PyQt5.QtWidgets import QFileDialog
            
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Logları Dışa Aktar", 
                f"email_logs_{QDateTime.currentDateTime().toString('yyyyMMdd_HHmmss')}.json",
                "JSON Dosyaları (*.json);;Tüm Dosyalar (*)"
            )
            
            if file_path:
                self.logger.export_detailed_logs(file_path)
                QMessageBox.information(self, "Başarılı", f"Loglar {file_path} dosyasına dışa aktarıldı!")
                
        except Exception as e:
            print(f"Log dışa aktarma hatası: {e}")
            QMessageBox.critical(self, "Hata", f"Loglar dışa aktarılamadı: {e}")
        
    def create_log_tab(self):
        """Log sekmesini oluştur - Modern Tasarım"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        self.last_update_label = QLabel("Son Güncelleme: -")
        self.last_update_label.setStyleSheet("color: #888; font-size: 11px; margin-left: 15px;")
        layout.addWidget(self.last_update_label)
        
        # ==================== ÜST KONTROL PANELİ ====================
        control_group = QGroupBox("📊 Log Kontrol Paneli")
        control_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: 2px solid #E3F2FD;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: #FAFAFA;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px;
                color: #1976D2;
            }
        """)
        control_layout = QHBoxLayout(control_group)
        control_layout.setSpacing(15)
        
        # Sol taraf - Filtreler
        filter_layout = QHBoxLayout()
        
        # Log seviyesi
        level_label = QLabel("🔍 Log Seviyesi:")
        level_label.setStyleSheet("font-weight: bold; color: #333;")
        filter_layout.addWidget(level_label)
        
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["TÜMÜ", "E-POSTA", "SİSTEM", "HATA"])
        self.log_level_combo.setCurrentText("TÜMÜ")
        self.log_level_combo.currentTextChanged.connect(self.on_log_level_changed)
        self.log_level_combo.setStyleSheet("""
            QComboBox {
                padding: 6px;
                border: 2px solid #E0E0E0;
                border-radius: 6px;
                background-color: white;
                font-size: 11px;
                min-width: 100px;
            }
            QComboBox:hover {
                border-color: #2196F3;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #666;
                margin-right: 5px;
            }
        """)
        filter_layout.addWidget(self.log_level_combo)
        
        # Tarih filtresi
        date_label = QLabel("📅 Tarih:")
        date_label.setStyleSheet("font-weight: bold; color: #333; margin-left: 15px;")
        filter_layout.addWidget(date_label)
        
        self.log_date_edit = QDateEdit()
        self.log_date_edit.setDate(QDate.currentDate())
        self.log_date_edit.dateChanged.connect(self.filter_logs)
        self.log_date_edit.setStyleSheet("""
            QDateEdit {
                padding: 6px;
                border: 2px solid #E0E0E0;
                border-radius: 6px;
                background-color: white;
                font-size: 11px;
                min-width: 100px;
            }
            QDateEdit:hover {
                border-color: #2196F3;
            }
        """)
        filter_layout.addWidget(self.log_date_edit)
        
        # Arama kutusu
        search_label = QLabel("🔎 Ara:")
        search_label.setStyleSheet("font-weight: bold; color: #333; margin-left: 15px;")
        filter_layout.addWidget(search_label)
        
        self.log_search_edit = QLineEdit()
        self.log_search_edit.setPlaceholderText("Loglarda arama yapın...")
        self.log_search_edit.textChanged.connect(self.filter_logs)
        self.log_search_edit.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                border: 2px solid #E0E0E0;
                border-radius: 6px;
                background-color: white;
                font-size: 11px;
                min-width: 150px;
            }
            QLineEdit:hover {
                border-color: #2196F3;
            }
            QLineEdit:focus {
                border-color: #1976D2;
                background-color: #F8F9FA;
            }
        """)
        filter_layout.addWidget(self.log_search_edit)
        
        filter_layout.addStretch()
        control_layout.addLayout(filter_layout)
        
        # Sağ taraf - Butonlar
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        # Yenile butonu
        refresh_btn = QPushButton("🔄 Yenile")
        refresh_btn.clicked.connect(self.refresh_logs)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 10px;
                min-width: 70px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        button_layout.addWidget(refresh_btn)
        
        # Log dışa aktarma butonu
        export_btn = QPushButton("📤 Dışa Aktar")
        export_btn.clicked.connect(self.export_logs)
        export_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 10px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
            QPushButton:pressed {
                background-color: #EF6C00;
            }
        """)
        button_layout.addWidget(export_btn)
        
        # Log temizleme butonu
        clear_btn = QPushButton("🗑️ Temizle")
        clear_btn.clicked.connect(self.clear_logs)
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #F44336;
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 10px;
                min-width: 70px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
            QPushButton:pressed {
                background-color: #c62828;
            }
        """)
        button_layout.addWidget(clear_btn)
        
        control_layout.addLayout(button_layout)
        layout.addWidget(control_group)
        
        # ==================== LOG TABLOSU ====================
        table_group = QGroupBox("📋 Log Detayları")
        table_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: 2px solid #E3F2FD;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: #FAFAFA;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px;
                color: #1976D2;
            }
        """)
        table_layout = QVBoxLayout(table_group)
        
        # Detaylı log tablosu
        self.log_table = QTableWidget()
        self.log_table.setColumnCount(6)
        self.log_table.setHorizontalHeaderLabels([
            "📅 Tarih/Saat", "🏷️ Tip", "📧 Konu", "👥 Alıcılar", "✅ Durum", "📝 Detaylar"
        ])
        
        # Tablo ayarları
        self.log_table.setAlternatingRowColors(True)
        self.log_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.log_table.setSortingEnabled(True)
        self.log_table.horizontalHeader().setStretchLastSection(True)
        self.log_table.verticalHeader().setVisible(True)
        self.log_table.verticalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.log_table.verticalHeader().setStyleSheet("""
            QHeaderView::section {
                background-color: #1976D2;
                color: white;
                padding: 4px;
                border: none;
                font-weight: bold;
                font-size: 11px;
                min-width: 30px;
            }
        """)
        self.log_table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                alternate-background-color: #F8F9FA;
                gridline-color: #E0E0E0;
                border: 1px solid #E0E0E0;
                border-radius: 6px;
                font-size: 12px;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid #F0F0F0;
                color: #333333;
                font-weight: normal;
            }
            QTableWidget::item:selected {
                background-color: #E3F2FD;
                color: #1976D2;
                font-weight: bold;
            }
            QHeaderView::section {
                background-color: #1976D2;
                color: white;
                padding: 12px 8px;
                border: none;
                font-weight: bold;
                font-size: 12px;
            }
            QHeaderView::section:hover {
                background-color: #1565C0;
            }
            QTableCornerButton::section {
                background-color: #1976D2;
                border: none;
            }
            QTableWidget QTableCornerButton::section {
                background-color: #1976D2;
                color: white;
                font-weight: bold;
                font-size: 11px;
            }
        """)
        
        # Sütun genişlikleri
        column_widths = [160, 90, 220, 120, 90, 350]
        for i, width in enumerate(column_widths):
            self.log_table.setColumnWidth(i, width)
        
        table_layout.addWidget(self.log_table)
        layout.addWidget(table_group)
        
        # ==================== DETAY PANELİ ====================
        detail_group = QGroupBox("📄 Seçili Log Detayları")
        detail_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: 2px solid #FFF3E0;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: #FFFBF5;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px;
                color: #E65100;
            }
        """)
        detail_layout = QVBoxLayout(detail_group)
        
        self.log_detail_text = QTextEdit()
        self.log_detail_text.setMaximumHeight(180)
        self.log_detail_text.setReadOnly(True)
        self.log_detail_text.setStyleSheet("""
            QTextEdit {
                background-color: white;
                border: 2px solid #E0E0E0;
                border-radius: 6px;
                padding: 10px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 11px;
                line-height: 1.4;
                color: #333;
            }
            QTextEdit:focus {
                border-color: #FF9800;
            }
        """)
        detail_layout.addWidget(self.log_detail_text)
        
        layout.addWidget(detail_group)
        
        # Tablo seçim olayını bağla
        self.log_table.itemSelectionChanged.connect(self.on_log_selection_changed)
        
        # Log seçim stabilitesi için değişken
        self._updating_logs = False
        
        # Timer başlat
        self.start_log_timer()
        
        return widget
        
    def add_vcard_signature(self, email_body, attachments=None):
        """E-posta gövdesine kartvizit imzası ve görsel ön izlemeleri ekler"""
        if not self.vcard_enabled_check.isChecked():
            return email_body
            
        # Mesaj içeriğini yüksek kontrastlı ve tema-dostu HTML'e çevir
        if not email_body.strip().startswith('<'):
            # Düz metni HTML'e çevir (madde işaretlerini otomatik listeye dönüştür)
            converted = plain_text_to_html_with_lists(email_body)
            email_body = f'''
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#ffffff" style="background-color:#ffffff;">
              <tr>
                <td align="left" style="font-family: 'Segoe UI', Arial, sans-serif; font-size:15px; line-height:1.7; color:#111827; margin:25px 0; padding:20px; border-radius:12px; box-shadow:0 2px 10px rgba(0,0,0,0.06); border-left:4px solid #2563eb;">
                  {converted}
                </td>
              </tr>
            </table>
            '''
        
        # Görsel ön izlemelerini ekle (en üstte, sola hizalı)
        image_preview_html = ""
        if attachments:
            image_counter = 1
            for file_path in attachments:
                if os.path.exists(file_path):
                    file_ext = os.path.splitext(file_path)[1].lower()
                    if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
                        image_preview_html += f"""
                        <table width="400" style="margin: 10px 0; border-collapse: collapse;">
                        <tr>
                            <td style="text-align: left; padding: 5px;">
                                <img src="cid:image{image_counter}" width="400" height="300" style="width: 400px; height: 300px; border-radius: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);" alt="Görsel Ön İzleme" />
                            </td>
                        </tr>
                    </table>
                        """
                        image_counter += 1
        
        # Kartvizit görselini HTML içinde referans ver (sadece HTML imza yoksa)
        # Kartvizit görselini tablo yapısında tut - Outlook uyumlu
        vcard_html = f"""
        <br><br>
        <table width="300" style="margin: 15px 0; border-collapse: collapse; background-color: #ffffff; border: 1px solid #e5e7eb; border-radius: 5px;">
            <tr>
                <td style="padding: 10px; text-align: left;">
                    <img src="cid:kartvizit" width="150" height="100" style="width: 150px; height: 100px; border-radius: 4px; float: left; margin-right: 10px;" alt="Kartvizit" />
                    <div style="font-family: Arial, sans-serif; font-size: 12px; color: #374151; margin-left: 160px;">
                        Kartvizit Bilgileri
                    </div>
                </td>
            </tr>
        </table>
        """
        
        # Profesyonel imza HTML'i ekle
        signature_html = ""
        if hasattr(self, 'vcard_signature_enabled') and self.vcard_signature_enabled.isChecked():
            name = self.signature_name_edit.text().strip()
            phone = self.signature_phone_edit.text().strip()
            mobile = self.signature_mobile_edit.text().strip()
            email = self.signature_email_edit.text().strip()
            web = self.signature_web_edit.text().strip()
            address = self.signature_address_edit.text().strip()
            services = self.signature_services_edit.text().strip()
            
            # Sadece dolu olan alanları HTML'e ekle
            signature_parts = []
            
            if name:
                signature_parts.append(f'<div style="font-weight: 600; font-size: 16px; color: #111827; margin-bottom: 4px;">{name}</div>')
            
            if phone:
                signature_parts.append(f'<div style="color: #374151; margin: 2px 0; font-size: 13px;">☎️ {phone}</div>')
            
            if mobile:
                signature_parts.append(f'<div style="color: #374151; margin: 2px 0; font-size: 13px;">📱 {mobile}</div>')
            
            if email:
                signature_parts.append(f'<div style="color: #374151; margin: 2px 0; font-size: 13px;">✉️ {email}</div>')
            
            if web:
                signature_parts.append(f'<div style="color: #374151; margin: 2px 0; font-size: 13px;">🌐 {web}</div>')
            
            if address:
                signature_parts.append(f'<div style="color: #6B7280; font-size: 12px; font-style: italic; margin: 4px 0 2px 0;">📍 {address}</div>')
            
            if services:
                signature_parts.append(f'<div style="color: #9CA3AF; font-size: 11px; font-style: italic; margin: 2px 0;">💼 {services}</div>')
            
            # Eğer en az bir alan doluysa HTML oluştur
            if signature_parts:
                # Fazla boşlukları önlemek için parça stillerini sıklaştır
                signature_parts = [p.replace("margin: 2px 0;", "margin: 1px 0;") for p in signature_parts]
                signature_parts = [p.replace("margin: 4px 0 2px 0;", "margin: 2px 0 1px 0;") for p in signature_parts]
                signature_html = f'''
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#ffffff" style="background-color:#ffffff; margin-top:25px;">
                  <tr>
                    <td align="left" style="font-family: 'Segoe UI', Arial, sans-serif; font-size:14px; color:#374151; padding:12px; line-height:1.35; border-left:4px solid #e74c3c; border-radius:10px; box-shadow:0 2px 8px rgba(0,0,0,0.06);">
                      {''.join(signature_parts)}
                    </td>
                  </tr>
                </table>
                '''

        # HTML imza varsa kartvizit görselini gösterme
        if signature_html:
            vcard_html = ""
        
        return image_preview_html + email_body + signature_html + vcard_html
    def on_vcard_image_changed(self, selected_text):
        """Kartvizit görsel seçimi değiştiğinde çalışır"""
        if selected_text == "Kartvizit Yok":
            self.vcard_image_path_edit.setText("")
            self.vcard_image_path_edit.setPlaceholderText("Kartvizit görseli seçilmedi")
        elif selected_text == "Özel Kartvizit":
            # Kaydedilmiş yolu kontrol et
            config = self.config_manager.load_config()
            saved_path = config.get("settings", {}).get("vcard_image_path", "")
            if saved_path and os.path.exists(saved_path):
                self.vcard_image_path_edit.setText(saved_path)
            else:
                # Eğer kaydedilmiş yol yoksa veya dosya mevcut değilse, dosya seçim dialogunu aç
                self.browse_vcard_image()
        else:
            # Seçilen dosya adına göre kartvizitler klasöründen dosyayı bul
            kartvizitler_path = "kartvizitler"
            file_path = os.path.join(kartvizitler_path, selected_text)
            if os.path.exists(file_path):
                self.vcard_image_path_edit.setText(file_path)
            else:
                self.vcard_image_path_edit.setText("")
                self.vcard_image_path_edit.setPlaceholderText(f"Dosya bulunamadı: {selected_text}")

    def browse_vcard_image(self):
        """Kartvizit görseli seç"""
        # Önce config'den kaydedilmiş yolu kontrol et
        config = self.config_manager.load_config()
        saved_path = ""
        if config.get("settings", {}).get("vcard_image_path"):
            saved_path = config["settings"]["vcard_image_path"]
        
        # Eğer kaydedilmiş yol varsa ve dosya mevcutsa, onu kullan
        if saved_path and os.path.exists(saved_path):
            self.vcard_image_path_edit.setText(saved_path)
            # ComboBox'ı "Özel Kartvizit" olarak güncelle
            self.vcard_image_combo.setCurrentText("Özel Kartvizit")
            return
        
        # Eğer kaydedilmiş yol yoksa veya dosya mevcut değilse, dosya seçim dialogunu aç
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Kartvizit Görseli Seç", "", 
            "Görsel Dosyaları (*.jpg *.jpeg *.png *.gif *.bmp);;Tüm Dosyalar (*)"
        )
        if file_path:
            self.vcard_image_path_edit.setText(file_path)
            # ComboBox'ı "Özel Kartvizit" olarak güncelle
            self.vcard_image_combo.setCurrentText("Özel Kartvizit")
        
    def apply_styles(self):
        """Uygulama stillerini uygula"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #cccccc;
                border-radius: 5px;
                margin-top: 1ex;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QPushButton {
                background-color: #4CAF50;
                border: none;
                color: white;
                padding: 8px 16px;
                text-align: center;
                text-decoration: none;
                font-size: 14px;
                margin: 4px 2px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QLineEdit, QTextEdit, QComboBox, QSpinBox {
                padding: 5px;
                border: 1px solid #ddd;
                border-radius: 3px;
                background-color: white;
            }
            QTableWidget {
                gridline-color: #ddd;
                background-color: white;
                alternate-background-color: #f9f9f9;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            QHeaderView::section {
                background-color: #f0f0f0;
                padding: 8px 4px;
                border: 1px solid #ddd;
                font-weight: bold;
                color: #333;
                text-align: left;
            }
            QHeaderView::section:hover {
                background-color: #e0e0e0;
            }
            QScrollArea {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: white;
            }
            QScrollBar:vertical {
                background-color: #f0f0f0;
                width: 16px;
                border-radius: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background-color: #c0c0c0;
                border-radius: 8px;
                min-height: 30px;
                margin: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #a0a0a0;
            }
            QScrollBar::add-line:vertical {
                height: 0px;
            }
            QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            QScrollBar:horizontal {
                background-color: #f0f0f0;
                height: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:horizontal {
                background-color: #c0c0c0;
                border-radius: 6px;
                min-width: 20px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #a0a0a0;
            }
        """)
        
    def load_config(self):
        """Yapılandırma dosyasını yükle"""
        try:
            config = self.config_manager.load_config()
            # Veritabanı ayarlarını arayüze yükle
            if config.get("database"):
                db = config["database"]
                self.db_host_edit.setText(db.get("host", ""))
                self.db_port_edit.setText(str(db.get("port", "")))
                self.db_name_edit.setText(db.get("database", ""))
                self.db_user_edit.setText(db.get("user", ""))
                self.db_password_edit.setText(db.get("password", ""))
            else:
                self.db_host_edit.setText("")
                self.db_port_edit.setText("")
                self.db_name_edit.setText("")
                self.db_user_edit.setText("")
                self.db_password_edit.setText("")
            # Genel ayarları arayüze yükle
            if config.get("settings"):
                s = config["settings"]
                # Backup ayarlarını geçici olarak signal'i devre dışı bırakarak yükle
                self.backup_check.stateChanged.disconnect()
                self.backup_check.setChecked(s.get("backup_enabled", False))
                self.backup_dir_edit.setText(s.get("backup_dir", ""))
                # Signal'i tekrar bağla
                self.backup_check.stateChanged.connect(self.toggle_auto_backup)
                self.sound_check.setChecked(s.get("sound_enabled", False))
                self.popup_check.setChecked(s.get("popup_enabled", False))
                self.email_error_check.setChecked(s.get("email_error_enabled", False))
                self.log_dir_edit.setText(s.get("log_dir", ""))
                # SMTP ayarları eklendi
                self.smtp_server_edit.setText(s.get("smtp_server", "smtp.gmail.com"))
                self.smtp_port_edit.setText(s.get("smtp_port", "587"))
                self.sender_email_edit.setText(s.get("sender_email", ""))
                self.sender_password_edit.setText(s.get("sender_password", ""))

                # Kartvizit ayarları eklendi
                self.vcard_enabled_check.setChecked(s.get("vcard_enabled", False))
                vcard_image_path = s.get("vcard_image_path", "")
                if vcard_image_path and os.path.exists(vcard_image_path):
                    self.vcard_image_path_edit.setText(vcard_image_path)
                    # ComboBox'ı uygun seçenekle güncelle
                    filename = os.path.basename(vcard_image_path)
                    kartvizitler_path = "kartvizitler"
                    if vcard_image_path.startswith(kartvizitler_path) and filename in [self.vcard_image_combo.itemText(i) for i in range(self.vcard_image_combo.count())]:
                        self.vcard_image_combo.setCurrentText(filename)
                    else:
                        self.vcard_image_combo.setCurrentText("Özel Kartvizit")
                else:
                    # Dosya mevcut değilse varsayılan değerleri ayarla
                    self.vcard_image_combo.setCurrentText("Kartvizit Yok")
                    self.vcard_image_path_edit.setText("")
                    self.vcard_image_path_edit.setPlaceholderText("Kartvizit görseli seçilmedi")
                
                # HTML İmza ayarları eklendi
                if hasattr(self, 'vcard_signature_enabled'):
                    self.vcard_signature_enabled.setChecked(s.get("vcard_signature_enabled", False))
                    self.signature_name_edit.setText(s.get("signature_name", ""))
                    self.signature_phone_edit.setText(s.get("signature_phone", ""))
                    self.signature_mobile_edit.setText(s.get("signature_mobile", ""))
                    self.signature_email_edit.setText(s.get("signature_email", ""))
                    self.signature_web_edit.setText(s.get("signature_web", ""))
                    self.signature_address_edit.setText(s.get("signature_address", ""))
                    self.signature_services_edit.setText(s.get("signature_services", ""))
                
                # BCC ayarları eklendi
                bcc_enabled = s.get("bcc_enabled", False)
                # Signal'i geçici olarak devre dışı bırak
                self.bcc_checkbox.stateChanged.disconnect()
                

                self.bcc_checkbox.setChecked(bcc_enabled)
                # Signal'i tekrar bağla
                self.bcc_checkbox.stateChanged.connect(self.on_bcc_checkbox_changed)
                if bcc_enabled:
                    self.bcc_status_label.setText("BCC Açık")
                    self.bcc_status_label.setStyleSheet("color: #4CAF50; font-size: 11px; font-style: italic; font-weight: bold;")
                else:
                    self.bcc_status_label.setText("BCC Kapalı")
                    self.bcc_status_label.setStyleSheet("color: #666; font-size: 11px; font-style: italic;")

            else:
                # Backup ayarlarını geçici olarak signal'i devre dışı bırakarak yükle
                self.backup_check.stateChanged.disconnect()
                self.backup_check.setChecked(False)
                self.backup_dir_edit.setText("")
                # Signal'i tekrar bağla
                self.backup_check.stateChanged.connect(self.toggle_auto_backup)
                self.sound_check.setChecked(False)
                self.popup_check.setChecked(False)
                self.email_error_check.setChecked(False)
                self.log_dir_edit.setText("")
                # SMTP ayarları varsayılan değerler
                self.smtp_server_edit.setText("smtp.gmail.com")
                self.smtp_port_edit.setText("587")
                self.sender_email_edit.setText("")
                self.sender_password_edit.setText("")
                # Kartvizit ayarları varsayılan değerler
                self.vcard_enabled_check.setChecked(False)
                self.vcard_image_combo.setCurrentText("Kartvizit Yok")
                self.vcard_image_path_edit.setText("")
                self.vcard_image_path_edit.setPlaceholderText("Kartvizit görseli seçilmedi")

                # BCC ayarları varsayılan değerler
                # Signal'i geçici olarak devre dışı bırak
                self.bcc_checkbox.stateChanged.disconnect()
                self.bcc_checkbox.setChecked(False)
                # Signal'i tekrar bağla
                self.bcc_checkbox.stateChanged.connect(self.on_bcc_checkbox_changed)
                self.bcc_status_label.setText("BCC Kapalı")
                self.bcc_status_label.setStyleSheet("color: #666; font-size: 11px; font-style: italic;")
                
            self.logger.info("Yapılandırma dosyası yüklendi")
            
            # Gönderim istatistiklerini yükle
            self.load_sending_stats()
            
            # Sonraki zamanlama etiketini güncelle
            self.update_next_schedule_label()
                
        except Exception as e:
            self.logger.error(f"Yapılandırma yüklenirken hata: {e}")
            
    def save_config(self):
        """Yapılandırma ayarlarını kaydet"""
        try:
            # Form verilerini topla ve kaydet
            settings = {
                "backup_enabled": self.backup_check.isChecked(),
                "backup_dir": self.backup_dir_edit.text(),
                "sound_enabled": self.sound_check.isChecked(),
                "popup_enabled": self.popup_check.isChecked(),
                "email_error_enabled": self.email_error_check.isChecked(),
                "log_dir": self.log_dir_edit.text(),
                # HTML İmza ayarları
                "vcard_signature_enabled": self.vcard_signature_enabled.isChecked(),
                "signature_name": self.signature_name_edit.text(),
                "signature_phone": self.signature_phone_edit.text(),
                "signature_mobile": self.signature_mobile_edit.text(),
                "signature_email": self.signature_email_edit.text(),
                "signature_web": self.signature_web_edit.text(),
                "signature_address": self.signature_address_edit.text(),
                "signature_services": self.signature_services_edit.text(),
                # SMTP ayarları
                "smtp_server": self.smtp_server_edit.text(),
                "smtp_port": self.smtp_port_edit.text(),
                "sender_email": self.sender_email_edit.text(),
                "sender_password": self.sender_password_edit.text(),
                # Kartvizit ayarları
                "vcard_enabled": self.vcard_enabled_check.isChecked(),
                "vcard_image_path": self.vcard_image_path_edit.text(),
                # BCC ayarları
                "bcc_enabled": self.bcc_checkbox.isChecked(),
                # E-posta delay ayarı
                "email_delay_schedule": str(self.email_delay_spin_schedule.value()),

            }
            self.config_manager.save_settings(settings)
            
            self.logger.info("Yapılandırma ayarları kaydedildi")
            QMessageBox.information(self, "Başarılı", "Yapılandırma ayarları kaydedildi!")
        except Exception as e:
            self.logger.error(f"Ayarlar kaydedilirken hata: {e}")
            QMessageBox.critical(self, "Hata", f"Ayarlar kaydedilemedi: {e}")
            
    def test_database_connection(self):
        """Veritabanı bağlantısını test et"""
        try:
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            
            # Veritabanı bağlantı parametrelerini al
            host = self.db_host_edit.text()
            port = self.db_port_edit.text()
            db_name = self.db_name_edit.text()
            user = self.db_user_edit.text()
            password = self.db_password_edit.text()
            
            self.progress_bar.setValue(50)
            
            # Bağlantıyı test et
            success = self.database_manager.test_connection(
                host, port, db_name, user, password
            )
            
            self.progress_bar.setValue(100)
            
            if success:
                self.db_status_label.setText("Veritabanı: Bağlı")
                self.db_status_label.setStyleSheet("color: green; font-weight: bold;")
                QMessageBox.information(self, "Başarılı", "Veritabanı bağlantısı başarılı!")
                self.populate_table_list()  # Tablo listesini doldur
                # Filtreleme penceresindeki tablo isimlerini güncelle
                self.update_filter_comboboxes()
            else:
                self.db_status_label.setText("Veritabanı: Bağlantı hatası")
                self.db_status_label.setStyleSheet("color: red; font-weight: bold;")
                QMessageBox.critical(self, "Hata", "Veritabanı bağlantısı başarısız!")
                self.table_list.setRowCount(0)  # Bağlantı yoksa tabloyu temizle
                # Filtreleme penceresindeki combobox'ları temizle
                if hasattr(self, 'filter_tablo_adi'):
                    self.filter_tablo_adi.clear()
                    self.filter_tablo_adi.addItem("")
                if hasattr(self, 'filter_il'):
                    self.filter_il.clear()
                    self.filter_il.addItem("")
                if hasattr(self, 'filter_sektor'):
                    self.filter_sektor.clear()
                    self.filter_sektor.addItem("")
            
        except Exception as e:
            self.logger.error(f"Veritabanı test hatası: {e}")
            QMessageBox.critical(self, "Hata", f"Veritabanı test hatası: {e}")
        finally:
            self.progress_bar.setVisible(False)
            
    def update_sending_counters(self, sent_count):
        """Gönderim sayaçlarını güncelle - İyileştirilmiş versiyon"""
        try:
            current_time = datetime.now()
            
            # 1. SAATLIK SAYAÇ KONTROLÜ - Daha kesin zamanlı
            current_hour = current_time.replace(minute=0, second=0, microsecond=0)
            if current_time >= self.last_hourly_reset + timedelta(hours=1):
                self.hourly_sent_count = 0
                self.last_hourly_reset = current_hour
                self.logger.info(f"Saatlik gönderim sayacı sıfırlandı - Yeni saat: {current_hour}")
            
            # 2. GÜNLÜK SAYAÇ KONTROLÜ - Daha kesin zamanlı
            current_day = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
            if current_time >= self.last_daily_reset + timedelta(days=1):
                self.daily_sent_count = 0
                self.last_daily_reset = current_day
                self.logger.info(f"Günlük gönderim sayacı sıfırlandı - Yeni gün: {current_day}")
            
            # 3. SAYAÇLARI GÜNCELLE
            self.hourly_sent_count += sent_count
            self.daily_sent_count += sent_count
            
            # 4. İSTATİSTİKLERİ GÜNCELLE
            self.update_sending_stats_display()
            
            # 5. DETAYLI LOG KAYDI
            self.logger.info(f"Gönderim sayaçları güncellendi - Gönderilen: {sent_count}, Saatlik: {self.hourly_sent_count}, Günlük: {self.daily_sent_count}")
            
            # 6. İSTATİSTİKLERİ KAYDET
            self.save_sending_stats()
            
        except Exception as e:
            self.logger.error(f"Gönderim sayaçları güncellenirken hata: {e}")
            # Hata durumunda bile istatistikleri kaydetmeye çalış
            try:
                self.save_sending_stats()
            except:
                pass
            
    def update_sending_stats_display(self):
        """Gönderim istatistiklerini ekranda güncelle - İyileştirilmiş versiyon"""
        try:
            # 1. WIDGET KONTROLÜ - Daha sağlam
            required_widgets = ['hourly_sent_label', 'daily_sent_label', 'hourly_limit_spin', 'daily_limit_spin']
            missing_widgets = [widget for widget in required_widgets if not hasattr(self, widget) or getattr(self, widget) is None]
            
            if missing_widgets:
                self.logger.warning(f"İstatistik widget'ları henüz oluşturulmamış: {missing_widgets}")
                return
            
            # 2. LİMİTLERİ AL
            hourly_limit = self.hourly_limit_spin.value()
            daily_limit = self.daily_limit_spin.value()
            
            # 3. RENK KODLARINI BELİRLE
            hourly_color = "#4CAF50" if self.hourly_sent_count < hourly_limit else "#F44336"
            daily_color = "#2196F3" if self.daily_sent_count < daily_limit else "#F44336"
            
            # 4. ETİKETLERİ GÜNCELLE
            self.hourly_sent_label.setText(f"{self.hourly_sent_count}/{hourly_limit} e-posta")
            self.hourly_sent_label.setStyleSheet(f"color: {hourly_color}; font-weight: bold; font-size: 11px;")
            
            self.daily_sent_label.setText(f"{self.daily_sent_count}/{daily_limit} e-posta")
            self.daily_sent_label.setStyleSheet(f"color: {daily_color}; font-weight: bold; font-size: 11px;")
            
            # 5. EMAIL STATS LABEL'INI GÜNCELLE
            if hasattr(self, 'email_stats_label') and self.email_stats_label:
                total_sent = self.hourly_sent_count + self.daily_sent_count
                stats_text = f"📊 E-posta İstatistikleri: Saatlik {self.hourly_sent_count}/{hourly_limit}, Günlük {self.daily_sent_count}/{daily_limit}"
                self.email_stats_label.setText(stats_text)
                
                # Renk kodunu belirle
                if self.hourly_sent_count >= hourly_limit or self.daily_sent_count >= daily_limit:
                    stats_color = "#F44336"  # Kırmızı - limit aşıldı
                elif self.hourly_sent_count >= hourly_limit * 0.8 or self.daily_sent_count >= daily_limit * 0.8:
                    stats_color = "#FF9800"  # Turuncu - limit yaklaşıyor
                else:
                    stats_color = "#4CAF50"  # Yeşil - normal
                
                self.email_stats_label.setStyleSheet(f"""
                    QLabel {{
                        font-size: 13px;
                        color: {stats_color};
                        font-weight: bold;
                        padding: 8px;
                        background-color: #E8F5E8;
                        border-radius: 6px;
                        border: 1px solid #C8E6C9;
                    }}
                """)
            
            # 6. DETAYLI LOG KAYDI
            self.logger.info(f"İstatistik güncellendi - Saatlik: {self.hourly_sent_count}/{hourly_limit}, Günlük: {self.daily_sent_count}/{daily_limit}")
            
            # 7. OTOMATİK KAYIT
            self.save_sending_stats()
                
        except Exception as e:
            self.logger.error(f"Gönderim istatistikleri güncellenirken hata: {e}")
            # Hata durumunda bile kaydetmeye çalış
            try:
                self.save_sending_stats()
            except:
                pass
            
    def refresh_sending_stats(self):
        """Gönderim istatistiklerini yenile - İyileştirilmiş versiyon"""
        try:
            current_time = datetime.now()
            
            # 1. SAATLIK SAYAÇ KONTROLÜ - Daha kesin zamanlı
            current_hour = current_time.replace(minute=0, second=0, microsecond=0)
            if current_time >= self.last_hourly_reset + timedelta(hours=1):
                self.hourly_sent_count = 0
                self.last_hourly_reset = current_hour
                self.logger.info(f"Saatlik gönderim sayacı sıfırlandı - Yeni saat: {current_hour}")
            
            # 2. GÜNLÜK SAYAÇ KONTROLÜ - Daha kesin zamanlı
            current_day = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
            if current_time >= self.last_daily_reset + timedelta(days=1):
                self.daily_sent_count = 0
                self.last_daily_reset = current_day
                self.logger.info(f"Günlük gönderim sayacı sıfırlandı - Yeni gün: {current_day}")
            
            # 3. İSTATİSTİKLERİ GÜNCELLE
            self.update_sending_stats_display()
            
            # 4. İSTATİSTİKLERİ KAYDET
            self.save_sending_stats()
            
            # 5. DETAYLI LOG KAYDI
            self.logger.info(f"Gönderim istatistikleri yenilendi - Saatlik: {self.hourly_sent_count}, Günlük: {self.daily_sent_count}")
            
        except Exception as e:
            self.logger.error(f"Gönderim istatistikleri yenilenirken hata: {e}")
            # Hata durumunda bile kaydetmeye çalış
            try:
                self.save_sending_stats()
            except:
                pass
            QMessageBox.critical(self, "Hata", f"İstatistikler yenilenemedi: {e}")
            
    def save_sending_stats(self):
        """Gönderim istatistiklerini kaydet - İyileştirilmiş versiyon"""
        try:
            # 1. VERİ DOĞRULAMA
            if not hasattr(self, 'hourly_sent_count') or not hasattr(self, 'daily_sent_count'):
                self.logger.error("Gönderim sayaçları tanımlanmamış")
                return
            
            # 2. İSTATİSTİK VERİLERİNİ HAZIRLA
            stats = {
                "hourly_sent_count": max(0, self.hourly_sent_count),  # Negatif değerleri engelle
                "daily_sent_count": max(0, self.daily_sent_count),     # Negatif değerleri engelle
                "last_hourly_reset": self.last_hourly_reset.isoformat(),
                "last_daily_reset": self.last_daily_reset.isoformat(),
                "last_save_time": datetime.now().isoformat()  # Son kayıt zamanı
            }
            
            # 3. KONFİGÜRASYONU YÜKLE VE GÜNCELLE
            config = self.config_manager.load_config()
            config["sending_stats"] = stats
            self.config_manager.save_config(config)
            
            # 4. BAŞARI LOGU
            self.logger.info(f"Gönderim istatistikleri kaydedildi - Saatlik: {self.hourly_sent_count}, Günlük: {self.daily_sent_count}")
            
        except Exception as e:
            self.logger.error(f"Gönderim istatistikleri kaydedilirken hata: {e}")
            # Kritik hata durumunda kullanıcıya bildir
            try:
                QMessageBox.warning(self, "Uyarı", "İstatistikler kaydedilemedi. Veriler geçici olarak kaybolabilir.")
            except:
                pass

    def load_sending_stats(self):
        """Gönderim istatistiklerini yükle - İyileştirilmiş versiyon"""
        try:
            # 1. KONFİGÜRASYONU YÜKLE
            config = self.config_manager.load_config()
            if "sending_stats" not in config:
                self.logger.info("Kayıtlı istatistik bulunamadı, varsayılan değerler kullanılıyor")
                self._initialize_default_stats()
                return
            
            stats = config["sending_stats"]
            
            # 2. VERİ DOĞRULAMA
            required_fields = ["hourly_sent_count", "daily_sent_count", "last_hourly_reset", "last_daily_reset"]
            missing_fields = [field for field in required_fields if field not in stats]
            
            if missing_fields:
                self.logger.warning(f"Eksik istatistik alanları: {missing_fields}, varsayılan değerler kullanılıyor")
                self._initialize_default_stats()
                return
            
            # 3. SAYAÇLARI YÜKLE
            self.hourly_sent_count = max(0, stats.get("hourly_sent_count", 0))
            self.daily_sent_count = max(0, stats.get("daily_sent_count", 0))
            
            # 4. TARİHLERİ YÜKLE
            try:
                self.last_hourly_reset = datetime.fromisoformat(stats.get("last_hourly_reset", ""))
                self.last_daily_reset = datetime.fromisoformat(stats.get("last_daily_reset", ""))
            except (ValueError, TypeError) as e:
                self.logger.warning(f"Tarih formatı hatası: {e}, varsayılan tarihler kullanılıyor")
                self.last_hourly_reset = datetime.now()
                self.last_daily_reset = datetime.now()
            
            # 5. BAŞARI LOGU
            self.logger.info(f"İstatistikler yüklendi - Saatlik: {self.hourly_sent_count}, Günlük: {self.daily_sent_count}")
            
        except Exception as e:
            self.logger.error(f"İstatistikler yüklenirken hata: {e}")
            self._initialize_default_stats()
    
    def _initialize_default_stats(self):
        """Varsayılan istatistik değerlerini başlat"""
        try:
            current_time = datetime.now()
            self.hourly_sent_count = 0
            self.daily_sent_count = 0
            self.last_hourly_reset = current_time.replace(minute=0, second=0, microsecond=0)
            self.last_daily_reset = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
            self.logger.info("Varsayılan istatistik değerleri başlatıldı")
        except Exception as e:
            self.logger.error(f"Varsayılan istatistik başlatılırken hata: {e}")

    def check_sending_limits(self):
        """Gönderim limitlerini kontrol et"""
        try:
            # Limit kontrolü aktif mi?
            if not self.limit_check.isChecked():
                return True, "Limit kontrolü devre dışı"
            
            # Sayaçları yenile
            self.refresh_sending_stats()
            
            # Limitleri al
            hourly_limit = self.hourly_limit_spin.value()
            daily_limit = self.daily_limit_spin.value()
            
            # Saatlik limit kontrolü
            if self.hourly_sent_count >= hourly_limit:
                next_hourly_reset = self.last_hourly_reset + timedelta(hours=1)
                remaining_time = next_hourly_reset - datetime.now()
                hours = int(remaining_time.total_seconds() // 3600)
                minutes = int((remaining_time.total_seconds() % 3600) // 60)
                
                return False, f"Saatlik limit ({hourly_limit}) doldu! {hours} saat {minutes} dakika sonra tekrar deneyin."
            
            # Günlük limit kontrolü
            if self.daily_sent_count >= daily_limit:
                next_daily_reset = self.last_daily_reset + timedelta(days=1)
                remaining_time = next_daily_reset - datetime.now()
                hours = int(remaining_time.total_seconds() // 3600)
                minutes = int((remaining_time.total_seconds() % 3600) // 60)
                
                return False, f"Günlük limit ({daily_limit}) doldu! {hours} saat {minutes} dakika sonra tekrar deneyin."
            
            return True, f"Limit kontrolü geçti - Saatlik: {self.hourly_sent_count}/{hourly_limit}, Günlük: {self.daily_sent_count}/{daily_limit}"
            
        except Exception as e:
            self.logger.error(f"Limit kontrolü sırasında hata: {e}")
            return False, f"Limit kontrolü hatası: {e}"
    def calculate_safe_sending_count(self, total_recipients):
        """Güvenli gönderim sayısını hesapla"""
        try:
            # Limit kontrolü
            can_send, message = self.check_sending_limits()
            if not can_send:
                return 0, message
            
            # Limitleri al
            hourly_limit = self.hourly_limit_spin.value()
            daily_limit = self.daily_limit_spin.value()
            
            # Kalan gönderim kapasitesini hesapla
            remaining_hourly = hourly_limit - self.hourly_sent_count
            remaining_daily = daily_limit - self.daily_sent_count
            
            # En düşük limiti seç
            safe_count = min(remaining_hourly, remaining_daily, total_recipients)
            
            if safe_count <= 0:
                return 0, "Gönderim limiti doldu!"
            
            return safe_count, f"Güvenli gönderim sayısı: {safe_count}/{total_recipients}"
            
        except Exception as e:
            self.logger.error(f"Güvenli gönderim sayısı hesaplanırken hata: {e}")
            return 0, f"Hesaplama hatası: {e}"

    def show_limit_status(self):
        """Limit durumunu göster"""
        try:
            # Sayaçları yenile
            self.refresh_sending_stats()
            
            # Limitleri al
            hourly_limit = self.hourly_limit_spin.value()
            daily_limit = self.daily_limit_spin.value()
            
            # Kalan süreleri hesapla
            current_time = datetime.now()
            
            # Saatlik limit için kalan süre
            next_hourly_reset = self.last_hourly_reset + timedelta(hours=1)
            hourly_remaining = next_hourly_reset - current_time
            hourly_hours = int(hourly_remaining.total_seconds() // 3600)
            hourly_minutes = int((hourly_remaining.total_seconds() % 3600) // 60)
            
            # Günlük limit için kalan süre
            next_daily_reset = self.last_daily_reset + timedelta(days=1)
            daily_remaining = next_daily_reset - current_time
            daily_hours = int(daily_remaining.total_seconds() // 3600)
            daily_minutes = int((daily_remaining.total_seconds() % 3600) // 60)
            
            # Durum mesajı
            status_message = f"GÖNDERİM LİMİT DURUMU\n\n"
            status_message += f"Saatlik Limit: {self.hourly_sent_count}/{hourly_limit}\n"
            status_message += f"Kalan Saatlik Süre: {hourly_hours} saat {hourly_minutes} dakika\n\n"
            status_message += f"Günlük Limit: {self.daily_sent_count}/{daily_limit}\n"
            status_message += f"Kalan Günlük Süre: {daily_hours} saat {daily_minutes} dakika\n\n"
            
            # Limit durumları
            if self.hourly_sent_count >= hourly_limit:
                status_message += "⚠️ SAATLİK LİMİT DOLDU!\n"
            if self.daily_sent_count >= daily_limit:
                status_message += "⚠️ GÜNLÜK LİMİT DOLDU!\n"
            if self.hourly_sent_count < hourly_limit and self.daily_sent_count < daily_limit:
                status_message += "✅ Limitler uygun, gönderim yapılabilir."
            
            QMessageBox.information(self, "Limit Durumu", status_message)
            
        except Exception as e:
            self.logger.error(f"Limit durumu gösterilirken hata: {e}")
            QMessageBox.critical(self, "Hata", f"Limit durumu gösterilemedi: {e}")

    def add_scheduled_email_to_list(self, email_data):
        """Zamanlanmış e-postayı listeye ekle"""
        try:
            # Zamanlama verilerini sakla
            self.scheduled_emails.append(email_data)
            
            # Tabloyu yenile
            self.refresh_schedule_list()
            
            # Sonraki zamanlama etiketini güncelle
            self.update_next_schedule_label()
            
            self.logger.info(f"Zamanlanmış e-posta listeye eklendi: {email_data['subject']}")
            
        except Exception as e:
            self.logger.error(f"Zamanlanmış e-posta listeye eklenirken hata: {e}")

    def refresh_schedule_list(self):
        """Zamanlama listesini yenile"""
        try:
            self.schedule_list.setRowCount(0)
            
            for i, email_data in enumerate(self.scheduled_emails):
                self.schedule_list.insertRow(i)
                
                # Görev adı
                task_name = f"E-posta Gönderimi #{i+1}"
                self.schedule_list.setItem(i, 0, QTableWidgetItem(task_name))
                
                # Konu
                subject = email_data.get('subject', 'Konu yok')
                if len(subject) > 30:
                    subject = subject[:27] + "..."
                self.schedule_list.setItem(i, 1, QTableWidgetItem(subject))
                
                # Zamanlanan tarih
                scheduled_datetime = email_data.get('datetime')
                if scheduled_datetime:
                    date_str = scheduled_datetime.toString('dd.MM.yyyy HH:mm')
                else:
                    date_str = "Belirtilmemiş"
                self.schedule_list.setItem(i, 2, QTableWidgetItem(date_str))
                
                # Alıcı sayısı
                recipients = email_data.get('recipients', [])
                recipient_count = len(recipients)
                self.schedule_list.setItem(i, 3, QTableWidgetItem(str(recipient_count)))
                
                # Durum - Gerçek gönderim durumunu kontrol et
                current_time = QDateTime.currentDateTime()
                status_item = QTableWidgetItem()
                status_item.setTextAlignment(Qt.AlignCenter)
                
                if scheduled_datetime:
                    if current_time >= scheduled_datetime:
                        # Zamanı geçmiş ama gönderilip gönderilmediğini kontrol et
                        if email_data.get('sent', False):
                            status = "✅ Tamamlandı"
                            status_item.setBackground(QColor("#E8F5E9"))  # Yeşil arka plan
                            status_item.setForeground(QColor("#2E7D32"))  # Koyu yeşil yazı
                        else:
                            status = "⏳ Gönderiliyor..."
                            status_item.setBackground(QColor("#E3F2FD"))  # Mavi arka plan
                            status_item.setForeground(QColor("#1565C0"))  # Koyu mavi yazı
                    else:
                        time_diff = current_time.msecsTo(scheduled_datetime)
                        hours = time_diff // 3600000
                        minutes = (time_diff % 3600000) // 60000
                        status = f"⏰ {hours}s {minutes}d kaldı"
                        status_item.setBackground(QColor("#FFF3E0"))  # Turuncu arka plan
                        status_item.setForeground(QColor("#E65100"))  # Koyu turuncu yazı
                else:
                    status = "❓ Belirsiz"
                    status_item.setBackground(QColor("#FFEBEE"))  # Kırmızı arka plan
                    status_item.setForeground(QColor("#C62828"))  # Koyu kırmızı yazı
                
                status_item.setText(status)
                self.schedule_list.setItem(i, 4, status_item)
                
                # İşlem butonu
                if scheduled_datetime and current_time < scheduled_datetime:
                    cancel_btn = QPushButton("İptal Et")
                    cancel_btn.setFixedSize(60, 25)
                    cancel_btn.setStyleSheet("background-color: #F44336; color: white; font-size: 9px; border: none; border-radius: 2px;")
                    cancel_btn.clicked.connect(lambda checked, row=i: self.cancel_scheduled_email(row))
                    self.schedule_list.setCellWidget(i, 5, cancel_btn)
                else:
                    self.schedule_list.setItem(i, 5, QTableWidgetItem(""))
            
            # Sütun genişliklerini ayarla
            self.schedule_list.setColumnWidth(0, 120)  # Görev
            self.schedule_list.setColumnWidth(1, 200)  # Konu
            self.schedule_list.setColumnWidth(2, 120)  # Tarih
            self.schedule_list.setColumnWidth(3, 80)   # Alıcı sayısı
            self.schedule_list.setColumnWidth(4, 120)  # Durum
            self.schedule_list.setColumnWidth(5, 80)   # İşlem
            
            self.logger.info(f"Zamanlama listesi yenilendi: {len(self.scheduled_emails)} zamanlama")
            
            # Sonraki zamanlama etiketini güncelle
            self.update_next_schedule_label()
            
        except Exception as e:
            self.logger.error(f"Zamanlama listesi yenilenirken hata: {e}")

    def update_next_schedule_label(self):
        """Sonraki zamanlama etiketini güncelle"""
        try:
            if not hasattr(self, 'next_schedule_label'):
                return
                
            current_time = QDateTime.currentDateTime()
            next_schedule = None
            min_time_diff = float('inf')
            
            # En yakın zamanlamayı bul
            for email_data in self.scheduled_emails:
                scheduled_datetime = email_data.get('datetime')
                if scheduled_datetime and current_time < scheduled_datetime:
                    # Henüz gönderilmemiş ve gelecekte olan zamanlamalar
                    if not email_data.get('sent', False):
                        time_diff = current_time.msecsTo(scheduled_datetime)
                        if time_diff < min_time_diff:
                            min_time_diff = time_diff
                            next_schedule = email_data
            
            if next_schedule:
                scheduled_datetime = next_schedule['datetime']
                subject = next_schedule.get('subject', 'Konu yok')
                
                # Kalan süreyi hesapla
                time_diff = current_time.msecsTo(scheduled_datetime)
                hours = time_diff // 3600000
                minutes = (time_diff % 3600000) // 60000
                
                if hours > 0:
                    time_str = f"{hours}s {minutes}d"
                else:
                    time_str = f"{minutes}d"
                
                # Etiketi güncelle
                next_schedule_text = f"Sonraki Zamanlama: {scheduled_datetime.toString('dd.MM.yyyy HH:mm')} ({time_str} kaldı) - {subject}"
                self.next_schedule_label.setText(next_schedule_text)
                self.next_schedule_label.setStyleSheet("color: #2196F3; font-weight: bold;")
                
                self.logger.info(f"Sonraki zamanlama güncellendi: {subject} - {time_str} kaldı")
            else:
                # Zamanlama yoksa
                self.next_schedule_label.setText("Sonraki Zamanlama: Yok")
                self.next_schedule_label.setStyleSheet("color: #666; font-weight: normal;")
                
                self.logger.info("Sonraki zamanlama bulunamadı")
                
        except Exception as e:
            self.logger.error(f"Sonraki zamanlama etiketi güncellenirken hata: {e}")
            self.next_schedule_label.setText("Sonraki Zamanlama: Hata")
            self.next_schedule_label.setStyleSheet("color: #F44336; font-weight: bold;")

    def delete_selected_schedule(self):
        """Seçili zamanlamayı sil"""
        try:
            current_row = self.schedule_list.currentRow()
            if current_row >= 0 and current_row < len(self.scheduled_emails):
                email_data = self.scheduled_emails[current_row]
                subject = email_data.get('subject', 'Bilinmeyen')
                
                reply = QMessageBox.question(self, "Zamanlama Sil", 
                    f"'{subject}' konulu zamanlanmış e-postayı silmek istediğinizden emin misiniz?",
                    QMessageBox.Yes | QMessageBox.No)
                
                if reply == QMessageBox.Yes:
                    # Timer'ı durdur
                    timer_id = f"email_{current_row}"
                    if timer_id in self.email_timers:
                        self.email_timers[timer_id].stop()
                        del self.email_timers[timer_id]
                    
                    # Listeden kaldır
                    del self.scheduled_emails[current_row]
                    
                    # Tabloyu yenile
                    self.refresh_schedule_list()
                    
                    # Sonraki zamanlama etiketini güncelle
                    self.update_next_schedule_label()
                    
                    QMessageBox.information(self, "Başarılı", "Zamanlama silindi!")
                    self.logger.info(f"Zamanlama silindi: {subject}")
                    
            else:
                QMessageBox.warning(self, "Uyarı", "Lütfen silinecek zamanlamayı seçin!")
                
        except Exception as e:
            self.logger.error(f"Zamanlama silinirken hata: {e}")
            QMessageBox.critical(self, "Hata", f"Zamanlama silinemedi: {e}")

    def cancel_scheduled_email(self, row_index):
        """Seçili zamanlanmış e-postayı iptal et"""
        try:
            if 0 <= row_index < len(self.scheduled_emails):
                email_data = self.scheduled_emails[row_index]
                
                # Timer'ı durdur (güvenli kontrol)
                timer_id = email_data.get('timer_id')
                if timer_id and timer_id in self.email_timers:
                    self.email_timers[timer_id].stop()
                    del self.email_timers[timer_id]
                
                # Listeden kaldır
                self.scheduled_emails.pop(row_index)
                
                # Tabloyu güncelle
                self.refresh_schedule_list()
                
                # Sonraki zamanlama etiketini güncelle
                self.update_next_schedule_label()
                
                self.logger.info(f"Zamanlanmış e-posta iptal edildi: {email_data['subject']}")
                QMessageBox.information(self, "Başarılı", "Zamanlanmış e-posta iptal edildi!")
                
        except Exception as e:
            self.logger.error(f"Zamanlanmış e-posta iptal edilirken hata: {e}")
            QMessageBox.critical(self, "Hata", f"E-posta iptal edilemedi: {e}")
            

    def add_recipient(self):
        """Alıcı listesine yeni alıcı ekle"""
        email = self.new_email_edit.text().strip()
        name = self.new_name_edit.text().strip()
        
        if email and name:
            # Tabloya ekle
            row = self.recipient_list.rowCount()
            self.recipient_list.insertRow(row)
            self.recipient_list.setItem(row, 0, QTableWidgetItem(email))
            self.recipient_list.setItem(row, 1, QTableWidgetItem(name))
            self.recipient_list.setItem(row, 2, QTableWidgetItem("Aktif"))
            
            # Formu temizle
            self.new_email_edit.clear()
            self.new_name_edit.clear()
        else:
            QMessageBox.warning(self, "Uyarı", "E-posta ve ad alanları doldurulmalıdır!")
            
    def apply_filters(self):
        """Filtreleme butonuna basınca çalışacak - Eşleştirme ile entegre"""
        tablo_adi = self.filter_tablo_adi.currentText()
        il = self.filter_il.currentText()
        sektor = self.filter_sektor.currentText()
        email_filter = self.filter_email_checkbox.isChecked()

        if not tablo_adi:
            QMessageBox.warning(self, "Uyarı", "Lütfen bir tablo adı seçin!")
            return
        
        try:
            conn = self.database_manager.conn or self.database_manager.connect_from_ui(self)
            cur = conn.cursor()
            
            # 1. EŞLEŞTİRME KONTROL ET
            mapping = self.mapping_manager.get_mapping(tablo_adi)
            
            if mapping:
                print(f"Manuel eşleştirme bulundu: {mapping}")
                mapped_data, mapped_headers = self.get_filtered_data_with_mapping(
                    tablo_adi, il, sektor, email_filter, mapping
                )
            else:
                print("Manuel eşleştirme bulunamadı, eski yöntem kullanılıyor")
                mapped_data = self.get_filtered_data_old_method(tablo_adi, il, sektor, email_filter)
                mapped_headers = ["ID", "il", "Sektör", "Firma Adı", "Yetkili Adı Soyadı", "E-posta 1", "E-posta 2", "Web Sitesi"]
            
            # 2. TABLOYA YERLEŞTİR
            self.filter_table.setRowCount(len(mapped_data))
            self.filter_table.setColumnCount(len(mapped_headers))
            self.filter_table.setHorizontalHeaderLabels(mapped_headers)
            
            for row_idx, row in enumerate(mapped_data):
                for col_idx, value in enumerate(row):
                    self.filter_table.setItem(row_idx, col_idx, 
                        QTableWidgetItem(str(value) if value else ""))
            
            # 3. SONUÇ
            self.add_to_recipients_btn.setEnabled(len(mapped_data) > 0)
            
            if len(mapped_data) == 0:
                QMessageBox.information(self, "Bilgi", "Seçilen kriterlere uygun kayıt bulunamadı.")
            else:
                QMessageBox.information(self, "Bilgi", f"{len(mapped_data)} kayıt bulundu.")
                
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Filtreleme hatası: {e}")
            print(f"Filtreleme hatası detayı: {e}")

    def add_filtered_results_to_recipients(self):
        """Filtreleme sonuçlarını e-posta alıcı listesine ekle"""
        try:
            # Filtreleme tablosundaki verileri al
            row_count = self.filter_table.rowCount()
            if row_count == 0:
                QMessageBox.warning(self, "Uyarı", "Filtreleme sonucu bulunamadı!")
                return
            
            added_count = 0
            duplicate_count = 0
            
            # Mevcut alıcı e-postalarını kontrol için set oluştur
            existing_emails = set()
            for row in range(self.recipient_list.rowCount()):
                email = self.recipient_list.item(row, 0).text().strip()
                if email:
                    existing_emails.add(email.lower())
            
            # Filtreleme sonuçlarını alıcı listesine ekle
            for row in range(row_count):
                # Eşleştirme ile dinamik sütun indeksleri kullan
                table_name = self.filter_tablo_adi.currentText()
                mapping = self.mapping_manager.get_mapping(table_name)
                
                # Sabit başlıklara göre sütun indekslerini bul
                headers = []
                for col in range(self.filter_table.columnCount()):
                    header_item = self.filter_table.horizontalHeaderItem(col)
                    if header_item:
                        headers.append(header_item.text())
                
                # E-posta ve diğer alanların indekslerini bul
                email1_index = -1
                email2_index = -1
                firma_adi_index = -1
                yetkili_adi_index = -1
                
                for i, header in enumerate(headers):
                    if header == "E-posta-1" or header == "E-posta 1":
                        email1_index = i
                    elif header == "E-posta 2":
                        email2_index = i
                    elif header == "Firma Adı":
                        firma_adi_index = i
                    elif header == "Yetkili Adı Soyadı":
                        yetkili_adi_index = i
                
                # Verileri al
                email1 = self.filter_table.item(row, email1_index).text().strip() if email1_index >= 0 and self.filter_table.item(row, email1_index) else ""
                email2 = self.filter_table.item(row, email2_index).text().strip() if email2_index >= 0 and self.filter_table.item(row, email2_index) else ""
                firma_adi = self.filter_table.item(row, firma_adi_index).text().strip() if firma_adi_index >= 0 and self.filter_table.item(row, firma_adi_index) else ""
                yetkili_adi = self.filter_table.item(row, yetkili_adi_index).text().strip() if yetkili_adi_index >= 0 and self.filter_table.item(row, yetkili_adi_index) else ""
                
                # E-posta adreslerini kontrol et ve ekle
                emails_to_add = []
                if email1 and '@' in email1:
                    emails_to_add.append(email1)
                if email2 and '@' in email2:
                    emails_to_add.append(email2)
                
                for email in emails_to_add:
                    email_lower = email.lower()
                    if email_lower not in existing_emails:
                        # Yeni alıcı ekle
                        recipient_row = self.recipient_list.rowCount()
                        self.recipient_list.insertRow(recipient_row)
                        
                        # E-posta adresi
                        self.recipient_list.setItem(recipient_row, 0, QTableWidgetItem(email))
                        
                        # Ad Soyad (Firma adı + Yetkili adı)
                        name = f"{firma_adi} - {yetkili_adi}" if firma_adi and yetkili_adi else (firma_adi or yetkili_adi or "Bilinmeyen")
                        self.recipient_list.setItem(recipient_row, 1, QTableWidgetItem(name))
                        
                        # Durum
                        self.recipient_list.setItem(recipient_row, 2, QTableWidgetItem("Aktif"))
                        
                        existing_emails.add(email_lower)
                        added_count += 1
                    else:
                        duplicate_count += 1
            
            # Sonuç mesajı göster
            if added_count > 0:
                message = f"{added_count} yeni alıcı eklendi."
                if duplicate_count > 0:
                    message += f" {duplicate_count} mükerrer e-posta atlandı."
                
                QMessageBox.information(self, "Başarılı", message)
                
                # E-posta sekmesine geç
                self.switch_to_email_tab()
            else:
                QMessageBox.information(self, "Bilgi", "Eklenebilecek yeni e-posta adresi bulunamadı.")
                
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Alıcı listesine ekleme hatası: {e}")
            print(f"Alıcı listesine ekleme hatası detayı: {e}")

    def clear_logs(self):
        """Logları temizle"""
        try:
            # Tabloyu temizle
            self.log_table.setRowCount(0)
            # Detay metnini temizle
            self.log_detail_text.clear()
            # Logger'ı temizle
            self.logger.clear_logs()
            self.logger.info("Loglar temizlendi")
        except Exception as e:
            print(f"Log temizleme hatası: {e}")

    def toggle_auto_backup(self):
        """Otomatik backup'ı aç/kapat"""
        if not hasattr(self, 'backup_stop_event') or self.backup_stop_event is None:
            self.backup_stop_event = threading.Event()
        if not hasattr(self, 'backup_thread'):
            self.backup_thread = None
            
        if self.backup_check.isChecked():
            # Backup dizini kontrolü
            backup_dir = self.backup_dir_edit.text().strip()
            if not backup_dir:
                QMessageBox.warning(self, "Uyarı", "Backup dizini belirtilmemiş! Lütfen önce backup dizinini ayarlayın.")
                self.backup_check.setChecked(False)
                return
            self.start_auto_backup()
        else:
            self.stop_auto_backup()

    def start_auto_backup(self):
        self.backup_stop_event.clear()
        if self.backup_thread is None or not self.backup_thread.is_alive():
            self.backup_thread = threading.Thread(target=self.auto_backup_loop, daemon=True)
            self.backup_thread.start()

    def stop_auto_backup(self):
        self.backup_stop_event.set()

    def auto_backup_loop(self):
        # İlk backup'ı hemen alma, 1 saat bekle
        for _ in range(3600):
            if self.backup_stop_event.is_set():
                break
            time.sleep(1)
        
        # Düzenli backup döngüsü
        while not self.backup_stop_event.is_set():
            self.perform_backup()
            # 1 saat bekle (3600 saniye), isterseniz ayarlanabilir
            for _ in range(3600):
                if self.backup_stop_event.is_set():
                    break
                time.sleep(1)

    def perform_backup(self):
        """PostgreSQL veritabanı yedekleme işlemi"""
        try:
            import subprocess
            # Yedekleme dizinini al ve oluştur
            backup_dir = self.backup_dir_edit.text().strip()
            if not backup_dir:
                # Varsayılan backup dizini yoksa yedekleme yapma
                print("UYARI: Backup dizini belirtilmemiş! Yedekleme yapılmayacak.")
                return False
            
            # Backup dizinini oluştur
            os.makedirs(backup_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(backup_dir, f"veritabani_yedek_{timestamp}.sql")
            # Veritabanı bağlantı bilgilerini al
            db_name = self.db_name_edit.text().strip()
            user = self.db_user_edit.text().strip()
            password = self.db_password_edit.text()
            host = self.db_host_edit.text().strip()
            port = self.db_port_edit.text().strip()
            if not all([db_name, user, password, host, port]):
                print("Veritabanı bağlantı bilgileri eksik!")
                return False
            # pg_dump komutu oluştur (plain text format)
            cmd = [
                'pg_dump',
                '-h', host,
                '-p', port,
                '-U', user,
                '-F', 'p',  # plain text format
                '-f', backup_file,
                db_name
            ]
            # Environment variables
            env = os.environ.copy()
            env['PGPASSWORD'] = password
            print(f"Yedekleme komutu: {' '.join(cmd)}")
            print(f"Yedekleme dosyası: {backup_file}")
            # Komutu çalıştır
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            if result.returncode == 0:
                # Dosya boyutunu kontrol et
                if os.path.exists(backup_file):
                    file_size = os.path.getsize(backup_file)
                    print(f"Yedekleme başarılı! Dosya boyutu: {file_size} bytes")
                    if file_size == 0:
                        print("UYARI: Yedek dosyası 0 byte! Veritabanı bağlantısını kontrol edin.")
                        return False
                    return True
                else:
                    print("HATA: Yedek dosyası oluşturulamadı!")
                    return False
            else:
                print(f"Yedekleme hatası: {result.stderr}")
                return False
        except Exception as e:
            print(f"Yedekleme hatası: {e}")
            return False

    def play_notification_sound(self, success=True):
        if not hasattr(self, 'sound_check') or not self.sound_check.isChecked():
            return
        try:
            if platform.system() == "Windows":
                if success:
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                else:
                    winsound.MessageBeep(winsound.MB_ICONHAND)
            else:
                # Diğer platformlar için basit bir bip
                print("\a")
        except Exception as e:
            print(f"Sesli uyarı hatası: {e}")

    def populate_table_list(self):
        """Veritabanındaki tablo adlarını ve kayıt sayılarını tabloya ekler."""
        try:
            conn = self.database_manager.conn or self.database_manager.connect_from_ui(self)
            cur = conn.cursor()
            # Sadece kullanıcı tablolarını getir (PostgreSQL)
            cur.execute("""
                SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public'
            """)
            tables = [row[0] for row in cur.fetchall()]
            self.table_list.setRowCount(0)
            
            # Mapping combo box'ını da doldur
            self.mapping_table_combo.clear()
            self.mapping_table_combo.addItem("-- Tablo Seçiniz --")
            
            for table in tables:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM \"{table}\"")
                    count = cur.fetchone()[0]
                    status = "Aktif"
                except Exception as e:
                    count = "-"
                    status = f"Hata: {e}"
                row = self.table_list.rowCount()
                self.table_list.insertRow(row)
                self.table_list.setItem(row, 0, QTableWidgetItem(table))
                self.table_list.setItem(row, 1, QTableWidgetItem(str(count)))
                self.table_list.setItem(row, 2, QTableWidgetItem(status))
                
                # Mapping combo box'a da ekle
                self.mapping_table_combo.addItem(table)
                
            cur.close()
            if not self.database_manager.conn:
                conn.close()
        except Exception as e:
            self.table_list.setRowCount(0)
            QMessageBox.critical(self, "Hata", f"Tablo listesi alınamadı: {e}")
    def save_database_config(self):
        """Veritabanı bağlantı ayarlarını config.json dosyasına kaydeder."""
        database = {
            "host": self.db_host_edit.text(),
            "port": self.db_port_edit.text(),
            "database": self.db_name_edit.text(),
            "user": self.db_user_edit.text(),
            "password": self.db_password_edit.text()
        }
        try:
            self.config_manager.save_database(database)
            QMessageBox.information(self, "Başarılı", "Veritabanı ayarları kaydedildi!")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Veritabanı ayarları kaydedilemedi: {e}")

    def manual_backup(self):
        """Manuel olarak yedekleme işlemi yapar ve kullanıcıya bilgi verir."""
        try:
            # Backup dizini kontrolü
            backup_dir = self.backup_dir_edit.text().strip()
            if not backup_dir:
                QMessageBox.warning(self, "Uyarı", "Backup dizini belirtilmemiş! Lütfen önce backup dizinini ayarlayın.")
                return
                
            # Backup işlemini gerçekleştir
            if self.perform_backup():
                self.play_notification_sound(success=True)
                QMessageBox.information(self, "Başarılı", "Manuel yedekleme tamamlandı!")
            else:
                self.play_notification_sound(success=False)
                QMessageBox.critical(self, "Hata", "Manuel yedekleme başarısız!")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Manuel yedekleme başarısız: {e}")
            
    def send_test_email(self):
        """Test e-postası gönder (SMTP kullanarak)"""
        try:
            # SMTP ayarlarını kontrol et
            smtp_server = self.smtp_server_edit.text().strip()
            smtp_port = int(self.smtp_port_edit.text()) if self.smtp_port_edit.text() else 587
            sender_email = self.sender_email_edit.text().strip()
            sender_password = self.sender_password_edit.text().strip()
            
            if not smtp_server or not sender_email or not sender_password:
                QMessageBox.warning(self, "Uyarı", "SMTP ayarları eksik! Lütfen yapılandırma sekmesinden SMTP ayarlarını kontrol edin.")
                return
            
            # SMTP ayarlarını hazırla
            smtp_settings = {
                'server': smtp_server,
                'port': smtp_port,
                'username': sender_email,
                'password': sender_password
            }
            
            # Test e-postası parametreleri
            subject = "Test E-postası - Otomatik E-posta Gönderim Sistemi"
            body = f"""Merhaba,

            Bu bir test e-postasıdır. Otomatik E-posta Gönderim Sistemi'nin SMTP ayarları başarıyla yapılandırılmıştır.

            SMTP Sunucu: {smtp_server}
            Port: {smtp_port}
            Gönderen: {sender_email}
            Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}

            Saygılarımızla,
            Sistem Yöneticisi"""
            
            # Kartvizit imzası ekle
            body_with_signature = self.add_vcard_signature(body)
            
            # Test e-postasını kendine gönder
            try:
                if send_email_smtp(subject, body_with_signature, sender_email, smtp_settings=smtp_settings, is_html=True, vcard_image_path=None):
                    self.play_notification_sound(success=True)
                    QMessageBox.information(self, "Başarılı", f"Test e-postası {sender_email} adresine gönderildi!")
                    self.logger.info(f"Test e-postası gönderildi: {sender_email}")
                    
                    # Detaylı test e-posta logu
                    self.logger.log_email_send(
                        subject=subject,
                        body=body_with_signature,
                        recipients=[sender_email],
                        attachments=[],
                        smtp_settings=smtp_settings,
                        send_time=datetime.now(),
                        batch_info={"batch_id": "test_email", "type": "TEST"}
                    )
                else:
                    self.play_notification_sound(success=False)
                    QMessageBox.critical(self, "Hata", "Test e-postası gönderilemedi!")
                    self.logger.error(f"Test e-postası gönderilemedi: {sender_email}")
                    
                    # Test e-posta hata logu
                    self.logger.log_email_error(
                        subject=subject,
                        recipients=[sender_email],
                        error_msg="Test e-postası gönderim başarısız",
                        send_time=datetime.now()
                    )
            except Exception as smtp_error:
                self.logger.error(f"Test e-postası gönderme hatası: {smtp_error}")
                QMessageBox.critical(self, "Hata", f"Test e-postası gönderilemedi: {smtp_error}")
                
                # Test e-posta hata logu
                self.logger.log_email_error(
                    subject=subject,
                    recipients=[sender_email],
                    error_msg=str(smtp_error),
                    send_time=datetime.now()
                )
                
        except Exception as e:
            self.logger.error(f"Test e-postası hazırlama hatası: {e}")
            QMessageBox.critical(self, "Hata", f"Test e-postası hazırlanamadı: {e}")
            
    def format_text(self, text_edit, format_type):
        """Metin formatlaması yap - HTML formatında"""
        cursor = text_edit.textCursor()
        selected_text = cursor.selectedText()
        
        if format_type == "bold":
            formatted_text = f"<b>{selected_text}</b>"
        elif format_type == "italic":
            formatted_text = f"<i>{selected_text}</i>"
        elif format_type == "underline":
            formatted_text = f"<u>{selected_text}</u>"
        elif format_type == "strikethrough":
            formatted_text = f" {selected_text} "
        elif format_type == "justify":
            formatted_text = f"<div style='text-align: justify;'>{selected_text}</div>"
        elif format_type == "align_left":
            formatted_text = f"<div style='text-align: left;'>{selected_text}</div>"
        elif format_type == "align_center":
            formatted_text = f"<div style='text-align: center;'>{selected_text}</div>"
        elif format_type == "align_right":
            formatted_text = f"<div style='text-align: right;'>{selected_text}</div>"
        elif format_type == "align_justify":
            formatted_text = f"<div style='text-align: justify;'>{selected_text}</div>"
        elif format_type == "bullet_list":
            formatted_text = f"<li>{selected_text}</li>"
        elif format_type == "number_list":
            formatted_text = f"<li>{selected_text}</li>"
        elif format_type == "indent":
            formatted_text = f"<div style='margin-left: 20px;'>{selected_text}</div>"
        elif format_type == "outdent":
            # Girinti azaltma - basit yaklaşım
            formatted_text = selected_text
        else:
            formatted_text = selected_text
            
        cursor.insertText(formatted_text)
        
    def choose_text_color(self, text_edit):
        """Metin rengi seç"""
        color = QColorDialog.getColor()
        if color.isValid():
            cursor = text_edit.textCursor()
            selected_text = cursor.selectedText()
            if selected_text:
                formatted_text = f'<span style="color: {color.name()};">{selected_text}</span>'
                cursor.insertText(formatted_text)

    def choose_bg_color(self, text_edit):
        """Arka plan rengi seç"""
        color = QColorDialog.getColor()
        if color.isValid():
            cursor = text_edit.textCursor()
            selected_text = cursor.selectedText()
            if selected_text:
                formatted_text = f'<span style="background-color: {color.name()};">{selected_text}</span>'
                cursor.insertText(formatted_text)

    def choose_font_family(self, text_edit):
        """Font ailesi seç"""
        font_families = ["Arial", "Times New Roman", "Courier New", "Verdana", "Georgia", "Tahoma"]
        font, ok = QInputDialog.getItem(self, "Font Ailesi Seç", "Font:", font_families, 0, False)
        if ok and font:
            cursor = text_edit.textCursor()
            selected_text = cursor.selectedText()
            if selected_text:
                formatted_text = f'<span style="font-family: {font};">{selected_text}</span>'
                cursor.insertText(formatted_text)

    def change_font_size(self, text_edit, direction):
        """Font boyutunu değiştir"""
        cursor = text_edit.textCursor()
        selected_text = cursor.selectedText()
        if selected_text:
            # Basit font boyutu değişimi
            if direction > 0:
                formatted_text = f'<span style="font-size: large;">{selected_text}</span>'
            else:
                formatted_text = f'<span style="font-size: small;">{selected_text}</span>'
            cursor.insertText(formatted_text)

    def show_more_formatting_options(self, text_edit):
        """Daha fazla formatlama seçenekleri menüsü"""
        menu = QMenu(self)
        
        # Özel formatlama seçenekleri
        menu.addAction("Kod Bloğu", lambda: self.insert_code_block(text_edit))
        menu.addAction("Alıntı", lambda: self.insert_quote(text_edit))
        menu.addAction("Tablo", lambda: self.insert_table(text_edit))
        menu.addAction("Bağlantı", lambda: self.insert_link(text_edit))
        
        # Menüyü göster
        menu.exec_(text_edit.mapToGlobal(text_edit.cursorRect().bottomLeft()))

    def insert_code_block(self, text_edit):
        """Kod bloğu ekle"""
        cursor = text_edit.textCursor()
        cursor.insertText("```\nKod buraya yazın\n```")

    def insert_quote(self, text_edit):
        """Alıntı ekle"""
        cursor = text_edit.textCursor()
        cursor.insertText("> Alıntı metni buraya yazın")

    def insert_table(self, text_edit):
        """Tablo ekle"""
        cursor = text_edit.textCursor()
        table_html = """
<table border="1">
<tr><td>Hücre 1</td><td>Hücre 2</td></tr>
<tr><td>Hücre 3</td><td>Hücre 4</td></tr>
</table>
"""
        cursor.insertText(table_html)

    def insert_link(self, text_edit):
        """Bağlantı ekle"""
        url, ok = QInputDialog.getText(self, "Bağlantı Ekle", "URL:")
        if ok and url:
            text, ok = QInputDialog.getText(self, "Bağlantı Metni", "Metin:")
            if ok and text:
                cursor = text_edit.textCursor()
                cursor.insertText(f'<a href="{url}">{text}</a>')

    def insert_emoji(self, text_edit):
        """Emoji ekle"""
        emojis = ["😊", "😂", "❤️", "👍", "🎉", "🔥", "💯", "✨", "🌟", "💪", "👏", "🙏"]
        emoji, ok = QInputDialog.getItem(self, "Emoji Seç", "Emoji:", emojis, 0, False)
        if ok and emoji:
            cursor = text_edit.textCursor()
            cursor.insertText(emoji)
        
    def show_attachment_menu(self, button, attachment_table):
        """Ek dosya menüsünü göster"""
        menu = QMenu()
        
        # Dosya türleri
        menu.addAction("📷 Fotoğraflar", lambda: self.add_attachment("image", attachment_table))
        menu.addAction("🎵 Ses Mesajı", lambda: self.add_attachment("audio", attachment_table))
        menu.addAction("🎬 Videolar", lambda: self.add_attachment("video", attachment_table))
        menu.addAction("📄 PDF", lambda: self.add_attachment("pdf", attachment_table))
        menu.addAction("📁 Belgeler", lambda: self.add_attachment("document", attachment_table))
        
        menu.addSeparator()
        
        # Temizleme
        menu.addAction("🗑️ Ek listesini temizle", lambda: self.clear_attachment_list(attachment_table))
        
        # Menüyü butonun altında göster
        menu.exec_(button.mapToGlobal(button.rect().bottomLeft()))
        
    def add_attachment(self, file_type, attachment_table):
        """Ek dosya ekle"""
        # Dosya türüne göre filtre
        if file_type == "image":
            file_filter = "Resim Dosyaları (*.jpg *.jpeg *.png *.gif *.bmp);;Tüm Dosyalar (*)"
        elif file_type == "audio":
            file_filter = "Ses Dosyaları (*.mp3 *.wav *.ogg *.m4a);;Tüm Dosyalar (*)"
        elif file_type == "video":
            file_filter = "Video Dosyaları (*.mp4 *.avi *.mov *.wmv);;Tüm Dosyalar (*)"
        elif file_type == "pdf":
            file_filter = "PDF Dosyaları (*.pdf);;Tüm Dosyalar (*)"
        elif file_type == "document":
            file_filter = "Belge Dosyaları (*.doc *.docx *.xls *.xlsx *.ppt *.pptx *.txt);;Tüm Dosyalar (*)"
        else:
            file_filter = "Tüm Dosyalar (*)"
            
        file_path, _ = QFileDialog.getOpenFileName(
            self, f"{file_type.title()} Dosyası Seç", "", file_filter
        )
        
        if file_path:
            # Dosya bilgilerini tabloya ekle
            row = attachment_table.rowCount()
            attachment_table.insertRow(row)
            
            file_name = os.path.basename(file_path)
            file_ext = os.path.splitext(file_name)[1].upper()
            
            attachment_table.setItem(row, 0, QTableWidgetItem(file_name))
            attachment_table.setItem(row, 1, QTableWidgetItem(file_ext))
            attachment_table.setItem(row, 2, QTableWidgetItem(""))
            
            # Dosya yolunu sakla
            attachment_table.item(row, 0).setData(Qt.UserRole, file_path)
            
            # Debug mesajı
            self.logger.info(f"Ek dosya tabloya eklendi: {file_name} -> {file_path}")
            QMessageBox.information(self, "Başarılı", f"Ek dosya eklendi: {file_name}")
            
    def clear_attachment_list(self, attachment_table):
        """Ek listesini temizle"""
        attachment_table.setRowCount(0)
        QMessageBox.information(self, "Bilgi", "Ek listesi temizlendi!")
        
    def schedule_remaining_emails(self, subject, body, remaining_recipients, attachments, smtp_settings):
        """Kalan alıcılar için 1 saat sonra e-posta gönderimi planla"""
        try:
            # 1 saat sonra çalışacak timer oluştur
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: self.send_remaining_emails(subject, body, remaining_recipients, attachments, smtp_settings))
            timer.start(3600000)  # 1 saat = 3600000 ms
            
            self.logger.info(f"Kalan {len(remaining_recipients)} alıcı için 1 saat sonra e-posta gönderimi planlandı")
            
            # Kullanıcıya bilgi ver
            QMessageBox.information(self, "Zamanlama", 
                f"Kalan {len(remaining_recipients)} alıcı için 1 saat sonra otomatik gönderim planlandı.\n"
                f"Gönderim durumu log sekmesinden takip edilebilir.")
            
        except Exception as e:
            self.logger.error(f"Kalan e-postalar planlanırken hata: {e}")

    def send_remaining_emails(self, subject, body, remaining_recipients, attachments, smtp_settings):
        """Kalan alıcılara e-posta gönder - Limit kontrolü ile"""
        try:
            # VCard imzasını ekle
            body_with_signature = self.add_vcard_signature(body, attachments)
            
            # Kartvizit görselini ayrı olarak sakla
            vcard_image_path = None
            if hasattr(self, 'vcard_enabled_check') and self.vcard_enabled_check.isChecked():
                vcard_image_path = self.vcard_image_path_edit.text().strip()
                if not vcard_image_path or not os.path.exists(vcard_image_path):
                    vcard_image_path = None
            
            # Limit kontrolü
            can_send, message = self.check_sending_limits()
            if not can_send:
                # Limit dolmuşsa, tekrar 1 saat sonra dene
                self.schedule_remaining_emails(subject, body, remaining_recipients, attachments, smtp_settings)
                self.logger.info(f"Limit doldu, tekrar 1 saat sonra denenecek: {message}")
                return
            
            # Güvenli gönderim sayısını hesapla
            safe_count, _ = self.calculate_safe_sending_count(len(remaining_recipients))
            
            if safe_count == 0:
                # Limit dolmuşsa, tekrar 1 saat sonra dene
                self.schedule_remaining_emails(subject, body, remaining_recipients, attachments, smtp_settings)
                self.logger.info("Güvenli gönderim sayısı 0, tekrar 1 saat sonra denenecek")
                return
            
            # Bu saatte gönderilecek alıcıları seç
            recipients_to_send_now = remaining_recipients[:safe_count]
            recipients_to_send_later = remaining_recipients[safe_count:]
            
            # E-postaları gönder
            success_count = 0
            failed_recipients = []
            
            if self.bcc_checkbox.isChecked():
                # BCC ile gönderim
                email_delay = self.email_delay_spin_schedule.value()  # UI'dan al
                for j, recipient in enumerate(recipients_to_send_now):
                    try:
                        self.logger.info(f"BCC e-posta gönderiliyor ({j+1}/{len(recipients_to_send_now)}): {recipient}")
                        if send_email_smtp(subject, body_with_signature, recipient, attachments, smtp_settings, True, vcard_image_path):
                            success_count += 1
                            self.logger.info(f"BCC e-posta gönderildi: {recipient}")
                        else:
                            failed_recipients.append(recipient)
                            self.logger.error(f"BCC e-posta gönderilemedi: {recipient}")
                    except Exception as e:
                        failed_recipients.append(recipient)
                        self.logger.error(f"BCC e-posta gönderme hatası ({recipient}): {e}")
                    
                    # Son e-posta değilse bekle
                    if j < len(recipients_to_send_now) - 1:
                        self.logger.info(f"Sonraki BCC e-posta için {email_delay} saniye bekleniyor...")
                        time.sleep(email_delay)
            else:
                # Normal gönderim
                email_delay = self.email_delay_spin_schedule.value()  # Zamanlama sekmesindeki ayar
                for j, recipient in enumerate(recipients_to_send_now):
                    try:
                        self.logger.info(f"E-posta gönderiliyor ({j+1}/{len(recipients_to_send_now)}): {recipient}")
                        if send_email_smtp(subject, body_with_signature, recipient, attachments, smtp_settings, True, vcard_image_path):
                            success_count += 1
                            self.logger.info(f"E-posta gönderildi: {recipient}")
                        else:
                            failed_recipients.append(recipient)
                            self.logger.error(f"E-posta gönderilemedi: {recipient}")
                    except Exception as e:
                        failed_recipients.append(recipient)
                        self.logger.error(f"E-posta gönderme hatası ({recipient}): {e}")
                    
                    # Son e-posta değilse bekle
                    if j < len(recipients_to_send_now) - 1:
                        self.logger.info(f"Sonraki e-posta için {email_delay} saniye bekleniyor...")
                        time.sleep(email_delay)
            
            # Gönderim sayılarını güncelle
            if success_count > 0:
                self.update_sending_counters(success_count)
                self.logger.info(f"Kalan e-postalardan {success_count} tanesi gönderildi")
            
            # Hala kalan alıcılar varsa, tekrar 1 saat sonra dene
            if recipients_to_send_later:
                self.schedule_remaining_emails(subject, body_with_signature, recipients_to_send_later, attachments, smtp_settings)
                self.logger.info(f"Kalan {len(recipients_to_send_later)} alıcı için tekrar 1 saat sonra denenecek")
            else:
                self.logger.info("Tüm e-postalar başarıyla gönderildi")
                
        except Exception as e:
            self.logger.error(f"Kalan e-postalar gönderilirken hata: {e}")
        
    def schedule_email(self, subject, body, attachment_table):
        """E-postayı belirli bir zamanda gönder - Kapsamlı Geliştirilmiş"""
        try:
            # 1. SMTP ayarlarını kontrol et
            smtp_server = self.smtp_server_edit.text()
            smtp_port = int(self.smtp_port_edit.text()) if self.smtp_port_edit.text() else 587
            sender_email = self.sender_email_edit.text().strip()
            sender_password = self.sender_password_edit.text().strip()
            
            if not smtp_server or not sender_email or not sender_password:
                QMessageBox.warning(self, "Uyarı", "SMTP ayarları eksik! Lütfen yapılandırma sekmesinden SMTP ayarlarını kontrol edin.")
                return
            
            # 2. SMTP ayarlarını hazırla
            smtp_settings = {
                'server': smtp_server,
                'port': smtp_port,
                'username': sender_email,
                'password': sender_password
            }
            
            # 3. Alıcı listesi kontrolü
            recipients = self.get_recipient_list()
            if not recipients:
                QMessageBox.warning(self, "Uyarı", "Alıcı listesi boş! Lütfen önce alıcı ekleyin.")
                return
            
            # 4. Ek dosya yollarını topla
            attachments = []
            for row in range(attachment_table.rowCount()):
                file_path = attachment_table.item(row, 0).data(Qt.UserRole)
                if file_path and os.path.exists(file_path):
                    attachments.append(file_path)
            
            # 5. Kartvizit imzası ekle
            body_with_signature = body
            
            # 6. Güvenli gönderim sayısını hesapla
            safe_count, message = self.calculate_safe_sending_count(len(recipients))
            
            if safe_count == 0:
                QMessageBox.warning(self, "Limit Uyarısı", message)
                return
            
            # 7. Kullanıcıya bilgi ver
            if safe_count < len(recipients):
                reply = QMessageBox.question(self, "Limit Bilgisi", 
                    f"{message}\n\n"
                    f"Zamanlandığında {safe_count} e-posta gönderilecek.\n"
                    f"Kalan {len(recipients) - safe_count} e-posta için 1 saat sonra otomatik devam edilecek.\n\n"
                    f"Devam etmek istiyor musunuz?",
                    QMessageBox.Yes | QMessageBox.No)
                
                if reply == QMessageBox.No:
                    return
            
            # 8. Zamanlama dialog'u oluştur
            dialog = QDialog(self)
            dialog.setWindowTitle("E-posta Zamanlama")
            dialog.setFixedSize(450, 400)
            
            layout = QVBoxLayout(dialog)
            
            # Alıcı sayısı bilgisi
            recipient_info = QLabel(f"📧 {len(recipients)} alıcıya gönderilecek")
            recipient_info.setStyleSheet("color: #2196F3; font-weight: bold; font-size: 11px; padding: 5px;")
            layout.addWidget(recipient_info)
            
            # Limit bilgisi
            limit_info = QLabel(f"🛡️ Güvenli gönderim: {safe_count} e-posta")
            limit_info.setStyleSheet("color: #4CAF50; font-weight: bold; font-size: 11px; padding: 5px;")
            layout.addWidget(limit_info)
            
            # Ek dosya bilgisi
            if attachments:
                attachment_info = QLabel(f"📎 {len(attachments)} ek dosya eklenecek")
                attachment_info.setStyleSheet("color: #FF9800; font-weight: bold; font-size: 11px; padding: 5px;")
                layout.addWidget(attachment_info)
            
            # BCC bilgisi
            if self.bcc_checkbox.isChecked():
                bcc_info = QLabel("🔒 BCC (Gizli Alıcı) modu aktif")
                bcc_info.setStyleSheet("color: #9C27B0; font-weight: bold; font-size: 11px; padding: 5px;")
                layout.addWidget(bcc_info)
            
            # Tarih seçici
            date_label = QLabel("Gönderim Tarihi:")
            layout.addWidget(date_label)
            
            date_edit = QDateEdit()
            date_edit.setDate(QDate.currentDate())
            date_edit.setMinimumDate(QDate.currentDate())
            layout.addWidget(date_edit)
            
            # Saat seçici
            time_label = QLabel("Gönderim Saati:")
            layout.addWidget(time_label)
            
            time_edit = QTimeEdit()
            time_edit.setTime(QTime.currentTime())
            layout.addWidget(time_edit)
            
            # E-posta arası süre bilgisi
            delay_info = QLabel(f"⏱️ E-posta arası süre: {self.email_delay_spin_schedule.value()} saniye")
            delay_info.setStyleSheet("color: #666; font-size: 10px; padding: 5px;")
            layout.addWidget(delay_info)
            
            # Butonlar
            button_layout = QHBoxLayout()
            
            ok_button = QPushButton("Zamanla")
            ok_button.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; padding: 8px 16px; border: none; border-radius: 4px; } QPushButton:hover { background-color: #45A049; }")
            ok_button.clicked.connect(dialog.accept)
            button_layout.addWidget(ok_button)
            
            cancel_button = QPushButton("İptal")
            cancel_button.setStyleSheet("QPushButton { background-color: #f44336; color: white; font-weight: bold; padding: 8px 16px; border: none; border-radius: 4px; } QPushButton:hover { background-color: #d32f2f; }")
            cancel_button.clicked.connect(dialog.reject)
            button_layout.addWidget(cancel_button)
            
            layout.addLayout(button_layout)
            
            # Dialog'u göster
            if dialog.exec_() == QDialog.Accepted:
                selected_date = date_edit.date()
                selected_time = time_edit.time()
                
                # Seçilen tarih ve saati datetime'a çevir
                scheduled_datetime = QDateTime(selected_date, selected_time)
                current_datetime = QDateTime.currentDateTime()
                
                # Geçmiş tarih kontrolü
                if scheduled_datetime <= current_datetime:
                    QMessageBox.warning(self, "Hata", "Geçmiş bir tarih seçtiniz!")
                    return
                
                # 9. Kapsamlı zamanlama bilgilerini hazırla
                email_data = {
                    'subject': subject,
                    'body': body_with_signature,  # Kartvizit imzası eklenmiş
                    'attachment_table': attachment_table,
                    'attachments': attachments,  # Ek dosya listesi
                    'datetime': scheduled_datetime,
                    'recipients': recipients,
                    'smtp_settings': smtp_settings,  # SMTP ayarları
                    'bcc_enabled': self.bcc_checkbox.isChecked(),  # BCC durumu
                    'email_delay': self.email_delay_spin_schedule.value(),  # E-posta arası süre
                    'safe_count': safe_count,  # Güvenli gönderim sayısı
                    'total_count': len(recipients)  # Toplam alıcı sayısı
                }
                
                # Listeye ekle
                self.add_scheduled_email_to_list(email_data)
                
                # Zamanlayıcıyı başlat
                timer_id = self.start_email_scheduler(scheduled_datetime)
                email_data['timer_id'] = timer_id
                
                # 10. Detaylı başarı mesajı
                QMessageBox.information(self, "Başarılı", 
                    f"E-posta {scheduled_datetime.toString('dd.MM.yyyy HH:mm')} tarihinde gönderilecek!\n\n"
                    f"📧 Alıcı sayısı: {len(recipients)}\n"
                    f"🛡️ Güvenli gönderim: {safe_count}\n"
                    f"📎 Ek dosya: {len(attachments)}\n"
                    f"⏱️ E-posta arası süre: {self.email_delay_spin_schedule.value()} saniye\n\n"
                    f"Zamanlama sekmesinden durumu takip edebilirsiniz.")
                
        except Exception as e:
            self.logger.error(f"E-posta zamanlama hatası: {e}")
            QMessageBox.critical(self, "Hata", f"E-posta zamanlanamadı: {e}")

    def start_email_scheduler(self, scheduled_datetime):
        """E-posta zamanlayıcısını başlat - Güncellenmiş"""
        try:
            # Zamanlayıcı timer'ı oluştur
            timer = QTimer()
            timer.setSingleShot(True)
            
            # Zamanlama süresini hesapla (milisaniye)
            current_datetime = QDateTime.currentDateTime()
            time_diff = current_datetime.msecsTo(scheduled_datetime)
            
            # Eğer zamanı geçmişse hemen çalıştır
            if time_diff <= 0:
                self.logger.info(f"Zamanlanmış e-posta zamanı geçmiş, hemen gönderiliyor: {scheduled_datetime.toString('dd.MM.yyyy HH:mm')}")
                self.send_scheduled_email()
            else:
                timer.timeout.connect(self.send_scheduled_email)
                timer.start(time_diff)
                self.logger.info(f"E-posta zamanlayıcısı başlatıldı: {scheduled_datetime.toString('dd.MM.yyyy HH:mm')} - {time_diff}ms sonra")
            
            # Timer'ı sakla
            timer_id = f"email_{len(self.scheduled_emails)}"
            self.email_timers[timer_id] = timer
            
            # Periyodik kontrol timer'ı başlat (her 30 saniyede bir kontrol et)
            if not hasattr(self, 'schedule_check_timer'):
                self.schedule_check_timer = QTimer()
                self.schedule_check_timer.timeout.connect(self.send_scheduled_email)
                self.schedule_check_timer.start(30000)  # 30 saniye
                self.logger.info("Periyodik zamanlama kontrolü başlatıldı")
            
            # Timer ID'sini döndür
            return timer_id
            
        except Exception as e:
            self.logger.error(f"E-posta zamanlayıcısı başlatılırken hata: {e}")
    def send_scheduled_email(self):
        """Zamanlanmış e-postayı gönder - Limit Kontrolü ile Düzeltilmiş"""
        try:
            self.logger.info(f"Zamanlanmış e-posta kontrolü başlatıldı - {len(self.scheduled_emails)} zamanlama mevcut")
            current_time = QDateTime.currentDateTime()
            completed_indices = []
            
            for i, email_data in enumerate(self.scheduled_emails):
                scheduled_datetime = email_data.get('datetime')
                self.logger.info(f"Zamanlama {i+1} kontrol ediliyor: {scheduled_datetime.toString('dd.MM.yyyy HH:mm') if scheduled_datetime else 'Belirsiz'}")
                
                if scheduled_datetime and current_time >= scheduled_datetime:
                    self.logger.info(f"Zamanlanmış e-posta gönderimi başlatılıyor: {email_data.get('subject', 'Konu yok')}")
                    
                    subject = email_data['subject']
                    body = email_data['body']
                    recipients = email_data.get('recipients', [])
                    
                    if not recipients:
                        self.logger.error(f"Zamanlanmış e-posta için alıcı listesi boş: {subject}")
                        completed_indices.append(i)
                        continue
                    
                    self.logger.info(f"Alıcı sayısı: {len(recipients)}")
                    
                    smtp_server = self.smtp_server_edit.text()
                    smtp_port = int(self.smtp_port_edit.text()) if self.smtp_port_edit.text() else 587
                    sender_email = self.sender_email_edit.text().strip()
                    sender_password = self.sender_password_edit.text().strip()
                    
                    if not smtp_server or not sender_email or not sender_password:
                        self.logger.error(f"SMTP ayarları eksik, zamanlanmış e-posta gönderilemedi: {subject}")
                        completed_indices.append(i)
                        continue
                    
                    smtp_settings = {
                        'server': smtp_server,
                        'port': smtp_port,
                        'username': sender_email,
                        'password': sender_password
                    }
                    
                    attachments = []
                    attachment_table = email_data.get('attachment_table')
                    if attachment_table:
                        for row in range(attachment_table.rowCount()):
                            file_path = attachment_table.item(row, 0).data(Qt.UserRole)
                            if file_path and os.path.exists(file_path):
                                attachments.append(file_path)
                    
                    self.logger.info(f"Ek dosya sayısı: {len(attachments)}")
                    
                    # Kartvizit imzası ekle
                    body_with_signature = self.add_vcard_signature(body, attachments)
                    
                    # Kartvizit görselini ayrı olarak sakla
                    vcard_image_path = None
                    if hasattr(self, 'vcard_enabled_check') and self.vcard_enabled_check.isChecked():
                        vcard_image_path = self.vcard_image_path_edit.text().strip()
                        if not vcard_image_path or not os.path.exists(vcard_image_path):
                            vcard_image_path = None
                    
                    # 1. Güvenli gönderim sayısını hesapla
                    safe_count, message = self.calculate_safe_sending_count(len(recipients))
                    
                    if safe_count == 0:
                        self.logger.warning(f"Limit doldu, zamanlanmış e-posta gönderilemedi: {subject}")
                        # Limit dolmuşsa, 1 saat sonra tekrar dene
                        email_data['datetime'] = current_time.addSecs(3600)  # 1 saat sonra
                        continue
                    
                    # 2. Alıcı listesini böl
                    recipients_to_send_now = recipients[:safe_count]
                    recipients_to_send_later = recipients[safe_count:]
                    
                    self.logger.info(f"Güvenli gönderim: {safe_count}/{len(recipients)} alıcı")
                    
                    # 3. Şimdi gönderilecek alıcılara e-posta gönder
                    success_count = 0
                    failed_recipients = []
                    
                    # E-posta gönderim süresi (saniye) - spam koruması için
                    email_delay = email_data.get('email_delay', self.email_delay_spin_schedule.value())
                    
                    if email_data.get('bcc_enabled', self.bcc_checkbox.isChecked()):
                        # BCC ile gönderim
                        for j, recipient in enumerate(recipients_to_send_now):
                            try:
                                self.logger.info(f"BCC e-posta gönderiliyor ({j+1}/{len(recipients_to_send_now)}): {subject} -> {recipient}")
                                if send_email_smtp(subject, body_with_signature, recipient, attachments, smtp_settings, True, vcard_image_path):
                                    success_count += 1
                                    self.logger.info(f"BCC e-posta gönderildi: {subject} -> {recipient}")
                                else:
                                    failed_recipients.append(recipient)
                                    self.logger.error(f"BCC e-posta gönderilemedi: {subject} -> {recipient}")
                            except Exception as e:
                                failed_recipients.append(recipient)
                                self.logger.error(f"BCC e-posta gönderme hatası ({recipient}): {e}")
                            
                            # Son e-posta değilse bekle
                            if j < len(recipients_to_send_now) - 1:
                                self.logger.info(f"Sonraki BCC e-posta için {email_delay} saniye bekleniyor...")
                                time.sleep(email_delay)
                    else:
                        # Normal gönderim
                        for j, recipient in enumerate(recipients_to_send_now):
                            try:
                                self.logger.info(f"E-posta gönderiliyor ({j+1}/{len(recipients_to_send_now)}): {subject} -> {recipient}")
                                if send_email_smtp(subject, body_with_signature, recipient, attachments, smtp_settings, True, vcard_image_path):
                                    success_count += 1
                                    self.logger.info(f"E-posta gönderildi: {subject} -> {recipient}")
                                else:
                                    failed_recipients.append(recipient)
                                    self.logger.error(f"E-posta gönderilemedi: {subject} -> {recipient}")
                            except Exception as e:
                                failed_recipients.append(recipient)
                                self.logger.error(f"E-posta gönderme hatası ({recipient}): {e}")
                            
                            # Son e-posta değilse bekle
                            if j < len(recipients_to_send_now) - 1:
                                self.logger.info(f"Sonraki e-posta için {email_delay} saniye bekleniyor...")
                                time.sleep(email_delay)
                    
                    # 4. Gönderim sayılarını güncelle
                    if success_count > 0:
                        self.logger.info(f"Zamanlanmış e-posta kısmı tamamlandı: {subject} - {success_count}/{len(recipients_to_send_now)} başarılı")
                        self.update_sending_counters(success_count)
                        # UI'ı güncelle
                        self.refresh_sending_stats()
                    
                    # 5. Kalan alıcılar varsa, zamanlayıcı başlat
                    if recipients_to_send_later:
                        self.logger.info(f"Kalan {len(recipients_to_send_later)} alıcı için 1 saat sonra otomatik devam edilecek")
                        self.schedule_remaining_emails(subject, body_with_signature, recipients_to_send_later, attachments, smtp_settings)
                        
                        # Zamanlama verilerini güncelle (kalan alıcılar için)
                        email_data['recipients'] = recipients_to_send_later
                        email_data['datetime'] = current_time.addSecs(3600)  # 1 saat sonra
                        email_data['sent'] = False  # Henüz tamamlanmadı
                        
                        self.logger.info(f"Zamanlama {i+1} güncellendi: {len(recipients_to_send_later)} alıcı kaldı")
                    else:
                        # Tüm alıcılar gönderildi, tamamlandı olarak işaretle
                        email_data['sent'] = True
                        completed_indices.append(i)
                        self.logger.info(f"Zamanlama {i+1} tamamlandı: {subject}")
                    
                else:
                    if scheduled_datetime:
                        time_diff = current_time.msecsTo(scheduled_datetime)
                        self.logger.info(f"Zamanlama {i+1} henüz zamanı gelmedi: {time_diff//1000} saniye kaldı")
            
            # Tamamlanan zamanlamaları listeden kaldır
            for index in reversed(completed_indices):
                del self.scheduled_emails[index]
            
            if completed_indices:
                self.logger.info(f"{len(completed_indices)} zamanlama tamamlandı ve listeden kaldırıldı")
                self.refresh_schedule_list()
                
                # Sonraki zamanlama etiketini güncelle
                self.update_next_schedule_label()
            
        except Exception as e:
            self.logger.error(f"Zamanlanmış e-posta gönderilirken hata: {e}")

    def get_recipient_list(self):
        """Alıcı listesini döndür"""
        recipients = []
        for row in range(self.recipient_list.rowCount()):
            email = self.recipient_list.item(row, 0).text()
            if email:
                recipients.append(email)
        return recipients
        
    def send_email_with_attachments(self, subject, body, attachment_table):
        """Ek dosyalarla e-posta gönder (SMTP kullanarak) - Gelişmiş limit kontrolü"""
        try:
            # SMTP ayarlarını kontrol et
            smtp_server = self.smtp_server_edit.text()
            smtp_port = int(self.smtp_port_edit.text()) if self.smtp_port_edit.text() else 587
            sender_email = self.sender_email_edit.text().strip()
            sender_password = self.sender_password_edit.text().strip()
            
            if not smtp_server or not sender_email or not sender_password:
                QMessageBox.warning(self, "Uyarı", "SMTP ayarları eksik! Lütfen yapılandırma sekmesinden SMTP ayarlarını kontrol edin.")
                return
            
            # SMTP ayarlarını hazırla
            smtp_settings = {
                'server': smtp_server,
                'port': smtp_port,
                'username': sender_email,
                'password': sender_password
            }
            
            # Ek dosya yollarını topla
            attachments = []
            for row in range(attachment_table.rowCount()):
                file_path = attachment_table.item(row, 0).data(Qt.UserRole)
                if file_path and os.path.exists(file_path):
                    attachments.append(file_path)
                    self.logger.info(f"Ek dosya eklendi: {file_path}")
                else:
                    self.logger.warning(f"Ek dosya bulunamadı: {file_path}")
            
            self.logger.info(f"Toplam {len(attachments)} ek dosya eklendi")
            
            # Kartvizit görselini ayrı olarak sakla
            vcard_image_path = None
            if hasattr(self, 'vcard_enabled_check') and self.vcard_enabled_check.isChecked():
                vcard_image_path = self.vcard_image_path_edit.text().strip()
                if not vcard_image_path or not os.path.exists(vcard_image_path):
                    vcard_image_path = None
            
            # Alıcı listesini al
            recipients = []
            for row in range(self.recipient_list.rowCount()):
                email = self.recipient_list.item(row, 0).text()
                if email:
                    recipients.append(email)
            
            if not recipients:
                QMessageBox.warning(self, "Uyarı", "Alıcı listesi boş!")
                return
            
            # Kartvizit imzası ve görsel ön izlemeleri ekle (HTML formatında)
            body_with_signature = self.add_vcard_signature(body, attachments)
            
            # HTML formatında gönder
            is_html = True
            
            # Güvenli gönderim sayısını hesapla
            safe_count, message = self.calculate_safe_sending_count(len(recipients))
            
            if safe_count == 0:
                QMessageBox.warning(self, "Limit Uyarısı", message)
                return
            
            # Kullanıcıya bilgi ver
            if safe_count < len(recipients):
                reply = QMessageBox.question(self, "Limit Bilgisi", 
                    f"{message}\n\n"
                    f"Şimdi {safe_count} e-posta gönderilecek.\n"
                    f"Kalan {len(recipients) - safe_count} e-posta için 1 saat sonra otomatik devam edilecek.\n\n"
                    f"Devam etmek istiyor musunuz?",
                    QMessageBox.Yes | QMessageBox.No)
                
                if reply == QMessageBox.No:
                    return
            
            # Şimdi gönderilecek alıcıları seç
            recipients_to_send_now = recipients[:safe_count]
            recipients_to_send_later = recipients[safe_count:]
            
            # Batch bilgisi
            batch_info = {
                "batch_id": f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "total_recipients": len(recipients),
                "attachment_count": len(attachments)
            }
            
            # E-postaları gönder
            success_count = 0
            failed_recipients = []
            
            if self.bcc_checkbox.isChecked():
                # BCC ile gönderim
                email_delay = self.email_delay_spin_schedule.value()  # Zamanlama sekmesindeki ayar
                for j, recipient in enumerate(recipients_to_send_now):
                    try:
                        self.logger.info(f"BCC e-posta gönderiliyor ({j+1}/{len(recipients_to_send_now)}): {recipient}")
                        if send_email_smtp(subject, body_with_signature, recipient, attachments, smtp_settings, is_html, vcard_image_path):
                            success_count += 1
                            self.logger.info(f"BCC e-posta gönderildi: {recipient}")
                        else:
                            failed_recipients.append(recipient)
                            self.logger.error(f"BCC e-posta gönderilemedi: {recipient}")
                            
                            # Hata logu
                            self.logger.log_email_error(
                                subject=subject,
                                recipients=[recipient],
                                error_msg="SMTP gönderim başarısız",
                                send_time=datetime.now()
                            )
                    except Exception as e:
                        failed_recipients.append(recipient)
                        self.logger.error(f"BCC e-posta gönderme hatası ({recipient}): {e}")
                        
                        # Hata logu
                        self.logger.log_email_error(
                            subject=subject,
                            recipients=[recipient],
                            error_msg=str(e),
                            send_time=datetime.now()
                        )
                
                    # Son e-posta değilse bekle
                    if j < len(recipients_to_send_now) - 1:
                        self.logger.info(f"Sonraki BCC e-posta için {email_delay} saniye bekleniyor...")
                        time.sleep(email_delay)
            else:
                # Normal gönderim
                email_delay = self.email_delay_spin_schedule.value()  # Zamanlama sekmesindeki ayar
                for j, recipient in enumerate(recipients_to_send_now):
                    try:
                        self.logger.info(f"E-posta gönderiliyor ({j+1}/{len(recipients_to_send_now)}): {recipient}")
                        if send_email_smtp(subject, body_with_signature, recipient, attachments, smtp_settings, is_html, vcard_image_path):
                            success_count += 1
                            self.logger.info(f"E-posta gönderildi: {recipient}")
                        else:
                            failed_recipients.append(recipient)
                            self.logger.error(f"E-posta gönderilemedi: {recipient}")
                    except Exception as e:
                        failed_recipients.append(recipient)
                        self.logger.error(f"E-posta gönderme hatası ({recipient}): {e}")
                
                    # Son e-posta değilse bekle
                    if j < len(recipients_to_send_now) - 1:
                        self.logger.info(f"Sonraki e-posta için {email_delay} saniye bekleniyor...")
                        time.sleep(email_delay)
                
                    # Gönderim sayılarını güncelle
            if success_count > 0:
                    self.update_sending_counters(success_count)

            # Batch tamamlama logu - Sadece batch logu, çift kayıt yok
            batch_details = f"Toplam {len(recipients_to_send_now)} alıcıya gönderim tamamlandı. "
            batch_details += f"Başarılı: {success_count}, Başarısız: {len(failed_recipients)}"
            
            if failed_recipients:
                batch_details += f" | Başarısız alıcılar: {', '.join(failed_recipients)}"
            
            self.logger.log_email_batch(
                batch_id=batch_info["batch_id"],
                total_recipients=len(recipients_to_send_now),
                sent_count=success_count,
                failed_count=len(failed_recipients),
                subject=subject,
                send_time=datetime.now(),
                recipients=recipients_to_send_now,
                details=batch_details
            )

            # Başarı mesajı
            success_message = f"{success_count}/{len(recipients_to_send_now)} e-posta başarıyla gönderildi!"

            if failed_recipients:
                success_message += f"\n\nBaşarısız olanlar: {', '.join(failed_recipients)}"

            # Kalan alıcılar varsa, zamanlayıcı başlat
            if recipients_to_send_later:
                self.schedule_remaining_emails(subject, body_with_signature, recipients_to_send_later, attachments, smtp_settings)
                success_message += f"\n\nKalan {len(recipients_to_send_later)} alıcı için 1 saat sonra otomatik devam edilecek."

            if success_count > 0:
                self.play_notification_sound(success=True)
                QMessageBox.information(self, "Başarılı", success_message)
            else:
                self.play_notification_sound(success=False)
                QMessageBox.critical(self, "Hata", "Hiçbir e-posta gönderilemedi!")
                
        except Exception as e:
            self.logger.error(f"E-posta gönderme hatası: {e}")
            QMessageBox.critical(self, "Hata", f"E-posta gönderme hatası: {e}")

    def test_email_connection(self):
        """E-posta bağlantısını test et ve sonucu sistem bilgileri panelinde göster"""
        smtp_server = self.smtp_server_edit.text().strip()
        smtp_port = int(self.smtp_port_edit.text()) if self.smtp_port_edit.text() else 587
        sender_email = self.sender_email_edit.text().strip()
        sender_password = self.sender_password_edit.text().strip()
        smtp_settings = {
            'server': smtp_server,
            'port': smtp_port,
            'username': sender_email,
            'password': sender_password
        }
        subject = "Bağlantı Testi"
        body = "Bu bir e-posta bağlantı testidir."
        try:
            if send_email_smtp(subject, body, sender_email, smtp_settings=smtp_settings, is_html=False, vcard_image_path=None):
                self.email_status_label.setText("E-posta Bağlantısı: Başarılı")
                self.email_status_label.setStyleSheet("color: green; font-weight: bold;")
                QMessageBox.information(self, "Başarılı", "E-posta bağlantısı başarılı!")
            else:
                self.email_status_label.setText("E-posta Bağlantısı: Başarısız")
                self.email_status_label.setStyleSheet("color: red; font-weight: bold;")
                QMessageBox.critical(self, "Hata", "E-posta bağlantısı başarısız!")
        except Exception as e:
            self.email_status_label.setText("E-posta Bağlantısı: Başarısız")
            self.email_status_label.setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Hata", f"E-posta bağlantısı başarısız: {e}")

    def show_manual_import_dialog(self):
        """Manuel import penceresini göster"""
        dialog = ManualImportDialog(self)
        if dialog.exec_() == QDialog.DialogCode.Accepted:
            # Import edilen alıcıları listeye ekle
            imported_contacts = dialog.get_imported_contacts()
            self.add_imported_contacts_to_list(imported_contacts)
            # E-posta sekmesine geç
            self.switch_to_email_tab()

    def add_imported_contacts_to_list(self, contacts):
        """İçe aktarılan kişileri alıcı listesine ekle"""
        try:
            added_count = 0
            duplicate_count = 0
            
            # Mevcut alıcı e-postalarını kontrol için set oluştur
            existing_emails = set()
            for row in range(self.recipient_list.rowCount()):
                email = self.recipient_list.item(row, 0).text().strip()
                if email:
                    existing_emails.add(email.lower())
            
            # İçe aktarılan kişileri ekle
            for contact in contacts:
                email = contact.get('email', '').strip()
                name = contact.get('name', '').strip()
                
                if email and '@' in email:
                    email_lower = email.lower()
                    if email_lower not in existing_emails:
                        # Yeni alıcı ekle
                        row = self.recipient_list.rowCount()
                        self.recipient_list.insertRow(row)
                        
                        self.recipient_list.setItem(row, 0, QTableWidgetItem(email))
                        self.recipient_list.setItem(row, 1, QTableWidgetItem(name))
                        self.recipient_list.setItem(row, 2, QTableWidgetItem("Aktif"))
                        
                        existing_emails.add(email_lower)
                        added_count += 1
                    else:
                        duplicate_count += 1
            
            # Sonuç mesajı göster
            if added_count > 0:
                message = f"{added_count} yeni alıcı eklendi."
                if duplicate_count > 0:
                    message += f" {duplicate_count} mükerrer e-posta atlandı."
                QMessageBox.information(self, "Başarılı", message)
            else:
                QMessageBox.information(self, "Bilgi", "Eklenebilecek yeni e-posta adresi bulunamadı.")
                
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Alıcı listesine ekleme hatası: {e}")

    def clear_recipient_list(self):
        """Alıcı listesini temizle"""
        reply = QMessageBox.question(self, "Onay", "Alıcı listesini temizlemek istediğinizden emin misiniz?",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.recipient_list.setRowCount(0)
            QMessageBox.information(self, "Bilgi", "Alıcı listesi temizlendi!")

    def switch_to_email_tab(self):
        """E-posta sekmesine geçiş yapar"""
        try:
            # Ana tab widget'ını bul
            central_widget = self.centralWidget()
            if central_widget:
                # Sağ paneli bul (tab widget'ın bulunduğu yer)
                main_layout = central_widget.layout()
                if main_layout and main_layout.count() > 1:
                    right_panel = main_layout.itemAt(1).widget()
                    if isinstance(right_panel, QTabWidget):
                        # E-posta sekmesinin indeksini bul
                        for i in range(right_panel.count()):
                            if right_panel.tabText(i) == "E-posta":
                                right_panel.setCurrentIndex(i)
                                print(f"E-posta sekmesine geçildi (indeks: {i})")
                                return
                        
                        # Eğer "E-posta" sekmesi bulunamazsa, 2. indekse geç (varsayılan)
                        if right_panel.count() > 2:
                            right_panel.setCurrentIndex(2)
                            print("E-posta sekmesine geçildi (varsayılan indeks: 2)")
                        else:
                            print("E-posta sekmesi bulunamadı")
                    else:
                        print("Sağ panel QTabWidget değil")
                else:
                    print("Ana layout bulunamadı")
            else:
                print("Central widget bulunamadı")
        except Exception as e:
            print(f"E-posta sekmesine geçiş hatası: {e}")

    def switch_to_filter_tab(self):
        """Filtreleme sekmesine geç"""
        try:
            # Filtreleme sekmesi 3. sırada (index 2)
            self.right_panel.setCurrentIndex(2)  # Filtreleme sekmesi
            print("Filtreleme sekmesine geçildi")
        except Exception as e:
            print(f"Filtreleme sekmesine geçiş hatası: {e}")

    def on_bcc_checkbox_changed(self, state):
        """BCC checkbox durumu değiştiğinde çalışır"""
        if state == Qt.Checked:
            self.bcc_status_label.setText("BCC Açık")
            self.bcc_status_label.setStyleSheet("color: #4CAF50; font-size: 11px; font-style: italic; font-weight: bold;")
            QMessageBox.information(self, "BCC Durumu", "BCC (Gizli Alıcı) özelliği açıldı!\n\nAlıcı listesindeki kişiler birbirlerini göremeyecek.")
        else:
            self.bcc_status_label.setText("BCC Kapalı")
            self.bcc_status_label.setStyleSheet("color: #666; font-size: 11px; font-style: italic;")
            QMessageBox.information(self, "BCC Durumu", "BCC (Gizli Alıcı) özelliği kapatıldı!\n\nAlıcı listesindeki kişiler birbirlerini görebilecek.")
        
        # Ayarı kaydet
        self.save_config()

    def load_limit_settings(self):
        """Limit ayarlarını UI oluşturulduktan sonra yükle"""
        try:
            # Önce schedule bölümünden yüklemeyi dene
            schedule = self.config_manager.load_schedule()
            if schedule:
                # Schedule bölümünden yükle
                hourly_limit = int(schedule.get("hourly_limit", 30))
                daily_limit = int(schedule.get("daily_limit", 150))
                limit_enabled = schedule.get("limit_enabled", True)
                email_delay = int(schedule.get("email_delay_schedule", 3))
            else:
                # Eski settings bölümünden yükle (geriye uyumluluk)
                config = self.config_manager.load_config()
                if config.get("settings"):
                    s = config["settings"]
                    hourly_limit = int(s.get("hourly_limit", 30))
                    daily_limit = int(s.get("daily_limit", 150))
                    limit_enabled = s.get("limit_enabled", True)
                    email_delay = int(s.get("email_delay_schedule", 3))
                else:
                    # Varsayılan değerler
                    hourly_limit = 30
                    daily_limit = 150
                    limit_enabled = True
                    email_delay = 3

            if hasattr(self, 'hourly_limit_spin'):
                self.hourly_limit_spin.setValue(hourly_limit)
            if hasattr(self, 'daily_limit_spin'):
                self.daily_limit_spin.setValue(daily_limit)
            if hasattr(self, 'limit_check'):
                self.limit_check.setChecked(limit_enabled)
            if hasattr(self, 'email_delay_spin_schedule'):
                self.email_delay_spin_schedule.setValue(email_delay)

            # İstatistikleri güncelle
            if hasattr(self, 'hourly_sent_label') and hasattr(self, 'daily_sent_label'):
                self.update_sending_stats_display()
            
            self.logger.info(f"Limit ayarları yüklendi - Saatlik: {hourly_limit}, Günlük: {daily_limit}, Bekleme: {email_delay}")
            
        except Exception as e:
            self.logger.error(f"Limit ayarları yüklenirken hata: {e}")

    def save_limit_settings(self):
        """Limit ayarlarını kaydet"""
        try:
            # UI'dan değerleri al
            hourly_limit = self.hourly_limit_spin.value()
            daily_limit = self.daily_limit_spin.value()
            email_delay = self.email_delay_spin_schedule.value()  # Zamanlama sekmesindeki değeri kullan
            limit_enabled = self.limit_check.isChecked()
            
            # Schedule config'i güncelle
            schedule = {
                "hourly_limit": str(hourly_limit),
                "daily_limit": str(daily_limit),
                "limit_enabled": limit_enabled,
                "email_delay_schedule": str(email_delay),
            }
            
            # Kaydet
            self.config_manager.save_schedule(schedule)
            
            # Başarı mesajı
            QMessageBox.information(self, "Başarılı", "Limit ayarları kaydedildi!")
            
            # İstatistikleri yenile
            self.refresh_sending_stats()
            
            self.logger.info(f"Limit ayarları kaydedildi - Saatlik: {hourly_limit}, Günlük: {daily_limit}, Bekleme: {email_delay}")
            
        except Exception as e:
            self.logger.error(f"Limit ayarları kaydedilirken hata: {e}")
            QMessageBox.critical(self, "Hata", f"Ayarlar kaydedilemedi: {e}")

    # EŞLEŞTİRME FONKSİYONLARI - YENİ
    def on_mapping_table_changed(self, table_name):
        """Tablo seçildiğinde SQL başlıklarını yükle"""
        if not table_name:
            return
        
        try:
            # SQL başlıklarını getir
            conn = self.database_manager.conn or self.database_manager.connect_from_ui(self)
            cur = conn.cursor()
            
            cur.execute(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = '{table_name}' 
                ORDER BY ordinal_position
            """)
            sql_headers = [row[0] for row in cur.fetchall()]
            
            # SQL başlıklarını listeye ekle
            self.sql_headers_list.clear()
            self.sql_headers_list.addItems(sql_headers)
            
            # Dropdown'ları güncelle
            for dropdown in self.mapping_dropdowns.values():
                dropdown.clear()
                dropdown.addItem("-- Seçiniz --")
                dropdown.addItems(sql_headers)
            
            # Mevcut eşleştirmeyi yükle
            self.load_existing_mapping()
            
            # Butonları aktif hale getir
            self.load_mapping_btn.setEnabled(True)
            self.save_mapping_btn.setEnabled(True)
            
            cur.close()
            if not self.database_manager.conn:
                conn.close()
                
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Tablo başlıkları yüklenirken hata: {e}")
    def load_existing_mapping(self):
        """Mevcut eşleştirmeyi yükle"""
        table_name = self.mapping_table_combo.currentText()
        if not table_name:
            return
        
        mapping = self.mapping_manager.get_mapping(table_name)
        
        # Dropdown'ları mevcut eşleştirmeye göre ayarla
        for fixed_field, dropdown in self.mapping_dropdowns.items():
            sql_field = mapping.get(fixed_field, "")
            if sql_field:
                index = dropdown.findText(sql_field)
                if index >= 0:
                    dropdown.setCurrentIndex(index)
            else:
                dropdown.setCurrentIndex(0)  # "-- Seçiniz --"
        
        QMessageBox.information(self, "Bilgi", f"'{table_name}' tablosu için mevcut eşleştirme yüklendi.")

    def save_field_mapping(self):
        """Eşleştirmeyi kaydet"""
        table_name = self.mapping_table_combo.currentText()
        if not table_name:
            QMessageBox.warning(self, "Uyarı", "Lütfen önce bir tablo seçin!")
            return
        
        # Dropdown'lardan eşleştirmeyi al
        mapping = {}
        for fixed_field, dropdown in self.mapping_dropdowns.items():
            selected_text = dropdown.currentText()
            if selected_text != "-- Seçiniz --":
                mapping[fixed_field] = selected_text
        
        if not mapping:
            QMessageBox.warning(self, "Uyarı", "Hiçbir eşleştirme yapılmadı!")
            return
        
        # Eşleştirmeyi kaydet
        self.mapping_manager.save_mapping(table_name, mapping)
        
        QMessageBox.information(self, "Başarılı", 
            f"'{table_name}' tablosu için {len(mapping)} alan eşleştirmesi kaydedildi!\n"
            "Bu eşleştirme kalıcı olarak saklanacak ve program her açıldığında kullanılacak.")

    def get_filtered_data_with_mapping(self, table_name, il, sektor, email_filter, mapping):
        """Eşleştirme ile filtrelenmiş veri getir"""
        conn = self.database_manager.conn
        cur = conn.cursor()
        
        # SQL sütunlarını al
        cur.execute(f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = '{table_name}' 
            ORDER BY ordinal_position
        """)
        sql_columns = [row[0] for row in cur.fetchall()]
        
        # Eşleştirilmiş sütunları bul
        mapped_columns = []
        for fixed_field in self.mapping_manager.fixed_fields:
            sql_field = mapping.get(fixed_field, "")
            if sql_field and sql_field in sql_columns:
                mapped_columns.append(sql_field)
            else:
                mapped_columns.append("NULL")  # Eşleşmeyen alanlar için
        
        # Sorgu oluştur
        select_clause = ", ".join([f'"{col}"' if col != "NULL" else "NULL" for col in mapped_columns])
        query = f'SELECT {select_clause} FROM "{table_name}"'
        conditions = []
        params = []
        
        # Filtreleme koşulları - eşleştirilmiş alanları kullan
        if il and il.strip():
            il_field = mapping.get("il", "il")
            if il_field != "NULL" and il_field in sql_columns:
                conditions.append(f'"{il_field}" ILIKE %s')
                params.append(f"%{il}%")
        
        if sektor and sektor.strip():
            sektor_field = mapping.get("Sektör", "sektor")
            if sektor_field != "NULL" and sektor_field in sql_columns:
                conditions.append(f'"{sektor_field}" ILIKE %s')
                params.append(f"%{sektor}%")
        
        if email_filter:
            email1_field = mapping.get("E-posta-1", "e_posta_1")
            email2_field = mapping.get("E-posta 2", "e_posta_2")
            if email1_field != "NULL" and email2_field != "NULL" and email1_field in sql_columns and email2_field in sql_columns:
                email_condition = f'("{email1_field}" IS NOT NULL AND "{email1_field}" <> \'\' OR "{email2_field}" IS NOT NULL AND "{email2_field}" <> \'\')'
                conditions.append(email_condition)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        print(f"Eşleştirme sorgusu: {query}")
        cur.execute(query, params)
        sql_data = cur.fetchall()
        
        # Eşleştirmeyi uygula
        mapped_data, mapped_headers = self.mapping_manager.apply_mapping_to_data(
            table_name, sql_data, mapped_columns
        )
        
        return mapped_data, mapped_headers

    def get_filtered_data_old_method(self, table_name, il, sektor, email_filter):
        """Eski yöntemle filtrelenmiş veri getir"""
        conn = self.database_manager.conn
        cur = conn.cursor()
        
        # Tablonun sütun adlarını al
        cur.execute(f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = '{table_name}' 
            ORDER BY ordinal_position
        """)
        columns = [row[0] for row in cur.fetchall()]
        
        # Sektör sütununun gerçek adını bul
        sektor_column = None
        for col in columns:
            if col.lower() in ['sektör', 'sektor', 'sector']:
                sektor_column = col
                break
        
        if not sektor_column:
            sektor_column = "sektor"  # Varsayılan
        
        # Firma adı ve yetkili adı sütunlarının gerçek adlarını bul
        firma_adi_column = None
        yetkili_adi_column = None
        
        for col in columns:
            if col.lower() in ['firma_adi', 'firma adı', 'firma_adi']:
                firma_adi_column = col
            elif col.lower() in ['yetkili_adi_soyadi', 'yetkili adı soyadı', 'yetkili_adi_soyadi']:
                yetkili_adi_column = col
        
        # Eğer bulunamazsa varsayılan değerler kullan
        if not firma_adi_column:
            firma_adi_column = "firma_adi"
        if not yetkili_adi_column:
            yetkili_adi_column = "yetkili_adi_soyadi"
        
        # Temel sorgu - gerçek sütun adlarını kullan
        query = f"""
            SELECT id, il, "{sektor_column}", "{firma_adi_column}", "{yetkili_adi_column}", 
                   e_posta_1, e_posta_2, web_sitesi 
            FROM "{table_name}"
        """
        params = []
        conditions = []
        
        # Sadece dolu olan alanlar için filtreleme ekle
        if il and il.strip():
            conditions.append("il ILIKE %s")
            params.append(f"%{il}%")
            
        if sektor and sektor.strip():
            conditions.append(f'"{sektor_column}" ILIKE %s')
            params.append(f"%{sektor}%")
        
        # E-posta filtresi - sadece e-posta adresi olanları göster
        if email_filter:
            conditions.append("(e_posta_1 IS NOT NULL AND e_posta_1 <> '' OR e_posta_2 IS NOT NULL AND e_posta_2 <> '')")
        
        # WHERE koşullarını ekle
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        # Sıralama ekle
        query += f" ORDER BY il, {sektor_column}, \"{firma_adi_column}\""
        
        cur.execute(query, params)
        return cur.fetchall()

class ManualImportDialog(QDialog):
    """Manuel import penceresi"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manuel İçe Aktar")
        self.setModal(True)
        self.setMinimumSize(500, 400)
        
        self.imported_contacts = []
        self.init_ui()
        
    def init_ui(self):
        """Kullanıcı arayüzünü oluştur"""
        layout = QVBoxLayout(self)
        
        # Başlık
        title_label = QLabel("E-posta Adreslerini Girin")
        title_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(title_label)
        
        # Açıklama
        desc_label = QLabel("Her satıra bir e-posta adresi yazın. İsteğe bağlı olarak ad soyad ekleyebilirsiniz:")
        desc_label.setStyleSheet("color: #666; font-style: italic; font-size: 11px;")
        layout.addWidget(desc_label)
        
        # Format açıklaması
        format_label = QLabel("Format: e-posta@domain.com veya Ad Soyad,e-posta@domain.com")
        format_label.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(format_label)
        
        # Giriş alanı
        self.contacts_text = TurkishTextEdit()
        self.contacts_text.setPlaceholderText("ornek@firma.com\nAhmet Yılmaz,ahmet@firma.com\ninfo@digerfirma.com")
        layout.addWidget(self.contacts_text)
        
        # Doğrulanmış kişiler tablosu
        validated_group = QGroupBox("Doğrulanmış Kişiler")
        validated_layout = QVBoxLayout(validated_group)
        
        self.validated_table = QTableWidget()
        self.validated_table.setColumnCount(2)
        self.validated_table.setHorizontalHeaderLabels(["Ad Soyad", "E-posta"])
        validated_layout.addWidget(self.validated_table)
        
        layout.addWidget(validated_group)
        
        # Özet bilgileri
        summary_layout = QHBoxLayout()
        
        self.total_label = QLabel("Toplam: 0")
        summary_layout.addWidget(self.total_label)
        
        self.duplicate_label = QLabel("Mükerrer: 0")
        summary_layout.addWidget(self.duplicate_label)
        
        # Mükerrer kaldırma seçeneği
        self.remove_duplicates_check = QCheckBox("Mükerrerleri kaldır")
        self.remove_duplicates_check.setChecked(True)
        summary_layout.addWidget(self.remove_duplicates_check)
        
        summary_layout.addStretch()
        layout.addLayout(summary_layout)
        
        # Butonlar
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        validate_btn = QPushButton("Doğrula")
        validate_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-size: 12px; border: none; border-radius: 4px; padding: 8px 16px; } QPushButton:hover { background-color: #388e3c; }")
        validate_btn.clicked.connect(self.validate_contacts)
        button_layout.addWidget(validate_btn)
        
        cancel_btn = QPushButton("İptal")
        cancel_btn.setStyleSheet("QPushButton { background-color: #f44336; color: white; font-size: 12px; border: none; border-radius: 4px; padding: 8px 16px; } QPushButton:hover { background-color: #d32f2f; }")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        import_btn = QPushButton("İçe Aktar")
        import_btn.setStyleSheet("QPushButton { background-color: #2196F3; color: white; font-size: 12px; border: none; border-radius: 4px; padding: 8px 16px; } QPushButton:hover { background-color: #1976D2; }")
        import_btn.clicked.connect(self.accept)
        import_btn.setEnabled(False)  # Başlangıçta devre dışı
        self.import_btn = import_btn
        button_layout.addWidget(import_btn)
        
        layout.addLayout(button_layout)
        
    def validate_contacts(self):
        """Girilen e-posta adreslerini doğrula"""
        try:
            text = self.contacts_text.toPlainText().strip()
            if not text:
                QMessageBox.warning(self, "Uyarı", "Lütfen e-posta adresleri girin!")
                return
            
            lines = text.split('\n')
            contacts = []
            duplicates = set()
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Virgül ile ayrılmış format kontrol et
                if ',' in line:
                    parts = line.split(',', 1)
                    name = parts[0].strip()
                    email = parts[1].strip()
                else:
                    # Sadece e-posta adresi
                    email = line.strip()
                    name = ""
                
                # E-posta formatını kontrol et
                if '@' in email and '.' in email.split('@')[1]:
                    email_lower = email.lower()
                    if email_lower not in duplicates:
                        contacts.append({
                            'name': name,
                            'email': email
                        })
                        duplicates.add(email_lower)
            
            # Tabloyu güncelle
            self.validated_table.setRowCount(len(contacts))
            for row, contact in enumerate(contacts):
                self.validated_table.setItem(row, 0, QTableWidgetItem(contact['name']))
                self.validated_table.setItem(row, 1, QTableWidgetItem(contact['email']))
            
            # Özet bilgileri güncelle
            total_count = len(lines) - lines.count('')
            duplicate_count = total_count - len(contacts)
            
            self.total_label.setText(f"Toplam: {total_count}")
            self.duplicate_label.setText(f"Mükerrer: {duplicate_count}")
            
            # İçe aktar butonunu aktif hale getir
            self.import_btn.setEnabled(len(contacts) > 0)
            
            # Sonuçları sakla
            self.imported_contacts = contacts
            
            if len(contacts) > 0:
                QMessageBox.information(self, "Başarılı", f"{len(contacts)} geçerli e-posta adresi bulundu!")
            else:
                QMessageBox.warning(self, "Uyarı", "Geçerli e-posta adresi bulunamadı!")
                
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Doğrulama hatası: {e}")
    
    def get_imported_contacts(self):
        """İçe aktarılan kişileri döndür"""
        return self.imported_contacts
    
    # ==================== LOG İŞLEVLERİ ====================
    
    def start_log_timer(self):
        """Log güncelleme timer'ını başlat"""
        try:
            self.log_timer = QTimer()
            self.log_timer.timeout.connect(self.update_log_display)
            self.log_timer.start(2000)  # Her 2 saniyede güncelle
        except Exception as e:
            print(f"Log timer başlatma hatası: {e}")
    
    def update_log_display(self):
        """Log görüntüleyiciyi güncelle"""
        try:
            # Detaylı e-posta loglarını al
            detailed_logs = self.logger.get_detailed_email_logs()
            
            # Tabloyu temizle
            self.log_table.setRowCount(0)
            
            # Logları tabloya ekle
            for i, log in enumerate(detailed_logs[-100:]):  # Son 100 log
                self.log_table.insertRow(i)
                
                # Tarih/Saat
                self.log_table.setItem(i, 0, QTableWidgetItem(log.get('timestamp', '')))
                
                # Tip
                log_type = log.get('type', '')
                type_display = {
                    'EMAIL_SEND': 'Gönderim',
                    'EMAIL_BATCH': 'Batch',
                    'EMAIL_ERROR': 'Hata'
                }.get(log_type, log_type)
                self.log_table.setItem(i, 1, QTableWidgetItem(type_display))
                
                # Konu
                subject = log.get('subject', '')
                self.log_table.setItem(i, 2, QTableWidgetItem(subject))
                
                # Alıcılar
                if log_type == 'EMAIL_SEND':
                    recipient_count = log.get('recipient_count', 0)
                    self.log_table.setItem(i, 3, QTableWidgetItem(str(recipient_count)))
                elif log_type == 'EMAIL_BATCH':
                    sent_count = log.get('sent_count', 0)
                    total_count = log.get('total_recipients', 0)
                    self.log_table.setItem(i, 3, QTableWidgetItem(f"{sent_count}/{total_count}"))
                else:
                    self.log_table.setItem(i, 3, QTableWidgetItem('-'))
                
                # Durum
                status = log.get('status', '')
                status_display = {
                    'SENT': 'Başarılı',
                    'FAILED': 'Başarısız'
                }.get(status, status)
                self.log_table.setItem(i, 4, QTableWidgetItem(status_display))
                
                # Detaylar
                if log_type == 'EMAIL_SEND':
                    recipients = log.get('recipients', [])
                    details = f"Alıcılar: {', '.join(recipients[:3])}{'...' if len(recipients) > 3 else ''}"
                elif log_type == 'EMAIL_BATCH':
                    success_rate = log.get('success_rate', 0)
                    details = f"Başarı Oranı: {success_rate:.1f}%"
                elif log_type == 'EMAIL_ERROR':
                    error_msg = log.get('error_message', '')
                    details = f"Hata: {error_msg}"
                else:
                    details = ''
                
                self.log_table.setItem(i, 5, QTableWidgetItem(details))
            
            # Son güncelleme zamanını güncelle
            self.last_update_label.setText(f"Son Güncelleme: {datetime.now().strftime('%H:%M:%S')}")
            
        except Exception as e:
            print(f"Log güncelleme hatası: {e}")  
    
    def on_log_selection_changed(self):
        """Log seçimi değiştiğinde detayları göster"""
        try:
            current_row = self.log_table.currentRow()
            if current_row >= 0:
                # Seçili satırın verilerini al
                timestamp = self.log_table.item(current_row, 0).text()
                log_type = self.log_table.item(current_row, 1).text()
                subject = self.log_table.item(current_row, 2).text()
                recipients = self.log_table.item(current_row, 3).text()
                status = self.log_table.item(current_row, 4).text()
                details = self.log_table.item(current_row, 5).text()
                
                # Detay metnini oluştur
                detail_text = f"""
                Tarih/Saat: {timestamp}
                Tip: {log_type}
                Konu: {subject}
                Alıcılar: {recipients}
                Durum: {status}
                Detaylar: {details}
                """.strip()
                
                self.log_detail_text.setPlainText(detail_text)
        except Exception as e:
            print(f"Log detay gösterme hatası: {e}")
    
    def on_log_level_changed(self):
        """Log seviyesi değiştiğinde filtrele"""
        self.filter_logs()
    
    def filter_logs(self):
        """Logları filtrele"""
        try:
            search_text = self.log_search_edit.text().lower()
            selected_date = self.log_date_edit.date()
            log_level = self.log_level_combo.currentText()
            
            # Tüm satırları kontrol et
            for row in range(self.log_table.rowCount()):
                show_row = True
                
                # Arama filtresi
                if search_text:
                    row_text = ""
                    for col in range(self.log_table.columnCount()):
                        item = self.log_table.item(row, col)
                        if item:
                            row_text += item.text() + " "
                    
                    if search_text not in row_text.lower():
                        show_row = False
                
                # Tarih filtresi
                if selected_date:
                    timestamp_item = self.log_table.item(row, 0)
                    if timestamp_item:
                        try:
                            log_date = datetime.strptime(timestamp_item.text(), '%Y-%m-%d %H:%M:%S')
                            if log_date.date() != selected_date.toPyDate():
                                show_row = False
                        except:
                            show_row = False
                
                # Log seviyesi filtresi
                if log_level != "TÜMÜ":
                    type_item = self.log_table.item(row, 1)
                    if type_item:
                        if log_level == "E-POSTA" and type_item.text() not in ["Gönderim", "Batch", "Hata"]:
                            show_row = False
                        elif log_level == "SİSTEM" and type_item.text() in ["Gönderim", "Batch", "Hata"]:
                            show_row = False
                        elif log_level == "HATA" and type_item.text() != "Hata":
                            show_row = False
                
                # Satırı göster/gizle
                self.log_table.setRowHidden(row, not show_row)
                
        except Exception as e:
            print(f"Log filtreleme hatası: {e}")
    
    def refresh_logs(self):
        """Logları yenile"""
        self.update_log_display()
    
    def export_logs(self):
        """Logları dosyaya kaydet"""
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Logları Kaydet", "", 
                "JSON Files (*.json);;Text Files (*.txt);;All Files (*)"
            )
            
            if file_path:
                if file_path.endswith('.json'):
                    success = self.logger.export_logs(file_path, "detailed_email")
                else:
                    success = self.logger.export_logs(file_path, "all")
                
                if success:
                    QMessageBox.information(self, "Başarılı", "Loglar başarıyla dışa aktarıldı!")
                else:
                    QMessageBox.warning(self, "Hata", "Loglar dışa aktarılamadı!")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Log dışa aktarma hatası: {e}")

def main():
    """Ana uygulama fonksiyonu"""
    app = QApplication(sys.argv)
    
    # Uygulama ayarları
    app.setApplicationName("Otomatik E-posta Gönderim Sistemi")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("Şirket Adı")
    
    # Ana pencereyi oluştur ve göster
    window = MainWindow()
    window.show()
    
    # Uygulamayı çalıştır
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 

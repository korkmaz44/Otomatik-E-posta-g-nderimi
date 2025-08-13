import logging
import os
import json
from datetime import datetime

class Logger:
    def __init__(self, log_dir="./logs"):
        self.log_dir = log_dir
        self.log_file = os.path.join(log_dir, "app.log")
        self.email_log_file = os.path.join(log_dir, "email.log")
        self.received_email_log_file = os.path.join(log_dir, "received_email.log")
        self.system_log_file = os.path.join(log_dir, "system.log")
        self.detailed_email_log_file = os.path.join(log_dir, "detailed_email.json")
        
        # Log dizinini oluştur
        os.makedirs(log_dir, exist_ok=True)
        
        # Ana logger
        self.logger = logging.getLogger('main')
        self.logger.setLevel(logging.INFO)
        
        # Dosya handler
        file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        
        # Format
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        
        # Handler'ı ekle
        if not self.logger.handlers:
            self.logger.addHandler(file_handler)
        
        # Log satırlarını sakla
        self.log_lines = []
        self.email_log_lines = []
        self.received_email_log_lines = []
        self.system_log_lines = []
        self.detailed_email_logs = []
        
        # Detaylı e-posta loglarını yükle
        self.load_detailed_email_logs()
    
    def load_detailed_email_logs(self):
        """Detaylı e-posta loglarını yükle"""
        try:
            if os.path.exists(self.detailed_email_log_file):
                with open(self.detailed_email_log_file, 'r', encoding='utf-8') as f:
                    self.detailed_email_logs = json.load(f)
        except Exception as e:
            print(f"Detaylı e-posta logları yüklenemedi: {e}")
            self.detailed_email_logs = []
    
    def save_detailed_email_logs(self):
        """Detaylı e-posta loglarını kaydet"""
        try:
            with open(self.detailed_email_log_file, 'w', encoding='utf-8') as f:
                json.dump(self.detailed_email_logs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Detaylı e-posta logları kaydedilemedi: {e}")
    
    def log_email_send(self, subject, body, recipients, attachments=None, 
                       smtp_settings=None, send_time=None, batch_info=None):
        """Detaylı e-posta gönderim logu"""
        if send_time is None:
            send_time = datetime.now()
        
        email_log = {
            "timestamp": send_time.strftime('%Y-%m-%d %H:%M:%S'),
            "type": "EMAIL_SEND",
            "subject": subject,
            "body_preview": body[:200] + "..." if len(body) > 200 else body,
            "recipients": recipients,
            "recipient_count": len(recipients),
            "attachments": attachments or [],
            "attachment_count": len(attachments) if attachments else 0,
            "smtp_server": smtp_settings.get('server', '') if smtp_settings else '',
            "batch_info": batch_info or {},
            "status": "SENT"
        }
        
        self.detailed_email_logs.append(email_log)
        self.save_detailed_email_logs()
        
        # Basit log mesajı
        msg = f"E-POSTA GÖNDERİLDİ - Konu: {subject} | Alıcılar: {len(recipients)} | Tarih: {send_time.strftime('%Y-%m-%d %H:%M:%S')}"
        self.info(msg)
    
    def log_email_batch(self, batch_id, total_recipients, sent_count, failed_count, 
                        subject, send_time=None, recipients=None, details=None):
        """E-posta batch logu"""
        if send_time is None:
            send_time = datetime.now()
        
        batch_log = {
            "timestamp": send_time.strftime('%Y-%m-%d %H:%M:%S'),
            "type": "EMAIL_BATCH",
            "batch_id": batch_id,
            "subject": subject,
            "recipients": recipients or [],
            "total_recipients": total_recipients,
            "sent_count": sent_count,
            "failed_count": failed_count,
            "status": "COMPLETED" if sent_count > 0 else "FAILED",
            "success_rate": (sent_count / total_recipients * 100) if total_recipients > 0 else 0,
            "details": details or f"Batch tamamlandı: {sent_count} başarılı, {failed_count} başarısız"
        }
        
        self.detailed_email_logs.append(batch_log)
        self.save_detailed_email_logs()
        
        msg = f"E-POSTA BATCH TAMAMLANDI - Batch ID: {batch_id} | Gönderilen: {sent_count}/{total_recipients} | Başarı Oranı: {batch_log['success_rate']:.1f}%"
        self.info(msg)
    
    def log_email_error(self, subject, recipients, error_msg, send_time=None):
        """E-posta hata logu"""
        if send_time is None:
            send_time = datetime.now()
        
        error_log = {
            "timestamp": send_time.strftime('%Y-%m-%d %H:%M:%S'),
            "type": "EMAIL_ERROR",
            "subject": subject,
            "recipients": recipients,
            "error_message": error_msg,
            "status": "FAILED"
        }
        
        self.detailed_email_logs.append(error_log)
        self.save_detailed_email_logs()
        
        msg = f"E-POSTA HATASI - Konu: {subject} | Hata: {error_msg}"
        self.error(msg)
    
    def get_detailed_email_logs(self, log_type=None, limit=100):
        """Detaylı e-posta loglarını getir"""
        if log_type:
            filtered_logs = [log for log in self.detailed_email_logs if log.get('type') == log_type]
        else:
            filtered_logs = self.detailed_email_logs
        
        return filtered_logs[-limit:] if limit else filtered_logs
    
    def get_email_summary(self, days=7):
        """E-posta özet istatistikleri"""
        from datetime import timedelta
        cutoff_date = datetime.now() - timedelta(days=days)
        
        recent_logs = []
        for log in self.detailed_email_logs:
            try:
                log_time = datetime.strptime(log['timestamp'], '%Y-%m-%d %H:%M:%S')
                if log_time >= cutoff_date:
                    recent_logs.append(log)
            except:
                continue
        
        summary = {
            'total_emails': len([log for log in recent_logs if log.get('type') == 'EMAIL_SEND']),
            'total_batches': len([log for log in recent_logs if log.get('type') == 'EMAIL_BATCH']),
            'total_errors': len([log for log in recent_logs if log.get('type') == 'EMAIL_ERROR']),
            'total_recipients': sum([log.get('recipient_count', 0) for log in recent_logs if log.get('type') == 'EMAIL_SEND']),
            'success_rate': 0
        }
        
        if summary['total_emails'] > 0:
            summary['success_rate'] = ((summary['total_emails'] - summary['total_errors']) / summary['total_emails']) * 100
        
        return summary
    
    def set_level(self, level):
        """Log seviyesini ayarla"""
        self.logger.setLevel(level)
    
    def info(self, msg):
        """Bilgi logu"""
        self.logger.info(msg)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.log_lines.append(f"[{timestamp}] BİLGİ - {msg}")
        
        # E-posta logları için özel kayıt
        if "E-POSTA GÖNDERİLDİ" in msg or "E-POSTA BATCH" in msg:
            self.email_log_lines.append(f"[{timestamp}] {msg}")
        elif "E-POSTA OKUNDU" in msg:
            self.received_email_log_lines.append(f"[{timestamp}] {msg}")
        else:
            self.system_log_lines.append(f"[{timestamp}] {msg}")
    
    def error(self, msg):
        """Hata logu"""
        self.logger.error(msg)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.log_lines.append(f"[{timestamp}] HATA - {msg}")
        self.system_log_lines.append(f"[{timestamp}] {msg}")
    
    def warning(self, msg):
        """Uyarı logu"""
        self.logger.warning(msg)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.log_lines.append(f"[{timestamp}] UYARI - {msg}")
        self.system_log_lines.append(f"[{timestamp}] {msg}")
    
    def debug(self, msg):
        """Debug logu"""
        self.logger.debug(msg)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.log_lines.append(f"[{timestamp}] DEBUG - {msg}")
        self.system_log_lines.append(f"[{timestamp}] {msg}")
    
    def get_log_text(self):
        """Tüm logları metin olarak döndür"""
        return "\n".join(self.log_lines[-1000:])  # Son 1000 satır
    
    def get_log_lines(self):
        """Log satırlarını döndür"""
        return self.log_lines
    
    def get_email_log_text(self):
        """E-posta gönderim loglarını döndür"""
        return "\n".join(self.email_log_lines[-500:])  # Son 500 satır
    
    def get_received_email_log_text(self):
        """E-posta okundu loglarını döndür"""
        return "\n".join(self.received_email_log_lines[-500:])  # Son 500 satır
    
    def get_system_log_text(self):
        """Sistem loglarını döndür"""
        return "\n".join(self.system_log_lines[-500:])  # Son 500 satır
    
    def clear_logs(self):
        """Tüm logları temizle"""
        self.log_lines.clear()
        self.email_log_lines.clear()
        self.received_email_log_lines.clear()
        self.system_log_lines.clear()
        self.detailed_email_logs.clear()
        self.save_detailed_email_logs()
        
        # Log dosyalarını da temizle
        for log_file in [self.log_file, self.email_log_file, self.received_email_log_file, self.system_log_file]:
            if os.path.exists(log_file):
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.write('')
    
    def export_logs(self, file_path, log_type="all"):
        """Logları dışa aktar"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                if log_type == "email":
                    f.write(self.get_email_log_text())
                elif log_type == "received_email":
                    f.write(self.get_received_email_log_text())
                elif log_type == "system":
                    f.write(self.get_system_log_text())
                elif log_type == "detailed_email":
                    json.dump(self.detailed_email_logs, f, ensure_ascii=False, indent=2)
                else:
                    f.write(self.get_log_text())
            return True
        except Exception as e:
            print(f"Log dışa aktarma hatası: {e}")
            return False 
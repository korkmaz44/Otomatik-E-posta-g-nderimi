import psycopg2
import logging
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

class DatabaseManager:
    def __init__(self):
        self.conn = None
        self.connection_params = None
        self.connection_pool = None
        self.logger = logging.getLogger(__name__)
        
    def test_connection(self, host, port, db_name, user, password):
        """Veritabanı bağlantısını test et"""
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                dbname=db_name,
                user=user,
                password=password
            )
            conn.close()
            return True
        except Exception as e:
            self.logger.error(f"Veritabanı bağlantı hatası: {e}")
            return False

    def connect_from_ui(self, ui):
        """UI'dan alınan bilgilerle bağlantı açar ve döndürür."""
        try:
            # Bağlantı parametrelerini kaydet
            self.connection_params = {
                'host': ui.db_host_edit.text(),
                'port': ui.db_port_edit.text(),
                'dbname': ui.db_name_edit.text(),
                'user': ui.db_user_edit.text(),
                'password': ui.db_password_edit.text()
            }
            
            # Bağlantıyı aç
            self.conn = psycopg2.connect(**self.connection_params)
            self.logger.info("Veritabanı bağlantısı başarıyla açıldı")
            return self.conn
            
        except Exception as e:
            self.logger.error(f"Veritabanı bağlantı hatası: {e}")
            return None
            
    def get_connection(self, ui=None):
        """Güvenli bağlantı alma"""
        try:
            # Mevcut bağlantı kontrolü
            if self.conn and not self.conn.closed:
                return self.conn
                
            # Yeni bağlantı açma
            if ui:
                return self.connect_from_ui(ui)
            elif self.connection_params:
                self.conn = psycopg2.connect(**self.connection_params)
                return self.conn
            else:
                self.logger.error("Bağlantı parametreleri bulunamadı")
                return None
                
        except Exception as e:
            self.logger.error(f"Bağlantı alma hatası: {e}")
            return None
            
    def close_connection(self):
        """Bağlantıyı güvenli kapat"""
        try:
            if self.conn and not self.conn.closed:
                self.conn.close()
                self.conn = None
                self.logger.info("Veritabanı bağlantısı kapatıldı")
        except Exception as e:
            self.logger.error(f"Bağlantı kapatma hatası: {e}")
            
    def validate_table_name(self, table_name):
        """Tablo adı doğrulama - SQL injection koruması"""
        if not table_name:
            return False
            
        # Sadece harf, rakam ve alt çizgi karakterlerine izin ver
        allowed_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
        return all(c in allowed_chars for c in table_name)
        
    def validate_column_name(self, column_name):
        """Sütun adı doğrulama - SQL injection koruması"""
        return self.validate_table_name(column_name)
        
    def safe_execute_query(self, query, params=None, fetch_all=True):
        """Güvenli sorgu çalıştırma"""
        try:
            conn = self.get_connection()
            if not conn:
                return None, "Veritabanı bağlantısı kurulamadı"
                
            cur = conn.cursor()
            cur.execute(query, params)
            
            if fetch_all:
                results = cur.fetchall()
            else:
                results = cur.rowcount
                
            cur.close()
            return results, None
            
        except psycopg2.Error as e:
            self.logger.error(f"Veritabanı hatası: {e}")
            return None, f"Veritabanı hatası: {e}"
        except Exception as e:
            self.logger.error(f"Beklenmeyen hata: {e}")
            return None, f"Beklenmeyen hata: {e}"
            
    def get_table_columns(self, table_name):
        """Tablo sütunlarını güvenli şekilde al"""
        if not self.validate_table_name(table_name):
            return None, "Geçersiz tablo adı"
            
        query = """
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = %s 
            ORDER BY ordinal_position
        """
        
        results, error = self.safe_execute_query(query, (table_name,))
        if error:
            return None, error
            
        return [row[0] for row in results], None
        
    def get_table_data(self, table_name, columns=None, conditions=None, limit=None):
        """Tablo verilerini güvenli şekilde al"""
        if not self.validate_table_name(table_name):
            return None, "Geçersiz tablo adı"
            
        # Sütun doğrulama
        if columns:
            for col in columns:
                if not self.validate_column_name(col):
                    return None, f"Geçersiz sütun adı: {col}"
                    
        # Sorgu oluşturma
        select_columns = "*"
        if columns:
            select_columns = ", ".join([f'"{col}"' for col in columns])
            
        query = f'SELECT {select_columns} FROM "{table_name}"'
        params = []
        
        # Koşul ekleme
        if conditions:
            where_clauses = []
            for condition in conditions:
                if self.validate_column_name(condition['column']):
                    where_clauses.append(f'"{condition["column"]}" {condition["operator"]} %s')
                    params.append(condition['value'])
            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)
                
        # Limit ekleme
        if limit and isinstance(limit, int) and limit > 0:
            query += f" LIMIT {limit}"
            
        return self.safe_execute_query(query, params)
        
    def get_distinct_values(self, table_name, column_name):
        """Belirli sütundaki benzersiz değerleri al"""
        if not self.validate_table_name(table_name) or not self.validate_column_name(column_name):
            return None, "Geçersiz tablo veya sütun adı"
            
        query = f'SELECT DISTINCT "{column_name}" FROM "{table_name}" WHERE "{column_name}" IS NOT NULL AND "{column_name}" <> \'\' ORDER BY "{column_name}"'
        
        results, error = self.safe_execute_query(query)
        if error:
            return None, error
            
        return [row[0] for row in results], None
        
    def get_table_count(self, table_name):
        """Tablo kayıt sayısını al"""
        if not self.validate_table_name(table_name):
            return None, "Geçersiz tablo adı"
            
        query = f'SELECT COUNT(*) FROM "{table_name}"'
        
        results, error = self.safe_execute_query(query)
        if error:
            return None, error
            
        return results[0][0] if results else 0, None 
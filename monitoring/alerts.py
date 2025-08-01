import smtplib
import os
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

class AlertManager:
    def __init__(self):
        self.smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_username = os.getenv('SMTP_USERNAME')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.alert_email = os.getenv('ALERT_EMAIL')
        
    def send_email_alert(self, subject, message):
        """Send email alert"""
        if not all([self.smtp_username, self.smtp_password, self.alert_email]):
            print("Email configuration missing, skipping email alert")
            return False
            
        try:
            msg = MimeMultipart()
            msg['From'] = self.smtp_username
            msg['To'] = self.alert_email
            msg['Subject'] = f"[Amazon Scraper Alert] {subject}"
            
            body = f"""
            Alert Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            
            {message}
            
            Please check your scraper system.
            """
            
            msg.attach(MimeText(body, 'plain'))
            
            server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            server.starttls()
            server.login(self.smtp_username, self.smtp_password)
            server.send_message(msg)
            server.quit()
            
            print(f"Alert sent: {subject}")
            return True
            
        except Exception as e:
            print(f"Failed to send email alert: {e}")
            return False
    
    def check_scraper_health(self, db_manager):
        """Check scraper health and send alerts if needed"""
        try:
            # Check recent scraping activity
            session = db_manager.get_session()
            from sqlalchemy import text
            
            # Count products scraped in last hour
            recent_products = session.execute(text("""
                SELECT COUNT(*) as count 
                FROM products 
                WHERE scraped_at > NOW() - INTERVAL '1 hour'
            """)).fetchone()
            
            # Count failed requests (you'd need to add a failures table)
            # For now, we'll simulate this check
            
            if recent_products.count == 0:
                self.send_email_alert(
                    "No Recent Scraping Activity",
                    "No products have been scraped in the last hour. Please check the scraper."
                )
            
            session.close()
            
        except Exception as e:
            self.send_email_alert(
                "Scraper Health Check Failed", 
                f"Failed to check scraper health: {str(e)}"
            )

alert_manager = AlertManager()

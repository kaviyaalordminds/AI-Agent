import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.services.email.base import EmailMessage, EmailProvider


class SMTPEmailProvider(EmailProvider):
    def __init__(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        use_tls: bool,
        from_address: str,
        from_name: str,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.from_address = from_address
        self.from_name = from_name

    def send(self, message: EmailMessage) -> None:
        mime_message = MIMEMultipart("alternative")
        mime_message["Subject"] = message.subject
        mime_message["From"] = f"{self.from_name} <{self.from_address}>"
        mime_message["To"] = message.to
        mime_message.attach(MIMEText(message.text_body, "plain"))
        if message.html_body:
            mime_message.attach(MIMEText(message.html_body, "html"))

        with smtplib.SMTP(self.host, self.port, timeout=10) as server:
            if self.use_tls:
                server.starttls()
            if self.username and self.password:
                server.login(self.username, self.password)
            server.sendmail(self.from_address, [message.to], mime_message.as_string())

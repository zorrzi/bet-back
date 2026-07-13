import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

def send_email(email: str, content: str, subject: str):
    """
    Envia um email usando SendGrid
    
    Args:
        email: Email do destinatário
        content: Conteúdo HTML do email
        subject: Assunto do email
    """
    message = Mail(
        from_email=os.getenv("SENDGRID_FROM_EMAIL", "noreply@example.com"),
        to_emails=email,
        subject=subject,
        html_content=content
    )
    
    try:
        sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
        response = sg.send(message)
        return {
            "status_code": response.status_code,
            "body": response.body,
            "headers": response.headers
        }
    except Exception as e:
        print(f"Erro ao enviar email: {str(e)}")
        raise e

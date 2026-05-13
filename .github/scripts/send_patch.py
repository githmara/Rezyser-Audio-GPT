import sys
import re
import smtplib
import os
from email.message import EmailMessage

def main():
    # Pobieramy treść issue przekazaną z Actions
    if len(sys.argv) < 2:
        print("Brak treści issue.")
        sys.exit(1)
        
    issue_body = sys.argv[1]
    
    # Wyciągamy adres email za pomocą wyrażenia regularnego
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', issue_body)
    
    if not email_match:
        print("Nie znaleziono adresu email w treści.")
        sys.exit(1) # Wyjście z błędem zatrzyma proces Actions
        
    recipient_email = email_match.group(0)
    print(f"Znaleziono email: {recipient_email}. Przygotowuję wysyłkę...")

    # Konfiguracja wiadomości
    msg = EmailMessage()
    msg['Subject'] = 'Potwierdzenie zgłoszenia i Twój Patch'
    msg['From'] = os.environ.get('SMTP_USER')
    msg['To'] = recipient_email
    msg.set_content('Cześć!\n\n Przesyłam patcha. Zgłoszenie zostało zamknięte.\nhttps://1drv.ms/u/c/717e0c193b743dcf/IQDbzNF_k71lR7r54Qtpfc_jASfUF0BwreedEUqqltWDbaU?e=KDJb38\nPozdrawiam\nMarek Uram')

    # Wysłanie przez SMTP (przykład dla Gmaila, zmień serwer/port według potrzeb)
    smtp_user = os.environ.get('SMTP_USER')
    smtp_pass = os.environ.get('SMTP_PASS')
    
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        print("Wiadomość wysłana pomyślnie.")
    except Exception as e:
        print(f"Błąd wysyłki maila: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
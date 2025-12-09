import os
import urllib.parse

def send_sms(to, message):
    # Format phone number with country code and no symbols (e.g., 911234567890)
    phone_number = to
    encoded_msg = urllib.parse.quote(message)
    # Create the WhatsApp intent using `am start`
    os.system(f'am start -a android.intent.action.VIEW -d "https://wa.me/{phone_number}?text={encoded_msg}"')

# Example usage
send_sms("911234567890", "Hello from Termux and Python!")
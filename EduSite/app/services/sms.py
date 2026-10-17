"""SMS sending abstraction.

Production: implement SmsProvider with a real provider (e.g. Kavenegar).
Development: ConsoleSms prints to server log; nothing external is used.
"""
import logging

log = logging.getLogger("sms")


class SmsProvider:
    def send_otp(self, phone, code):
        raise NotImplementedError


class ConsoleSms(SmsProvider):
    """Dev-only. Never used when DEV_MODE=0."""

    def send_otp(self, phone, text):
        log.info("[DEV SMS] to=%s body=%s", phone, text)
        try:
            print(f"[DEV SMS] to={phone} body={text}")
        except UnicodeEncodeError:
            # Windows consoles (cp1252 etc.) cannot encode Persian digits/letters.
            print(f"[DEV SMS] to={phone} body={text.encode('ascii', 'backslashreplace').decode('ascii')}")


class HttpSms(SmsProvider):
    """Placeholder for the production provider. NOT implemented in MVP."""

    def __init__(self, api_key):
        self.api_key = api_key

    def send_otp(self, phone, text):
        raise NotImplementedError(
            "Real SMS provider is not configured yet. "
            "Implement HttpSms.send_otp with the chosen Iranian gateway."
        )


def get_sms_provider(config):
    if config["DEV_MODE"]:
        return ConsoleSms()
    raise RuntimeError(
        "No production SMS provider configured. Implement HttpSms with a real gateway."
    )

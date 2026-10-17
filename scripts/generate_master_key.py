"""Print a new random master key for MASTER_KEY in .env. Do not commit or log it."""

from uscis_assistant.storage.crypto import encode_key, generate_key

if __name__ == "__main__":
    print(encode_key(generate_key()))

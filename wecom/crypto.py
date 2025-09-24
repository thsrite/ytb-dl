from __future__ import annotations

import base64
import hashlib
import os
import struct
from dataclasses import dataclass
from typing import Tuple

from Crypto.Cipher import AES


class WeComCryptoError(Exception):
    """Raised when message decryption or signature validation fails."""


@dataclass
class WeComCrypto:
    token: str
    encoding_aes_key: str
    corp_id: str

    def __post_init__(self) -> None:
        key = self.encoding_aes_key + "="
        self.aes_key = base64.b64decode(key)
        if len(self.aes_key) != 32:
            raise WeComCryptoError("Invalid AES key length; expected 256-bit key")
        self.iv = self.aes_key[:16]

    def verify_signature(self, signature: str, timestamp: str, nonce: str, encrypt: str) -> None:
        """Validate SHA1 signature using the known token."""
        expected = self._sha1(timestamp, nonce, encrypt)
        if expected != signature:
            raise WeComCryptoError("Signature verification failed")

    def decrypt(self, encrypt: str) -> Tuple[str, str]:
        """Decrypt encrypted message and return (xml, receive_id)."""
        cipher = AES.new(self.aes_key, AES.MODE_CBC, self.iv)
        padded = cipher.decrypt(base64.b64decode(encrypt))
        plaintext = self._pkcs7_unpad(padded)

        # Skip the random 16 bytes
        content = plaintext[16:]
        xml_length = struct.unpack(">I", content[:4])[0]
        xml_data = content[4:4 + xml_length]
        receive_id = content[4 + xml_length:].decode()
        if receive_id != self.corp_id:
            raise WeComCryptoError("Receiver corp id mismatch")
        return xml_data.decode(), receive_id

    def encrypt(self, xml: str, timestamp: str, nonce: str) -> dict:
        """Encrypt reply XML and build response payload."""
        xml_bytes = xml.encode()
        random_bytes = os.urandom(16)
        packed_length = struct.pack(">I", len(xml_bytes))
        text = random_bytes + packed_length + xml_bytes + self.corp_id.encode()
        padded = self._pkcs7_pad(text)

        cipher = AES.new(self.aes_key, AES.MODE_CBC, self.iv)
        encrypt = base64.b64encode(cipher.encrypt(padded)).decode()
        signature = self._sha1(timestamp, nonce, encrypt)
        return {
            "msg_signature": signature,
            "timestamp": timestamp,
            "nonce": nonce,
            "encrypt": encrypt,
        }

    def _sha1(self, timestamp: str, nonce: str, encrypt: str) -> str:
        params = sorted([self.token, timestamp, nonce, encrypt])
        return hashlib.sha1("".join(params).encode()).hexdigest()

    @staticmethod
    def _pkcs7_unpad(text: bytes) -> bytes:
        pad = text[-1]
        if pad < 1 or pad > 32:
            raise WeComCryptoError("Invalid padding")
        return text[:-pad]

    @staticmethod
    def _pkcs7_pad(text: bytes) -> bytes:
        block_size = AES.block_size
        pad_length = block_size - len(text) % block_size
        return text + bytes([pad_length]) * pad_length

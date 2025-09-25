import os
import json
import base64
import hashlib
import requests
from hashlib import md5
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Random import get_random_bytes
from datetime import datetime


class CookieCloud:
    def __init__(self, config: Dict[str, str]):
        """
        Initialize CookieCloud client

        Args:
            config: Dictionary containing:
                - server_url: CookieCloud server URL
                - uuid_key: User UUID key
                - password: Encryption password
        """
        self.server_url = config.get('server_url', '').rstrip('/')
        self.uuid_key = config.get('uuid_key', '')
        self.password = config.get('password', '')
        self.enabled = bool(self.server_url and self.uuid_key and self.password)

    def is_enabled(self) -> bool:
        """Check if CookieCloud is properly configured"""
        return self.enabled

    def _get_crypt_key(self) -> bytes:
        """
        Generate encryption key from UUID and password
        Uses MD5 hash of "uuid_key-password" and takes first 16 characters of the hex string
        This matches CookieCloud's key generation method
        """
        combined_string = f"{self.uuid_key}-{self.password}"
        # Get MD5 hash as hex string
        md5_hex = hashlib.md5(combined_string.encode('utf-8')).hexdigest()
        # Return first 16 characters of the hex string as UTF-8 encoded bytes
        # This will be a 16-byte string like "a1b2c3d4e5f67890"
        return md5_hex[:16].encode('utf-8')

    def _decrypt_data(self, encrypted: str) -> int | bytes | None | str:
        """
        Decrypt CookieCloud data using CryptoJS AES format

        Args:
            encrypted: Base64 encoded encrypted data

        Returns:
            Decrypted JSON string or None if decryption fails
        """
        try:
            # Get the 16-byte key from UUID and password
            passphrase = self._get_crypt_key()  # This is the 16-char string from MD5 hash

            # 确保输入是字节类型
            if isinstance(encrypted, str):
                encrypted = encrypted.encode("utf-8")
            # Base64 解码
            encrypted = base64.b64decode(encrypted)
            # 检查前8字节是否为 "Salted__"
            assert encrypted.startswith(b"Salted__"), "Invalid encrypted data format"
            # 提取盐值
            salt = encrypted[8:16]
            # 通过密码短语和盐值生成密钥和IV
            key_iv = self.bytes_to_key(passphrase, salt, 32 + 16)
            key = key_iv[:32]
            iv = key_iv[32:]
            # 创建AES解密器（CBC模式）
            aes = AES.new(key, AES.MODE_CBC, iv)
            # 解密加密部分
            decrypted_padded = aes.decrypt(encrypted[16:])
            # 移除PKCS#7填充
            padding_length = decrypted_padded[-1]
            if isinstance(padding_length, str):
                padding_length = ord(padding_length)
            decrypted = decrypted_padded[:-padding_length]
            return decrypted
        except Exception as e:
            print(f"Decryption error: {e}")
            return None

    def _evp_kdf(self, passphrase: bytes, salt: bytes, key_len: int = 16, iv_len: int = 16) -> Tuple[bytes, bytes]:
        """
        Equivalent to CryptoJS's EvpKDF (OpenSSL's EVP_BytesToKey with MD5)

        Args:
            passphrase: The passphrase bytes
            salt: Salt bytes (8 bytes)
            key_len: Desired key length (default 16 for AES-128)
            iv_len: Desired IV length (default 16)

        Returns:
            Tuple of (key, iv)
        """
        m = []
        i = 0
        while len(b''.join(m)) < (key_len + iv_len):
            if i == 0:
                data = passphrase + salt
            else:
                data = m[i - 1] + passphrase + salt

            md5_hash = hashlib.md5(data).digest()
            m.append(md5_hash)
            i += 1

        ms = b''.join(m)
        return ms[:key_len], ms[key_len:key_len + iv_len]

    def fetch_cookies(self) -> Optional[Dict]:
        """
        Fetch and decrypt cookies from CookieCloud server

        Returns:
            Dictionary containing cookies data or None if fetch fails
        """
        if not self.is_enabled():
            print("CookieCloud is not configured")
            return None

        try:
            # Construct API URL
            url = f"{self.server_url}/get/{self.uuid_key}"

            # Make request
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            # Parse response
            data = response.json()

            if not data.get('encrypted'):
                print("No encrypted data in response")
                return None

            # Decrypt the data
            decrypted_json = self._decrypt_data(data['encrypted'])

            if not decrypted_json:
                print("Failed to decrypt cookie data")
                return None

            # Parse decrypted JSON
            cookie_data = json.loads(decrypted_json)

            return cookie_data

        except requests.exceptions.RequestException as e:
            print(f"Failed to fetch from CookieCloud: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"Failed to parse cookie data: {e}")
            return None

    def get_cookies_for_domain(self, domain: str = 'youtube.com') -> Optional[List[Dict]]:
        """
        Get cookies for a specific domain

        Args:
            domain: Domain to get cookies for

        Returns:
            List of cookie dictionaries or None if not available
        """
        cookie_data = self.fetch_cookies()

        if not cookie_data:
            return None

        all_cookies = cookie_data.get('cookie_data')
        if not all_cookies:
            return None

        domain_cookies = []

        # Check if it's the expected dictionary format
        if isinstance(all_cookies, dict):
            # Iterate through all domains in the cookie data
            for sync_domain, cookies_list in all_cookies.items():
                # Check if this domain matches what we're looking for
                # Match exact domain or subdomain
                if domain in sync_domain or sync_domain.endswith(f'.{domain}'):
                    if isinstance(cookies_list, list):
                        domain_cookies.extend(cookies_list)
                # Also check for YouTube-specific domains
                elif domain == 'youtube.com' and ('youtube' in sync_domain.lower() or 'google' in sync_domain.lower()):
                    if isinstance(cookies_list, list):
                        domain_cookies.extend(cookies_list)

        return domain_cookies if domain_cookies else None

    def save_cookies_to_file(self, output_file: str, domain: str = 'youtube.com') -> bool:
        """
        Save cookies for a domain to a Netscape format cookie file

        Args:
            output_file: Path to save the cookie file
            domain: Domain to filter cookies for

        Returns:
            True if successful, False otherwise
        """
        cookies = self.get_cookies_for_domain(domain)

        if not cookies:
            print(f"No cookies found for domain: {domain}")
            return False

        try:
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_file) or '.', exist_ok=True)

            with open(output_file, 'w') as f:
                # Write Netscape cookie file header
                f.write("# Netscape HTTP Cookie File\n")
                f.write("# This file was generated by CookieCloud sync\n")
                f.write("# http://curl.haxx.se/rfc/cookie_spec.html\n\n")

                # Write each cookie in Netscape format
                for cookie in cookies:
                    domain_str = cookie.get('domain', '')
                    if domain_str.startswith('.'):
                        include_subdomains = 'TRUE'
                    else:
                        include_subdomains = 'FALSE'
                        domain_str = '.' + domain_str if not domain_str.startswith('.') else domain_str

                    path = cookie.get('path', '/')
                    secure = 'TRUE' if cookie.get('secure', False) else 'FALSE'
                    expires = str(int(cookie.get('expirationDate', 0)))
                    name = cookie.get('name', '')
                    value = cookie.get('value', '')

                    # Format: domain include_subdomains path secure expires name value
                    line = f"{domain_str}\t{include_subdomains}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n"
                    f.write(line)

            print(f"Successfully saved {len(cookies)} cookies to {output_file}")
            return True

        except Exception as e:
            print(f"Failed to save cookies to file: {e}")
            return False

    def sync_cookies(self, output_dir: str = None) -> Tuple[bool, str]:
        """
        Sync cookies from CookieCloud and save to local file

        Args:
            output_dir: Directory to save cookies (default: config directory)

        Returns:
            Tuple of (success, message)
        """
        if not self.is_enabled():
            return False, "CookieCloud is not configured"

        # Determine output path
        if output_dir is None:
            if os.path.exists("/app"):
                output_dir = "/app/config"
            else:
                base_dir = os.path.dirname(os.path.dirname(__file__))
                output_dir = os.path.join(base_dir, "config")

        output_file = os.path.join(output_dir, "cookies.txt")

        # Fetch and save cookies
        if self.save_cookies_to_file(output_file, 'youtube.com'):
            # Get cookie count for status message
            cookies = self.get_cookies_for_domain('youtube.com')
            cookie_count = len(cookies) if cookies else 0

            # Add timestamp to track last sync
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            return True, f"Successfully synced {cookie_count} cookies from CookieCloud at {timestamp}"
        else:
            return False, "Failed to sync cookies from CookieCloud"

    def test_connection(self) -> Tuple[bool, str]:
        """
        Test connection to CookieCloud server

        Returns:
            Tuple of (success, message)
        """
        if not self.is_enabled():
            return False, "CookieCloud is not configured"

        try:
            # First test server connectivity
            url = f"{self.server_url}/get/{self.uuid_key}"
            response = requests.get(url, timeout=10)

            if response.status_code != 200:
                return False, f"Server returned status code: {response.status_code}"

            data = response.json()
            if not data.get('encrypted'):
                return False, "Server response does not contain encrypted data"

            # Try to decrypt
            decrypted = self._decrypt_data(data['encrypted'])

            if decrypted:
                try:
                    cookie_data = json.loads(decrypted)
                    # Count cookies - check if data has 'cookie_data' wrapper
                    total_cookies = 0
                    total_domains = 0

                    # Check for cookie_data wrapper (same structure as fetch_cookies expects)
                    if 'cookie_data' in cookie_data and isinstance(cookie_data['cookie_data'], dict):
                        cookies_dict = cookie_data['cookie_data']
                        for domain, cookies in cookies_dict.items():
                            if isinstance(cookies, list):
                                total_cookies += len(cookies)
                                total_domains += 1
                    elif isinstance(cookie_data, dict):
                        # Direct dictionary format
                        for domain, cookies in cookie_data.items():
                            if isinstance(cookies, list):
                                total_cookies += len(cookies)
                                total_domains += 1

                    return True, f"Successfully connected to CookieCloud! Found {total_cookies} cookies from {total_domains} domains."
                except json.JSONDecodeError as e:
                    print(f"JSON decode error: {e}")
                    print(f"Decrypted data preview: {decrypted[:200]}...")
                    return False, "Decrypted data is not valid JSON"
            else:
                return False, "Connected to server but failed to decrypt data. Please check your password."

        except requests.exceptions.RequestException as e:
            return False, f"Connection failed: {str(e)}"
        except Exception as e:
            return False, f"Error: {str(e)}"

    @staticmethod
    def bytes_to_key(data: bytes, salt: bytes, output=48) -> bytes:
        """
        生成加密/解密所需的密钥和初始化向量 (IV)
        """
        # extended from https://gist.github.com/gsakkis/4546068
        assert len(salt) == 8, len(salt)
        data += salt
        key = md5(data).digest()
        final_key = key
        while len(final_key) < output:
            key = md5(key + data).digest()
            final_key += key
        return final_key[:output]
"""Tuya Cloud API for Proscenic vacuum credential retrieval."""
from __future__ import annotations

import base64
import functools
import hashlib
import hmac
import json
import logging
import time
from typing import Any

import requests

from .const import PROSCENIC_CLIENT_ID, PROSCENIC_SECRET

_LOGGER = logging.getLogger(__name__)

_TUYA_USER_AGENT = "TY-UA=APP/Android/1.1.6/SDK/null"
_TUYA_API_VERSION = "1.0"


class TuyaCloudApiError(Exception):
    """Base exception for Tuya Cloud API errors."""


class InvalidUserSession(TuyaCloudApiError):
    """Invalid user session error."""


class InvalidAuthentication(TuyaCloudApiError):
    """Invalid authentication error."""


class TuyaCloudApi:
    """Tuya Cloud API client for Proscenic devices."""

    def __init__(
        self,
        region: str,
        username: str,
        password: str,
    ) -> None:
        """Initialize the Tuya Cloud API client.

        Args:
            region: The Tuya region (eu, us, cn, in)
            username: The Proscenic app account email
            password: The Proscenic app password
        """
        self._endpoint = f"https://a1.tuya{region}.com/api.json"
        self._username = username
        self._password = password
        self._country_code = ""
        self._client_id = PROSCENIC_CLIENT_ID
        self._secret = PROSCENIC_SECRET
        self._session = requests.Session()
        self._sid: str | None = None

    def _api(
        self,
        action: str,
        payload: dict[str, Any] | None = None,
        extra_params: dict[str, str] | None = None,
        requires_sid: bool = True,
    ) -> Any:
        """Make an API request to Tuya Cloud.

        Args:
            action: The API action to call
            payload: Optional payload data
            extra_params: Optional extra URL parameters
            requires_sid: Whether a session ID is required

        Returns:
            The API response result

        Raises:
            InvalidUserSession: If the session is invalid
            InvalidAuthentication: If authentication fails
            TuyaCloudApiError: For other API errors
        """
        headers = {"User-Agent": _TUYA_USER_AGENT}

        if extra_params is None:
            extra_params = {}

        params = {
            "a": action,
            "clientId": self._client_id,
            "v": _TUYA_API_VERSION,
            "time": str(int(time.time())),
            **extra_params,
        }

        if requires_sid:
            if self._sid is None:
                raise TuyaCloudApiError("You need to login first.")
            params["sid"] = self._sid

        data: dict[str, str] = {}
        if payload is not None:
            data["postData"] = json.dumps(payload, separators=(",", ":"))

        params["sign"] = self._sign({**params, **data})

        _LOGGER.debug("Request: params %s", params)

        response = self._session.post(
            self._endpoint,
            params=params,
            data=data,
            headers=headers,
            timeout=30,
        )
        result = self._handle(response.json())

        _LOGGER.debug("Result: %s", result)

        return result

    def _sign(self, data: dict[str, str]) -> str:
        """Sign the API request.

        Args:
            data: The data to sign

        Returns:
            The HMAC-SHA256 signature
        """
        keys_not_to_sign = ["gid"]
        sorted_keys = sorted(data.keys())

        str_to_sign = ""
        for key in sorted_keys:
            if key in keys_not_to_sign:
                continue
            if key == "postData":
                if str_to_sign:
                    str_to_sign += "||"
                str_to_sign += key + "=" + self._mobile_hash(data[key])
            else:
                if str_to_sign:
                    str_to_sign += "||"
                str_to_sign += key + "=" + data[key]

        return hmac.new(
            bytes(self._secret, "utf-8"),
            msg=bytes(str_to_sign, "utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _mobile_hash(data: str) -> str:
        """Generate mobile hash for payload signing.

        Args:
            data: The data to hash

        Returns:
            The reordered MD5 hash
        """
        prehash = hashlib.md5(bytes(data, "utf-8")).hexdigest()
        return prehash[8:16] + prehash[0:8] + prehash[24:32] + prehash[16:24]

    @staticmethod
    def _handle(result: dict[str, Any]) -> Any:
        """Handle API response.

        Args:
            result: The API response

        Returns:
            The result data

        Raises:
            InvalidUserSession: If the session is invalid
            InvalidAuthentication: If authentication fails
            TuyaCloudApiError: For other API errors
        """
        if result.get("success"):
            return result.get("result")
        error_code = result.get("errorCode", "")
        error_msg = result.get("errorMsg", "Unknown error")
        if error_code == "USER_SESSION_INVALID":
            raise InvalidUserSession(error_msg)
        if error_code == "USER_PASSWD_WRONG":
            raise InvalidAuthentication(error_msg)
        raise TuyaCloudApiError(f"{error_msg} ({error_code})")

    @staticmethod
    def _plain_rsa_encrypt(modulus: int, exponent: int, message: bytes) -> bytes:
        """Encrypt message using plain (textbook) RSA.

        Args:
            modulus: RSA modulus
            exponent: RSA exponent
            message: Message to encrypt

        Returns:
            Encrypted message bytes
        """
        message_int = int.from_bytes(message, "big")
        enc_message_int = pow(message_int, exponent, modulus)
        return enc_message_int.to_bytes(256, "big")

    def _enc_password(self, modulus: str, exponent: str, password: str) -> str:
        """Encrypt password for login.

        Args:
            modulus: RSA modulus from token
            exponent: RSA exponent from token
            password: Plain text password

        Returns:
            Encrypted password as hex string
        """
        passwd_hash = hashlib.md5(password.encode("utf8")).hexdigest().encode("utf8")
        return self._plain_rsa_encrypt(
            int(modulus), int(exponent), passwd_hash
        ).hex()

    async def async_login(self) -> None:
        """Login to Tuya Cloud (async wrapper).

        This is a blocking call wrapped for async context.
        Should be called with async_add_executor_job.
        """
        self.login()

    def login(self) -> None:
        """Login to Tuya Cloud.

        Raises:
            InvalidAuthentication: If credentials are invalid
            TuyaCloudApiError: For other API errors
        """
        payload = {"countryCode": self._country_code, "email": self._username}
        token_info = self._api(
            "tuya.m.user.email.token.create", payload, requires_sid=False
        )

        payload = {
            "countryCode": self._country_code,
            "email": self._username,
            "ifencrypt": 1,
            "options": '{"group": 1}',
            "passwd": self._enc_password(
                token_info["publicKey"], token_info["exponent"], self._password
            ),
            "token": token_info["token"],
        }
        login_info = self._api(
            "tuya.m.user.email.password.login", payload, requires_sid=False
        )

        self._sid = login_info["sid"]
        _LOGGER.debug("Login successful, got session ID")

    def list_devices(self) -> list[dict[str, Any]]:
        """List all devices from Tuya Cloud.

        Returns:
            List of device dictionaries with id, name, local_key, ip (if available)

        Raises:
            TuyaCloudApiError: If the API call fails
        """
        devices: list[dict[str, Any]] = []

        # Fetch all groups (homes)
        for group in self._api("tuya.m.location.list"):
            # Fetch devices for each group
            group_devices = self._api(
                "tuya.m.my.group.device.list",
                extra_params={"gid": group["groupId"]},
            )
            for dev in group_devices:
                device_info = self._map_device(dev)
                devices.append(device_info)

        return devices

    def _map_device(self, dev: dict[str, Any]) -> dict[str, Any]:
        """Map raw device data to integration format.

        Args:
            dev: Raw device data from API

        Returns:
            Mapped device dictionary
        """
        device = {
            "id": dev["devId"],
            "name": dev["name"],
            "local_key": dev["localKey"],
            "category": dev.get("category", ""),
            "product_id": dev.get("productId", ""),
            "mac": self._format_mac(dev.get("mac", "")),
            "ip": None,
        }

        # Try to extract IP from DPS 34 (base64-encoded device info)
        dps = dev.get("dps", {})
        if "34" in dps:
            try:
                device_info_raw = dps["34"]
                device_info = json.loads(base64.b64decode(device_info_raw))
                device["ip"] = device_info.get("IP")
                dps_mac = device_info.get("Mac") or device_info.get("MAC")
                if dps_mac:
                    device["mac"] = self._format_mac(
                        str(dps_mac).replace(":", "").replace("-", "")
                    )
                device["serial_number"] = device_info.get("Device_SN")
                device["firmware_version"] = device_info.get("Firmware_Version")
                _LOGGER.debug("Extracted IP %s from DPS 34", device["ip"])
            except (json.JSONDecodeError, ValueError, TypeError) as err:
                _LOGGER.debug("Could not decode DPS 34: %s", err)

        return device

    @staticmethod
    def _format_mac(mac: str) -> str:
        """Format MAC address with colons.

        Args:
            mac: MAC address without separators

        Returns:
            MAC address with colon separators
        """
        if not mac or ":" in mac:
            return mac
        return ":".join(mac[i : i + 2] for i in range(0, len(mac), 2))


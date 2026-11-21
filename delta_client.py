import time
import json
import hmac
import hashlib
import logging
from typing import Optional, Dict, Any, List
import requests

logger = logging.getLogger("delta_client")

class DeltaExchangeClient:
    """
    Client for Delta Exchange REST API v2 (Demo / Testnet / Live).
    Strictly defaults to Demo/Testnet base URLs.
    """
    def __init__(self, api_key: str, api_secret: str, base_url: str):
        self.api_key = api_key.strip()
        self.api_secret = api_secret.strip()
        self.base_url = base_url.rstrip("/")

    def _generate_signature(self, method: str, path: str, query_string: str = "", payload: str = "") -> tuple[str, str]:
        timestamp = str(int(time.time()))
        signature_data = method.upper() + timestamp + path + query_string + payload
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            signature_data.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return signature, timestamp

    def _request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        path = endpoint
        query_string = ""
        if params:
            import urllib.parse
            query_string = "?" + urllib.parse.urlencode(params)
            path_with_query = path + query_string
        else:
            path_with_query = path

        payload_str = ""
        if data is not None:
            payload_str = json.dumps(data, separators=(',', ':'))

        signature, timestamp = self._generate_signature(method, path, query_string, payload_str)

        headers = {
            "api-key": self.api_key,
            "timestamp": timestamp,
            "signature": signature,
            "Content-Type": "application/json"
        }

        url = self.base_url + path_with_query
        logger.info(f"Sending {method} request to {url}")

        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            data=payload_str if data is not None else None,
            timeout=10
        )

        try:
            res_json = response.json()
        except Exception:
            res_json = {"raw_text": response.text, "status_code": response.status_code}

        if not response.ok:
            logger.error(f"Delta API error: HTTP {response.status_code} - {res_json}")
            raise RuntimeError(f"Delta API Error: HTTP {response.status_code} - {res_json}")

        return res_json

    def get_wallet_balances(self) -> Dict[str, Any]:
        """Fetch wallet balances to verify authentication."""
        return self._request("GET", "/v2/wallet/balances")

    def get_positions(self) -> List[Dict[str, Any]]:
        """Fetch all current open margined positions."""
        res = self._request("GET", "/v2/positions/margined")
        if isinstance(res, dict) and "result" in res:
            result = res["result"]
            return result if isinstance(result, list) else [result]
        return res if isinstance(res, list) else []

    def get_position_for_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Return the current open position for a given symbol, if any."""
        positions = self.get_positions()
        for pos in positions:
            pos_symbol = pos.get("product_symbol") or pos.get("product", {}).get("symbol")
            if pos_symbol == symbol:
                size = float(pos.get("size", 0))
                if size != 0:
                    return pos
        return None

    def close_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Close existing position for the symbol by issuing a reduce_only market order.
        """
        pos = self.get_position_for_symbol(symbol)
        if not pos:
            logger.info(f"No active position to close for {symbol}.")
            return None

        current_size = float(pos.get("size", 0))
        if current_size == 0:
            return None

        # If current_size > 0, we are LONG, so sell to close.
        # If current_size < 0, we are SHORT, so buy to close.
        close_side = "sell" if current_size > 0 else "buy"
        contracts_to_close = int(abs(current_size))

        logger.info(f"Closing position of {current_size} contracts on {symbol} via {close_side.upper()} order.")
        return self.place_order(
            symbol=symbol,
            size=contracts_to_close,
            side=close_side,
            order_type="market_order",
            reduce_only=True
        )

    def place_order(
        self,
        symbol: str,
        size: int,
        side: str,
        order_type: str = "market_order",
        reduce_only: bool = False
    ) -> Dict[str, Any]:
        """
        Place a new order on Delta Exchange.
        """
        payload = {
            "product_symbol": symbol,
            "size": int(size),
            "side": side.lower(),
            "order_type": order_type
        }
        if reduce_only:
            payload["reduce_only"] = True

        logger.info(f"Placing order: {payload}")
        return self._request("POST", "/v2/orders", data=payload)

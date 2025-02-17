# examples/stock_core.py

# pylint: disable=no-member

"""
Stock monitoring core classes and logic.

This module provides a simulated stock market data generator (`StockService`),
a processor for handling price updates and alerts (`StockProcessor`), and a
view-model class (`StockViewModel`) that can be connected to various UI or CLI
front-ends.

Usage:
  1. Instantiate `StockService` to generate price data.
  2. Instantiate `StockProcessor` to handle alert conditions and further processing.
  3. Instantiate `StockViewModel` to manage UI-related state or to relay
     processed data to the presentation layer.
  4. Connect the emitters/listeners between these objects to build a reactive flow
     that updates real-time stock information and triggers alerts when conditions are met.
"""

import asyncio
from dataclasses import dataclass
import random
import threading
import time
from typing import Dict, Optional
from pynnex import with_emitters, emitter, listener, with_worker, nx_property
from utils import logger_setup

logger = logger_setup(__name__)


@dataclass
class StockPrice:
    """
    A dataclass to represent stock price data.

    Attributes
    ----------
    symbol : str
        The stock ticker symbol (e.g., 'AAPL', 'GOOGL', etc.).
    price : float
        The current price of the stock.
    change : float
        The percentage change compared to the previous price (in %).
    timestamp : float
        A UNIX timestamp representing the moment of this price capture.
    """

    symbol: str
    price: float
    change: float
    timestamp: float


@with_worker
class StockService:
    """
    Virtual stock price data generator and distributor.

    This class simulates real-time stock price updates by randomly fluctuating
    the prices of a predefined list of stock symbols. It runs in its own worker
    thread, driven by an asyncio event loop.

    Attributes
    ----------
    prices : Dict[str, float]
        A mapping of stock symbol to current price.
    last_prices : Dict[str, float]
        A mapping of stock symbol to the previous price (for calculating percentage change).
    _running : bool
        Indicates whether the price generation loop is active.
    _update_task : asyncio.Task, optional
        The asyncio task that periodically updates prices.

    Emitters
    -------
    price_updated
        Emitted every time a single stock price is updated. Receives a `StockPrice` object.

    Lifecycle
    ---------
    - `on_started()` is called after the worker thread starts and before `update_prices()`.
    - `on_stopped()` is called when the worker thread is shutting down.
    """

    def __init__(self):
        logger.debug("[StockService][__init__] started")

        self.prices: Dict[str, float] = {
            "AAPL": 180.0,  # Apple Inc.
            "GOOGL": 140.0,  # Alphabet Inc.
            "MSFT": 370.0,  # Microsoft Corporation
            "AMZN": 145.0,  # Amazon.com Inc.
            "TSLA": 240.0,  # Tesla Inc.
        }
        self._desc_lock = threading.RLock()
        self._descriptions = {
            "AAPL": "Apple Inc.",
            "GOOGL": "Alphabet Inc.",
            "MSFT": "Microsoft Corporation",
            "AMZN": "Amazon.com Inc.",
            "TSLA": "Tesla Inc.",
        }
        self.last_prices = self.prices.copy()
        self._running = False
        self._update_task = None
        self.started.connect(self.on_started)
        self.stopped.connect(self.on_stopped)
        super().__init__()

    @nx_property
    def descriptions(self) -> Dict[str, str]:
        """
        Get the stock descriptions.

        Returns
        -------
        Dict[str, str]
            A dictionary mapping stock symbols to their descriptive names (e.g. "AAPL": "Apple Inc.").
        """

        with self._desc_lock:
            return dict(self._descriptions)

    @emitter
    def price_updated(self):
        """Emitter emitted when stock price is updated"""

    async def on_started(self):
        """
        Called automatically when the worker thread is started.

        Prepares and launches the asynchronous price update loop.
        """

        logger.info("[StockService][on_started] started")
        self._running = True
        self.queue_task(self.update_prices())

    async def on_stopped(self):
        """
        Called automatically when the worker thread is stopped.

        Performs cleanup and cancellation of any active update tasks.
        """

        logger.info("[StockService][on_stopped] stopped")
        self._running = False

    async def update_prices(self):
        """
        Periodically update stock prices in a loop.

        Randomly perturbs the prices within a small percentage range, then
        emits `price_updated` with a new `StockPrice` object for each stock.
        """

        while self._running:
            for symbol, price in self.prices.items():
                self.last_prices[symbol] = price
                change_pct = random.uniform(-0.01, 0.01)
                self.prices[symbol] *= 1 + change_pct

                price_data = StockPrice(
                    symbol=symbol,
                    price=self.prices[symbol],
                    change=((self.prices[symbol] / self.last_prices[symbol]) - 1) * 100,
                    timestamp=time.time(),
                )

                logger.debug(
                    "[StockService][update_prices] price_data: %s",
                    price_data,
                )
                self.price_updated.emit(price_data)

            logger.debug(
                "[StockService][update_prices] prices updated price_data: %s",
                price_data,
            )

            await asyncio.sleep(1)


@with_emitters
class StockViewModel:
    """
    UI state manager for stock prices and alerts.

    This class holds the current stock prices and user-defined alert settings,
    and provides emitters/listeners for updating UI layers or notifying other components
    about price changes and alerts.

    Attributes
    ----------
    current_prices : Dict[str, StockPrice]
        The latest known stock prices.
    alerts : list[tuple[str, str, float]]
        A list of triggered alerts in the form (stock_symbol, alert_type, current_price).
    alert_settings : Dict[str, tuple[Optional[float], Optional[float]]]
        A mapping of stock_symbol to (lower_alert_threshold, upper_alert_threshold).
    """

    def __init__(self):
        self.current_prices: Dict[str, StockPrice] = {}
        self.alerts: list[tuple[str, str, float]] = []
        self.alert_settings: Dict[str, tuple[Optional[float], Optional[float]]] = {}

    @emitter
    def price_updated(self):
        """
        Emitter emitted when stock prices are updated.

        Receives a stock price data.
        """

    @emitter
    def alert_added(self):
        """
        Emitter emitted when a new alert is added.

        Receives (symbol, alert_type, current_price).
        """

    @emitter
    def set_alert(self):
        """
        Emitter emitted when user requests to set an alert.

        Receives (symbol, lower, upper).
        """

    @emitter
    def remove_alert(self):
        """
        Emitter emitted when user requests to remove an alert.

        Receives (symbol).
        """

    @listener
    def on_price_processed(self, price_data: StockPrice):
        """
        Receive processed stock price data from StockProcessor.

        Updates the local `current_prices` and notifies listeners that prices
        have changed.
        """

        logger.debug("[StockViewModel][on_price_processed] price_data: %s", price_data)
        self.current_prices[price_data.symbol] = price_data
        self.price_updated.emit(price_data)

    @listener
    def on_alert_triggered(self, symbol: str, alert_type: str, price: float):
        """
        Receive an alert trigger from StockProcessor.

        Appends the alert to `alerts` and emits `alert_added`.
        """

        self.alerts.append((symbol, alert_type, price))
        self.alert_added.emit(symbol, alert_type, price)

    @listener
    def on_alert_settings_changed(
        self, symbol: str, lower: Optional[float], upper: Optional[float]
    ):
        """
        Receive alert settings change notification from StockProcessor.

        If both lower and upper are None, remove any alert setting for that symbol.
        Otherwise, update or create a new alert setting for that symbol.
        """

        if lower is None and upper is None:
            self.alert_settings.pop(symbol, None)
        else:
            self.alert_settings[symbol] = (lower, upper)


@with_worker
class StockProcessor:
    """
    Stock price data processor and alert condition checker.

    This class runs in a separate worker thread, receiving price updates from
    `StockService` and determining whether alerts should be triggered based on
    user-defined thresholds. If an alert condition is met, an `alert_triggered`
    emitter is emitted.

    Attributes
    ----------
    price_alerts : Dict[str, tuple[Optional[float], Optional[float]]]
        A mapping of stock_symbol to (lower_alert_threshold, upper_alert_threshold).

    Emitters
    -------
    price_processed
        Emitted after processing a new price data and optionally triggering alerts.
    alert_triggered
        Emitted if a stock price crosses its set threshold.
    alert_settings_changed
        Emitted whenever a stock's alert thresholds are changed.

    Lifecycle
    ---------
    - `on_started()` is invoked when the worker is fully initialized.
    - `on_stopped()` is called upon shutdown/cleanup.
    """

    def __init__(self):
        logger.debug("[StockProcessor][__init__] started")
        self.price_alerts: Dict[str, tuple[Optional[float], Optional[float]]] = {}
        self.started.connect(self.on_started)
        self.stopped.connect(self.on_stopped)
        super().__init__()

    async def on_started(self):
        """Worker initialization"""

        logger.info("[StockProcessor][on_started] started")

    async def on_stopped(self):
        """Worker shutdown"""

        logger.info("[StockProcessor][on_stopped] stopped")

    @emitter
    def price_processed(self):
        """Emitter emitted when stock price is processed"""

    @emitter
    def alert_triggered(self):
        """Emitter emitted when price alert condition is met"""

    @emitter
    def alert_settings_changed(self):
        """Emitter emitted when price alert settings are changed"""

    @listener
    def on_set_price_alert(
        self, symbol: str, lower: Optional[float], upper: Optional[float]
    ):
        """
        Receive a price alert setting request from the main thread or UI.

        Updates (or creates) a new alert threshold entry, then emits `alert_settings_changed`.
        """

        self.price_alerts[symbol] = (lower, upper)
        self.alert_settings_changed.emit(symbol, lower, upper)

    @listener
    def on_remove_price_alert(self, symbol: str):
        """
        Receive a price alert removal request from the main thread or UI.

        Deletes the alert thresholds for a given symbol, then emits `alert_settings_changed`.
        """

        if symbol in self.price_alerts:
            del self.price_alerts[symbol]
            self.alert_settings_changed.emit(symbol, None, None)

    @listener
    def on_price_updated(self, price_data: StockPrice):
        """
        Receive stock price updates from the `StockService`.

        Delegates the actual processing to `process_price` via the task queue to
        avoid blocking other operations.
        """

        logger.debug("[StockProcessor][on_price_updated] price_data: %s", price_data)

        try:
            self.queue_task(self.process_price(price_data))
        except Exception as e:
            logger.error("Error in on_price_updated: %s", e, exc_info=True)

    async def process_price(self, price_data: StockPrice):
        """
        Process the updated price data.

        Checks if the stock meets the alert conditions (e.g., crossing upper/lower limits),
        emits `alert_triggered` as needed, then emits `price_processed`.
        """

        # logger.debug("[StockProcessor][process_price] price_data: %s", price_data)

        try:
            if price_data.symbol in self.price_alerts:
                logger.debug(
                    "[process_price] Process price event loop: %s",
                    asyncio.get_running_loop(),
                )

            if price_data.symbol in self.price_alerts:
                lower, upper = self.price_alerts[price_data.symbol]

                if lower and price_data.price <= lower:
                    self.alert_triggered.emit(price_data.symbol, "LOW", price_data.price)

                if upper and price_data.price >= upper:
                    self.alert_triggered.emit(price_data.symbol, "HIGH", price_data.price)

            self.price_processed.emit(price_data)
        except Exception as e:
            logger.error("[StockProcessor][process_price] error: %s", e)
            raise

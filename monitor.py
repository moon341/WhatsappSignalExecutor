"""
WhatsApp Web Monitor - Monitors a WhatsApp group chat for new messages.

Uses Selenium with a dedicated Chrome profile (not the user's main browser).
On first run, the user scans a QR code to log into WhatsApp Web. The session
persists in the Chrome profile for subsequent runs.

Requirements:
    pip install selenium webdriver-manager

Usage:
    python monitor.py

Configuration: Edit config.json (copy from config.example.json)
"""

import json
import time
import logging
import os
import sys
import hashlib
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException,
)

from parser import SignalParser
from signal_writer import SignalWriter

# Optional AI parser support. If an AI parser implementation is not available
# the monitor will fall back to the regex `SignalParser` above.
try:
    from ai_parser import AISignalParser  # optional dependency
    AI_AVAILABLE = True
except Exception:
    AISignalParser = None
    AI_AVAILABLE = False

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(config):
    log_config = config.get("logging", {})
    level = getattr(logging, log_config.get("level", "INFO").upper(), logging.INFO)
    log_file = log_config.get("log_file", "signal_bridge.log")

    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    from logging.handlers import RotatingFileHandler
    max_bytes = log_config.get("max_log_size_mb", 10) * 1024 * 1024
    backup_count = log_config.get("backup_count", 3)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# WhatsApp Web Monitor
# ---------------------------------------------------------------------------

class WhatsAppMonitor:
    """
    Monitors a WhatsApp group chat for new messages using WhatsApp Web.

    Uses data-testid attributes (more stable than class names) with
    multiple fallback selectors for compatibility across WhatsApp versions.
    """

    WHATSAPP_WEB_URL = "https://web.whatsapp.com/"

    # Multiple selectors per element type for resilience against DOM changes.
    # Listed in priority order — first match wins.
    LOGIN_INDICATORS = [
        # Chat list container (logged in)
        '[data-testid="chat-list"]',
        'div[data-testid="cell-frame-container"]',
        '#pane-side',
        'div[role="grid"]',
        # Search box (logged in)
        '[data-testid="chat-list-search"]',
        'div[contenteditable="true"][data-tab="3"]',
        # Message input (logged in, chat open)
        'div[contenteditable="true"][data-tab="10"]',
        'div[contenteditable="true"][data-tab="1"]',
    ]

    QR_INDICATORS = [
        # QR code (not logged in)
        'canvas',
        '[data-testid="qrcode"]',
        'div[role="img"]',
        'img[alt="QR code"]',
        # Phone number linking (alternative login)
        '[data-testid="link-with-phone-number"]',
        'div[role="button"]',
    ]

    CHAT_ENTRY_SELECTORS = [
        '[data-testid="cell-frame-container"]',
        'div[role="listitem"]',
        'div[class*="chat"]',
    ]

    CHAT_TITLE_SELECTORS = [
        'span[title]',
        'span[dir="auto"][title]',
    ]

    MESSAGE_SELECTORS = [
        'div[data-testid="msg-container"]',
        'div.message-in',
        'div.message-out',
        'div[role="row"]',
        'div[data-id^="true_"]',
        'div[class*="message"]',
    ]

    MESSAGE_TEXT_SELECTORS = [
        'span.selectable-text.copyable-text',
        'span.selectable-text',
        'span[dir="ltr"]',
        'span[dir="auto"]',
    ]

    SEARCH_BOX_SELECTORS = [
        '[data-testid="chat-list-search"]',
        'div[contenteditable="true"][data-tab="3"]',
        'div[contenteditable="true"][data-tab="1"]',
        'input[type="text"]',
    ]

    def __init__(self, config: dict):
        self.config = config
        wa_config = config["whatsapp"]
        self.group_name = wa_config["group_name"]
        self.chrome_profile_path = wa_config["chrome_profile_path"]
        self.poll_interval = wa_config.get("poll_interval_seconds", 2)
        self.headless = wa_config.get("headless", False)
        self.max_messages = wa_config.get("max_messages_per_scan", 20)

        sf_config = config["signal_file"]
        self.signal_output_path = sf_config["output_path"]

        p_config = config.get("parser", {})
        self.parser_enabled = p_config.get("enabled", True)

        regex_parser = SignalParser(
            symbol_aliases=p_config.get("symbol_aliases"),
            default_symbol=p_config.get("default_symbol", "XAUUSD"),
            min_confidence=p_config.get("min_confidence", 0.4),
            pip_value=p_config.get("pip_value", 1.0),
        )

        # AI parser (if configured and parsing is enabled)
        ai_config = config.get("ai_parser", {})
        if self.parser_enabled:
            if ai_config.get("enabled", False) and AI_AVAILABLE and ai_config.get("api_key", "") not in ("", "YOUR_GROQ_API_KEY_HERE"):
                self.parser = AISignalParser(
                    api_key=ai_config.get("api_key", "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"),
                    model=ai_config.get("model", "llama-3.3-70b-versatile"),
                    base_url=ai_config.get("base_url", "https://api.groq.com/openai/v1"),
                    fallback_parser=regex_parser,
                )
                self.parser_source = "AI"
                logger.info("Using AI-powered parser (with regex fallback)")
            else:
                self.parser = regex_parser
                self.parser_source = "regex"
                if ai_config.get("enabled", False) and not AI_AVAILABLE:
                    logger.warning("AI parser enabled in config, but the optional ai_parser module is not installed. Using regex parser.")
                    logger.warning("Install the AI parser package or remove ai_parser.enabled from config.")
                elif ai_config.get("enabled", False) and ai_config.get("api_key", "") in ("", "YOUR_GROQ_API_KEY_HERE"):
                    logger.warning("AI parser enabled but no valid API key provided. Using regex parser.")
                    logger.warning("Get a free API key at https://console.groq.com/keys")
                else:
                    logger.info("Using regex parser (set ai_parser.enabled=true in config to use AI)")
        else:
            self.parser = None
            self.parser_source = "disabled"
            logger.info("Parser is disabled. Incoming messages will not be parsed.")

        self.writer = SignalWriter(
            output_path=self.signal_output_path,
            max_signals=sf_config.get("max_signals_in_file", 50),
            temp_suffix=sf_config.get("temp_suffix", ".tmp"),
            encoding=sf_config.get("encoding", "utf-8"),
        )

        self.driver = None
        self._seen_message_hashes = set()
        self._logged_in = False

    # ------------------------------------------------------------------
    # Chrome / Selenium setup
    # ------------------------------------------------------------------

    def _create_driver(self) -> webdriver.Chrome:
        """Create Chrome driver with a dedicated persistent profile."""
        options = Options()

        options.add_argument(f"--user-data-dir={self.chrome_profile_path}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-gpu")
        options.add_argument("--lang=en-US")
        # Stability flags to prevent Chrome from crashing
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-features=RendererCodeIntegrity")
        options.add_argument("--disable-software-rasterizer")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        if self.headless:
            options.add_argument("--headless=new")

        # Find the chromedriver
        chromedriver_path = None
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            chromedriver_path = ChromeDriverManager().install()
            logger.info(f"Using chromedriver: {chromedriver_path}")
        except Exception as e:
            logger.warning(f"webdriver-manager failed: {e}")

        # Try to create the driver with multiple approaches
        driver = None
        errors = []

        # Approach 1: Use cached chromedriver from webdriver-manager
        if chromedriver_path:
            try:
                import subprocess
                service = Service(chromedriver_path)
                service.log_output = subprocess.DEVNULL  # Suppress chromedriver logs
                driver = webdriver.Chrome(service=service, options=options)
                logger.info("Chrome started successfully (webdriver-manager driver)")
            except Exception as e:
                errors.append(f"Approach 1 (webdriver-manager): {e}")
                logger.warning(f"Chrome failed with webdriver-manager driver: {e}")

        # Approach 2: Use system chromedriver (let Selenium find it)
        if driver is None:
            try:
                service = Service()
                driver = webdriver.Chrome(service=service, options=options)
                logger.info("Chrome started successfully (system driver)")
            except Exception as e:
                errors.append(f"Approach 2 (system driver): {e}")
                logger.warning(f"System chromedriver failed: {e}")

        # Approach 3: Try with a fresh profile (maybe the profile is locked/corrupted)
        if driver is None:
            try:
                logger.warning("Trying with a fresh Chrome profile...")
                import tempfile
                fresh_profile = tempfile.mkdtemp(prefix="wa_chrome_")
                options2 = Options()
                options2.add_argument(f"--user-data-dir={fresh_profile}")
                options2.add_argument("--disable-blink-features=AutomationControlled")
                options2.add_argument("--no-first-run")
                options2.add_argument("--no-default-browser-check")
                options2.add_argument("--no-sandbox")
                options2.add_argument("--disable-dev-shm-usage")
                options2.add_argument("--start-maximized")
                options2.add_argument("--disable-extensions")
                options2.add_argument("--disable-gpu")
                options2.add_argument("--lang=en-US")
                options2.add_experimental_option("excludeSwitches", ["enable-automation"])
                options2.add_experimental_option("useAutomationExtension", False)

                if chromedriver_path:
                    service = Service(chromedriver_path)
                    driver = webdriver.Chrome(service=service, options=options2)
                else:
                    service = Service()
                    driver = webdriver.Chrome(service=service, options=options2)
                logger.info("Chrome started with fresh profile. You will need to scan QR code again.")
            except Exception as e:
                errors.append(f"Approach 3 (fresh profile): {e}")
                logger.warning(f"Fresh profile also failed: {e}")

        if driver is None:
            logger.error("=" * 60)
            logger.error("All Chrome launch attempts failed!")
            logger.error("=" * 60)
            logger.error("")
            logger.error("Possible causes and fixes:")
            logger.error("")
            logger.error("1. CHROME IS ALREADY RUNNING")
            logger.error("   Close ALL Chrome windows, then run this script again.")
            logger.error("   Or use Task Manager to end all 'chrome.exe' processes.")
            logger.error("")
            logger.error("2. PROFILE LOCKED")
            logger.error(f"   Delete the profile folder: {self.chrome_profile_path}")
            logger.error("   Then run again (you'll need to re-scan the QR code).")
            logger.error("")
            logger.error("3. CHROMEDRIVER VERSION MISMATCH")
            logger.error("   Make sure Chrome is up to date.")
            logger.error("   Run: pip install --upgrade selenium webdriver-manager")
            logger.error("")
            logger.error("4. ANTIVIRUS BLOCKING")
            logger.error("   Add Chrome and chromedriver to your antivirus exclusions.")
            logger.error("")
            logger.error("Errors from each attempt:")
            for i, err in enumerate(errors):
                logger.error(f"  Attempt {i+1}: {err[:200]}")
            logger.error("")
            raise Exception("Could not start Chrome. See errors above.")

        # Anti-detection
        try:
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    window.navigator.chrome = {runtime: {}};
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                """
            })
        except Exception:
            pass

        return driver

    def _take_screenshot(self, filename="whatsapp_debug.png"):
        """Take a screenshot and save it for debugging."""
        try:
            screenshot_path = os.path.join(
                os.path.dirname(self.config.get("logging", {}).get("log_file", ".")),
                filename
            )
            self.driver.save_screenshot(screenshot_path)
            logger.info(f"Screenshot saved: {screenshot_path}")
            return screenshot_path
        except Exception as e:
            logger.error(f"Could not take screenshot: {e}")
            return None

    def _find_element_by_selectors(self, selectors, timeout=5):
        """Try multiple CSS selectors to find an element. Returns first match or None."""
        for selector in selectors:
            try:
                element = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                logger.debug(f"Found element with selector: {selector}")
                return element
            except TimeoutException:
                continue
        return None

    def _find_elements_by_selectors(self, selectors):
        """Try multiple CSS selectors to find elements. Returns first non-empty list."""
        for selector in selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    return elements
            except Exception:
                continue
        return []

    # ------------------------------------------------------------------
    # WhatsApp Web interaction
    # ------------------------------------------------------------------

    def start(self):
        """Start the monitor: open WhatsApp Web and wait for login."""
        logger.info("Starting WhatsApp Web monitor...")
        self.driver = self._create_driver()
        self.driver.get(self.WHATSAPP_WEB_URL)

        # Wait for page to start loading
        time.sleep(5)

        logger.info("WhatsApp Web loaded. Waiting for login...")
        self._wait_for_login()

        if self._logged_in:
            logger.info("Logged in successfully!")
            time.sleep(3)
            self._open_group_chat()
        else:
            logger.error("Failed to log in. Exiting.")
            self._take_screenshot("login_failed.png")
            self.shutdown()
            return False

        return True

    def _wait_for_login(self, timeout=300):
        """
        Wait for the user to scan the QR code and log in.
        Uses multiple selectors and a long timeout.
        Also supports manual confirmation (press Enter in console).
        """
        logger.info("Waiting for WhatsApp Web to load...")
        logger.info("If QR code appears, scan it with your phone:")
        logger.info("  WhatsApp -> Settings -> Linked Devices -> Link a Device")
        logger.info("")
        logger.info("If already logged in, this will be quick.")
        logger.info("You can also press Enter in this console once you see chats loaded.")
        logger.info("")

        start_time = time.time()
        check_interval = 2  # Check every 2 seconds

        while time.time() - start_time < timeout:
            # Check if already logged in (any login indicator found)
            for selector in self.LOGIN_INDICATORS:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        self._logged_in = True
                        logger.info(f"Login detected (found: {selector})")
                        return
                except Exception:
                    continue

            # Check if QR code is visible (not logged in yet)
            qr_found = False
            for selector in self.QR_INDICATORS:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements and elements[0].is_displayed():
                        qr_found = True
                        break
                except Exception:
                    continue

            if qr_found:
                elapsed = int(time.time() - start_time)
                if elapsed % 30 == 0 and elapsed > 0:
                    logger.info(f"QR code visible. Waiting for scan... ({elapsed}s elapsed)")
            else:
                # Neither logged in nor QR visible — page might still be loading
                elapsed = int(time.time() - start_time)
                if elapsed % 15 == 0 and elapsed > 0:
                    logger.info(f"Waiting for WhatsApp Web to fully load... ({elapsed}s elapsed)")

            time.sleep(check_interval)

        # Timeout reached
        logger.error(f"Login timed out after {timeout} seconds.")
        logger.error("Taking screenshot for debugging...")
        self._take_screenshot("login_timeout.png")
        logger.error("Check the screenshot to see what WhatsApp Web is showing.")
        logger.error("You can also try:")
        logger.error("1. Make sure Chrome is up to date")
        logger.error("2. Delete the chrome-profile folder and run again")
        logger.error("3. Check your internet connection")

    def _open_group_chat(self):
        """Open the specified group chat."""
        logger.info(f"Opening group chat: {self.group_name}")

        # Wait for chat list to be present
        chat_list_found = False
        for selector in self.LOGIN_INDICATORS:
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                chat_list_found = True
                break
            except TimeoutException:
                continue

        if not chat_list_found:
            logger.error("Chat list not found after login.")
            self._take_screenshot("no_chat_list.png")
            return False

        # Try to find the group by title in the chat list
        group_found = False
        attempts = 0
        max_attempts = 5

        while not group_found and attempts < max_attempts:
            attempts += 1
            entries = self._find_elements_by_selectors(self.CHAT_ENTRY_SELECTORS)
            logger.info(f"Found {len(entries)} chat entries. Searching for '{self.group_name}'...")

            for entry in entries:
                try:
                    for title_sel in self.CHAT_TITLE_SELECTORS:
                        try:
                            title_elem = entry.find_element(By.CSS_SELECTOR, title_sel)
                            title = title_elem.get_attribute("title")
                            if title and self.group_name.lower() in title.lower():
                                # Scroll into view and click
                                self.driver.execute_script("arguments[0].scrollIntoView(true);", entry)
                                time.sleep(0.5)
                                entry.click()
                                group_found = True
                                logger.info(f"Found and opened group: {title}")
                                break
                        except (NoSuchElementException, StaleElementReferenceException):
                            continue
                    if group_found:
                        break
                except (NoSuchElementException, StaleElementReferenceException):
                    continue

            if not group_found:
                # Try using the search box
                logger.info(f"Group not in visible chats. Trying search...")
                try:
                    search_box = self._find_element_by_selectors(self.SEARCH_BOX_SELECTORS, timeout=5)
                    if search_box:
                        search_box.click()
                        time.sleep(1)
                        # Clear any existing text
                        self.driver.execute_script("""
                            var el = arguments[0];
                            el.innerHTML = '';
                            el.dispatchEvent(new Event('input', {bubbles: true}));
                        """, search_box)
                        # Type group name character by character
                        for char in self.group_name:
                            search_box.send_keys(char)
                            time.sleep(0.05)
                        time.sleep(3)

                        # Look for group in search results
                        entries = self._find_elements_by_selectors(self.CHAT_ENTRY_SELECTORS)
                        for entry in entries:
                            try:
                                for title_sel in self.CHAT_TITLE_SELECTORS:
                                    try:
                                        title_elem = entry.find_element(By.CSS_SELECTOR, title_sel)
                                        title = title_elem.get_attribute("title")
                                        if title and self.group_name.lower() in title.lower():
                                            entry.click()
                                            group_found = True
                                            logger.info(f"Found group via search: {title}")
                                            break
                                    except (NoSuchElementException, StaleElementReferenceException):
                                        continue
                                if group_found:
                                    break
                            except (NoSuchElementException, StaleElementReferenceException):
                                continue

                        # Clear search (press Escape)
                        from selenium.webdriver.common.keys import Keys
                        search_box.send_keys(Keys.ESCAPE)
                        time.sleep(1)
                except Exception as e:
                    logger.warning(f"Search attempt failed: {e}")

            time.sleep(1)

        if not group_found:
            logger.error(f"Could not find group: {self.group_name}")
            logger.error("Make sure the group name in config.json matches exactly.")
            self._take_screenshot("group_not_found.png")
            return False

        time.sleep(2)
        return True

    def _extract_messages(self):
        """
        Extract visible messages from the active group chat.
        Returns list of dicts: {"text": str, "sender": str, "timestamp": str}
        """
        messages = []

        message_elements = self._find_elements_by_selectors(self.MESSAGE_SELECTORS)

        for elem in message_elements[-self.max_messages:]:
            try:
                # Get message text
                text = ""
                for text_sel in self.MESSAGE_TEXT_SELECTORS:
                    try:
                        text_elems = elem.find_elements(By.CSS_SELECTOR, text_sel)
                        for te in text_elems:
                            t = te.text.strip()
                            if t:
                                text = t
                                break
                        if text:
                            break
                    except (NoSuchElementException, StaleElementReferenceException):
                        continue

                if not text:
                    text = elem.text.strip()

                if not text or len(text) < 3:
                    continue

                # Try to get sender
                sender = ""
                try:
                    parent = elem.find_element(By.XPATH, "..")
                    sender_elems = parent.find_elements(By.CSS_SELECTOR, 'span[dir="auto"]')
                    if sender_elems:
                        sender = sender_elems[0].text.strip()
                except (NoSuchElementException, StaleElementReferenceException):
                    pass

                messages.append({
                    "text": text,
                    "sender": sender,
                    "timestamp": datetime.now().isoformat(),
                })

            except StaleElementReferenceException:
                continue
            except Exception as e:
                logger.debug(f"Error extracting message: {e}")
                continue

        return messages

    def _message_hash(self, msg: dict) -> str:
        """Create a hash for deduplication using text, sender, and timestamp."""
        content = f"{msg.get('sender', '')}:{msg.get('text', '')}:{msg.get('timestamp', '')}"
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Main monitoring loop
    # ------------------------------------------------------------------

    def monitor_loop(self):
        """Main loop: poll for new messages, parse, and write signals."""
        logger.info("Starting message monitoring loop...")
        logger.info(f"Polling every {self.poll_interval} seconds")
        logger.info(f"Signal file: {self.signal_output_path}")

        # Initialize seen messages with current visible messages (don't process old ones)
        initial_messages = self._extract_messages()
        for msg in initial_messages:
            self._seen_message_hashes.add(self._message_hash(msg))
        logger.info(f"Loaded {len(initial_messages)} existing messages as baseline (will not re-process).")

        while True:
            try:
                messages = self._extract_messages()

                new_messages = []
                for msg in messages:
                    h = self._message_hash(msg)
                    if h not in self._seen_message_hashes:
                        self._seen_message_hashes.add(h)
                        new_messages.append(msg)

                if new_messages:
                    logger.info(f"Found {len(new_messages)} new message(s)")

                    for msg in new_messages:
                        logger.info(f"New message from {msg['sender'] or 'unknown'}: {msg['text'][:100]}")
                        logger.info(f"Parsing with {self.parser_source} parser")

                        if not self.parser_enabled:
                            logger.info("Parser is disabled, skipping message parsing.")
                            continue

                        signal = self.parser.parse(msg["text"], msg.get("sender", ""))

                        if signal:
                            logger.info(f"Signal detected: {signal.side} {signal.symbol} "
                                       f"Entry: {signal.entry_min}-{signal.entry_max} "
                                       f"SL: {signal.stop_loss} ({signal.sl_type}) "
                                       f"TPs: {signal.take_profits} ({signal.tp_type})")

                            written = self.writer.write_signal(signal)
                            if written:
                                logger.info(f"Signal written to file: {signal.signal_id}")
                            else:
                                logger.debug(f"Signal not written (duplicate or error): {signal.signal_id}")
                        else:
                            logger.debug(f"Not a signal: {msg['text'][:80]}")

                time.sleep(self.poll_interval)

            except KeyboardInterrupt:
                logger.info("Monitoring stopped by user (Ctrl+C)")
                break
            except WebDriverException as e:
                logger.error(f"Browser error: {e}")
                logger.info("Attempting to reconnect in 10 seconds...")
                time.sleep(10)
                try:
                    self.driver.get(self.WHATSAPP_WEB_URL)
                    time.sleep(10)
                    self._open_group_chat()
                except Exception:
                    logger.error("Reconnection failed. Restarting monitor...")
                    self._take_screenshot("reconnect_failed.png")
                    break
            except Exception as e:
                logger.error(f"Unexpected error in monitor loop: {e}", exc_info=True)
                time.sleep(5)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self):
        """Clean up and close the browser."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
        logger.info("Monitor shut down.")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def load_config(config_path="config.json") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"

    if not os.path.exists(config_path):
        print(f"Config file not found: {config_path}")
        print("Copy config.example.json to config.json and edit it.")
        sys.exit(1)

    config = load_config(config_path)
    setup_logging(config)

    monitor = WhatsAppMonitor(config)

    try:
        if monitor.start():
            monitor.monitor_loop()
        else:
            logger.error("Failed to start monitor.")
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        monitor.shutdown()


if __name__ == "__main__":
    main()

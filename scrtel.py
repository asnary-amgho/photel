import bcrypt
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import os
import time
import queue
import telebot
from PIL import ImageGrab
from datetime import datetime
import customtkinter as ctk
import keyboard
import threading
import json
import logging
from concurrent.futures import ThreadPoolExecutor

CONFIG_FILE = "config.json"

TELEGRAM_API_TOKEN = None
CHANNEL_ID = None
bot = None
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

latest_photo_index = {}
authorized_users = [] 
class TelegramScreenshotUploader:
    def __init__(self, bot, channel_id, max_retry_attempts=3):
        """
        Initialize the screenshot uploader with a queue-based approach

        :param bot: Telegram bot instance
        :param channel_id: Telegram channel/chat ID
        :param max_retry_attempts: Maximum number of retry attempts for sending
        """
        self.bot = bot
        self.channel_id = channel_id
        self.screenshot_queue = queue.Queue()
        self.max_retry_attempts = max_retry_attempts
        self.unsent_directory = None

        # Start the upload worker thread
        self.upload_thread = threading.Thread(target=self._upload_worker, daemon=True)
        self.upload_thread.start()

    def set_unsent_directory(self, path):
        """Set the directory for unsent screenshots"""
        self.unsent_directory = path
        if not os.path.exists(path):
            os.makedirs(path)

    def enqueue_screenshot(self, image_path):
        """
        Add a screenshot to the upload queue

        :param image_path: Path to the screenshot image
        """
        self.screenshot_queue.put(image_path)
        logging.info(f"Screenshot queued: {image_path}")

    def _upload_worker(self):
        """
        Continuous worker thread to process screenshot upload queue
        """
        while True:
            try:
                image_path = self.screenshot_queue.get()

                success = self._send_screenshot(image_path)

                self.screenshot_queue.task_done()

                if not success and self.unsent_directory:
                    self._move_to_unsent(image_path)

            except Exception as e:
                logging.error(f"Error in upload worker: {e}")

            time.sleep(1)

    def _send_screenshot(self, image_path):
        """
        Attempt to send a screenshot with retry mechanism

        :param image_path: Path to the screenshot image
        :return: Boolean indicating successful send
        """
        for attempt in range(self.max_retry_attempts):
            try:
                with open(image_path, 'rb') as photo:
                    self.bot.send_photo(self.channel_id, photo)

                self._safe_delete(image_path)
                logging.info(f"Screenshot sent successfully: {image_path}")
                return True

            except telebot.apihelper.ApiException as api_error:
                logging.warning(f"Telegram API error (Attempt {attempt + 1}): {api_error}")
                time.sleep(2 ** attempt)  

            except Exception as e:
                logging.error(f"Error sending screenshot (Attempt {attempt + 1}): {e}")
                time.sleep(2 ** attempt)

        return False

    def _safe_delete(self, file_path):
        """
        Safely delete a file with multiple attempts

        :param file_path: Path to the file to delete
        """
        for _ in range(3):
            try:
                os.remove(file_path)
                logging.info(f"File deleted: {file_path}")
                return
            except Exception as e:
                logging.warning(f"Delete failed: {e}")
                time.sleep(1)

    def _move_to_unsent(self, image_path):
        """
        Move failed screenshot to unsent directory

        :param image_path: Path to the screenshot image
        """
        if not self.unsent_directory:
            logging.warning("Unsent directory not set")
            return

        try:
            filename = os.path.basename(image_path)
            unsent_path = os.path.join(self.unsent_directory, filename)
            os.rename(image_path, unsent_path)
            logging.warning(f"Screenshot moved to unsent: {unsent_path}")
        except Exception as e:
            logging.error(f"Failed to move unsent screenshot: {e}")

class DraggableApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Photel")
        self.geometry("400x300")
        ctk.set_appearance_mode("dark")
        self.bind("<ButtonPress-1>", self.start_drag)
        self.bind("<B1-Motion>", self.on_drag)

        self.is_new_user = not os.path.exists(CONFIG_FILE)
        self.api_token = None
        self.channel_id = None
        self.save_path = None
        self.screenshot_uploader = None
        self.input_index = 0

        self.frame = ctk.CTkFrame(self)
        self.frame.pack(padx=20, pady=20)

        self.label = ctk.CTkLabel(self.frame, text="", wraplength=380)
        self.label.pack(pady=5)

        self.entry = ctk.CTkEntry(self.frame, width=300)
        self.entry.pack(pady=5)

        self.button = ctk.CTkButton(self.frame, text="Submit", command=self.handle_input)
        self.button.pack(pady=5)

        self.status_label = ctk.CTkLabel(self.frame, text="", wraplength=380)
        self.status_label.pack(pady=5)

        if self.is_new_user:
            self.setup_new_user()
        else:
            self.setup_password_prompt()

    def initialize_ui(self):
        if self.is_new_user:
            self.setup_new_user()
        else:
            self.setup_password_prompt()

    def setup_new_user(self):
        """Initialize UI for new users"""
        self.prompts = [
            "Enter your Telegram API Token:",
            "Enter your channel ID:",
            "Enter the file path:",
            "Set a password for encryption:"
        ]
        self.label.configure(text=self.prompts[0])
        self.entry.configure(show='')
        self.button.configure(command=self.handle_input)
        self.entry.bind("<Return>", self.handle_input)
    def setup_password_prompt(self):
        """Initialize UI for existing users"""
        self.label.configure(text="Enter your password:")
        self.entry.configure(show='*')
        self.button.configure(command=self.verify_password)
        self.entry.bind("<Return>", self.verify_password)

    def handle_input(self, event=None):
        """Handle input for new users during setup"""
        current_input = self.entry.get().strip()
        self.entry.delete(0, ctk.END)

        if self.input_index == 0:
            self.api_token = current_input
        elif self.input_index == 1:
            self.channel_id = current_input
        elif self.input_index == 2:
            self.save_path = current_input
        elif self.input_index == 3:
            self.save_config(current_input)  
            self.show_capture_instruction()
            return

        self.input_index += 1
        if self.input_index < len(self.prompts):
            show_asterisk = self.input_index == 3
            self.entry.configure(show='*' if show_asterisk else '')
            self.label.configure(text=self.prompts[self.input_index])
        else:
            self.show_capture_instruction()

    def verify_password(self, event=None):
        self.button.configure(state=ctk.DISABLED) 
        try:
            password = self.entry.get().strip() 
            self.entry.delete(0, ctk.END)

            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)

            if bcrypt.checkpw(password.encode(), config['password_hash'].encode()):

                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=base64.b64decode(config['salt']),
                    iterations=100000,
                )
                key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
                fernet = Fernet(key)

                decrypted_config = fernet.decrypt(config['encrypted_data'].encode()).decode()
                config_data = json.loads(decrypted_config)

                self.api_token = config_data['api_token']
                self.channel_id = config_data['channel_id']
                self.save_path = config_data['save_path']
                self.show_capture_instruction()
            else:
                self.status_label.configure(text="Invalid password", text_color="red")
        except Exception as e:
            logging.error(f"Decryption error: {e}")
            self.status_label.configure(text="Error loading config", text_color="red")
        finally:
            self.button.configure(state=ctk.NORMAL) 
    def show_capture_instruction(self):
        global TELEGRAM_API_TOKEN, CHANNEL_ID, bot
        TELEGRAM_API_TOKEN = self.api_token
        CHANNEL_ID = self.channel_id

        if not os.path.isdir(self.save_path):
            self.status_label.configure(text="Invalid path. Exiting program.", text_color="red")
            return

        try:
            bot = telebot.TeleBot(TELEGRAM_API_TOKEN)

            unsent_directory = os.path.join(self.save_path, 'unsent')
            os.makedirs(unsent_directory, exist_ok=True)

            self.screenshot_uploader = TelegramScreenshotUploader(bot, CHANNEL_ID)
            self.screenshot_uploader.set_unsent_directory(unsent_directory)

            threading.Thread(target=self.screen_capture, args=(self.save_path,), daemon=True).start()
            threading.Thread(target=self.bot_polling, daemon=True).start()

            self.label.pack_forget()
            self.entry.pack_forget()
            self.button.pack_forget()

            self.status_label.configure(text="Shortcut for taking pics is SHIFT + `")

            self.background_button = ctk.CTkButton(self.frame, text="Go to Background", command=self.hide_ctk)
            self.background_button.pack(pady=5)

            keyboard.add_hotkey("ctrl + ]", self.restore_ctk)

        except Exception as e:
            logging.error(f"Error initializing screenshot uploader: {e}")
            self.status_label.configure(text=f"Initialization Error: {e}", text_color="red")

    def load_config(self):
        """Load configuration from a JSON file."""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    self.api_token = config.get("api_token")
                    self.channel_id = config.get("channel_id")
                    self.save_path = config.get("save_path")

                if self.api_token and self.channel_id and self.save_path:
                    self.show_capture_instruction()
                    return
        except json.JSONDecodeError:
            logging.error("Invalid configuration file")
        except Exception as e:
            logging.error(f"Error loading configuration: {e}")

    def save_config(self, password):
        """Save configuration with encryption using the provided password"""

        hashed_pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt())

        salt = os.urandom(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        fernet = Fernet(key)

        config_data = {
            "api_token": self.api_token,
            "channel_id": self.channel_id,
            "save_path": self.save_path
        }
        encrypted_data = fernet.encrypt(json.dumps(config_data).encode())

        with open(CONFIG_FILE, 'w') as f:
            json.dump({
                "password_hash": hashed_pw.decode(),
                "salt": base64.b64encode(salt).decode(),
                "encrypted_data": encrypted_data.decode()
            }, f)
    def get_input(self, event=None):
        input_text = self.entry.get()
        self.entry.delete(0, ctk.END)

        if self.input_index == 0:
            self.api_token = input_text
        elif self.input_index == 1:
            self.channel_id = int(input_text)
        elif self.input_index == 2:
            self.save_path = input_text
        elif self.input_index == 3:  # Password setup
            self.save_config()
            self.show_capture_instruction()

        self.entry.delete(0, ctk.END)

        self.input_index += 1

        if self.input_index < len(self.prompts):
            self.label.configure(text=self.prompts[self.input_index])
        else:
            print("All inputs received. Updating the window.")
            self.label.pack_forget()
            self.entry.pack_forget()
            self.button.pack_forget()
            self.status_label.configure(
                text="Shortcut for taking pics is SHIFT + ` and Shortcut for going to fg again CTRL + ]")
            self.save_config()  

    def show_capture_instruction(self):

        global TELEGRAM_API_TOKEN, CHANNEL_ID, bot
        TELEGRAM_API_TOKEN = self.api_token
        CHANNEL_ID = self.channel_id

        if not os.path.isdir(self.save_path):
            self.status_label.configure(text="Invalid path. Exiting program.", text_color="red")
            return

        try:
            bot = telebot.TeleBot(TELEGRAM_API_TOKEN)

            unsent_directory = os.path.join(self.save_path, 'unsent')
            os.makedirs(unsent_directory, exist_ok=True)

            self.screenshot_uploader = TelegramScreenshotUploader(bot, CHANNEL_ID)
            self.screenshot_uploader.set_unsent_directory(unsent_directory)

            threading.Thread(target=self.screen_capture, args=(self.save_path,), daemon=True).start()
            threading.Thread(target=self.bot_polling, daemon=True).start()

            self.label.pack_forget()
            self.entry.pack_forget()
            self.button.pack_forget()
            self.update_idletasks()
            self.status_label.configure(text="Shortcut for taking pics is SHIFT + `")

            self.background_button = ctk.CTkButton(self.frame, text="Go to Background", command=self.hide_ctk)
            self.background_button.pack(pady=5)

            keyboard.add_hotkey("ctrl + ]", self.restore_ctk)

        except Exception as e:
            logging.error(f"Error initializing screenshot uploader: {e}")
            self.status_label.configure(text=f"Initialization Error: {e}", text_color="red")
    def start_drag(self, event):
        self.start_x = event.x_root
        self.start_y = event.y_root
        self.win_x = self.winfo_x()
        self.win_y = self.winfo_y()

    def on_drag(self, event):
        delta_x = event.x_root - self.start_x
        delta_y = event.y_root - self.start_y
        new_x = self.win_x + delta_x
        new_y = self.win_y + delta_y

        self.geometry(f"+{new_x}+{new_y}")
    def screen_capture(self, path):
        print("Screen capture program started. Press SHIFT + ` to capture a screenshot.")

        keyboard.add_hotkey("shift + `", lambda: self.capture_and_save_screen(path))

        keyboard.wait("esc")

    def capture_and_save_screen(self, path):
        screenshot = ImageGrab.grab()
        current_time = datetime.now()
        timestamp = current_time.strftime("%Y%m%d%H%M%S%f")[:-3]  
        filename = f"screenshot_{timestamp}.png"
        save_path = os.path.join(path, filename)
        screenshot.save(save_path)
        logging.info(f"Screenshot saved: {save_path}")

        if hasattr(self, 'screenshot_uploader') and self.screenshot_uploader:
            self.screenshot_uploader.enqueue_screenshot(save_path)
            self.status_label.configure(text=f"Screenshot queued: {filename}", text_color="green")
        else:
            logging.error("Screenshot uploader not initialized")
            self.status_label.configure(text="Screenshot uploader not ready", text_color="red")
    def upload_to_telegram(self, image_path):
        latest_index = latest_photo_index.get(CHANNEL_ID, -1)

        with open(image_path, 'rb') as photo_file:
            file_content = photo_file.read()

        if int(os.path.basename(image_path).split('_')[1][:14]) > latest_index:
            latest_photo_index[CHANNEL_ID] = int(os.path.basename(image_path).split('_')[1][:14])
            try:
                bot.send_photo(CHANNEL_ID, file_content)
                time.sleep(10)
                self.retry_delete(image_path)
            except Exception as e:
                print(f"Failed to send screenshot: {e}")
                self.move_unsent(image_path)
        else:
            parent_directory = os.path.dirname(os.path.abspath(image_path))
            backup_path = os.path.join(parent_directory, os.path.basename(image_path))
            os.rename(image_path, backup_path)
            print(f"Screenshot already sent. Moved to parent directory: {backup_path}")

    def retry_delete(self, file_path, attempts=3, delay=10):
        for _ in range(attempts):
            try:
                os.remove(file_path)
                print(f"Screenshot deleted: {file_path}")
                break
            except Exception as e:
                print(f"Failed to delete screenshot: {e}")
                time.sleep(delay)

    def move_unsent(self, image_path):
        parent_directory = os.path.dirname(os.path.abspath(image_path))
        unsent_directory = os.path.join(parent_directory, 'unsent')
        if not os.path.exists(unsent_directory):
            os.makedirs(unsent_directory)
        unsent_path = os.path.join(unsent_directory, os.path.basename(image_path))
        os.rename(image_path, unsent_path)
        print(f"Screenshot not sent. Moved to unsent directory: {unsent_path}")

    def bot_polling(self):
        global bot
        bot.polling(none_stop=True)

    def hide_ctk(self):
        self.withdraw()

    def restore_ctk(self):
        self.deiconify()

if __name__ == "__main__":
    app = DraggableApp()
    app.mainloop()

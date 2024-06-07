import os
import time
import telebot
from PIL import ImageGrab
from datetime import datetime
import customtkinter as ctk
import keyboard
import threading
import win32console
import win32gui
import win32con



TELEGRAM_API_TOKEN = None
CHANNEL_ID = None
bot = None
latest_photo_index = {}
authorized_users = [CHANNEL_ID]  # Add your authorized user IDs here

class DraggableApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Photel")
        self.geometry("400x300")  

        # Set the appearance mode of CTk (dark mode)
        ctk.set_appearance_mode("dark")

        # Bind mouse events to the root window
        self.bind("<ButtonPress-1>", self.start_drag)
        self.bind("<B1-Motion>", self.on_drag)

        # Create a frame
        self.frame = ctk.CTkFrame(self)
        self.frame.pack(padx=20, pady=20)

        # Initialize input index
        self.input_index = 0

        # List of prompts for each input
        self.prompts = [
            "Enter your Telegram API Token:",
            "Enter your channel ID:",
            "Enter the file path:"
        ]

        # Create a label
        self.label = ctk.CTkLabel(self.frame, text=self.prompts[self.input_index], wraplength=380)
        self.label.pack(pady=5)

        # Create an entry box
        self.entry = ctk.CTkEntry(self.frame, width=300)
        self.entry.pack(pady=5)

        # Create a button to get input
        self.button = ctk.CTkButton(self.frame, text="Submit", command=self.get_input)
        self.button.pack(pady=5)

        # Bind the Enter key to get_input function
        self.entry.bind("<Return>", self.get_input)

        # Initialize variables to store user input
        self.api_token = None
        self.channel_id = None
        self.save_path = None

        # Create a label to display status messages
        self.status_label = ctk.CTkLabel(self.frame, text="", wraplength=380)
        self.status_label.pack(pady=5)

    def get_input(self, event=None):
        input_text = self.entry.get()
        print(input_text)

        # Clear the entry box
        self.entry.delete(0, ctk.END)

        # Store user input in the corresponding variable
        if self.input_index == 0:
            self.api_token = input_text
        elif self.input_index == 1:
            self.channel_id = int(input_text)
        elif self.input_index == 2:
            self.save_path = input_text
            self.show_capture_instruction()

        
        self.input_index += 1

        # If there are more prompts, update the label and ask for the next input
        if self.input_index < len(self.prompts):
            self.label.configure(text=self.prompts[self.input_index])
        else:
            print("All inputs received. Updating the window.")
            self.label.pack_forget()
            self.entry.pack_forget()
            self.button.pack_forget()
            self.status_label.configure(text="Shortcut for taking pics is SHIFT + ` and Shortcut for going to fg again CTRL + ]")
            
            
    def show_capture_instruction(self):
        global TELEGRAM_API_TOKEN, CHANNEL_ID, bot
        TELEGRAM_API_TOKEN = self.api_token
        CHANNEL_ID = self.channel_id

        # Validate the save path
        if not os.path.isdir(self.save_path):
            self.status_label.configure(text="Invalid path. Exiting program.", text_color="red")
            return

        # Initialize the bot
        bot = telebot.TeleBot(TELEGRAM_API_TOKEN)

        # Start the screen capture and bot polling in separate threads
        threading.Thread(target=self.screen_capture, args=(self.save_path,), daemon=True).start()
        threading.Thread(target=self.bot_polling, daemon=True).start()

        # Update the UI
        self.label.pack_forget()
        self.entry.pack_forget()
        self.button.pack_forget()

        self.status_label.configure(text="Shortcut for taking pics is SHIFT + `")

        self.background_button = ctk.CTkButton(self.frame, text="Go to Background", command=self.hide_ctk)
        self.background_button.pack(pady=5)

        keyboard.add_hotkey("ctrl + ]", self.restore_ctk)

    def start_drag(self, event):
        # Record the initial position of the mouse click
        self.start_x = event.x_root
        self.start_y = event.y_root

    def on_drag(self, event):
        # Calculate the distance moved by the mouse
        delta_x = event.x_root - self.start_x
        delta_y = event.y_root - self.start_y

        # Update the window position
        self.geometry(f"+{self.winfo_x() + delta_x}+{self.winfo_y() + delta_y}")

    def screen_capture(self, path):
        print("Screen capture program started. Press SHIFT + ` to capture a screenshot.")

        # Monitor keyboard events
        keyboard.add_hotkey("shift + `", lambda: self.capture_and_save_screen(path))

        # Block indefinitely to keep the program running
        keyboard.wait("esc")

    def capture_and_save_screen(self, path):
        # Capture the screen
        screenshot = ImageGrab.grab()

        
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"screenshot_{timestamp}.png"

        # Save the screenshot to the specified path
        save_path = os.path.join(path, filename)
        screenshot.save(save_path)
        print(f"Screenshot saved: {save_path}")

       
        time.sleep(1)

        # Upload the screenshot to Telegram
        try:
            self.upload_to_telegram(save_path)
            self.status_label.configure(text=f"Screenshot sent: {filename}", text_color="green")
        except Exception as e:
            print(f"Failed to send screenshot: {e}")
            self.move_unsent(save_path)
            self.status_label.configure(text=f"Failed to send screenshot: {filename}", text_color="red")

    def upload_to_telegram(self, image_path):
        
        latest_index = latest_photo_index.get(CHANNEL_ID, -1)
      
        with open(image_path, 'rb') as photo_file:
            file_content = photo_file.read()
        
        if int(os.path.basename(image_path).split('_')[1][:14]) > latest_index:
           
            latest_photo_index[CHANNEL_ID] = int(os.path.basename(image_path).split('_')[1][:14])
            # Send the photo to the chat or channel
            try:
                bot.send_photo(CHANNEL_ID, file_content)
                # Add a delay before attempting to delete the file
                time.sleep(10)
                # Retry deletion
                self.retry_delete(image_path)
            except Exception as e:
                print(f"Failed to send screenshot: {e}")
                # Move the unsent screenshot to a directory called "unsent"
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
        # Move the unsent screenshot to a directory called "unsent"
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

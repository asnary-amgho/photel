import os
import time
import telebot
import keyboard
from PIL import ImageGrab
from datetime import datetime
TELEGRAM_API_TOKEN =input("enter telegram api token")



CHANNEL_ID =int(input("enter channel id "))
bot = telebot.TeleBot(TELEGRAM_API_TOKEN)
latest_photo_index = {}

authorized_users = [ CHANNEL_ID ]  # Add your authorized user IDs here

def capture_and_save_screen(path):
    # Capture the screen
    screenshot = ImageGrab.grab()

    # Generate a filename using current timestamp
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"screenshot_{timestamp}.png"

    # Save the screenshot to the specified path
    save_path = os.path.join(path, filename)
    screenshot.save(save_path)
    print(f"Screenshot saved: {save_path}")

    # Add a delay of 1 second
    time.sleep(1)

    # Upload the screenshot to Telegram
    try:
        upload_to_telegram(save_path)
    except Exception as e:
        print(f"Failed to send screenshot: {e}")

def upload_to_telegram(image_path):
    # Get the latest photo index sent to the user
    latest_index = latest_photo_index.get(CHANNEL_ID, -1)
    # Get the file content
    with open(image_path, 'rb') as photo_file:
        file_content = photo_file.read()
    # Check if the file is new
    if int(os.path.basename(image_path).split('_')[1][:14]) > latest_index:
        # Update the latest photo index sent to the user
        latest_photo_index[CHANNEL_ID] = int(os.path.basename(image_path).split('_')[1][:14])
        # Send the photo to the chat or channel
        try:
            bot.send_photo(CHANNEL_ID, file_content)
            # Add a delay before attempting to delete the file
            time.sleep(10)
            # Retry deletion
            retry_delete(image_path)
        except Exception as e:
            print(f"Failed to send screenshot: {e}")
            # Move the unsent screenshot to a directory called "unsent"
            move_unsent(image_path)
    else:
        # Move the file to the parent directory
        parent_directory = os.path.dirname(os.path.abspath(image_path))
        backup_path = os.path.join(parent_directory, os.path.basename(image_path))
        os.rename(image_path, backup_path)
        print(f"Screenshot already sent. Moved to parent directory: {backup_path}")

def retry_delete(file_path, attempts=3, delay=10):
    for _ in range(attempts):
        try:
            os.remove(file_path)
            print(f"Screenshot deleted: {file_path}")
            break
        except Exception as e:
            print(f"Failed to delete screenshot: {e}")
            time.sleep(delay)

def move_unsent(image_path):
    # Move the unsent screenshot to a directory called "unsent"
    parent_directory = os.path.dirname(os.path.abspath(image_path))
    unsent_directory = os.path.join(parent_directory, 'unsent')
    if not os.path.exists(unsent_directory):
        os.makedirs(unsent_directory)
    unsent_path = os.path.join(unsent_directory, os.path.basename(image_path))
    os.rename(image_path, unsent_path)
    print(f"Screenshot not sent. Moved to unsent directory: {unsent_path}")

def start_screen_capture(path):
    print("Screen capture program started. Press SHIFT + ` to capture a screenshot.")

    # Monitor keyboard events
    keyboard.add_hotkey("shift + `", lambda: capture_and_save_screen(path))

    # Block indefinitely to keep the program running
    keyboard.wait("esc")

@bot.message_handler(commands=["chatid"])
def get_chat_id(message: telebot.types.Message):
    bot.reply_to(message, f"Your chat ID is {message.chat.id}")

@bot.message_handler(commands=['photos'])
def photos_send(message: telebot.types.Message):
    # Check if the user is authorized to access the command
    if message.from_user.id not in authorized_users:
        bot.reply_to(message, "Sorry, you are not authorized to access this command.")
        return
    
    # Define the directory path
    directory_path = r'E:\.1\Newfolder2'
    # Get all files in the directory
    all_files = os.listdir(directory_path)
    # Filter files that start with "screenshot_" and end with ".png"
    photo_files = [file for file in all_files if file.startswith('screenshot_') and file.endswith('.png')]
    # Sort the files based on their names
    photo_files.sort(key=lambda x: int(x.split('_')[1][:14]))
    
    # Filter out photos that have already been sent to the user
    new_photos = [file for file in photo_files if int(file.split('_')[1][:14]) > latest_photo_index.get(CHANNEL_ID, -1)]
    if not new_photos:
        bot.reply_to(message, "You've already received all available photos.")
        return
    
    # Split photos into batches of 10 or less
    for i in range(0, len(new_photos), 10):
        batch_photos = new_photos[i:i+10]
        media = []
        for file in batch_photos:
            # Construct the full file path
            file_path = os.path.join(directory_path, file)
            # Read the file content
            upload_to_telegram(file_path)
            # Add a delay of 1 second between sending each batch
            time.sleep(1)

if __name__ == "__main__":
    save_path = input("Enter the absolute path to save screenshots: ")

    if not os.path.isdir(save_path):
        print("Invalid path. Exiting program.")
        exit()

    start_screen_capture(save_path)

# Start polling for messages
bot.polling(timeout=60)

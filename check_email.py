import pyautogui, time, subprocess, sys

subprocess.Popen(['start', 'chrome', 'https://mail.google.com'], shell=True)
time.sleep(8)
img = pyautogui.screenshot()
img.save('C:/Users/User/BruceAI/gmail2.png')
print('shot taken')

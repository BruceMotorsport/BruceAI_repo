import pyautogui, time, subprocess, sys, os

OUT = 'C:/Users/User/BruceAI/wiki_poll.png'

subprocess.Popen(['start', 'chrome', 'https://mail.google.com/mail/u/0/#search/wikipedia'], shell=True)
time.sleep(12)

# refresh search box with query to force fresh results
pyautogui.click(750, 149)
time.sleep(1)
pyautogui.hotkey('ctrl', 'a')
pyautogui.typewrite('wikipedia', interval=0.05)
pyautogui.press('enter')
time.sleep(6)

img = pyautogui.screenshot()
img.save(OUT)
print('saved', OUT, os.path.getsize(OUT))

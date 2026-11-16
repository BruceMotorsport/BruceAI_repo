import pyautogui, time

# click search box
pyautogui.click(750, 149)
time.sleep(1)
pyautogui.typewrite('wikipedia', interval=0.05)
pyautogui.press('enter')
time.sleep(4)
img = pyautogui.screenshot()
img.save('C:/Users/User/BruceAI/gmail_search.png')
print('shot')

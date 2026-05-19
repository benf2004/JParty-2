import os
import websocket
import json
import pygame
import sys
import ctypes
import ctypes.util

from websocket import create_connection

host_ip = "localhost"

buzzers = [
  "red",
  "blue",
  "yellow",
  "green",
  "white",
  "black",
]
  
def sendBuzz(color):
  try:
    ws = websocket.create_connection(f"ws://{host_ip}:8080/buzzersocket", timeout=2)
    connectPayload = json.dumps({'buzzerColor': color, 'message': 'CHECK_IF_EXISTS', 'text': ''})
    ws.send(connectPayload)
    server_res = ws.recv()
    print("server res: " + server_res)
    res_json = json.loads(server_res)
    if res_json["message"] == "EXISTS":
      print("Sending " + color + " buzz...")
      value = json.dumps({'buzzerColor': color, 'message': 'BUZZ', 'text': ''})
      ws.send(value)
      print("Done.")
    ws.close()
  except Exception as e:
    print("failed to buzz: ", e)


def run_buzzers():
    if sys.platform == "darwin":
        try:
            # Try to hide the dock icon using AppKit via ctypes
            objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library('objc'))
            objc.objc_getClass.restype = ctypes.c_void_p
            objc.sel_registerName.restype = ctypes.c_void_p
            objc.objc_msgSend.restype = ctypes.c_void_p
            
            NSApplication = objc.objc_getClass(b'NSApplication')
            sharedApplication_sel = objc.sel_registerName(b'sharedApplication')
            shared_app = objc.objc_msgSend(NSApplication, sharedApplication_sel)
            
            if shared_app:
                setActivationPolicy_sel = objc.sel_registerName(b'setActivationPolicy:')
                # 2 = NSApplicationActivationPolicyProhibited
                objc.objc_msgSend(shared_app, setActivationPolicy_sel, ctypes.c_long(2))
        except Exception as e:
            print(f"Could not hide dock icon: {e}")

    pygame.init()
    if pygame.joystick.get_count() == 0:
        print("No joysticks connected.")
        return

    j = pygame.joystick.Joystick(0)
    j.init()

    try:
        while True:
            # Check if parent process is still alive
            if os.getppid() == 1:
                print("Parent process died, exiting buzzer process.")
                break

            events = pygame.event.get()
            for event in events:
                if event.type == pygame.JOYBUTTONDOWN:
                    print(event.dict, event.joy, event.button, 'pressed')
                    sendBuzz(buzzers[event.button])
            pygame.time.wait(10)

    except KeyboardInterrupt:
        print("EXITING NOW")
        j.quit()

if __name__ == "__main__":
    run_buzzers()
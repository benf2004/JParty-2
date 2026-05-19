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
    # Set environment variable to hide pygame support prompt
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    
    pygame.joystick.init()
    if pygame.joystick.get_count() == 0:
        print("No joysticks connected.")
        return

    if sys.platform == "darwin":
        try:
            # Try to hide the dock icon using AppKit via ctypes
            import ctypes.util
            objc_path = ctypes.util.find_library('objc')
            if objc_path:
                objc = ctypes.cdll.LoadLibrary(objc_path)
                
                # Define types for safety
                objc.objc_getClass.restype = ctypes.c_void_p
                objc.objc_getClass.argtypes = [ctypes.c_char_p]
                objc.sel_registerName.restype = ctypes.c_void_p
                objc.sel_registerName.argtypes = [ctypes.c_char_p]
                
                # Use CFUNCTYPE for msgSend to be safe on ARM64
                # msgSend(id, SEL) -> id
                msgSend_type = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
                msgSend = msgSend_type(objc.objc_msgSend)
                
                nsapp_class = objc.objc_getClass(b'NSApplication')
                shared_app_sel = objc.sel_registerName(b'sharedApplication')
                shared_app = msgSend(nsapp_class, shared_app_sel)
                
                if shared_app:
                    set_policy_sel = objc.sel_registerName(b'setActivationPolicy:')
                    # msgSend(id, SEL, long) -> void
                    msgSend_policy_type = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long)
                    msgSend_policy = msgSend_policy_type(objc.objc_msgSend)
                    # 2 = NSApplicationActivationPolicyProhibited
                    msgSend_policy(shared_app, set_policy_sel, 2)
                    print("Buzzer process hidden from dock.")
        except Exception as e:
            print(f"Could not hide dock icon: {e}")

    pygame.event.init()
    # Joystick was already initialized above
    try:
        j = pygame.joystick.Joystick(0)
        j.init()
    except pygame.error:
        print("Could not initialize joystick 0")
        return

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
    import multiprocessing
    multiprocessing.freeze_support()
    run_buzzers()
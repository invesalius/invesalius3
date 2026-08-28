import time
import threading

class MockSplash:
    def __init__(self):
        self.main = None
        self.control = None

class MockApp:
    def __init__(self):
        self.splash = MockSplash()
        self.frame = None
        self.control = None
        self.calls = 0
        self.log = []

    def SetTopWindow(self, frame):
        self.log.append(f"SetTopWindow called with {frame}")

    def Startup2(self):
        self.calls += 1
        self.log.append(f"Startup2 call #{self.calls}")
        
        # This mimics the logic I added to app.py
        if not self.splash.main:
            self.log.append("Frame not ready, rescheduling...")
            # In real app this is wx.CallLater. Here we avoid the event loop.
            return False
            
        self.control = self.splash.control
        self.frame = self.splash.main
        self.SetTopWindow(self.frame)
        self.log.append("Initialization complete!")
        return True

def simulate_slow_startup():
    app = MockApp()
    
    # Run Startup2
    while not app.Startup2():
        print(app.log[-1])
        time.sleep(0.5)
        
        # Halfway through, initialize the frame
        if app.calls == 3:
            print("--- Simulating frame initialization ---")
            app.splash.main = "MainFrameObject"
            app.splash.control = "ControllerObject"

    print("\nFinal Log:")
    for entry in app.log:
        print(f"  {entry}")
    
    if app.frame == "MainFrameObject" and app.calls > 1:
        print("\nSUCCESS: Startup2 waited for the frame and then completed successfully.")
    else:
        print("\nFAILURE: Logic did not work as expected.")

if __name__ == "__main__":
    simulate_slow_startup()

import numpy as np
from imutils import face_utils
import imutils
import cv2
import argparse
import json
from CameraController import PTZOptics20x
import time, sys, os, signal


from RealtimeInterval import RealtimeInterval
from CVParameterGroup import CVParameterGroup
import CameraReaderAsync
from WeightedFramerateCounter import WeightedFramerateCounter

''' cambot.py
	Uses CV facial recognition to control a pan/tilt/zoom camera
	and keep a speaker centered and framed appropriately.
'''

# Tunable parameters

g_debugMode = True
g_testImage = None

class Face():
    _recentThresholdSeconds = 0

    visible = False
    didDisappear = False
    recentlyVisible = False
    lastSeenTime = 0
    firstSeenTime = 0
    hcenter = -1
    
    def __init__(self, cfg):
        self._recentThresholdSeconds = cfg["recentThresholdSeconds"]
    
    def found(self, hcenter):
        now = time.time()
        if not self.visible:
            self.firstSeenTime = now
        self.lastSeenTime = now

        self.hcenter = hcenter
        self.visible = True
        self.recentlyVisible = True
        self.didDisappear = False
        return
        
    def lost(self):
        now = time.time()
        if self.visible:
            self.didDisappear = True
            self.firstSeenTime = 0
        else:
            self.didDisappear = False
        if now - self.lastSeenTime <= self._recentThresholdSeconds:
            self.recentlyVisible = True
        else:
            self.recenlyVisible = False
        self.visible = False
        return
        
    def age(self):
        now = time.time()
        if self.firstSeenTime:
            return now - self.firstSeenTime
        else:
            return 0

class Subject():
    hcenter = -1
    offset = 0
    offsetHistory = {}
    isCentered = True
    isFarLeft = False
    isFarRight = False
    
    def evaluate(self, face, camera):
        self.hcenter = face.hcenter
        return
        
class Camera():
    cvcamera = None
    cvreader = None
    controller = None
    ip = ""
    viscaport = 0
    width = 0
    height = 0
    panPos = 0
    tiltPos = 0
    zoomPos = 0
    
    def __init__(self, cfg, usbdevnum):
        self.ip = cfg["ip"]
        self.viscaport = int(cfg["viscaport"])
        self.cvcamera = cv2.VideoCapture(usbdevnum)
        self.width = int(self.cvcamera.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cvcamera.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.cvreader = CameraReaderAsync.CameraReaderAsync(self.cvcamera)
        self.controller = PTZOptics20x(self.ip, self.viscaport)
        self.controller.init()

class Stage():	
    def __init__(self, cfg):
        self.homePan = cfg['homePan']
        self.homeTilt = cfg['homeTilt']
        self.homeZoom = cfg['homeZoom']
        self.maxLeftPan = cfg['maxLeftPan']
        self.maxRightPan = cfg['maxRightPan']
        self.trackingZoom = cfg['trackingZoom']
        self.trackingTilt = cfg['trackingTilt']
        
class Scene():
    homePauseTimer = None
    atHome = False
    confidence = 0.01
    
    def __init__(self, cfg, camera, stage):
        self.minConfidence = cfg["minConfidence"]
        self.homePauseSeconds = cfg["homePauseSeconds"]
        self.returnHomeSpeed = cfg["returnHomeSpeed"]
        
        camera.controller.reset()
        self.goHome(camera, stage)
        
    def goHome(self, camera, stage):
        camera.controller.goto(
            stage.homePan, 
            stage.homeTilt, 
            speed=self.returnHomeSpeed)
        camera.controller.zoomto(stage.homeZoom)
        self.homePauseTimer = RealtimeInterval(self.homePauseSeconds, False)
        self.atHome = True
    
    def evaluate(self, camera, stage, subject, faceCount):
        self.confidence = 1.0/faceCount if faceCount else 0
        
        # Are we in motion and should we stay in motion?
        
        # Should we return to home position?
        
        # Should we initiate tracking motion?
        
        if self.atHome and self.homePauseTimer.hasElapsed():
            print("been home long enough, ready to track")
        return
    
    def trackSubject(self, camera, stage, subject):
        self.atHome = False
        return

def printif(message):
    if g_debugMode:
        print message

def main():
    camera = Camera(cfg['camera'], args["usbDeviceNum"])
    stage = Stage(cfg['stage'])
    subject = Subject()
    face = Face(cfg['face'])
    scene = Scene(cfg['scene'], camera, stage)
    
    fpsDisplay = True
    fpsCounter = WeightedFramerateCounter()
    fpsInterval = RealtimeInterval(5.0, False)

    # Loop on acquisition
    while 1:
        raw = None
        raw = camera.cvreader.Read()

        if raw is not None:

            ### This is the primary frame processing block
            fpsCounter.tick()

            raw = imutils.resize(raw, width=500)
            gray = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)

            camera.panPos, camera.tiltPos = camera.controller.get_pan_tilt_position()
            camera.zoomPos = camera.controller.get_zoom_position()
            cv2.putText(raw, "P #{}".format(camera.panPos), (5, 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            cv2.putText(raw, "T #{}".format(camera.tiltPos), (5, 45),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            cv2.putText(raw, "Z #{}".format(camera.zoomPos), (5, 75),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
            # scan for faces here against a grayscale frame
            cascPath = "haarcascade_frontalface_default.xml"
            faceCascade = cv2.CascadeClassifier(cascPath)
            faces = faceCascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(30, 30)
                #flags = cv2.CV_HAAR_SCALE_IMAGE
            )

            #~ printif("Found {0} faces!".format(len(faces)))
            
            if len(faces):
                (x, __, w, __) = faces[0]
                face.found(x + w/2)
            else:
                face.lost()

            # Decorate the image with CV findings and camera stats
            for (x, y, w, h) in faces:
                    cv2.rectangle(raw, (x, y), (x+w, y+h), (0, 255, 0), 2)

            subject.evaluate(face, camera)
            scene.evaluate(camera, stage, subject, len(faces))

            # show the output image with decorations
            if g_debugMode:
                cv2.imshow("Output", raw) 

        if fpsDisplay and fpsInterval.hasElapsed():
            print "{0:.1f} fps (processing)".format(fpsCounter.getFramerate())
            if camera.cvreader is not None:
                print "{0:.1f} fps (camera)".format(camera.cvreader.fps.getFramerate())
            print "Face has been seen for {0:.1f} seconds".format(face.age())

        # Monitor for control keystrokes in debug mode
        if g_debugMode:
            keyPress = cv2.waitKey(1)
            if keyPress != -1:
                keyPress = keyPress & 0xFF
            if keyPress == ord("q"):
                break
    # Clean up
    printif("Cleaning up")
    if camera.cvreader is not None:
        camera.cvreader.Stop()
        time.sleep(0.5)
    if camera.cvcamera is not None:
        camera.cvcamera.release()
    if g_debugMode:
        cv2.destroyAllWindows() 

    printif("End of main function")

# construct the argument parser and parse the arguments
ap = argparse.ArgumentParser(description="OpenCV camera operation robot")
ap.add_argument("--usb", dest="usbDeviceNum", type=int, action="store", default=0,
                help="USB device number; USB device 0 is the default camera")
ap.add_argument("--stream", type=str, action="store",
                help="optional stream context, appended to IP and used instead of USB for CV frame reads")
ap.add_argument("--release", dest="releaseMode", action="store_const", const=True, default=not g_debugMode,
                    help="hides all debug windows (default: False)")
args = vars(ap.parse_args())
g_debugMode = not args["releaseMode"]

with open("config.json", "r") as configFile:
    cfg = json.load(configFile)

main()
exit()

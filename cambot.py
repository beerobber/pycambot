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
            self.recentlyVisible = False
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
    offsetHistory = []
    isPresent = False
    isCentered = True
    isFarLeft = False
    isFarRight = False
    
    def __init__(self, cfg):
        self.centeredPercentVariance = cfg["centeredPercentVariance"]
        self.offCenterPercentVariance = cfg["offCenterPercentVariance"]
    
    def manageOffsetHistory(self, rawOffset):
        self.offsetHistory.append(rawOffset)
        if (len(self.offsetHistory) > 10):
            self.offsetHistory.pop(0)
        return
        
    def isVolatile(self):
        if len(self.offsetHistory) < 2:
            return True
        # volatility is shown when consecutive offsets have large
        # deltas. We will calculate the deltas and average them.
        deltas = []
        history = iter(self.offsetHistory)
        prior = history.next()
        current = history.next()
        try:
            while True:
                deltas.append(abs(current - prior))
                prior = current
                current = history.next()
        except StopIteration:
            pass
        avgDelta = float(sum(deltas) / len(deltas))
        return True if avgDelta > 9 else False
        
    def evaluate(self, face, scene):
        if not face.visible:
            if not face.recentlyVisible:
                # If we haven't seen a face in a while, reset
                self.hcenter = -1
                self.offset = 0
                self.isPresent = False
                self.isCentered = True
                self.isFarLeft = False
                self.isFarRight = False
            # If we still have a recent subject location, keep it
            self.isPresent = True
            return
        
        # We have a subject and can characterize location in the frame 
        self.isPresent = True    
        self.hcenter = face.hcenter
        frameCenter = scene.imageWidth / 2.0
        self.offset = frameCenter - self.hcenter
        percentVariance = (self.offset * 2.0 / frameCenter) * 100
        self.manageOffsetHistory(percentVariance)
        #~ print "hcenter: {0:d}; offset: {1:f}; variance: {2:f}".format(
            #~ self.hcenter,
            #~ self.offset,
            #~ percentVariance)
        if abs(percentVariance) <= self.centeredPercentVariance:
            self.isCentered = True
        else:
            self.isCentered = False
        if abs(percentVariance) > self.offCenterPercentVariance:
            if self.hcenter < frameCenter:
                self.isFarLeft = True
            else:
                self.isFarRight = True
        else:
            self.isFarLeft = False
            self.isFarRight = False
        return

    def text(self):
        msg = "Subj: "
        msg += "! " if self.isVolatile() else "- "
        if not self.isPresent:
            msg += "..."
            return msg
        if not self.isCentered and not self.isFarLeft and not self.isFarRight:
            msg += "oOo"
        if self.isCentered:
            msg += ".|."
        if self.isFarLeft:
            msg += "<.."
        if self.isFarRight:
            msg += "..>"
        return msg
        
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
    zoomPos = -1
    _badPTZcount = 0
    
    def __init__(self, cfg, usbdevnum):
        # Start by establishing control connection
        self.ip = cfg["ip"]
        self.viscaport = int(cfg["viscaport"])
        self.controller = PTZOptics20x(self.ip, self.viscaport)
        if self.controller.init() is None:
            self.controller = None
            print "Exception: Can't communicate with " + \
                str(self.ip) + ":" + str(self.viscaport)
            return None

        # Open video stream as CV camera
        self.cvcamera = cv2.VideoCapture(usbdevnum)
        self.width = int(self.cvcamera.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cvcamera.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.cvreader = CameraReaderAsync.CameraReaderAsync(self.cvcamera)
    
    def lostPTZfeed(self):
        return False if self._badPTZcount < 5 else True
            
    def updatePTZ(self):
        nowPanPos, nowTiltPos = self.controller.get_pan_tilt_position()
        nowZoomPos = self.controller.get_zoom_position()
        
        if nowZoomPos < 0:
            self._badPTZcount += 1
            return

        self._badPTZcount = 0
        print "P: {0:d} T: {1:d} Z: {2:d}".format( \
            nowPanPos, nowTiltPos, nowZoomPos)
        
        self.panPos = nowPanPos
        self.tiltPos = nowTiltPos
        self.zoomPos = nowZoomPos

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
    zoomTimer = None
    atHome = False
    subjectVolatile = True
    confidence = 0.01
    lastKnownZoom = -1
    
    def __init__(self, cfg, camera, stage):
        self.imageWidth = cfg["imageWidth"]
        self.minConfidence = cfg["minConfidence"]
        self.returnHomeSpeed = cfg["returnHomeSpeed"]
        self.homePauseSeconds = cfg["homePauseSeconds"]
        self.homePauseTimer = RealtimeInterval(cfg["homePauseSeconds"], False)
        self.zoomTimer = RealtimeInterval(cfg["zoomMaxSecondsSafety"], False)
        
        camera.controller.reset()
        self.goHome(camera, stage)
                
    def goHome(self, camera, stage):
        camera.controller.cancel()
        camera.controller.stop()
        camera.controller.goto(
            stage.homePan, 
            stage.homeTilt, 
            speed=self.returnHomeSpeed)
        camera.controller.zoomto(stage.homeZoom)
        self.atHome = True
        self.lastKnownZoom = stage.homeZoom
        time.sleep(self.homePauseSeconds)
        
    def evaluate(self, camera, stage, subject, face, faceCount):
        self.confidence = 100.0/faceCount if faceCount else 0
        self.subjectVolatile = subject.isVolatile()
        if camera.zoomPos is not None and camera.zoomPos > 0:
            self.lastKnownZoom = camera.zoomPos

        if camera.lostPTZfeed():
            camera.controller.zoomstop()

        # Halt zoom if we are at correct tracking zoom level
        if camera.controller.zoomOngoing():
            if self.lastKnownZoom > stage.trackingZoom:
                camera.controller.zoomstop()
                       
        # Are we in motion and should we stay in motion?
        if camera.controller.panTiltOngoing():
            if self.confidence < self.minConfidence \
            or not face.recentlyVisible \
            or self.subjectVolatile \
            or subject.isCentered:
                camera.controller.stop()
        
        # Should we return to home position?
        if not face.recentlyVisible \
        and not self.atHome:
            self.goHome(camera, stage)
            time.sleep(1)
            return
            
        if not face.recentlyVisible:
            return
         
        # With many caveats...start zooming in on stable subject    
        if False and subject.isCentered \
        and not self.subjectVolatile \
        and self.lastKnownZoom > 0 \
        and self.lastKnownZoom < stage.trackingZoom \
        and not camera.controller.zoomOngoing():
            camera.controller.zoomin(0)
            self.zoomTimer.reset()
            # This is a cheat, in case camera doesn't report Z well
            self.lastKnownZoom = stage.trackingZoom
        
        # Maybe we don't need to track
        if subject.isCentered:
            return
            
        if subject.isFarLeft:
            camera.controller.left(1)
            self.atHome = False
        elif subject.isFarRight:
            camera.controller.right(1)
            self.atHome = False
                
        return
    
def printif(message):
    if g_debugMode:
        print message

def main(cfg):
    camera = Camera(cfg['camera'], args["usbDeviceNum"])
    if camera.controller is None:
        print "Failed to initialize camera"
        return False
    stage = Stage(cfg['stage'])
    subject = Subject(cfg['subject'])
    face = Face(cfg['face'])
    scene = Scene(cfg['scene'], camera, stage)
    
    fpsDisplay = True
    fpsCounter = WeightedFramerateCounter()
    fpsInterval = RealtimeInterval(10.0, False)

    # Loop on acquisition
    while 1:
        camera.updatePTZ()
        raw = None
        raw = camera.cvreader.Read()

        if raw is not None:

            ### This is the primary frame processing block
            fpsCounter.tick()

            raw = imutils.resize(raw, width=scene.imageWidth)
            gray = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)
            
            #~ panMsg = "*" if camera.controller.panTiltOngoing() else "-"
            #~ tiltMsg = "-"
            #~ zoomMsg =  "*" if camera.controller.zoomOngoing() else "-"

            #~ cv2.putText(raw, "P {} #{}".format(panMsg, camera.panPos), (5, 15),
                        #~ cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            #~ cv2.putText(raw, "T {} #{}".format(tiltMsg, camera.tiltPos), (5, 45),
                        #~ cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            #~ cv2.putText(raw, "Z {} #{}".format(zoomMsg, camera.zoomPos), (5, 75),
                        #~ cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
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
            subject.evaluate(face, scene)
            scene.evaluate(camera, stage, subject, face, len(faces))

            # Decorate the image with CV findings and camera stats
            #~ cv2.putText(raw, subject.text(), (5, 105),
                #~ cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            #~ for (x, y, w, h) in faces:
                    #~ cv2.rectangle(raw, (x, y), (x+w, y+h), (0, 255, 0), 2)

            # show the output image with decorations
            # (not easy to do on Docker)
            #~ if g_debugMode:
                #~ cv2.imshow("Output", raw) 

        if fpsDisplay and fpsInterval.hasElapsed():
            print "{0:.1f} fps (processing)".format(fpsCounter.getFramerate())
            #~ if camera.cvreader is not None:
                #~ print "{0:.1f} fps (camera)".format(camera.cvreader.fps.getFramerate())
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

main(cfg)
exit()

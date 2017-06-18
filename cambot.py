import numpy as np
from imutils import face_utils
import imutils
import dlib
import cv2
import argparse
from CameraController import PTZOptics20x
import time, sys, os, signal


from RealtimeInterval import RealtimeInterval
from CVParameterGroup import CVParameterGroup
import TriangleSimilarityDistanceCalculator as DistanceCalculator
import CameraReaderAsync
from WeightedFramerateCounter import WeightedFramerateCounter

''' cambot.py
	Uses CV facial recognition to control a pan/tilt/zoom camera
	and keep a speaker centered and framed appropriately.
'''

# Tunable parameters

g_debugMode = True
g_cameraFrameWidth = 0
g_cameraFrameHeight = 0
g_testImage = None

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


def printif(message):
    if g_debugMode:
        print message

def setCVParameters(params):
    # HUES: GREEEN=65/75 BLUE=110
    params.addParameter("hue", 75, 179)
    params.addParameter("hueWidth", 20, 25)
    params.addParameter("low", 70, 255)
    params.addParameter("high", 255, 255)
    params.addParameter("countourSize", 50, 200)
    params.addParameter("keystone", 0, 320)

def createCVCamera(usbdev=0):
    # return a camera object with exposure and contrast set
    global g_cameraFrameWidth
    global g_cameraFrameHeight

    cvcam = cv2.VideoCapture(usbdev)
    g_cameraFrameWidth = int(cvcam.get(cv2.CAP_PROP_FRAME_WIDTH))
    g_cameraFrameHeight = int(cvcam.get(cv2.CAP_PROP_FRAME_HEIGHT))
    return cvcam

def main():
    params = CVParameterGroup("Sliders", g_debugMode)
    setCVParameters(params)

    camera = Camera()
    camera.ip = args["ip"]
    camera.viscaport = args["port"]

    # Start the camera
    camera.cvcamera = createCVCamera(args["usbDeviceNum"])
    camera.cvreader = CameraReaderAsync.CameraReaderAsync(camera.cvcamera)
    camera.controller = PTZOptics20x(camera.ip, camera.viscaport)
    camera.controller.init()

    fpsDisplay = True
    fpsCounter = WeightedFramerateCounter()
    fpsInterval = RealtimeInterval(5.0, False)

    # We need to skip the first frame to make sure we don't process bad image data.
    firstFrameSkipped = False

    # initialize dlib's face detector (HOG-based) and then create
    # the facial landmark predictor
    # http://www.pyimagesearch.com/2014/11/10/histogram-oriented-gradients-object-detection/
    detector = dlib.get_frontal_face_detector()
    predictor = dlib.shape_predictor(args["shape_predictor"])

    # Loop on acquisition
    while 1:
        raw = None
        raw = camera.cvreader.Read()

        if raw is not None and firstFrameSkipped:

            ### This is the primary frame processing block
            fpsCounter.tick()

            raw = imutils.resize(raw, width=800)
            gray = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)
            rects = detector(gray, 1)

            camera.panPos, camera.tiltPos = camera.controller.get_pan_tilt_position()
            camera.zoomPos = camera.controller.get_zoom_position()
            cv2.putText(raw, "P #{}".format(camera.panPos), (5, 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            cv2.putText(raw, "T #{}".format(camera.tiltPos), (5, 45),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            cv2.putText(raw, "Z #{}".format(camera.zoomPos), (5, 75),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            # loop over the face detections
            if rects:
                # determine the facial landmarks for the face region, then
                # convert the facial landmark (x, y)-coordinates to a NumPy
                # array
                shape = predictor(gray, rects[0])
                shape = face_utils.shape_to_np(shape)

                # convert dlib's rectangle to a OpenCV-style bounding box
                # [i.e., (x, y, w, h)], then draw the face bounding box
                (x, y, w, h) = face_utils.rect_to_bb(rects[0])
                cv2.rectangle(raw, (x, y), (x + w, y + h), (0, 255, 0), 2)

                # show the face number
                # cv2.putText(raw, "Face #{}".format(i + 1), (x - 10, y - 10),
                #             cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                cv2.putText(raw, "Face", (x - 10, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                # loop over the (x, y)-coordinates for the facial landmarks
                # and draw them on the image
                for (x, y) in shape:
                    cv2.circle(raw, (x, y), 1, (0, 0, 255), -1)

            # show the output image with the face detections + facial landmarks
            cv2.imshow("Output", raw)

        if raw is not None:
            firstFrameSkipped = True
        if fpsDisplay and fpsInterval.hasElapsed():
            print "{0:.1f} fps (processing)".format(fpsCounter.getFramerate())
            if camera.cvreader is not None:
                print "{0:.1f} fps (camera)".format(camera.cvreader.fps.getFramerate())

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

    if camera.cvcamera is not None:
        camera.cvcamera.release()
    cv2.destroyAllWindows()

    printif("End of main function")

# construct the argument parser and parse the arguments
ap = argparse.ArgumentParser(description="OpenCV/dlib camera operation robot")
ap.add_argument("-p", "--shape-predictor", required=True,
                help="path to facial landmark predictor")
ap.add_argument("--ip", type=str, action="store", required=False,
                help="IP address of camera, for control and optional stream read")
ap.add_argument("--port", type=int, action="store", required=False,
                help="port for TCP control of camera")
ap.add_argument("--usb", dest="usbDeviceNum", type=int, action="store", default=0,
                help="USB device number; USB device 0 is the default camera")
ap.add_argument("--stream", type=str, action="store",
                help="optional stream context, appended to IP and used instead of USB for CV frame reads")
ap.add_argument("--release", dest="releaseMode", action="store_const", const=True, default=not g_debugMode,
                    help="hides all debug windows (default: False)")
args = vars(ap.parse_args())
g_debugMode = not args["releaseMode"]
#g_debugMode = not args.releaseMode

main()
exit()

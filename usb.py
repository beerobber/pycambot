import cv2

# Get the number of cameras available
def count_cameras():
    max_tested = 5
    for i in range(max_tested):
        try:
            temp_camera = cv2.VideoCapture(i)
        except:
            print "failed: " + str(i)
        if temp_camera.isOpened():
            temp_camera.release()
            print "camera: " + str(i)
            continue
    return i

print(count_cameras())
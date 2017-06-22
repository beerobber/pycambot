import cv2

# Get the number of cameras available
def count_cameras():
    max_tested = 1
    num_found = 0
    for i in range(max_tested):
	print "probing video device # " + str(i)
        try:
            temp_camera = cv2.VideoCapture(i)
        except:
            print "failed: " + str(i)
        if temp_camera.isOpened():
            temp_camera.release()
            print "camera: " + str(i)
	    num_found += 1
            continue
    return num_found

print("Cameras found: " + str(count_cameras()))
